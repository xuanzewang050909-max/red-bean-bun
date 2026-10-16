"""Offline audit of real W5a compact evidence; never promotes HOST fixtures."""
import argparse
import ast
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_w5a.protocol import file_info,require,sha,write_json
from w5a_board import validate_w5a
from verify_w5a_run import check_run
from verify_c7_w4_results import execution_cells


class CompactArchive:
    def __init__(self, archive, records):
        self.archive=archive
        self.references={r['run_id']+'/'+name:target for r in records for name,target in r['storage_refs'].items()}

    def read(self,name):
        return self.archive.read(self.references.get(name,name))


def verify_schedule(records,images):
    require(len(records)==1000 and len(images)==20,'Wrong task/catalog count')
    suite=None;previous=None
    for i,r in enumerate(records):
        req=r['request'];block=i//10
        expected=dict(image_id=images[block%20],side=(512,256)[(block//20)%2],algorithm='C7',
                      threshold=[96,112,128][block%3],mode='final',mode_code=3,png_profile='fast')
        require(all(req[k]==v for k,v in expected.items()),'Wrong independent schedule')
        match=re.fullmatch(r'w5a_([A-Za-z0-9_-]{8,80})_(0|[1-9][0-9]*)',req['client_nonce'])
        require(match is not None and int(match[2])==i,'Wrong nonce/index')
        if suite is None:suite=match[1]
        require(match[1]==suite,'Mixed suites')
        o=r['browser_timing']
        require(o['visibility']=='visible' and all(o[k] is None for k in ('loop_id','loop_index','loop_start_ms','browser_actual_fps')),'Hidden/invalid paced sample')
        for key,expected_value in dict(run_id=r['run_id'],session_id=r['session_id'],client_nonce=req['client_nonce'],
            config_id=r['config_id'],input_sha256=r['input']['sha256'],output_sha256=r['output']['sha256'],evidence_kind='PYNQ_PL_DMA').items():
            require(o[key]==expected_value,'Browser observation identity differs')
        t=[o[k] for k in ('request_start_ms','result_received_ms','images_decoded_ms','render_done_ms')]
        require(all(type(x) in (int,float) and 0<=x<float('inf') for x in t) and t==sorted(t) and t[-1]-t[0]<=120000,'Invalid browser clock')
        require(o['request_to_render_ms']==t[-1]-t[0] and o['result_received_to_render_ms']==t[-1]-t[1],'Browser timing arithmetic differs')
        require(r['raw_timestamps_ns']['worker_result_ready_ns']<=r['storage_end_ns']<=r['resources']['server_ns'], 'Storage/resource ordering differs')
        require(0<=r['storage_dedup_ns']<=r['storage_end_ns']-r['raw_timestamps_ns']['worker_result_ready_ns'],'Storage duration differs')
        if previous:
            require(previous['browser_timing']['render_done_ms']<=t[0], 'Nonconsecutive client clock')
            require(previous['resources']['server_ns']<r['accepted_server_ns'] and
                    0<r['accepted_server_ns']-previous['accepted_server_ns']<=60_000_000_000,'Task overlap/long pause')
        previous=r
    server=(records[-1]['storage_end_ns']-records[0]['accepted_server_ns'])/1e9
    client=(records[-1]['browser_timing']['render_done_ms']-records[0]['browser_timing']['request_start_ms'])/1000
    require(server>=1800 and client>=1800,'Less than 30 minutes on either clock')
    growth=max(r['resources']['rss_bytes'] for r in records[100:])-records[99]['resources']['rss_bytes']
    available=min(r['resources']['available_bytes'] for r in records)
    require(growth<=96*1024**2 and available>=48*1024**2,'Memory acceptance failed')
    return dict(status='COLLECTED_PENDING_DOWNLOAD_AUDIT',tasks=1000,suite=suite,
        server_elapsed_seconds=server,browser_elapsed_seconds=client,paced_display_fps=1000/client,
        rss_growth_after_100_bytes=growth,min_available_bytes=available,
        scope='W5a endurance only; W5b recovery/queue, instrument power and final quality remain pending')


def verify(archive,notebook,release):
    package=release/'package';release_manifest=validate_w5a(package)
    manifest=json.loads((package/'browser_manifest.json').read_bytes())
    reference=json.loads((release/'upload/c7_w5a_stability.ipynb').read_bytes())
    actual=json.loads(notebook.read_bytes());cells,empty=execution_cells(actual,reference)
    original=[c for c in reference['cells'] if c['cell_type']=='code']
    require(len(cells)==len(original)==7,'Wrong Notebook count')
    streams=[]
    for a,b in zip(cells,original):
        require(a['source']==b['source'] and type(a['execution_count']) is int and a['execution_count']>0,'Notebook modified/unexecuted')
        require(all(o['output_type']!='error' for o in a['outputs']),'Notebook error retained')
        streams.append(''.join(''.join(o.get('text',[])) for o in a['outputs']))
    require([c['execution_count'] for c in cells]==sorted(set(c['execution_count'] for c in cells)),'Notebook order differs')
    for i,marker in enumerate(('W5A_PACKAGE_PASS','W5A_PRECHECK_PASS','BROWSER_SERVICE_READY','W5A_BROWSER_READY',
                              'W5A_COLLECTION_COMPLETE','W5A_CLOSED_IDLE','W5A_RESULTS_READY')):
        require(marker in streams[i],'Notebook marker missing: '+marker)
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        require(len(names)==len(set(names)) and len(names)<10000 and sum(e.file_size for e in entries)<1536*1024**2,'Archive bounds/inventory')
        require(all(not e.is_dir() and not Path(e.filename).is_absolute() and '..' not in Path(e.filename).parts and
                    ':' not in e.filename and '\\' not in e.filename for e in entries),'Unsafe archive')
        inventory=json.loads(z.read('bundle_manifest.json'))
        require(inventory['revision']==release_manifest['revision'] and set(names)==set(inventory['files'])|{'bundle_manifest.json'},'Inventory mismatch')
        for name,info in inventory['files'].items():
            data=z.read(name);require(dict(bytes=len(data),sha256=sha(data))==info,'Object/record corrupted: '+name)
        session=json.loads(z.read('session.json'));status=session['status'];caps=json.loads(z.read('capabilities.json'))
        require(status['evidence_kind']==caps['evidence_kind']=='PYNQ_PL_DMA','HOST evidence is not board evidence')
        require(status['session_id']==caps['session_id'] and status['service_state']=='CLOSED' and status['hardware_state']=='IDLE' and
                status['completed']==status['accepted']==1000 and status['overlay_downloads']==1 and status['pending']==status['retained_buffer_count']==0 and
                status['active_run_id'] is None and status['error'] is None,'Final hardware lifecycle differs')
        require(json.loads(z.read('browser_manifest.json'))==manifest,'Different release')
        env=json.loads(z.read('environment.json'))
        require(env['machine'] in ('armv7l','armv7') and env['pynq']=='3.0.1' and
                env['runtime_fclk0_mhz_register_readback']==100.0,'Wrong board runtime/clock')
        runtime=[ast.literal_eval(line[len('Runtime: '):]) for line in streams[1].splitlines() if line.startswith('Runtime: ')]
        require(len(runtime)==1 and all(env.get(k)==v for k,v in runtime[0].items()),'Notebook/runtime mismatch')
        ids=session['run_ids'];require(len(ids)==len(set(ids))==1000,'Missing/duplicate tasks')
        records=[json.loads(z.read(rid+'/record.json')) for rid in ids]
        used=set();expected_top={'bundle_manifest.json','config_outputs.json','measurements.csv','capabilities.json','environment.json','browser_manifest.json','session.json','events.jsonl','w5a_summary.json'}
        for rid,r in zip(ids,records):
            require(r['run_id']==rid and r['session_id']==status['session_id'] and r['evidence_kind']==r['evidence']['evidence_kind']=='PYNQ_PL_DMA','Mixed task/session')
            require(set(r['storage_refs'])==set(r['files']),'Storage references missing')
            for name,target in r['storage_refs'].items():
                require(target=='objects/'+r['files'][name]['sha256'] and inventory['files'][target]==r['files'][name],'Wrong content reference')
                used.add(target)
            r['browser_timing']=json.loads(z.read(rid+'/browser_timing.json'))
            expected_top.update((rid+'/record.json',rid+'/browser_timing.json'))
        require(set(names)==expected_top|used,'Unexpected/failure/unreferenced files')
        summary=verify_schedule(records,sorted(manifest['images']))
        require(summary==json.loads(z.read('w5a_summary.json')) and session['suite']==summary['suite'],'Summary differs')
        registry={}
        for r in records:
            require(registry.setdefault(r['config_id'],r['output']['sha256'])==r['output']['sha256'],'Nondeterministic actual output')
        require(registry==json.loads(z.read('config_outputs.json')),'Config output registry differs')
        rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))))
        require(len(rows)==1000,'CSV count differs')
        require(set(rows[0])=={'run_id','image_id','side','threshold','algorithm','mode','pl_core_frame_ns',
            'dma_transaction_ns','inference_ns','storage_dedup_ns','browser_request_to_render_ms','rss_bytes','available_bytes','disk_free_bytes'},'CSV columns differ')
        for row,r in zip(rows,records):
            for key,value in row.items():
                if key=='run_id':expected=r[key]
                elif key in r['request']:expected=r['request'][key]
                elif key in r['timing_ns']:expected=r['timing_ns'][key]
                elif key=='storage_dedup_ns':expected=r[key]
                elif key=='browser_request_to_render_ms':expected=r['browser_timing']['request_to_render_ms']
                elif key in r['resources']:expected=r['resources'][key]
                else:raise ValueError('Unknown CSV field')
                require(value==str(expected),'CSV data differs')
        adapter=CompactArchive(z,records);previous=0;words=0;pngs=0
        for i,r in enumerate(records):
            checked=check_run(adapter,r,package,manifest)
            require(checked['frame_status_before']==previous and checked['hardware']['sequence']==i+1,'Counter reset/gap/extra frame')
            previous=checked['frame_status_after'];words+=checked['matched_words'];pngs+=checked['matched_png_images']
            if (i+1)%10==0:print('W5A_AUDIT_PROGRESS',i+1,'/1000',flush=True)
        require(status['last_completed_frame_status']==previous,'Final count mismatch')
        events=[json.loads(line) for line in z.read('events.jsonl').splitlines()]
        require([e['event'] for e in events]==['SERVICE_READY']+[kind for _ in records for kind in
            ('RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED','BROWSER_FIRST_RENDER')]+['SERVICE_FINISHED_IDLE'],'Unexpected lifecycle/error/retry')
        require([e['server_ns'] for e in events]==sorted(e['server_ns'] for e in events) and events[-1]['detail']==status and
                events[-1]['server_ns']<=session['export_server_ns'],'Event order/final state differs')
        for i,r in enumerate(records):
            ev=events[1+4*i:5+4*i]
            require(all(e['detail']['run_id']==r['run_id'] for e in ev) and ev[0]['detail']['request']==r['request'] and
                    ev[2]['detail']['output_sha256']==r['output']['sha256'] and ev[3]['detail']==r['browser_timing'],'Event identity differs')
        return dict(status='W5A_BOARD_ENDURANCE_VERIFIED_ONLY',archive=file_info(archive),notebook=file_info(notebook),
            tasks=1000,matched_words=words,matched_pngs=pngs,summary=summary,ignored_empty_cells=empty,
            power='NOT_MEASURED_NO_INSTRUMENT',w5b='NOT_RUN',quality='NOT_FINALLY_ACCEPTED')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('archive','notebook','destination'):p.add_argument(key,type=Path)
    p.add_argument('--release',type=Path,required=True);a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=False)
    try:
        result=verify(a.archive,a.notebook,a.release);write_json(a.destination/'verification.json',result);print(result['status'])
    except BaseException as exc:
        write_json(a.destination/'rejection.json',dict(status='REJECTED',error=type(exc).__name__+': '+str(exc)));raise
