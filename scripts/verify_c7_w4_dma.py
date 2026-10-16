"""Independent full-output and lifecycle audit; never promotes host fixtures."""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dma_bench.common import PROTOCOL, REVISION, info, require, summarize, validate, word_sha, write_json
from scripts.verify_c7_w4_results import execution_cells


def audit(archive, executed, release, output):
    require(not output.exists(), 'Fresh audit directory required')
    output.mkdir(parents=True)
    try:
        validate(release/'package')
        original=json.loads((release/'upload/c7_w4_dma.ipynb').read_bytes())
        actual=json.loads(executed.read_bytes())
        codes,_=execution_cells(actual, original)
        frozen=[c for c in original['cells'] if c['cell_type']=='code']
        require(len(codes)==len(frozen)==7, 'Notebook code count changed')
        for a,b in zip(codes,frozen):
            require(''.join(a['source'])==''.join(b['source']), 'Notebook source changed')
            require(type(a['execution_count']) is int and a['execution_count']>0, 'Unexecuted cell')
            require(all(o['output_type']!='error' for o in a['outputs']), 'Notebook contains error')
        require([c['execution_count'] for c in codes]==sorted(set(c['execution_count'] for c in codes)), 'Notebook order invalid')
        text=''.join(''.join(o.get('text',[])) for c in codes for o in c['outputs'])
        for marker in ['PACKAGE_PASS','PRECHECK_PASS','LOAD_PASS','SMOKE_PASS','256_COMPLETE','512_COMPLETE','CLOSED_IDLE','RESULTS_READY']:
            require('W4C_'+marker in text, 'Notebook marker missing: '+marker)
        with zipfile.ZipFile(archive) as z:
            entries=z.infolist();names=[e.filename for e in entries]
            require(len(names)==len(set(names)) and len(names)<700, 'Archive inventory invalid')
            require(sum(e.file_size for e in entries)<600*1024**2, 'Archive too large')
            for e in entries:
                p=Path(e.filename)
                require(not p.is_absolute() and '..' not in p.parts and ':' not in e.filename and '\\' not in e.filename and not e.is_dir(), 'Unsafe member')
            manifest=json.loads(z.read('bundle_manifest.json'))
            require(manifest['revision']==REVISION and set(names)==set(manifest['files'])|{'bundle_manifest.json'}, 'Manifest mismatch')
            import hashlib
            for name, m in manifest['files'].items():
                data=z.read(name)
                require(dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())==m, 'File changed: '+name)
            report=json.loads(z.read('report.json'))
            require(report['revision']==REVISION and report['protocol']==PROTOCOL, 'Protocol changed')
            require(report['evidence_kind']=='PYNQ_PL_DMA', 'HOST is not board evidence')
            require(report['state']=='CLOSED_IDLE' and report['error'] is None and report['retained_buffers']==0, 'Not safely completed')
            require(report['overlay_downloads']==1 and report['channels_stopped'] is True, 'Wrong lifecycle')
            require(report['package']==info(release/'package/w4c_manifest.json'), 'Wrong release')
            require(report['runtime']['machine'] in ('armv7l','armv7') and report['runtime']['pynq']=='3.0.1', 'Wrong runtime')
            require(report['driver']=='pynq.lib.dma.DMA', 'Wrong driver')
            require(report['clock']['monotonic'] is True and report['clock']['adjustable'] is False, 'Invalid timing clock')
            for status in report['close_status'].values(): require(status&2 and not status&0x70, 'Closing DMA status error')
            expected_order=[(0,0,0,17)]+[(s,r,i,s*s) for s in (256,512) for r in (1,2,3) for i in range(103)]
            require(len(report['rows'])==619, 'Wrong row count')
            total=0;previous_end=0
            for seq,(row,expected) in enumerate(zip(report['rows'],expected_order),1):
                side,repeat,index,n=expected
                require((row['side'],row['repeat'],row['index'],row['words'])==expected and row['sequence']==seq,'Order/size mismatch')
                require(row['warmup']==(index<3) and row['exact_match'] is True, 'Warmup/result invalid')
                require(row['send_bytes']==row['recv_bytes']==n*4, 'Length mismatch')
                a,b=row['tx_address'],row['rx_address']
                require(all(v%8==0 and 0x100000<=v and v+n*4<=0x20000000 for v in (a,b)) and (a+n*4<=b or b+n*4<=a),'DDR overlap/range')
                require(set(row['dma_status'])=={'mm2s','s2mm'},'Status missing')
                require(all(v&2 and not v&0x70 for v in row['dma_status'].values()),'DMA error')
                t0,t1,t2,t3=[row[k] for k in ('start_ns','idle_observed_ns','waits_done_ns','snapshot_done_ns')]
                require(previous_end<t0<t1<t2<t3,'Timestamps invalid');previous_end=t3
                require([row[k] for k in ('transaction_ns','submit_to_observed_idle_ns','wait_invalidate_ns','snapshot_ns')]==[t2-t0,t1-t0,t2-t1,t3-t2],'Timing formula mismatch')
                name=f'raw/{seq:04d}.npy'
                require(row['raw']==name and row['raw_file']==manifest['files'][name],'Raw identity mismatch')
                words=np.load(io.BytesIO(z.read(name)),allow_pickle=False)
                require(words.dtype==np.uint32 and words.shape==(n,), 'Raw format invalid')
                # Separate integer expression; do not import board pattern().
                expected_words=np.bitwise_xor(np.arange(n,dtype=np.uint32),np.uint32((seq*2654435769)%(1<<32)))
                require(np.array_equal(words,expected_words),'Full word mismatch')
                require(row['output_sha256']==row['input_sha256']==word_sha(words),'Word hash mismatch')
                total+=n
            require(set(names)=={'bundle_manifest.json','report.json'}|{f'raw/{i:04d}.npy' for i in range(1,620)},'Unexpected extra files')
            summary=summarize(report['rows'])
            require(report['summary']==summary,'Summary mismatch')
        result=dict(status='W4C_DMA_BOARD_DATA_VERIFIED_ONLY',transfers=619,words=total,
            archive=info(archive),notebook=info(executed),summary=summary,
            scope='Independent A0 transport; not C7 resident performance or pure silicon cycle timing.')
        write_json(output/'verification.json',result)
        print(result['status'],total)
        return result
    except BaseException as exc:
        write_json(output/'rejection.json',dict(status='REJECTED',error=type(exc).__name__+': '+str(exc)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('notebook',type=Path);p.add_argument('output',type=Path);p.add_argument('--release',type=Path,required=True);a=p.parse_args()
    audit(a.archive,a.notebook,a.release,a.output)
