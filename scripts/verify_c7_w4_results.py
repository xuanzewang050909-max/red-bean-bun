"""Independent download verifier; requires exact released package and Notebook.

Never accepts host mocks as board measurements. Recompute whole words using the
historical C7 reference, counters, register timing and statistics from raw data.
"""
import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from system_bench.common import require, info, word_sha, write_json, validate, group_order
from scripts.prepare_q4d_detector_vectors import expected_words


def execution_cells(notebook, original):
    """Jupyter Shift+Enter can append an empty unexecuted final cell.

    Ignore only that editor artifact, never changed code or executed extras.
    """
    actual=[c for c in notebook['cells'] if c['cell_type']=='code']
    frozen=[c for c in original['cells'] if c['cell_type']=='code']
    require(len(actual)>=len(frozen), 'Missing Notebook code cells')
    extra=actual[len(frozen):]
    require(all(not ''.join(c['source']).strip() and c.get('execution_count') is None and
                c.get('outputs')==[] for c in extra), 'Unexpected extra code/execution/output')
    cells=actual[:len(frozen)]
    require([''.join(c['source']) for c in cells]==[''.join(c['source']) for c in frozen], 'Notebook code differs')
    return cells, len(extra)


def verify_hardware(row, sequence):
    h=row['hardware']; side=row['side']; n=side*side
    expected=3|56|(4 if side==256 else 0)|(112<<8)|(sequence<<16)
    require(h['evidence_kind']=='PYNQ_PL_DMA' and h['requested_control_word']==expected, 'Wrong PL evidence/control')
    obs=h['hardware_latched_parameter_readback']; p=obs['raw_pages']
    require(obs['abi']=='W2_RQ71_V1' and obs['sequence']==p['4']==p['11']==sequence and
            obs['latched_control']==p['3']==expected and p['1']==2 and p['9']==p['10']==n and
            obs['task_tag']==sequence, 'Wrong atomic RQ71 parameters/sequence/word counts')
    core,drain,gaps,stalls=(p[str(i)] for i in (5,6,7,8))
    require(n-1<=core<=drain and gaps<=core and drain-core<=stalls<=drain, 'Invalid hardware cycles')
    require(obs['clock_hz_from_paired_implementation']==100000000 and
            obs['pl_core_cycles']==core and obs['pl_core_frame_ns']==core*10 and
            obs['pl_drain_cycles']==drain and obs['pl_drain_ns']==drain*10 and
            obs['pl_input_empty_cycles']==gaps and obs['pl_output_backpressure_cycles']==stalls,
            'Hardware derived cycles differ')
    require(h['applied_parameters']==dict(algorithm='C7',threshold=112,side=side,mode_code=3,task_tag=sequence), 'Applied fields differ')
    require(h['frame_status_before']==((sequence-1)|((sequence-1)<<14)) and
            h['frame_status_after']==(sequence|(sequence<<14)) and h['frame_count']==sequence and
            h['frame_counter_wrapped'] is False, 'Frame sequence invalid')
    require(h['send_bytes']==h['recv_bytes']==n*4 and len(h['dma_status'])==2 and
            all(x&2 and not x&0x771 for x in h['dma_status'].values()), 'DMA status/bytes invalid')
    tx,rx=(h['buffers'][k] for k in ('tx','rx'))
    for b in (tx,rx):
        require(b['nbytes']==n*4 and b['dtype']=='uint32' and b['shape']==[n] and b['strides']==[4] and
                b['physical_address']%8==0 and 0x100000<=b['physical_address']<=0x20000000-n*4,'Invalid buffer')
    require(abs(tx['physical_address']-rx['physical_address'])>=n*4,'Overlapping native buffers')
    m=h['raw_timestamps_ns']; t=h['timing_ns']
    names=('config_start_ns','config_end_ns','dma_start_ns','dma_end_ns','snapshot_start_ns','snapshot_end_ns','observer_end_ns')
    require(row['call_start_ns']<=m[names[0]] and m[names[-1]]<=row['call_end_ns'] and
            [m[x] for x in names]==sorted(m[x] for x in names),'Broken timing enclosure')
    for key,begin,end in [('config_ns','config_start_ns','config_end_ns'),('dma_transaction_ns','dma_start_ns','dma_end_ns'),
        ('cpu_snapshot_ns','snapshot_start_ns','snapshot_end_ns'),('inference_ns','config_start_ns','snapshot_end_ns'),
        ('observer_readback_ns','snapshot_end_ns','observer_end_ns')]:
        require(t[key]==m[end]-m[begin], 'Wrong derived '+key)
    require(t['pl_core_frame_ns']==core*10<=t['dma_transaction_ns'] and t['pl_core_cycles']==core and
            t['pure_dma_transport_ns'] is None and obs['pure_dma_transport_ns'] is None, 'Wrong core or claimed pure DMA')


def audit(release, archive_path, notebook_path):
    package=release/'package'; manifest=validate(package)
    nb=json.loads(notebook_path.read_bytes()); original=json.loads((release/'upload/c7_w4_processing.ipynb').read_bytes())
    cells,empty_tail_count=execution_cells(nb,original)
    counts=[c['execution_count'] for c in cells]
    require(all(type(x)is int for x in counts) and counts==sorted(set(counts)), 'Execution order differs')
    outputs=[]
    for c in cells:
        require(all(o['output_type']!='error' for o in c['outputs']), 'Notebook contains failure')
        outputs.append(''.join(''.join(o.get('text',[])) for o in c['outputs']))
    for text,marker in zip(outputs,('W4_PACKAGE_PASS','W4_PRECHECK_PASS','W4_LOAD_PASS','W4_256_COMPLETE','W4_512_COMPLETE','W4_SUMMARY_READY','W4_RESULTS_READY')):
        require(marker in text,'Missing completion: '+marker)
    with zipfile.ZipFile(archive_path) as z:
        require(len(z.namelist())==len(set(z.namelist())),'Duplicate ZIP members')
        inventory=json.loads(z.read('result_manifest.json'))
        require(set(z.namelist())==set(inventory['files'])|{'result_manifest.json'},'Unexpected result members')
        require(inventory['package_manifest_sha']==info(package/'w4_manifest.json')['sha256'],'Wrong package identity')
        require(sum(i.file_size for i in z.infolist())<2*1024**3,'Unexpected result size')
        for name,expected in inventory['files'].items():
            data=z.read(name);require(dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())==expected,'Result hash differs: '+name)
        read=lambda name:json.loads(z.read(name))
        identity=read('identity.json');require(identity['package_manifest']==manifest and identity['opencv_threads']==1 and
            identity['evidence_kind']=='PYNQ_REAL_PL_PLUS_SEPARATE_PS_CPU_BENCHMARK','Not this board experiment')
        require(identity['runtime']['pynq']=='3.0.1' and identity['runtime']['machine'] in ('armv7l','armv7'),'Not measured PYNQ ARM runtime')
        state=read('state.json');require(state['state']=='CLOSED_IDLE' and state['hardware_state']=='IDLE' and state['pl_frames']==618 and
            state['retained_buffers']==0 and state['overlay_downloads']==1 and not state['error'] and
            state['completed_sizes']==[256,512] and state['session']==identity['session'],'Wrong final lifecycle')
        loaded=read('loaded.json');require(loaded['runtime']['runtime_fclk0_mhz_register_readback']==100.0,'Wrong actual clock')
        require('failure.json' not in z.namelist(),'Failure must not be accepted')
        rows=[json.loads(line) for line in z.read('samples.jsonl').splitlines()]
        plan=[(s,r,k,i) for s in (256,512) for r in (1,2,3) for k in group_order(r) for i in range(103)]
        require([(x['side'],x['repeat'],x['kind'],x['index']) for x in rows]==plan,'Missing/reordered/extra samples')
        candidate=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
        expected={}; inputs={}
        for side in (256,512):
            inputs[side]=np.load(io.BytesIO(z.read('input_%d.npy'%side)),allow_pickle=False)
            original_input=np.load(package/'c7_baseline/inputs'/('im0001_%d.npy'%side),allow_pickle=False)
            require(np.array_equal(inputs[side],original_input),'Different input')
            expected[side]=expected_words(inputs[side],3,'C7',112,candidate)
        sequence=0; previous=0
        for row in rows:
            s=row['side']; out=np.load(io.BytesIO(z.read(row['raw'])),allow_pickle=False)
            require(out.dtype==np.uint32 and np.array_equal(out,expected[s]),'Whole-word output differs')
            require(row['output_sha256']==word_sha(out) and row['input_sha256']==word_sha(inputs[s]),'Word SHA differs')
            require(row['warmup']==(row['index']<3) and previous<=row['iteration_start_ns']<=row['call_start_ns']<row['call_end_ns']<=row['data_saved_ns'], 'Nonmonotonic sample')
            require(0<=row['process_start_ns']<row['process_end_ns'],'Wrong CPU time')
            previous=row['data_saved_ns']
            if row['kind']=='PL':
                sequence+=1;verify_hardware(row,sequence)
                require(row['hardware']['output_sha256']==row['output_sha256'],'DMA SHA mismatch')
            else: require(row['hardware'] is None, 'CPU mislabeled hardware evidence')
        # Independently recompute group quantiles, without calling collector statistics.
        report=read('summary.json'); groups=read('groups.json')
        require(len(groups)==len(report['groups'])==12,'Incomplete groups')
        for g in report['groups']:
            selected=[r for r in rows if (r['side'],r['repeat'],r['kind'])==(g['side'],g['repeat'],g['kind']) and not r['warmup']]
            require(len(selected)==100,'Wrong timed sample count')
            values={'call':[r['call_end_ns']-r['call_start_ns'] for r in selected]}
            if g['kind']=='CPU':values['cpu_process']=[r['process_end_ns']-r['process_start_ns'] for r in selected]
            else:
                for key in ('pl_core_frame_ns','dma_transaction_ns','inference_ns','cpu_snapshot_ns'):
                    values[key]=[r['hardware']['timing_ns'][key] for r in selected]
            require(set(values)==set(g['metrics']),'Metrics missing/extra')
            for key,v in values.items():
                recomputed=dict(n=100,mean_ns=float(sum(v)/100),median_ns=float(np.median(v)),p95_ns=float(np.percentile(v,95)),min_ns=min(v),max_ns=max(v))
                require(g['metrics'][key]==recomputed,'Summary mismatch: '+key)
            match=[b for b in groups if (b['side'],b['repeat'],b['kind'])==(g['side'],g['repeat'],g['kind'])]
            require(len(match)==1,'Loop grouping changed'); b=match[0]
            require(b['start_ns']<=b['measured_start_ns']<=selected[0]['iteration_start_ns'] and selected[-1]['data_saved_ns']<=b['measured_end_ns']<=b['end_ns'],'Loop boundary mismatch')
            dt=b['measured_end_ns']-b['measured_start_ns']
            require(g['evidence_loop_ns']==dt and g['evidence_loop_fps']==100e9/dt,'Loop FPS wrong')
    return dict(status='W4_PROCESSING_BOARD_DATA_VERIFIED_ONLY',pl_frames=sequence,cpu_calls=618,
        matched_words=sum(r['side']**2 for r in rows),groups=report['groups'],archive=info(archive_path),notebook=info(notebook_path),
        ignored_trailing_empty_unexecuted_cells=empty_tail_count,
        caveat='Not browser FPS / pure DMA / final quality / final real-time acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('release',type=Path);p.add_argument('archive',type=Path)
    p.add_argument('notebook',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=audit(a.release,a.archive,a.notebook);a.output.parent.mkdir(parents=True,exist_ok=True);write_json(a.output,result)
    print(result['status'],result['pl_frames'])
