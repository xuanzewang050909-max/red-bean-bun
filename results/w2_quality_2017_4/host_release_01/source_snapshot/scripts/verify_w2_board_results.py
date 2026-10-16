"""Independently reconcile downloaded W2 arrays, hardware pages and notebook.

Only run on user-returned board records for board evidence. Host tests with fake
DMA remain host tests; this verifier never executes the medical algorithm.
"""
import argparse
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_app'))
from quality_observer import QualityObserver
from w2_quality_board_test import REVISION,NOTEBOOK,array_sha
from a1_point_board_test import notebook_code_hash
from check_b_hardware import require,info


def verify(bundle,executed,release):
    release=Path(release)
    manifest=json.loads((release/'w2_manifest.json').read_text(encoding='utf-8'))
    vectors=json.loads((release/'w2_vectors.json').read_text(encoding='utf-8'))
    for name,record in manifest['artifacts'].items():require(info(release/name)==record,'Release changed '+name)
    notebook=json.loads(Path(executed).read_text(encoding='utf-8'))
    require(notebook_code_hash(notebook)==manifest['notebook_validation']['sha256'],'Executed notebook code changed')
    cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    require(len(cells)==7 and all(type(c.get('execution_count')) is int and c['execution_count']>0 for c in cells),'Notebook not completely executed')
    counts=[c['execution_count'] for c in cells];require(counts==sorted(set(counts)),'Notebook execution order mismatch')
    markers=[None,'W2_PRECHECK_PASS','W2_LOAD_PASS','W2_SMOKE_PASS','W2_BASELINE_PASS','W2_CANDIDATE_PASS','W2_RESULTS_READY']
    for cell,marker in zip(cells,markers):
        require(not any(o.get('output_type')=='error' for o in cell.get('outputs',[])),'Notebook contains error')
        texts=[]
        for output in cell.get('outputs',[]):
            if output.get('output_type')=='stream':
                value=output.get('text','');texts.append(''.join(value) if isinstance(value,list) else value)
        require(marker is None or marker in ''.join(texts),'Notebook completion missing '+str(marker))
    with ZipFile(bundle) as archive, np.load(release/'w2_vectors.npz',allow_pickle=False) as golden:
        require(archive.testzip() is None,'Corrupt ZIP')
        names=archive.namelist();require(len(names)==len(set(names)),'Duplicate archive member')
        report=json.loads(archive.read('w2_result.json'))
        require(report['revision']==REVISION and report['manifest']==manifest,'Wrong release pairing')
        require(report['status']=='W2_BOARD_EXACT_OUTPUT_COMPLETE_Q3_PENDING' and report['retained_buffers']==0 and 'active_case' not in report and 'error' not in report,'Incomplete/failed board run')
        require(report['pynq']=='3.0.1' and report['runtime_fclk0_mhz_register_readback']==100.0,'Wrong runtime clock/environment')
        require(report['drivers']=={'dma':'pynq.lib.dma.DMA','control':'pynq.lib.axigpio.AxiGPIO','observer':'pynq.lib.axigpio.AxiGPIO'},'Wrong official drivers')
        require(report['quality_status']=='NOT_FULL_DATASET_EVALUATED' and report['browser_fps'] is None and report['pure_dma_transport_ns'] is None,'Unsupported completion claim')
        records=report['transfers'];require(len(records)==80==len(vectors['cases']),'Missing frames')
        expected_names={'w2_result.json','w2_actual_comparison.png'}|{f'w2_actual_outputs/frame_{i:03d}.npy' for i in range(80)}
        require(set(names)==expected_names,'Unexpected/missing ZIP content')
        outputs={};words=0;previous_end=-1
        for index,(record,case) in enumerate(zip(records,vectors['cases'])):
            require(all(record[k]==v for k,v in case.items()),'Wrong frame metadata '+str(index))
            raw=archive.read(record['saved_output']['name'])
            import hashlib
            require(hashlib.sha256(raw).hexdigest()==record['saved_output']['sha256'],'Actual file hash mismatch')
            actual=np.load(io.BytesIO(raw),allow_pickle=False);expected=golden[case['expected_key']]
            require(actual.dtype==np.uint32 and actual.shape==(case['side'],case['side']),'Wrong actual output shape/type')
            require(np.array_equal(actual,expected),'Actual output word mismatch frame '+str(index))
            require(array_sha(actual)==record['output_sha256']==case['expected_sha256'],'Actual digest mismatch')
            require(array_sha(golden[case['input_key']])==case['input_sha256'],'Input digest mismatch')
            n=case['words'];require(record['send_bytes']==record['recv_bytes']==4*n,'DMA byte count mismatch')
            require(record['native_status']==(index+1)|((index+1)<<14),'Native frame/error mismatch')
            require(record['status']=='PASS_EXACT_REAL_DMA_WORDS','Wrong frame status')
            for status in record['dma_status'].values():require(status&2 and not status&0x70,'DMA did not end idle without errors')
            tx,rx=record['tx_address'],record['rx_address']
            require(all(type(a) is int and a%8==0 and 0x100000<=a<=0x20000000-4*n for a in (tx,rx)) and abs(tx-rx)>=4*n,'Invalid recorded DDR buffers')
            pages={int(k):v for k,v in record['hardware']['raw_pages'].items()}
            replay=QualityObserver.__new__(QualityObserver);replay.clock_hz=100_000_000;replay.read_word=lambda page:pages[page]
            observed=replay.completed(expected_control=case['control'],previous_sequence=index,expected_words=n)
            require(observed==record['hardware'],'Hardware snapshot or conversion mismatch')
            t=record['timing_ns']
            require(all(type(v) is int for v in t.values()),'Noninteger timing boundary')
            require(previous_end<t['config_start']<=t['dma_start']<t['dma_end']<=t['snapshot_end'],'Invalid monotonic ordering')
            require(t['dma_transaction']==t['dma_end']-t['dma_start'] and t['full_inference']==t['snapshot_end']-t['config_start'] and t['snapshot']==t['snapshot_end']-t['dma_end'],'Timing arithmetic mismatch')
            require(observed['pl_core_frame_ns']<=t['dma_transaction'],'Core elapsed exceeds containing DMA window')
            previous_end=t['snapshot_end'];words+=n
            outputs[index]=actual
        require(words==13303808,'Incomplete words')
        preview_raw=archive.read('w2_actual_comparison.png')
        require(hashlib.sha256(preview_raw).hexdigest()==report['preview']['sha256'],'Preview hash mismatch')
        preview=np.array(Image.open(io.BytesIO(preview_raw)).convert('RGB'))
        require(preview.shape==(560,1024,3),'Preview shape mismatch')
        require(report['preview_frames']==[74,75],'Wrong comparison frames')
        for row,index in enumerate(report['preview_frames']):
            data=outputs[index];g=(data&255).astype(np.uint8);e=((data>>8)&255).astype(np.uint8);m=((data>>16)&255).astype(np.uint8)
            overlay=np.repeat(g[:,:,None],3,axis=2);overlay[m!=0]=[0,255,0]
            for col,arr in enumerate((g,e,m,overlay)):
                pixels=np.asarray(Image.fromarray(arr).convert('RGB').resize((256,256),resample=Image.NEAREST))
                require(np.array_equal(preview[row*280+24:row*280+280,col*256:col*256+256],pixels),'Preview not from actual DMA array')
    return dict(status='PASS_DOWNLOADED_W2_EXACT_WORDS_AND_OBSERVERS',frames=80,words=words,
                bundle=info(bundle),executed_notebook=info(executed),release_manifest=info(release/'w2_manifest.json'),
                full_dataset_quality='PENDING_Q3',browser_fps=None,pure_dma_transport_ns=None,
                scope='Only supplied board evidence; no full performance/quality acceptance')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('notebook',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--release',type=Path,default=ROOT/'build/deploy/w2_quality_2017_4_r1')
    a=p.parse_args();require(not a.output.exists(),'Preserve previous verification');r=verify(a.bundle,a.notebook,a.release)
    a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(r['status'],r['frames'],r['words'])
