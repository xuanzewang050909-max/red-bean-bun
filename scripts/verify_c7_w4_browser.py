"""Independent full-array, timing, foreground and lifecycle audit of W4b downloads."""
import argparse
import ast
import csv
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from pynq_w4b.protocol import require, file_info, write_json, REVISION, MODES, PNG_PROFILES
from verify_w4b_run import check_run, latency_statistics
from verify_c7_w4_results import execution_cells
from w4b_board import validate_w4b


def browser_groups(records, observations):
    require(len(records)==len(observations)==309, 'Need exactly 309 actual frames and observations')
    seen=set();suite=None;groups=[];previous_render=0
    for repeat in range(1,4):
        latencies=[];first=None
        for within in range(103):
            position=(repeat-1)*103+within;r=records[position];o=observations[position]
            require(r['run_id'] not in seen,'Duplicate actual run');seen.add(r['run_id'])
            q=r['request'];fixed=dict(image_id='im0001',side=512,algorithm='C7',threshold=112,mode='final',png_profile='fast')
            require(all(q[k]==v for k,v in fixed.items()),'Fixed formal configuration changed')
            match=re.fullmatch(r'w4b_([a-f0-9]{32})_r([123])_([wm])(\d{1,3})',q['client_nonce'])
            require(match is not None,'Invalid formal nonce')
            identity,group,phase,index=match.groups()
            if suite is None:suite=identity
            expected_phase='w' if within<3 else 'm';expected_index=within+1 if within<3 else within-2
            require(identity==suite and int(group)==repeat and phase==expected_phase and int(index)==expected_index,'Formal schedule/browser instance changed')
            require(o['run_id']==r['run_id'] and o['session_id']==r['session_id'] and o['client_nonce']==q['client_nonce'] and
                    o['config_id']==r['config_id'] and o['input_sha256']==r['input']['sha256'] and o['output_sha256']==r['output']['sha256'],'Stale browser observation')
            require(o['evidence_kind']=='PYNQ_PL_DMA' and o['visibility']=='visible','Non-board/hidden observation')
            times=[o[k] for k in ('request_start_ms','result_received_ms','images_decoded_ms','render_done_ms')]
            require(all(type(t) in (int,float) and math.isfinite(t) and t>=0 for t in times) and times==sorted(times) and times[0]>=previous_render,'Client clock/order changed')
            require(0<times[-1]-times[0]<=120000 and o['request_to_render_ms']==times[-1]-times[0] and o['result_received_to_render_ms']==times[-1]-times[1],'Client interval arithmetic differs')
            previous_render=times[-1]
            if within<3:
                require(all(o[k] is None for k in ('loop_id','loop_index','loop_start_ms','browser_actual_fps')),'Warmup counted as measured')
            else:
                if within==3:first=times[0]
                require(o['loop_id']==suite+'_r%d'%repeat and o['loop_index']==expected_index and o['loop_start_ms']==first,'Loop index/start differs')
                fps=expected_index*1000/(times[-1]-first) if expected_index>=2 else None
                require(o['browser_actual_fps']==fps,'FPS is not completed unique frames / elapsed time')
                latencies.append(times[-1]-times[0])
        elapsed=previous_render-first
        groups.append(dict(repeat=repeat,warmup=3,n=100,loop_id=suite+'_r%d'%repeat,
            mean_ms=float(np.mean(latencies)),median_ms=float(np.median(latencies)),p95_ms=float(np.percentile(latencies,95)),
            elapsed_ms=elapsed,actual_fps=100000/elapsed))
    return suite,groups


def verify(archive_path, notebook_path, package, release_notebook):
    package=Path(package);release=validate_w4b(package)
    manifest=json.loads((package/'browser_manifest.json').read_bytes())
    executed=json.loads(Path(notebook_path).read_bytes());original=json.loads(Path(release_notebook).read_bytes())
    code,extra=execution_cells(executed,original)
    require(len(code)==7 and all(type(c.get('execution_count')) is int and not any(o.get('output_type')=='error' for o in c.get('outputs',[])) for c in code),'Notebook did not complete all seven steps')
    require([c['execution_count'] for c in code]==sorted(set(c['execution_count'] for c in code)),'Notebook execution order changed')
    streams=[''.join(''.join(o.get('text',[])) for o in c.get('outputs',[]) if o.get('output_type')=='stream') for c in code]
    markers=['W4B_PACKAGE_PASS','W4B_PRECHECK_PASS','BROWSER_SERVICE_READY','W4B_BROWSER_READY','W4B_SUMMARY_READY','W4B_CLOSED_IDLE','W4B_RESULTS_READY']
    require(all(marker in stream for marker,stream in zip(markers,streams)),'Missing lifecycle completion marker')
    with zipfile.ZipFile(archive_path) as z:
        names=z.namelist()
        require(len(names)==len(set(names)) and all(not Path(n).is_absolute() and '..' not in Path(n).parts and '\\' not in n and ':' not in n for n in names),'Unsafe/duplicate evidence names')
        require(sum(i.file_size for i in z.infolist())<=2*1024**3,'Evidence exceeds bounded size')
        for name in ('browser_manifest.json','w4b_manifest.json'):
            require(z.read(name)==(package/name).read_bytes(),'Execution package differs: '+name)
        caps=json.loads(z.read('capabilities.json'));env=json.loads(z.read('environment.json'));session=json.loads(z.read('session.json'));s=session['status']
        require(caps['evidence_kind']=='PYNQ_PL_DMA','HOST TEST is not board evidence')
        require(caps['revision']==REVISION and caps['session_run_limit']==309 and caps['modes']==MODES and caps['png_profiles']==PNG_PROFILES,'Capabilities differ')
        require(env['pynq']=='3.0.1' and env['machine'] in ('armv7l','armv7') and env['runtime_fclk0_mhz_register_readback']==100.0,'Wrong board runtime/clock')
        require(env['drivers']=={'dma':'pynq.lib.dma.DMA','control':'pynq.lib.axigpio.AxiGPIO','observer':'pynq.lib.axigpio.AxiGPIO'},'Wrong driver bindings')
        require(s['session_id']==caps['session_id'] and s['service_state']=='CLOSED' and s['hardware_state']=='IDLE' and s['overlay_downloads']==1 and
                s['completed']==s['accepted']==309 and s['active_run_id'] is None and s['pending']==s['retained_buffer_count']==0 and s['error'] is None,'Session not safely closed/single load/complete')
        require(len(session['run_ids'])==len(set(session['run_ids']))==309,'Wrong run inventory')
        records=[json.loads(z.read(rid+'/record.json')) for rid in session['run_ids']]
        observations=[json.loads(z.read(rid+'/browser_timing.json')) for rid in session['run_ids']]
        require([r['accepted_server_ns'] for r in records]==sorted(set(r['accepted_server_ns'] for r in records)),'Run order changed')
        checked=[];previous=0
        for i,r in enumerate(records):
            require(r['session_id']==caps['session_id'] and r['evidence_kind']==r['evidence']['evidence_kind']=='PYNQ_PL_DMA','Mixed/non-board records')
            if i:require(records[i-1]['raw_timestamps_ns']['worker_result_ready_ns']<r['accepted_server_ns'],'Overlapping formal tasks')
            c=check_run(z,r,package,manifest)
            require(c['frame_status_before']==previous and c['hardware']['sequence']==i+1,'PL frame reset/extra/missing task')
            previous=c['frame_status_after'];checked.append(c)
        require(s['last_completed_frame_status']==previous,'Final PL counter differs')
        suite,groups=browser_groups(records,observations)
        summary=json.loads(z.read('w4b_summary.json'))
        require(summary['suite_id']==suite and summary['groups']==groups and summary['status']=='COLLECTED_PENDING_DOWNLOAD_AUDIT','Recomputed formal summary differs')
        expected_top={'capabilities.json','environment.json','browser_manifest.json','session.json','events.jsonl','measurements.csv','w4b_summary.json','w4b_manifest.json'}
        expected_names=expected_top|{r['run_id']+'/'+name for r in records for name in set(r['files'])|{'record.json','browser_timing.json'}}
        require(set(names)==expected_names,'Missing/extra failure or evidence member')
        events=[json.loads(line) for line in z.read('events.jsonl').splitlines()]
        expected_events=['SERVICE_READY']+[k for _ in records for k in ('RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED','BROWSER_FIRST_RENDER')]+['SERVICE_FINISHED_IDLE']
        require([e['event'] for e in events]==expected_events,'Unexpected lifecycle/fault/retry events')
        require([e['server_ns'] for e in events]==sorted(e['server_ns'] for e in events) and events[-1]['detail']==s and events[-1]['server_ns']<=session['export_server_ns'],'Lifecycle timing/status differs')
        for i,r in enumerate(records):
            ev=events[1+4*i:5+4*i]
            require(all(e['detail']['run_id']==r['run_id'] for e in ev) and ev[0]['detail']['request']==r['request'] and ev[2]['detail']['output_sha256']==r['output']['sha256'] and ev[3]['detail']==observations[i],'Lifecycle run identity differs')
            require(ev[0]['server_ns']>=r['accepted_server_ns'] and ev[1]['server_ns']<=r['raw_timestamps_ns']['worker_start_ns']<=r['raw_timestamps_ns']['worker_result_ready_ns']<=ev[2]['server_ns'],'Worker/event order differs')
        rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))))
        require(len(rows)==309 and [r['run_id'] for r in rows]==session['run_ids'],'CSV inventory differs')
        for row,r,o in zip(rows,records,observations):
            for key,value in row.items():
                if key=='run_id':expected=r[key]
                elif key in r['request']:expected=r['request'][key]
                elif key in r['timing_ns']:expected=r['timing_ns'][key]
                elif key=='vessel_area_fraction':expected=r['quality'][key]
                elif key in ('dice_AH','iou_AH','dice_VK','iou_VK'):
                    metric,observer=key.split('_');expected=r['quality']['annotations'][observer][metric]
                elif key=='browser_request_to_render_ms':expected=o['request_to_render_ms']
                elif key=='browser_actual_fps':expected=o['browser_actual_fps']
                else:raise ValueError('Unknown CSV column '+key)
                require(value==('' if expected is None else str(expected)),'CSV value differs: '+key)
        for index in (2,3):
            printed=[ast.literal_eval(line) for line in streams[index].splitlines() if line.startswith("{'session_id':")]
            require(len(printed)==1 and printed[0]['session_id']==caps['session_id'] and printed[0]['completed']==0 and printed[0]['overlay_downloads']==1 and printed[0]['service_state']=='READY' and printed[0]['hardware_state']=='IDLE','Startup Notebook/session mismatch')
        runtime=[ast.literal_eval(line.removeprefix('Runtime: ')) for line in streams[1].splitlines() if line.startswith('Runtime: ')]
        require(len(runtime)==1 and all(env.get(k)==v for k,v in runtime[0].items()),'Notebook runtime differs')
    fields=('pl_core_frame_ns','dma_transaction_ns','inference_ns','cpu_snapshot_ns','observer_readback_ns','input_read_ns','raw_save_ns','evaluation_ns','array_decode_overlay_ns','png_fromarray_ns','png_save_ns','png_file_hash_ns','file_inventory_hash_ns','worker_result_ns')
    return dict(status='W4B_BOARD_BROWSER_DATA_VERIFIED',archive=file_info(archive_path),notebook=file_info(notebook_path),
        session_id=caps['session_id'],verified_runs=309,matched_words=sum(c['matched_words'] for c in checked),matched_png_images=sum(c['matched_png_images'] for c in checked),
        ignored_trailing_empty_unexecuted_cells=extra,groups=groups,
        server_groups=[dict(repeat=i+1,metrics={k:latency_statistics([r['timing_ns'][k]/1e6 for r in records[i*103+3:(i+1)*103]]) for k in fields}) for i in range(3)],
        measured_frames=300,warmup_frames=9,pure_dma_transport_ns=None,clinical_acceptance=False,
        realtime_requirement_pass=False,scope='Measured foreground client request-to-double-rAF; retains evidence/PNG/scoring overhead. No physical scanout claim, no full W4/quality acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','notebook','destination'):p.add_argument(name,type=Path)
    p.add_argument('--release',type=Path,default=ROOT/'build/deploy/c7_w4_browser_r1');a=p.parse_args()
    a.destination.mkdir(parents=True,exist_ok=False)
    try:result=verify(a.archive,a.notebook,a.release/'package',a.release/'upload/c7_w4_browser.ipynb')
    except Exception as exc:
        write_json(a.destination/'failed_verification.json',dict(status='FAILED_VERIFICATION',error=type(exc).__name__+': '+str(exc)));raise
    write_json(a.destination/'verification.json',result);print(result['status'],result['matched_words'],'words')
