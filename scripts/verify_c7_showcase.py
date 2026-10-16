"""Audit variable-length showcase download; HOST fixtures cannot pass as board."""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_showcase.protocol import require,sha,write_json,file_info
from showcase_board import validate_showcase, EXAMPLES
from verify_showcase_run import check_run
from verify_c7_w4_results import execution_cells

def verify(archive,notebook,reference,package,*,host_fixture=False):
    validate_showcase(package)
    cells,empty=execution_cells(json.loads(notebook.read_bytes()),json.loads(reference.read_bytes()))
    expected=[c for c in json.loads(reference.read_bytes())['cells'] if c['cell_type']=='code']
    markers=['SHOWCASE_PACKAGE_PASS','SHOWCASE_PRECHECK_PASS','BROWSER_SERVICE_READY','SHOWCASE_MANUAL_READY','SHOWCASE_CLOSED_IDLE','SHOWCASE_RESULTS_READY','SHOWCASE_FINISHED']
    require(len(cells)==len(expected)==7,'Seven exact code cells required')
    for a,b,marker in zip(cells,expected,markers):
        require(a['source']==b['source'] and type(a['execution_count']) is int and a['execution_count']>0,'Changed code or missing execution')
        require(all(o['output_type']!='error' for o in a['outputs']),'Notebook error')
        require(marker in ''.join(''.join(o.get('text',[])) for o in a['outputs']),'Missing marker '+marker)
    require([c['execution_count'] for c in cells]==sorted(set(c['execution_count'] for c in cells)),'Execution order')
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist())==3 and set(z.namelist())=={'original_session_export.zip','showcase_summary.json','showcase_bundle_manifest.json'},'Outer inventory')
        index=json.loads(z.read('showcase_bundle_manifest.json'))
        for key,name in [('original_session_export','original_session_export.zip'),('summary','showcase_summary.json')]:
            data=z.read(name);require(index[key]==dict(bytes=len(data),sha256=sha(data)),'Outer hash mismatch')
        summary=json.loads(z.read('showcase_summary.json'))
        with zipfile.ZipFile(io.BytesIO(z.read('original_session_export.zip'))) as inner:
            s=json.loads(inner.read('session.json'));st=s['status'];ids=s['run_ids']
            kind='HOST_TEST_DOUBLE_NOT_BOARD' if host_fixture else 'PYNQ_PL_DMA'
            require(st['evidence_kind']==kind and st['service_state']=='CLOSED' and st['hardware_state']=='IDLE' and
                    st['completed']==st['accepted']==len(ids) and 1 <= len(ids) <= 100 and st['run_limit']==100 and st['overlay_downloads']==1 and st['pending']==st['retained_buffer_count']==0 and
                    st['active_run_id'] is None and st['error'] is None,'Lifecycle/board evidence')
            require(len(ids)==len(set(ids)),'Wrong task count')
            manifest=json.loads((package/'browser_manifest.json').read_bytes())
            require(json.loads(inner.read('browser_manifest.json'))==manifest,'Wrong package')
            env=json.loads(inner.read('environment.json'))
            if not host_fixture:
                require(env['pynq']=='3.0.1' and env['machine'] in ('armv7l','armv7') and env['runtime_fclk0_mhz_register_readback']==100.0,'Wrong runtime')
            records=[json.loads(inner.read(r+'/record.json')) for r in ids]
            allowed={'capabilities.json','environment.json','browser_manifest.json','session.json','events.jsonl','measurements.csv'}
            pages=[];observed=[];words=pngs=0
            for i,r in enumerate(records):
                require(r['run_id']==ids[i] and r['session_id']==st['session_id'] and r['evidence_kind']==r['evidence']['evidence_kind']==kind,'Wrong task identity')
                checked=check_run(inner,r,package,manifest);words+=checked['matched_words'];pngs+=checked['matched_png_images']
                require(r['evidence']['hardware_latched_parameter_readback']['sequence']==i+1,'Wrong PL sequence')
                allowed.update(ids[i]+'/'+n for n in r['files']);allowed.add(ids[i]+'/record.json')
                obs_path=ids[i]+'/browser_timing.json'
                if obs_path in inner.namelist():
                    allowed.add(obs_path)
                    obs=json.loads(inner.read(obs_path))
                    require(obs['run_id']==ids[i] and obs['session_id']==st['session_id'] and obs['evidence_kind']==kind and obs['client_nonce']==r['request']['client_nonce'] and
                            obs['input_sha256']==r['input']['sha256'] and obs['output_sha256']==r['output']['sha256'] and obs['config_id']==r['config_id'], 'Wrong browser observation')
                    import re, math
                    require(re.fullmatch('[0-9a-f]{32}',obs['page_id']) is not None,'Bad page ID')
                    times=[obs[k] for k in ('request_start_ms','result_received_ms','images_decoded_ms','render_done_ms')]
                    require(all(isinstance(t,(float,int)) and math.isfinite(t) and t>=0 for t in times) and times==sorted(times),'Browser time order')
                    require(abs(obs['request_to_render_ms']-(times[-1]-times[0]))<1e-6,'Wrong render duration')
                    pages.append(obs['page_id'])
                    if obs['visibility']=='visible' and obs['loop_id'] is None: observed.append(ids[i])
            require(len(inner.namelist())==len(allowed) and set(inner.namelist())==allowed,'Missing/unexpected inner files')
            require(summary['status']=='SHOWCASE_COLLECTED_PENDING_DOWNLOAD_AUDIT' and summary['session_id']==st['session_id'] and summary['tasks']==len(ids), 'Summary mismatch')
            require(summary['observed_run_ids']==observed and summary['unobserved_run_ids']==[rid for rid in ids if rid not in observed], 'Observation coverage mismatch')
            require(summary['images']==sorted({r['request']['image_id'] for r in records}), 'Image coverage mismatch')
            import uuid,csv
            uuid.UUID(summary['boot']['boot_id']);require(summary['boot']['uptime_seconds']>=0,'Bad boot uptime')
            rows=list(csv.DictReader(io.StringIO(inner.read('measurements.csv').decode('utf-8-sig'))))
            require([r['run_id'] for r in rows]==ids,'CSV order')
            for row,r in zip(rows,records):
                for name in ('dma_transaction_ns','inference_ns'):require(int(row[name])==r['timing_ns'][name],'CSV timing')
            events=[json.loads(x) for x in inner.read('events.jsonl').splitlines()]
            require(events[0]['event']=='SERVICE_READY' and events[-1]['event']=='SERVICE_FINISHED_IDLE' and events[-1]['detail']==st,'Lifecycle events')
            for name in ('RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED'):
                require([e['detail']['run_id'] for e in events if e['event']==name]==ids,'Task lifecycle order')
    normal=[r['request'] for r in records if r['request']['algorithm']=='C7' and r['request']['mode']=='final' and r['request']['threshold']==112]
    coverage=dict(images_c7_final_t112=sorted({r['image_id'] for r in normal if not r['image_id'].endswith('_nogt')}),
        sides=sorted({r['request']['side'] for r in records}), visible_frames=len(observed), missing_visible_frames=len(ids)-len(observed),
        no_gt=any(r['request']['image_id']=='im0324_nogt' and not r['quality']['annotations'] for r in records),
        bypass=any(r['request']['algorithm']=='C7' and r['request']['mode']=='bypass' for r in records),
        c2_modes=sorted({r['request']['mode_code'] for r in records if r['request']['algorithm']=='C2'}))
    return dict(status='HOST_SHOWCASE_FIXTURE_NOT_BOARD' if host_fixture else 'SHOWCASE_BOARD_ARRAYS_VERIFIED_COVERAGE_REPORTED',
                tasks=len(ids),matched_words=words,matched_pngs=pngs,boot=summary['boot'],archive=file_info(archive),notebook=file_info(notebook),ignored_empty_cells=empty,
                coverage=coverage,video='DEFERRED_BY_USER',
                exclusions=['Array verification does not prove a physical power cycle', 'Not forced power/network/DMA-fault recovery', 'Not a new FPS or quality benchmark', 'Navigation gestures require separate user observation; frame identity/order verified here'])

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('archive','notebook','reference','package','destination'):p.add_argument(name,type=Path)
    a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=False)
    try:write_json(a.destination/'verification.json',verify(a.archive,a.notebook,a.reference,a.package))
    except BaseException as e:write_json(a.destination/'rejection.json',dict(error=type(e).__name__+': '+str(e)));raise
