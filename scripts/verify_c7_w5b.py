"""Independent downloaded W5b audit. HOST runs never receive board acceptance."""
import argparse
import ast
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_w5b.protocol import file_info,require,sha,write_json
from w5b_board import validate_w5b
from verify_w5b_run import check_run
from verify_c7_w4_results import execution_cells


def verify(archive,notebook,release,*,host_fixture=False):
    package=release/'package';protocol=validate_w5b(package)
    manifest=json.loads((package/'browser_manifest.json').read_bytes())
    reference=json.loads((release/'upload/c7_w5b_interaction.ipynb').read_bytes())
    cells,empty=execution_cells(json.loads(notebook.read_bytes()),reference)
    expected=[c for c in reference['cells'] if c['cell_type']=='code']
    markers=['W5B_PACKAGE_PASS','W5B_PRECHECK_PASS','BROWSER_SERVICE_READY','W5B_AUTO_COMPLETE',
             'W5B_MANUAL_READY','W5B_CLOSED_IDLE','W5B_RESULTS_READY']
    require(len(cells)==len(expected)==7,'Wrong notebook count')
    streams=[]
    for a,b,marker in zip(cells,expected,markers):
        require(a['source']==b['source'] and type(a['execution_count']) is int and a['execution_count']>0,'Notebook code/order changed')
        require(all(o['output_type']!='error' for o in a['outputs']),'Notebook error')
        stream=''.join(''.join(o.get('text',[])) for o in a['outputs']);streams.append(stream)
        require(marker in stream,'Missing marker '+marker)
    require([c['execution_count'] for c in cells]==sorted(set(c['execution_count'] for c in cells)),'Execution order')
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        require(len(names)==len(set(names)) and len(names)<1500 and sum(e.file_size for e in entries)<1024**3,'Archive size/inventory')
        require(all(not e.is_dir() and not Path(e.filename).is_absolute() and '..' not in Path(e.filename).parts and
                    ':' not in e.filename and '\\' not in e.filename for e in entries),'Unsafe member')
        index=json.loads(z.read('w5b_bundle_manifest.json'))
        require(index['revision']==protocol['revision'] and set(names)==set(index['files'])|{'w5b_bundle_manifest.json'},'Wrong inventory')
        for name,info in index['files'].items():
            data=z.read(name);require(dict(bytes=len(data),sha256=sha(data))==info,'Hash mismatch '+name)
        session=json.loads(z.read('session.json'));s=session['status'];caps=json.loads(z.read('capabilities.json'))
        kind='HOST_TEST_DOUBLE_NOT_BOARD' if host_fixture else 'PYNQ_PL_DMA'
        require(s['evidence_kind']==caps['evidence_kind']==kind,'HOST is not board evidence')
        require(s['session_id']==caps['session_id'] and s['completed']==s['accepted']==42 and s['run_limit']==42 and
                s['service_state']=='CLOSED' and s['hardware_state']=='IDLE' and s['overlay_downloads']==1 and
                s['pending']==s['retained_buffer_count']==0 and s['active_run_id'] is None and s['error'] is None,'Final lifecycle')
        require(json.loads(z.read('browser_manifest.json'))==manifest,'Wrong release')
        env=json.loads(z.read('environment.json'))
        if host_fixture:
            require(env.get('evidence_kind')==kind and 'warning' in env,'Host fixture runtime must remain marked')
        else:
            require(env['pynq']=='3.0.1' and env['machine'] in ('armv7l','armv7') and env['runtime_fclk0_mhz_register_readback']==100.0,'Wrong runtime')
        runtime=[ast.literal_eval(line[len('Runtime: '):]) for line in streams[1].splitlines() if line.startswith('Runtime: ')]
        require(len(runtime)==1 and all(env.get(k)==v for k,v in runtime[0].items()),'Runtime notebook differs')
        ids=session['run_ids'];require(len(ids)==len(set(ids))==42,'Wrong tasks')
        records=[json.loads(z.read(rid+'/record.json')) for rid in ids]
        allowed={'capabilities.json','environment.json','browser_manifest.json','events.jsonl','session.json',
                 'w5b_checks.jsonl','w5b_summary.json','w5b_export_source.json','original_session_export.zip','w5b_bundle_manifest.json'}
        for i,r in enumerate(records):
            allowed.update(r['run_id']+'/'+name for name in r['files'])
            allowed.add(r['run_id']+'/record.json')
            if i>=35:allowed.add(r['run_id']+'/browser_timing.json')
        require(set(names)==allowed,'Unexpected/missing/failure files')
        expected_cases=protocol['automatic']+protocol['manual']
        previous=0;words=pngs=0;pages=[];observations=[]
        for i,(r,case) in enumerate(zip(records,expected_cases)):
            require(r['run_id']==ids[i] and r['session_id']==s['session_id'] and r['evidence_kind']==r['evidence']['evidence_kind']==kind,'Identity differs')
            require(all(r['request'][k]==v for k,v in case.items()),'Wrong case/order')
            if i<35:require(r['request']['client_nonce']=='w5b_auto_%03d'%i,'Wrong automatic nonce')
            checked=check_run(z,r,package,manifest)
            labels=manifest['images'][case['image_id']][str(case['side'])]['evaluation_only']
            require(set(r['quality']['annotations'])==(set(labels) if case['mode']!='bypass' else set()),'Unexpected annotation scores')
            require(checked['frame_status_before']==previous and checked['hardware']['sequence']==i+1,'Counter gap/reload')
            previous=checked['frame_status_after'];words+=checked['matched_words'];pngs+=checked['matched_png_images']
            if i>=35:
                o=json.loads(z.read(ids[i]+'/browser_timing.json'));observations.append(o);pages.append(o['page_id'])
                require(o['visibility']=='visible' and all(o[k] is None for k in ('loop_id','loop_index','loop_start_ms','browser_actual_fps')),'Bad manual visibility/scope')
                require(o['run_id']==ids[i] and o['session_id']==s['session_id'] and o['config_id']==r['config_id'] and
                        o['client_nonce']==r['request']['client_nonce'] and o['input_sha256']==r['input']['sha256'] and o['output_sha256']==r['output']['sha256'],'Wrong observation identity')
                times=[o[k] for k in ('request_start_ms','result_received_ms','images_decoded_ms','render_done_ms')]
                require(all(type(t) in (int,float) and 0<=t<float('inf') for t in times) and times==sorted(times) and times[-1]-times[0]<=120000,'Invalid client timing')
                require(o['request_to_render_ms']==times[-1]-times[0] and o['result_received_to_render_ms']==times[-1]-times[1],'Client timing arithmetic')
                if len(observations)>1 and i!=41:require(times[0]>=observations[-2]['render_done_ms'],'Nonconsecutive first page')
            if case['image_id'].endswith('_nogt'):
                require(r['quality']['annotations']=={} and r['quality']['quality_reason']=='No matching annotation for this image; Dice/IoU are unavailable','No-GT leaked stale scores')
        require(s['last_completed_frame_status']==previous,'Final counter')
        require(len(set(pages[:6]))==1 and pages[6]!=pages[0],'Manual reload not evidenced')
        require(records[35]['output']['sha256']==records[41]['output']['sha256'],'Reload output changed')
        threshold_pairs={}
        for offset in (0,16):
            for start,end,label in ((0,4,'C7'),(5,9,'C2')):
                require(records[offset+start]['output']['sha256']!=records[offset+end]['output']['sha256'],'Extreme thresholds had no response')
                threshold_pairs[str(records[offset]['request']['side'])+'_'+label]=True
        checks=[json.loads(x) for x in z.read('w5b_checks.jsonl').splitlines()]
        require(len(checks)==51 and not any(c['kind'].endswith('FAILED') for c in checks),'Missing/unexpected checks')
        require([c['server_ns'] for c in checks]==sorted(c['server_ns'] for c in checks),'Check clock order')
        http=[c for c in checks if c['kind']=='HTTP']
        require(len(http)==44 and all(c['expected']==c['actual'] for c in http),'HTTP outcomes differ')
        require([c['actual'] for c in http[:8]]==[422]*8,'Invalid input rejection missing')
        busy=[c for c in checks if c['kind']=='EXPECTED_BUSY']
        require([c['name'] for c in busy]==['queue_full','nonce_conflict','close_busy','export_busy'],'Busy coverage missing')
        require(all(c['state']['accepted']==34 and c['state']['pending']==1 and c['state']['completed']==32 and c['state']['error'] is None for c in busy),'Busy state differs')
        queue=[c for c in checks if c['kind']=='QUEUE_ADMISSION'];require(len(queue)==1,'Queue evidence missing')
        require(queue[0]['run_ids']==ids[32:34] and queue[0]['duplicate_id']==ids[32],'Queue nonce identity')
        for i in range(32):require(http[8+i]['response']['run_id']==ids[i] and http[8+i]['body']['client_nonce']==records[i]['request']['client_nonce'],'HTTP job order')
        require(http[40]['actual']==422 and http[40]['path']=='/api/runs/'+ids[31]+'/browser-timing' and http[40]['body']['config_id']=='wrong_config','Stale observation rejection missing')
        require(http[41]['response']['run_id']==ids[32] and http[42]['response']['run_id']==http[43]['response']['run_id']==ids[34],'Retry/reconnect IDs differ')
        require(http[43]['response']['status']=='COMPLETED','Reconnect incomplete')
        closed=[c for c in checks if c['kind']=='CLIENT_CLOSED_AFTER_ACCEPT'];require(len(closed)==1 and closed[0]['run_id']==ids[34],'Client closure not recorded')
        require(closed[0]['state']['active_run_id']==ids[34] and closed[0]['state']['completed']==34,'Client closed outside in-progress task')
        require(checks[-1]['kind']=='AUTO_COMPLETE' and checks[-1]['status']['completed']==35,'Automatic completion missing')
        summary=json.loads(z.read('w5b_summary.json'))
        require(summary['status']=='COLLECTED_PENDING_DOWNLOAD_AUDIT' and summary['tasks']==42 and summary['automatic']==35 and summary['manual']==7 and summary['page_ids']==pages and summary['session_id']==s['session_id'],'Summary differs')
        events=[json.loads(x) for x in z.read('events.jsonl').splitlines()]
        require(events[0]['event']=='SERVICE_READY' and events[-1]['event']=='SERVICE_FINISHED_IDLE' and events[-1]['detail']==s,'Lifecycle events missing')
        require(len(events)==135 and [e['server_ns'] for e in events]==sorted(e['server_ns'] for e in events),'Extra events/clock')
        for kind in ('RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED'):
            require([e['detail']['run_id'] for e in events if e['event']==kind]==ids,'Lifecycle task order '+kind)
        require([e['detail'] for e in events if e['event']=='BROWSER_FIRST_RENDER']==observations,'Browser events differ')
        for i in range(1,42):
            require(records[i]['raw_timestamps_ns']['worker_start_ns']>=records[i-1]['raw_timestamps_ns']['worker_result_ready_ns'],'Native workers overlap')
        # Revalidate the original exporter inside the outer evidence bundle.
        data=z.read('original_session_export.zip');source=json.loads(z.read('w5b_export_source.json'))
        require(source['file']==dict(bytes=len(data),sha256=sha(data)),'Original export identity')
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            inner_names=inner.namelist()
            inner_expected={'capabilities.json','environment.json','browser_manifest.json','events.jsonl','session.json','measurements.csv'}
            inner_expected.update(n for n in allowed if n.split('/')[0] in ids)
            require(len(inner_names)==len(set(inner_names)) and set(inner_names)==inner_expected,'Original exporter inventory differs')
            for name in inner.namelist():
                if name!='measurements.csv':require(inner.read(name)==z.read(name),'Original exporter byte mismatch '+name)
            rows=list(csv.DictReader(io.StringIO(inner.read('measurements.csv').decode('utf-8-sig'))))
            require([r['run_id'] for r in rows]==ids,'Export CSV order')
            for row,r in zip(rows,records):
                for key in ('dma_transaction_ns','inference_ns'):
                    require(int(row[key])==r['timing_ns'][key],'CSV duration mismatch')
        return dict(status=('HOST_FIXTURE_VALIDATED_NOT_BOARD' if host_fixture else 'W5B_BOARD_BOUNDED_INTERACTION_VERIFIED_ONLY'),archive=file_info(archive),notebook=file_info(notebook),
            tasks=42,matched_words=words,matched_pngs=pngs,threshold_extremes_changed=threshold_pairs,
            automatic_checks=51,manual_page_ids=pages,ignored_empty_cells=empty,
            exclusions=['No physical Ethernet/power interruption','No forced real DMA fault','No new segmentation quality acceptance','No measured power'])


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('archive','notebook','destination'):p.add_argument(k,type=Path)
    p.add_argument('--release',type=Path,required=True);a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=False)
    try:
        result=verify(a.archive,a.notebook,a.release);write_json(a.destination/'verification.json',result);print(result['status'])
    except BaseException as exc:
        write_json(a.destination/'rejection.json',dict(status='REJECTED',error=type(exc).__name__+': '+str(exc)));raise
