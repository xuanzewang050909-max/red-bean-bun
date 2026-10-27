"""Offline import/verification by default. Hardware only through explicit start().
PS transfers existing RGB/FOV/old-mask words and displays results. PL computes all
new evidence, selection, propagation and union. No masks from expected files are
transferred to hardware. No retry/reset/free on failure.
"""
from pathlib import Path
import json,hashlib,time,os,uuid,traceback,zipfile,inspect,platform
import numpy as np
import transport,evidence_io
import refinement_clock_contract
from refinement_clock_contract import require_refinement_clock
CONTEXT=None
CONFIRM='I_AUTHORIZE_SINGLE_IMAGE_BOARD_TEST_ONCE'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify(root):
    root=Path(root).resolve();m=json.loads((root/'manifest.json').read_text())
    assert m['algorithm']=='single-image-vessel-valley-v1' and m['clock_mhz']==50
    assert m['processing_shape']==[512,512] and m['hardware_release']=='OFFLINE_PHYSICAL_GATES_PASS'
    for name,ref in m['files'].items():
        p=(root/name).resolve();assert root in p.parents and p.stat().st_size==ref['bytes'] and sha(p)==ref['sha256'],name
    assert sha(__file__)==m['files']['board_run.py']['sha256']
    for mod in [transport,evidence_io,refinement_clock_contract]:assert sha(inspect.getfile(mod))==m['files'][mod.__name__+'.py']['sha256']
    return m
def call(ctx,label,fn,**details):return evidence_io.trace_call(ctx,label,fn,details)
def persist(ctx,name,array):
    dest=ctx['dest'];tmp=dest/(name+'.npy.partial');final=dest/(name+'.npy')
    assert not tmp.exists() and not final.exists()
    with tmp.open('xb') as f:np.save(f,array,allow_pickle=False);f.flush();os.fsync(f.fileno())
    assert np.array_equal(np.load(tmp,allow_pickle=False),array)
    os.link(tmp,final);evidence_io.sync_directory(dest);tmp.unlink();evidence_io.sync_directory(dest)
    assert np.array_equal(np.load(final,allow_pickle=False),array)
    return dict(path=final.name,bytes=final.stat().st_size,sha256=sha(final),raw_sha256=transport.raw_sha(array))
def transaction(ctx,ip,op,timeout=120.):
    call(ctx,'OP_WRITE',lambda:ip.write(0x20,op),op=op)
    t=time.perf_counter();call(ctx,'AP_START',lambda:ip.write(0,1),op=op)
    # MMIO accesses themselves can stall below Python; timeout covers poll duration only.
    # Durable per-access INTENT/RETURN and no blocking console before actions.
    while True:
        c=call(ctx,'POLL',lambda:int(ip.read(0)),op=op)
        if c&2:break
        if time.perf_counter()-t>timeout:raise TimeoutError('STOP_AND_RETAIN: operation '+str(op))
        time.sleep(.05)
    rc=call(ctx,'RETURN_CODE',lambda:int(ip.read(0x10)),op=op)
    if rc:raise RuntimeError('PL_RETURN:'+str(rc))
    transport.event(ctx,'OP_DONE',dict(op=op,seconds=time.perf_counter()-t),console=False)
def frame(ctx,root,case,ip,allocate):
    # Native and smoke inputs are pre-frozen source data, not added-mask answers.
    ctx['phase']=case+':PREPARE'
    inp=np.load(root/(case+'_input.npy'),allow_pickle=False);h,w=inp.shape;n=h*w
    expect=np.load(root/(case+'_expected.npy'),allow_pickle=False)
    assert inp.dtype==np.uint32 and expect.dtype==np.uint32 and expect.size==6*n
    buf=call(ctx,'ALLOCATE',lambda:allocate((6*n+32,),dtype=np.uint32),words=6*n+32);ctx['buffers'].append(buf)
    buf[:]=np.uint32(0xdeadbeef);buf[:n]=inp.ravel()
    addr=int(buf.physical_address);assert 0<=addr and addr+(6*n+32)*4<=0x20000000 and addr%4==0
    call(ctx,'SYNC_TO_DEVICE',buf.flush,case=case)
    for reg,value in [(0x18,addr),(0x28,h),(0x30,w),(0x38,6*n)]:
        call(ctx,'CONTROL_WRITE',lambda r=reg,v=value:ip.write(r,v),offset=reg,value=value)
        got=call(ctx,'CONTROL_READBACK',lambda r=reg:int(ip.read(r)),offset=reg)
        assert got==value,('CONTROL_READBACK',reg,got,value)
    t=time.perf_counter()
    for op in [0,1,2]+[3]*16+[4]:
        ctx['phase']=case+':op'+str(op);transaction(ctx,ip,op)
    call(ctx,'SYNC_FROM_DEVICE',buf.invalidate,case=case)
    got=np.array(buf,dtype=np.uint32,copy=True)
    saved=persist(ctx,case+'_actual',got)
    differences=int(np.count_nonzero(got[:6*n]!=expect.ravel()))
    guard_ok=bool(np.all(got[6*n:]==np.uint32(0xdeadbeef)))
    record=dict(source='REAL_PYNQ_PL',case=case,shape=[h,w],physical_address=addr,words=6*n,guard_words=32,
                differences=differences,guard_ok=guard_ok,seconds=time.perf_counter()-t,actual=saved,input_sha256=sha(root/(case+'_input.npy')))
    transport.write(ctx['dest']/(case+'_record.json'),record)
    assert differences==0 and guard_ok,('STOP_NUMERIC_DIFFERENCE',record)
    return record
def start(root,destination,operator_confirmation):
    global CONTEXT
    if operator_confirmation!=CONFIRM:raise RuntimeError('EXPLICIT_MANUAL_AUTHORIZATION_REQUIRED')
    if CONTEXT is not None:raise RuntimeError('SESSION_ALREADY_EXISTS; no retry')
    root=Path(root).resolve();dest=Path(destination).resolve();m=verify(root)
    if (root/'ATTEMPT_STARTED.json').exists():raise RuntimeError('ALREADY_ATTEMPTED; preserve evidence')
    dest.mkdir(exist_ok=False)
    ctx=dict(dest=dest,start=time.perf_counter(),phase='PREPARE',buffers=[],failed=False);CONTEXT=ctx
    session=dict(session=uuid.uuid4().hex,manifest_sha256=sha(root/'manifest.json'),confirmation=operator_confirmation,board='PYNQ-Z2',algorithm=m['algorithm'])
    transport.write(root/'ATTEMPT_STARTED.json',session);transport.write(dest/'session.json',session)
    try:
        from pynq import Overlay,allocate,Clocks
        import pynq
        assert pynq.__version__=='3.0.1' and platform.machine() in ('armv7l','armv7')
        runtime=json.loads((root/'runtime_contract.json').read_text())
        actual={}
        for name,obj in [('Overlay',Overlay),('allocate',allocate)]:
            p=Path(inspect.getfile(obj));ref=runtime[name]
            assert p.stat().st_size==ref['bytes'] and sha(p)==ref['sha256'],('RUNTIME_SOURCE',name)
            actual[name]=dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
        transport.write(dest/'runtime_identity.json',dict(pynq=pynq.__version__,machine=platform.machine(),sources=actual))
        transport.write(dest/'boot_context.json',evidence_io.boot_context())
        overlay=call(ctx,'LOAD_METADATA',lambda:Overlay(str(root/'single_repair.bit'),download=False));ctx['overlay']=overlay
        assert overlay.ip_dict['repair_0']['type']=='xilinx.com:hls:valley_repair:1.0'
        call(ctx,'DOWNLOAD_NEW_OVERLAY',overlay.download)
        clock=call(ctx,'CLOCK_READBACK',lambda:require_refinement_clock(Clocks,overlay.clock_dict))
        transport.write(dest/'clock.json',clock);ip=overlay.repair_0
        records=[frame(ctx,root,'smoke',ip,allocate),frame(ctx,root,'native',ip,allocate)]
        summary=dict(status='BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW',records=records,model_inference_on_PS=False,
                     source='REAL_PYNQ_PL',software_quality='SINGLE_IMAGE_VISUAL_REVIEW_ONLY',LATENCY_TARGET='UNSET')
        transport.write(dest/'summary.json',summary);ctx['phase']='COMPLETE';return summary
    except BaseException as e:
        ctx['failed']=True;transport.write(dest/'FAULT.json',dict(phase=ctx['phase'],error=str(e),traceback=traceback.format_exc(),retained_buffers=len(ctx['buffers']),retry=False))
        raise
def export_results(path):
    if CONTEXT is None:raise RuntimeError('NO_SESSION')
    target=Path(path)
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(CONTEXT['dest'].rglob('*')):
            if p.is_file():z.write(p,p.relative_to(CONTEXT['dest']))
    return dict(zip=str(target),sha256=sha(target))

def render_saved(root,destination):
    """Read only a fully completed, persisted board result; no hardware imports."""
    root=Path(root);dest=Path(destination);verify(root)
    if (dest/'FAULT.json').exists():raise RuntimeError('FAILED_RUN_NOT_DISPLAYABLE_AS_SUCCESS')
    summary=json.loads((dest/'summary.json').read_text())
    assert summary['status']=='BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW' and summary['source']=='REAL_PYNQ_PL'
    rec=json.loads((dest/'native_record.json').read_text())
    p=dest/rec['actual']['path'];assert sha(p)==rec['actual']['sha256']
    actual=np.load(p,allow_pickle=False);expected=np.load(root/'native_expected.npy',allow_pickle=False)
    assert actual.dtype==expected.dtype==np.uint32 and actual.size==expected.size+32
    assert np.array_equal(actual[:expected.size],expected) and np.all(actual[expected.size:]==0xdeadbeef)
    words=np.load(root/'native_input.npy',allow_pickle=False);n=words.size
    old=((words>>25)&1)!=0;mask=(actual[5*n:6*n].reshape(words.shape)&1)!=0
    assert not np.any(old&~mask)
    rgb=np.stack([(words>>s).astype(np.uint8) for s in (16,8,0)],axis=-1)
    before=rgb.copy();before[old]=[0,255,0]
    final=rgb.copy();final[mask]=[0,255,0]
    colors=rgb.copy();colors[old]=[0,255,0];colors[mask&~old]=[0,255,255]
    from PIL import Image
    for name,a in [('native_real_PL_overlay',final),('native_real_PL_comparison',np.concatenate([rgb,before,colors],axis=1))]:
        with (dest/(name+'.png')).open('xb') as f:Image.fromarray(a).save(f,format='PNG')
    return dest/'native_real_PL_comparison.png'
