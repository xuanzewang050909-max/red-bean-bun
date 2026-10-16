"""Audit seven-frame demonstration download; HOST fixtures cannot pass as board."""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_w5b.protocol import require,sha,write_json,file_info
from w5b_board import validate_w5b,manual_cases
from verify_w5b_run import check_run
from verify_c7_w4_results import execution_cells

def verify(archive,notebook,reference,package,*,host_fixture=False):
    validate_w5b(package)
    cells,empty=execution_cells(json.loads(notebook.read_bytes()),json.loads(reference.read_bytes()))
    expected=[c for c in json.loads(reference.read_bytes())['cells'] if c['cell_type']=='code']
    markers=['W5B_PACKAGE_PASS','DEMO_PRECHECK_PASS','BROWSER_SERVICE_READY','DEMO_MANUAL_READY','DEMO_CLOSED_IDLE','DEMO_RESULTS_READY','DEMO_FINISHED']
    require(len(cells)==len(expected)==7,'Seven exact code cells required')
    for a,b,marker in zip(cells,expected,markers):
        require(a['source']==b['source'] and type(a['execution_count']) is int and a['execution_count']>0,'Changed code or missing execution')
        require(all(o['output_type']!='error' for o in a['outputs']),'Notebook error')
        require(marker in ''.join(''.join(o.get('text',[])) for o in a['outputs']),'Missing marker '+marker)
    require([c['execution_count'] for c in cells]==sorted(set(c['execution_count'] for c in cells)),'Execution order')
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist())==3 and set(z.namelist())=={'original_session_export.zip','demo_summary.json','demo_bundle_manifest.json'},'Outer inventory')
        index=json.loads(z.read('demo_bundle_manifest.json'))
        for key,name in [('original_session_export','original_session_export.zip'),('summary','demo_summary.json')]:
            data=z.read(name);require(index[key]==dict(bytes=len(data),sha256=sha(data)),'Outer hash mismatch')
        summary=json.loads(z.read('demo_summary.json'))
        with zipfile.ZipFile(io.BytesIO(z.read('original_session_export.zip'))) as inner:
            s=json.loads(inner.read('session.json'));st=s['status'];ids=s['run_ids']
            kind='HOST_TEST_DOUBLE_NOT_BOARD' if host_fixture else 'PYNQ_PL_DMA'
            require(st['evidence_kind']==kind and st['service_state']=='CLOSED' and st['hardware_state']=='IDLE' and
                    st['completed']==st['accepted']==7 and st['overlay_downloads']==1 and st['pending']==st['retained_buffer_count']==0 and
                    st['active_run_id'] is None and st['error'] is None,'Lifecycle/board evidence')
            require(len(ids)==len(set(ids))==7,'Wrong task count')
            manifest=json.loads((package/'browser_manifest.json').read_bytes())
            require(json.loads(inner.read('browser_manifest.json'))==manifest,'Wrong package')
            env=json.loads(inner.read('environment.json'))
            if not host_fixture:
                require(env['pynq']=='3.0.1' and env['machine'] in ('armv7l','armv7') and env['runtime_fclk0_mhz_register_readback']==100.0,'Wrong runtime')
            records=[json.loads(inner.read(r+'/record.json')) for r in ids]
            allowed={'capabilities.json','environment.json','browser_manifest.json','session.json','events.jsonl','measurements.csv'}
            pages=[];words=pngs=0
            for i,(r,case) in enumerate(zip(records,manual_cases())):
                require(r['run_id']==ids[i] and r['session_id']==st['session_id'] and r['evidence_kind']==r['evidence']['evidence_kind']==kind,'Wrong task identity')
                require(all(r['request'][k]==v for k,v in case.items()),'Wrong demonstration order')
                checked=check_run(inner,r,package,manifest);words+=checked['matched_words'];pngs+=checked['matched_png_images']
                require(r['evidence']['hardware_latched_parameter_readback']['sequence']==i+1,'Wrong PL sequence')
                obs=json.loads(inner.read(ids[i]+'/browser_timing.json'))
                require(obs['run_id']==ids[i] and obs['session_id']==st['session_id'] and obs['evidence_kind']==kind and obs['client_nonce']==r['request']['client_nonce'] and obs['visibility']=='visible' and obs['loop_id'] is None and
                        obs['input_sha256']==r['input']['sha256'] and obs['output_sha256']==r['output']['sha256'] and obs['config_id']==r['config_id'],'Wrong browser observation')
                require(obs['request_start_ms']<=obs['result_received_ms']<=obs['images_decoded_ms']<=obs['render_done_ms'],'Browser time order')
                pages.append(obs['page_id'])
                allowed.update(ids[i]+'/'+n for n in r['files']);allowed.update([ids[i]+'/record.json',ids[i]+'/browser_timing.json'])
            require(len(inner.namelist())==len(allowed) and set(inner.namelist())==allowed,'Missing/unexpected inner files')
            require(len(set(pages[:6]))==1 and pages[-1]!=pages[0] and records[0]['output']==records[-1]['output'],'Reload/output mismatch')
            require(summary['status']=='DEMO_COLLECTED_PENDING_DOWNLOAD_AUDIT' and summary['session_id']==st['session_id'] and summary['tasks']==7 and summary['pages']==pages,'Summary mismatch')
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
    return dict(status='HOST_DEMO_FIXTURE_NOT_BOARD' if host_fixture else 'C7_DEMO_BOARD_RECORDS_VERIFIED_VIDEO_REVIEW_SEPARATE',
                tasks=7,matched_words=words,matched_pngs=pngs,boot=summary['boot'],archive=file_info(archive),notebook=file_info(notebook),ignored_empty_cells=empty,
                exclusions=['Physical restart/video requires separate human evidence','Not forced power/network/DMA-fault recovery','Not a new FPS or quality benchmark'])

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('archive','notebook','reference','package','destination'):p.add_argument(name,type=Path)
    a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=False)
    try:write_json(a.destination/'verification.json',verify(a.archive,a.notebook,a.reference,a.package))
    except BaseException as e:write_json(a.destination/'rejection.json',dict(error=type(e).__name__+': '+str(e)));raise
