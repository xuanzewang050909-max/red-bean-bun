"""PYNQ functional validation. PS transfers/schedules; all refinement is PL.

Explicit notebook invocation only. Failure retains buffers, kernel and files.
No automatic reload, reset, retry, CPU inference or quality reclassification.
"""
from refinement_clock_contract import require_refinement_clock
from pathlib import Path
import hashlib, json, os, platform, sys, time, traceback, socket, inspect, uuid
import numpy as np

CONTEXT = None

def require(ok, message):
    if not ok: raise RuntimeError(message)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def raw_sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())

def write(path, value):
    payload=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with Path(path).open('xb') as f: f.write(payload); f.flush(); os.fsync(f.fileno())

def verify(root):
    root=Path(root).resolve(); manifest=read(root/'manifest.json')
    for name, ref in manifest['files'].items():
        path=(root/name).resolve()
        require(root in path.parents,'PATH_ESCAPE')
        require(path.stat().st_size==ref['bytes'] and sha(path)==ref['sha256'],'SHA:'+name)
    require(manifest['algorithm']=='SR_ATOMIC_BRIDGE_DEVBUDGET1_V1','RULE')
    require(manifest['software_quality']=='NOT_QUALIFIED','PRESERVE_QUALITY_FAILURE')
    require(manifest['frames']==['HRF_01_dr_256','HRF_01_dr_512','STARE_im0324_256','STARE_im0324_512'],'FRAME_SCOPE')
    return manifest

def event(ctx, name, data, *, console=True):
    line=json.dumps(dict(event=name,elapsed_seconds=time.perf_counter()-ctx['start'],data=data),allow_nan=False)
    with (ctx['dest']/'events.jsonl').open('a',encoding='utf8') as f:
        f.write(line+'\n');f.flush();os.fsync(f.fileno())
    if console:
        print(name, data, flush=True)

def wait_ip(ip, cmd, timeout=180.):
    require(len(cmd)==16,'COMMAND_LENGTH')
    before=int(ip.read(0));require(before&4,'IP_NOT_IDLE')
    for i,v in enumerate(cmd): ip.write(0x40+4*i,int(v)&0xffffffff)
    start=time.perf_counter();ip.write(0,1)
    while True:
        control=int(ip.read(0))
        if control&2: break
        if time.perf_counter()-start>timeout:
            raise TimeoutError('HLS timeout; retain state control='+hex(control))
        time.sleep(0.001)
    result=int(ip.read(0x10))
    require(result==0,'HLS_RETURN:'+str(result))
    return dict(seconds=time.perf_counter()-start,control=control,result=result,timeout_seconds=timeout)

def check_environment(env, contract):
    require(env['pynq']=='3.0.1' and env['machine'] in ('armv7','armv7l'),'RUNTIME')
    for k, ref in contract['runtime_driver_sources'].items():
        got=env['runtime_driver_sources'][k]
        require(got['sha256']==ref['sha256'] and got['bytes']==ref['bytes'],'RUNTIME_SHA:'+k)

def validate_c7(src, out):
    require(src.shape==out.shape and src.dtype==out.dtype==np.dtype('uint32'),'C7_SHAPE')
    f=src>>24;q=out>>24;m=(out>>16)&255
    require(np.all(f<=1) and np.all((m==0)|(m==255)),'C7_ENCODING')
    require(np.array_equal(m!=0,(q>=112)&(f!=0)),'C7_T112')
    require(np.array_equal(out&255,(src>>8)&255),'C7_RAW_GREEN')

def snapshot(frame, mem, work, schedule, expected):
    n=schedule['side']**2;arrays={};hh,zz=schedule['outputs']['S'];rr=schedule['outputs']['R']
    for name, item in [('h',hh),('z',zz),('r',rr)]:
        shape=item['shape'];shape=shape['items'] if isinstance(shape,dict) else shape
        arrays[name]=np.array(mem[item['offset']:item['offset']+int(np.prod(shape))]).reshape(shape)
    arrays['flags']=np.array(mem[schedule['flags']:schedule['flags']+n]).reshape(schedule['side'],schedule['side'])
    arrays['ledger']=np.array(work[3*(n+1):3*(n+1)+10])
    np.savez_compressed(frame/'pl_arrays.npz',**arrays)
    actual={k:raw_sha(v) for k,v in arrays.items()}
    write(frame/'actual_array_sha.json',actual)
    require(actual==expected,'PL_ARRAY_MISMATCH: '+str([k for k in actual if actual[k]!=expected[k]]))
    return actual

def start(root, destination, operator_confirmation):
    global CONTEXT
    require(operator_confirmation=='ATOMIC_BRIDGE_FIXED_PL_TEST_AUTHORIZED','AUTHORIZATION')
    require(CONTEXT is None,'NO_AUTOMATIC_RETRY')
    require('ipykernel' in sys.modules and platform.machine() in ('armv7l','armv7'),'PERSISTENT_PYNQ_NOTEBOOK_REQUIRED')
    root=Path(root).resolve();dest=Path(destination).resolve();manifest=verify(root)
    require(sha(__file__)==manifest['files']['board_run.py']['sha256'],'IMPORTED_BOARD_RUNNER')
    require(not (root/'ATTEMPT_STARTED.json').exists(),'ALREADY_ATTEMPTED')
    with socket.socket() as s: s.bind(('0.0.0.0',8090))
    dest.mkdir(exist_ok=False)
    ctx=dict(root=root,dest=dest,start=time.perf_counter(),phase='PREPARE',buffers=[],failed=False)
    CONTEXT=ctx
    session=dict(session=uuid.uuid4().hex,destination=str(dest),manifest_sha=sha(root/'manifest.json'),runner_sha=sha(__file__))
    write(root/'ATTEMPT_STARTED.json',session);write(dest/'session.json',session)
    try:
        sys.path.insert(0,str(root/'trusted_c7'))
        from pynq_q4d.hardware import PynqHardware
        from pynq_q4d import protocol, quality_observer
        from pynq import Overlay, allocate, Clocks
        import pynq
        contract=read(root/'trusted_c7/capture_contract.json')
        require(sha(inspect.getfile(PynqHardware))==contract['trusted_files']['pynq_q4d/hardware.py']['sha256'],'IMPORTED_C7_DRIVER')
        for name,module in [('protocol',protocol),('quality_observer',quality_observer)]:
            require(sha(inspect.getfile(module))==contract['trusted_files']['pynq_q4d/'+name+'.py']['sha256'],'IMPORTED_C7_MODULE:'+name)
        hw=PynqHardware(root/'trusted_c7');ctx['c7']=hw;hw.prepare()
        check_environment(hw.environment,contract);write(dest/'environment.json',hw.environment)
        event(ctx,'PREFLIGHT_PASS',dict(manifest_sha=sha(root/'manifest.json'),quality='NOT_QUALIFIED'))
        t=time.perf_counter();hw.open();event(ctx,'TRUSTED_C7_LOADED',dict(seconds=time.perf_counter()-t))
        write(dest/'environment_c7_loaded.json',hw.environment)
        # Capture all native C7 outputs before the single switch to refinement.
        for frame_id in manifest['frames']:
            frame=dest/frame_id;frame.mkdir();ref=read(root/'frames'/frame_id/'request.json')
            ctx['phase']='C7:'+frame_id
            words=np.fromfile(root/'frames'/frame_id/'input.bin',dtype='<u4').reshape(ref['side'],ref['side'])
            t=time.perf_counter();out,record=hw.run(words,dict(side=ref['side'],mode_code=3,algorithm='C7',threshold=112))
            np.save(frame/'c7_output.npy',out,allow_pickle=False);write(frame/'c7_record.json',record)
            validate_c7(words,out);require(raw_sha(out)==ref['c7_raw_sha'],'C7_BASELINE_DIFFERENCE')
            event(ctx,'C7_FRAME_PASS',dict(frame=frame_id,seconds=time.perf_counter()-t,record_sha=sha(frame/'c7_record.json')))
        require(hw.state=='IDLE' and not hw.retained,'C7_NOT_IDLE')
        ctx['phase']='REFINEMENT_LOAD';overlay=Overlay(str(root/'overlay/ab_refine.bit'),download=False);ctx['overlay']=overlay
        for name,typ in [('sr_compute_0','xilinx.com:hls:sr_compute:1.0'),('atomic_bridge_0','xilinx.com:hls:atomic_bridge:1.0')]:
            require(overlay.ip_dict[name]['type']==typ,'REFINEMENT_IP:'+name)
        t=time.perf_counter();overlay.download();event(ctx,'REFINEMENT_LOADED',dict(seconds=time.perf_counter()-t,
            ips={k:dict(type=overlay.ip_dict[k]['type'],phys_addr=int(overlay.ip_dict[k]['phys_addr']),addr_range=int(overlay.ip_dict[k]['addr_range']))
                 for k in ('sr_compute_0','atomic_bridge_0','axi_dma_0')}))
        require_refinement_clock(Clocks, overlay.clock_dict)
        write(dest/'environment_refinement_loaded.json',dict(clock_mhz=float(Clocks.fclk0_mhz),
            bit_sha=sha(root/'overlay/ab_refine.bit'),hwh_sha=sha(root/'overlay/ab_refine.hwh'),loaded=bool(overlay.is_loaded())))
        compute=overlay.sr_compute_0;bridge=overlay.atomic_bridge_0
        # All arrays are explicit DMA-capable DDR. No Python feature computation.
        for frame_id in manifest['frames']:
            frame=dest/frame_id;ref=read(root/'frames'/frame_id/'request.json');side=ref['side'];n=side*side
            schedule=read(root/'plans'/str(side)/'schedule.json');ctx['phase']='ALLOCATE:'+frame_id
            t_frame=time.perf_counter()
            mem=allocate(shape=(schedule['memory_shorts'],),dtype=np.int16);ctx['buffers'].append(mem)
            work=allocate(shape=(schedule['work_ints'],),dtype=np.int32);ctx['buffers'].append(work)
            wa=np.fromfile(root/'plans'/str(side)/'weights.bin',dtype='<i2');ba=np.fromfile(root/'plans'/str(side)/'biases.bin',dtype='<i8')
            wt=allocate(shape=wa.shape,dtype=np.int16);ctx['buffers'].append(wt)
            bi=allocate(shape=ba.shape,dtype=np.int64);ctx['buffers'].append(bi)
            for buf in ctx['buffers']:
                require(0x100000<=int(buf.physical_address)<0x20000000-int(buf.nbytes),'DDR_ADDRESS')
            words=np.fromfile(root/'frames'/frame_id/'input.bin',dtype='<u4')
            c7=np.load(frame/'c7_output.npy',allow_pickle=False).ravel()
            # Only lossless 32-bit transport packing; unpack and scaling occur in PL op10.
            packed=np.stack([words&65535,words>>16,c7&65535,c7>>16],axis=1).astype('<u2').view('<i2').ravel()
            mem[:]=0;work[:]=0;mem[schedule['packed']:schedule['packed']+4*n]=packed;wt[:]=wa;bi[:]=ba
            t_sync=time.perf_counter()
            for buf in ctx['buffers']:buf.flush()
            sync_seconds=time.perf_counter()-t_sync
            event(ctx,'DDR_READY',dict(frame=frame_id,plan_sha=sha(root/'plans'/str(side)/'schedule.json'),
                buffers=[dict(physical_address=int(buf.physical_address),nbytes=int(buf.nbytes),dtype=str(buf.dtype)) for buf in ctx['buffers']]))
            compute.write(0x18,int(mem.physical_address));compute.write(0x20,int(wt.physical_address));compute.write(0x28,int(bi.physical_address))
            bridge.write(0x18,int(mem.physical_address));bridge.write(0x20,int(work.physical_address))
            operations=[];t_pl=time.perf_counter()
            for op in schedule['commands']:
                ctx['phase']=frame_id+':'+op['name'];require(overlay.is_loaded(),'OVERLAY_CHANGED')
                stat=wait_ip(compute,op['cmd']);operations.append(dict(name=op['name'],**stat))
                event(ctx,'COMPUTE_DONE',dict(frame=frame_id,name=op['name'],**stat))
            ctx['phase']=frame_id+':AtomicBridge';stat=wait_ip(bridge,schedule['bridge'])
            operations.append(dict(name='AtomicBridge',**stat));pl_seconds=time.perf_counter()-t_pl
            t_sync=time.perf_counter();mem.invalidate();work.invalidate();sync_seconds+=time.perf_counter()-t_sync
            write(frame/'operations.json',operations)
            actual=snapshot(frame,mem,work,schedule,ref['expected_array_sha'])
            event(ctx,'REFINEMENT_FRAME_PASS',dict(frame=frame_id,pl_and_ps_poll_seconds=pl_seconds,cache_sync_seconds=sync_seconds,
                frame_wall_seconds=time.perf_counter()-t_frame,array_sha=actual,source='REAL_PYNQ_PL_NOT_CPU_INFERENCE'))
            for buf in ctx['buffers']:buf.freebuffer()
            ctx['buffers'].clear()
        ctx['phase']='COMPLETE'
        write(dest/'summary.json',dict(status='BOARD_CAPTURED_PENDING_HOST_VERIFICATION',frames=manifest['frames'],
            manifest_sha=sha(root/'manifest.json'),source='PYNQ_Z2_PL',clock_mhz=float(Clocks.fclk0_mhz),
            software_quality='NOT_QUALIFIED',LATENCY_TARGET='UNSET',retries=0,seconds=time.perf_counter()-ctx['start']))
        return read(dest/'summary.json')
    except BaseException as exc:
        ctx['failed']=True
        write(dest/'FAULT.json',dict(error=repr(exc),traceback=traceback.format_exc(),phase=ctx['phase'],
            retained_buffers=len(ctx['buffers']),retries=0,instruction='STOP; keep kernel, buffers and files. No retry/reset/reload.'))
        raise

def export_results(path):
    import zipfile
    require(CONTEXT is not None,'NO_SESSION');dest=CONTEXT['dest'];path=Path(path).resolve()
    require(dest not in path.parents,'ZIP_OUTSIDE_RESULTS')
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(dest))
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path),failed=CONTEXT['failed'])
