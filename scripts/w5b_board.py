"""W5b orchestration only. No medical-image computation or automatic recovery."""
import asyncio
import json
import shutil
import time
import zipfile
from pathlib import Path
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from pynq_w5b.launch import prepare, start
from pynq_w5b.protocol import file_info, require, validate_package, write_json
from pynq_w5b.service import BusyError


def config(image='im0001', side=512, algorithm='C7', mode='final', threshold=112):
    return dict(image_id=image, side=side, algorithm=algorithm, mode=mode,
                threshold=threshold, png_profile='fast')


def planned_cases():
    cases=[]
    for side in (256,512):
        for t in (1,111,112,113,255):
            cases.append(config(side=side,threshold=t))
        for t in (1,27,28,29,255):
            cases.append(config(side=side,algorithm='C2',threshold=t))
        for a in ('A','C5'):
            cases.append(config(side=side,algorithm=a,threshold=28))
        for mode in ('threshold_candidate','closed_candidate'):
            cases.append(config(side=side,algorithm='C2',mode=mode,threshold=28))
        cases.append(config(side=side,mode='bypass'))
        cases.append(config('im0324_nogt',side=side))
    cases.extend([config(threshold=111), config('im0324',side=256,threshold=113), config()])
    return cases


def manual_cases():
    return [config(), config('im0324_nogt'), config('im0324',mode='bypass'),
            config(algorithm='C2',mode='threshold_candidate',threshold=28),
            config(algorithm='C2',mode='closed_candidate',threshold=28),
            config(algorithm='C2',threshold=28), config()]


def validate_w5b(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'w5b_manifest.json').read_bytes())
    require(manifest['revision']=='c7_w5b_interaction_r1','Wrong W5b release')
    require(manifest['automatic']==planned_cases() and manifest['manual']==manual_cases(),'Wrong frozen cases')
    for name,info in manifest['artifacts'].items():
        require(file_info(root/name)==info,'W5b file changed: '+name)
    validate_package(root)
    return manifest


def prepare_w5b(root):
    root=Path(root).resolve();validate_w5b(root)
    require(Path(__file__).resolve()==root/'w5b_board.py','Use paired helper in a fresh kernel')
    require(not (root/'browser_results').exists(),'Preserve prior session; fresh folder required')
    require(shutil.disk_usage(root).free>=1024**3,'Need at least 1 GiB free for records and export')
    ctx=prepare(root,8090)
    print('W5B_PRECHECK_PASS: paired original C7, one GiB free; FPGA unchanged',flush=True)
    return ctx


def note(ctx, kind, **detail):
    item=dict(kind=kind,server_ns=time.perf_counter_ns(),**detail)
    with (ctx['manager'].directory/'w5b_checks.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n')
    return item


async def http(ctx,path,body=None,expected=200,client=None):
    request=HTTPRequest('http://127.0.0.1:'+str(ctx['port'])+path,
        method='GET' if body is None else 'POST',
        body=None if body is None else json.dumps(body),
        headers={} if body is None else {'Content-Type':'application/json'},request_timeout=60)
    response=await (client or AsyncHTTPClient()).fetch(request,raise_error=False)
    value=json.loads(response.body)
    note(ctx,'HTTP',path=path,body=body,expected=expected,actual=response.code,response=value)
    require(response.code==expected,'Unexpected HTTP response; stop and preserve records: '+str(response.code))
    return value


async def wait_run(ctx,rid):
    deadline=time.monotonic()+60
    while True:
        job=ctx['manager'].get(rid)
        if job['status']=='COMPLETED':
            require(ctx['manager'].error is None,'Service fault; preserve session')
            return job
        require(job['status'] in ('QUEUED','RUNNING'),'Task failed; preserve session')
        require(time.monotonic()<deadline,'Task timeout; do not retry/reset/release buffers')
        await asyncio.sleep(.05)


async def automatic_w5b(ctx):
    m=ctx['manager']
    require(not ctx.get('w5b_auto_attempted') and m.status()['accepted']==0,'Run automatic suite once')
    ctx['w5b_auto_attempted']=True
    def body(i):return dict(**planned_cases()[i],client_nonce='w5b_auto_%03d'%i)
    try:
        # Valid JSON but unsupported requests must be rejected before any native operation.
        base=body(0)
        invalid=[dict(base,threshold=v) for v in (0,256,1.5,True)]
        invalid += [dict(base,side=128),dict(base,image_id='missing_image'),
                    dict(base,mode='threshold_candidate'),dict(base,extra='unexpected')]
        for bad in invalid:
            before=m.status()
            await http(ctx,'/api/runs',bad,422)
            require(m.status()==before,'Rejected input changed state')
        for i in range(32):
            accepted=await http(ctx,'/api/runs',body(i),202)
            job=await wait_run(ctx,accepted['run_id'])
            require(job['evidence']['hardware_latched_parameter_readback']['sequence']==i+1,'Frame identity mismatch')
            print('W5B_FRAME_SAVED:',i+1,'/35',job['request']['image_id'],flush=True)
        stale=dict(client_nonce=job['request']['client_nonce'],config_id='wrong_config',
                   input_sha256=job['input']['sha256'],output_sha256=job['output']['sha256'],
                   request_start_ms=1,result_received_ms=2,images_decoded_ms=3,render_done_ms=4,
                   visibility='visible',user_agent='W5b deliberate stale-observation rejection probe',
                   loop_id=None,loop_index=None,loop_start_ms=None,page_id='0'*32)
        snapshot=m.status()
        await http(ctx,'/api/runs/'+job['run_id']+'/browser-timing',stale,422)
        require(m.status()==snapshot and m.get(job['run_id'])['browser_timing'] is None,'Stale observation altered state')
        # These four probes deliberately use the SAME production manager without yielding:
        # deterministic admission test, not a claim of concurrent TCP clients or active AXI.
        before=m.status()
        first=m.submit(body(32)); second=m.submit(body(33))
        require(m.active==first['run_id'] and len(m.queue)==1,'Queue admission differs')
        repeat=m.submit(body(32));require(repeat['run_id']==first['run_id'],'Nonce repeated PL')
        for name,operation in [('queue_full',lambda:m.submit(body(34))),
                               ('nonce_conflict',lambda:m.submit(dict(body(32),threshold=112))),
                               ('close_busy',m.finish)]:
            try:operation()
            except BusyError as exc:note(ctx,'EXPECTED_BUSY',name=name,message=str(exc),state=m.status())
            else:raise RuntimeError('Expected busy rejection: '+name)
        try:await m.export()
        except BusyError as exc:note(ctx,'EXPECTED_BUSY',name='export_busy',message=str(exc),state=m.status())
        else:raise RuntimeError('Busy export unexpectedly accepted')
        note(ctx,'QUEUE_ADMISSION',before=before,after=m.status(),run_ids=[first['run_id'],second['run_id']],
             duplicate_id=repeat['run_id'],scope='Production manager admission without yielding; no AXI fault injection')
        await wait_run(ctx,first['run_id']);await wait_run(ctx,second['run_id'])
        snapshot=m.status()
        repeated=await http(ctx,'/api/runs',body(32),202)
        require(repeated['run_id']==first['run_id'] and m.status()==snapshot,'Completed retry created another frame')
        # Close only an HTTP client after accepted response, leaving the board's owner intact.
        client=AsyncHTTPClient(force_instance=True)
        try:accepted=await http(ctx,'/api/runs',body(34),202,client=client)
        finally:client.close()
        require(m.active==accepted['run_id'] and m.get(accepted['run_id'])['status'] in ('QUEUED','RUNNING'),
                'Client-close timing window missed; preserve session, do not retry')
        note(ctx,'CLIENT_CLOSED_AFTER_ACCEPT',run_id=accepted['run_id'],state=m.status(),
             scope='Local HTTP client disposal after accepted response; not Ethernet loss or kernel restart')
        await wait_run(ctx,accepted['run_id'])
        fresh=AsyncHTTPClient(force_instance=True)
        try:recovered=await http(ctx,'/api/runs/'+accepted['run_id'],client=fresh)
        finally:fresh.close()
        require(recovered['status']=='COMPLETED' and m.status()['completed']==35,'Reconnect missing completed task')
        require(m.status()['overlay_downloads']==1 and not m.error,'Unexpected reload/error')
        note(ctx,'AUTO_COMPLETE',status=m.status())
        ctx['w5b_auto_complete']=True
        print('W5B_AUTO_COMPLETE: 35 real tasks; boundary, queue admission and HTTP client checks saved',flush=True)
    except BaseException as exc:
        note(ctx,'AUTO_FAILED',error=type(exc).__name__+': '+str(exc),status=m.status())
        raise


def manual_ready_w5b(ctx):
    require(ctx.get('w5b_auto_complete') and ctx['manager'].status()['completed']==35,'Automatic checks not complete')
    print('W5B_MANUAL_READY: seven manual frames; reload after sixth, no Ethernet/power disconnection',flush=True)
    return ctx['manager'].status()


def summary_w5b(ctx):
    m=ctx['manager'];s=m.status();jobs=list(m.jobs.values())
    require(ctx.get('w5b_auto_complete') and s['accepted']==s['completed']==42,'Need 35 automatic + 7 manual tasks')
    require(s['overlay_downloads']==1 and s['hardware_state']=='IDLE' and not s['pending'] and
            s['active_run_id'] is None and s['error'] is None and s['retained_buffer_count']==0,'Unsafe state')
    for i,(job,expected) in enumerate(zip(jobs,planned_cases()+manual_cases())):
        require(all(job['request'][k]==v for k,v in expected.items()),'Unexpected case/order: '+str(i+1))
        require(job['evidence']['hardware_latched_parameter_readback']['sequence']==i+1,'Missing/extra PL frame')
        if i>=35:
            observation=job.get('browser_timing')
            require(observation and observation['visibility']=='visible' and observation['loop_id'] is None,'Missing manual foreground result')
        if job['request']['image_id'].endswith('_nogt'):
            require(job['quality']['annotations']=={} and job['quality']['quality_reason'],'Stale GT result on no-GT fixture')
    pages=[j['browser_timing']['page_id'] for j in jobs[35:]]
    require(len(set(pages[:6]))==1 and pages[-1]!=pages[0],'Need one intentional reload after six observations')
    require(jobs[35]['output']['sha256']==jobs[41]['output']['sha256'],'Reload changed same-config output')
    for offset in (0,16):
        group=[j['output']['sha256'] for j in jobs[offset:offset+5]]
        require(group[0]!=group[-1],'Threshold extremes did not change PL output')
    result=dict(status='COLLECTED_PENDING_DOWNLOAD_AUDIT',tasks=42,automatic=35,manual=7,
        page_ids=pages,session_id=s['session_id'],scope='W5b bounded protocol/manual reload, no physical network loss or forced DMA fault')
    write_json(m.directory/'w5b_summary.json',result)
    return result


async def close_w5b(ctx):
    result=summary_w5b(ctx)
    ctx['manager'].finish();ctx['server'].stop()
    await ctx['server'].close_all_connections()
    ctx['w5b_closed']=True
    print('W5B_CLOSED_IDLE:',result,flush=True)


async def export_w5b(ctx):
    require(ctx.get('w5b_closed') and not ctx.get('w5b_export_attempted'),'Close safely first; export once')
    ctx['w5b_export_attempted']=True
    m=ctx['manager'];root=m.directory
    # Use original session exporter to exercise its PNG/NPY/CSV result path.
    original=await m.export()
    write_json(root/'w5b_export_source.json',dict(path=original.relative_to(root).as_posix(),file=file_info(original)))
    files=[p for p in sorted(root.rglob('*')) if p.is_file() and 'exports' not in p.relative_to(root).parts]
    require(shutil.disk_usage(root).free>=sum(p.stat().st_size for p in files)+128*1024**2,'Insufficient export space; preserve results')
    target=m.root.parent/'c7_w5b_results.zip'
    require(not target.exists(),'Preserve existing result ZIP')
    inventory={p.relative_to(root).as_posix():file_info(p) for p in files}
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in files:z.write(p,p.relative_to(root).as_posix())
        z.write(original,'original_session_export.zip')
        inventory['original_session_export.zip']=file_info(original)
        z.writestr('w5b_bundle_manifest.json',json.dumps(dict(revision='c7_w5b_interaction_r1',files=inventory)))
    ctx['executor'].shutdown(wait=False)
    print('W5B_RESULTS_READY:',str(target),flush=True)
    return str(target)
