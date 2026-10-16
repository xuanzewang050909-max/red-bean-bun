"""Same-overlay B validation with unchanged official PYNQ DMA/video drivers.

The A4 transfer/reference helpers remain byte-identical to the measured release.
Display submissions are not observations. Monotonic timings are host-visible
completed transactions, not PL cycle counts or measured display refresh rates.
"""
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from a0_dma_board_test import guarded_phase, sha256_file, wait_both_idle
from a1_point_board_test import notebook_code_hash
from a4_segmentation_board_test import transfer_a4, full_cases, make_pattern, segmentation_expected

REVISION='b_integration_r2_explicit_video_imports'
NOTEBOOK='b_integration_check.ipynb'
FIXED={'b_integration.bit','b_integration.hwh','b_integration_board_test.py',
    'a4_segmentation_board_test.py','a3_background_board_test.py','a2_gaussian_board_test.py',
    'a1_point_board_test.py','a0_dma_board_test.py','stare_im0001_256.npy','stare_im0001_512.npy','使用说明.txt'}


def require(value, message):
    if not value: raise RuntimeError(message)


def validate_b_package(directory, manifest):
    directory=Path(directory)
    require(manifest.get('revision')==REVISION and set(manifest.get('artifacts',{}))==FIXED|{NOTEBOOK},'Incomplete or wrong B release')
    for name in sorted(FIXED):
        require(sha256_file(directory/name)==manifest['artifacts'][name]['sha256'],'Package mismatch: '+name)
    contract=manifest.get('notebook_validation',{})
    code_hash=notebook_code_hash(json.loads((directory/NOTEBOOK).read_text(encoding='utf-8')))
    require(contract.get('algorithm')=='sha256-code-cells-v1' and contract.get('sha256')==code_hash,'Notebook code mismatch')
    return {'fixed_artifacts':'PASS_EXACT_SHA256','notebook_code':'PASS_CANONICAL_CODE_SHA256',
        'notebook_code_sha256':code_hash,'current_notebook_sha256':sha256_file(directory/NOTEBOOK),
        'original_notebook_sha256':manifest['artifacts'][NOTEBOOK]['sha256']}


def assert_loaded(context):
    require(context['report'].get('overlay_downloads')==1 and context['overlay'].is_loaded(),
        'B must remain loaded once; another notebook changed the FPGA')


def phase(context, name, action):
    try: guarded_phase(context,name,action)
    except BaseException:
        context['report']['retained_display_frames']=len(context.get('display_retained',[]))
        context['save'](); raise


def prepare_b(directory, retained):
    import pynq
    from pynq import Overlay,allocate
    from pynq.lib import DMA,AxiGPIO
    # Import registers the original hierarchy and IP drivers, before Overlay.
    from pynq.lib.video.common import VideoMode,PIXEL_BGR
    from pynq.lib.video.dma import AxiVDMA
    from pynq.lib.video.hierarchies import VideoOut,HDMIWrapper
    require(pynq.__version__=='3.0.1' and platform.machine() in ('armv7l','armv7'),'Use measured PYNQ-Z2 3.0.1')
    require(not retained,'Earlier in-flight buffers remain')
    directory=Path(directory).resolve(); output=directory/'b_integration_result.json'
    require(not output.exists(),'Use a new B folder; preserve earlier result')
    manifest=json.loads((directory/'b_manifest.json').read_text(encoding='utf-8'))
    validation=validate_b_package(directory,manifest)
    overlay=Overlay(str(directory/'b_integration.bit'),download=False)
    for name,expected in manifest['control_addresses'].items():
        require(overlay.ip_dict[name]['phys_addr']==int(expected,0),'Wrong IP address: '+name)
    for name,contract in manifest['driver_metadata'].items():
        description=overlay.ip_dict[name]
        require(description['type']==contract['type'],'Wrong IP type: '+name)
        for key,value in contract['parameters'].items():
            require(description['parameters'][key]==value,'Wrong IP parameter: '+name+'/'+key)
    require(not overlay.ip_dict['axi_dma_0']['interrupts'],'Algorithm DMA must use bounded polling')
    require({'mm2s_introut','s2mm_introut'}<=overlay.ip_dict['video/axi_vdma']['interrupts'].keys(),'Lost official VDMA interrupts')
    report={'status':'B_PRECHECK_FPGA_UNCHANGED','manifest':manifest,'package_validation':validation,
        'pynq':pynq.__version__,'python':platform.python_version(),'kernel':platform.release(),
        'board_clock_utc_unverified':datetime.now(timezone.utc).isoformat(),'transfers':[],
        'overlay_downloads':0,'display':{'visual_status':'PENDING_USER_OBSERVATION','submissions':[]},
        'scope':'Frozen M0 algorithm A and official HDMI in one bitstream; digital comparisons and measured host-visible timings; visual confirmation and clinical quality separate'}
    def save():
        tmp=output.with_suffix('.json.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');tmp.replace(output)
    save();print('B_PRECHECK_PASS: matched package and metadata; FPGA unchanged',flush=True)
    return {'directory':directory,'overlay':overlay,'allocate':allocate,'dma_class':DMA,'gpio_class':AxiGPIO,
        'video_class':HDMIWrapper,'video_out_class':VideoOut,'vdma_class':AxiVDMA,'video_mode_class':VideoMode,
        'pixel_bgr':PIXEL_BGR,'retained':retained,'display_retained':[],'report':report,'save':save}


def load_b(context):
    require(context['report']['status']=='B_PRECHECK_FPGA_UNCHANGED','Precheck once before load')
    def action():
        context['overlay'].download();context['report']['overlay_downloads']+=1;context['save']()
        dma=context['overlay'].axi_dma_0;gpio=context['overlay'].point_control;video=context['overlay'].video
        require(isinstance(dma,context['dma_class']) and isinstance(gpio,context['gpio_class']),'Official DMA/GPIO did not bind')
        require(isinstance(video,context['video_class']) and isinstance(video.hdmi_out,context['video_out_class']) and isinstance(video.axi_vdma,context['vdma_class']),'Official HDMI hierarchy/VDMA did not bind')
        context.update(dma=dma,gpio=gpio,video=video,hdmi_out=video.hdmi_out)
        gpio.channel1.setdirection('out');gpio.channel2.setdirection('in')
        require(gpio.channel2.read()==0,'Algorithm state did not reset')
        assert_loaded(context)
        context['report']['drivers']={name:type(obj).__module__+'.'+type(obj).__name__ for name,obj in {'dma':dma,'gpio':gpio,'video':video,'hdmi_out':video.hdmi_out,'vdma':video.axi_vdma}.items()}
        context['report']['status']='B_LOADED_NO_TRANSFER';context['save']()
        print('B_LOAD_PASS: one B overlay; original DMA/GPIO/HDMI/VDMA drivers',flush=True)
    phase(context,'B_LOADING_AND_BINDING_OFFICIAL_DRIVERS',action)


def smoke_b(context):
    require(context['report']['status']=='B_LOADED_NO_TRANSFER','Load before short test')
    def action():
        assert_loaded(context);transfer_a4(context,256,3,'vessel_stripes')
        context['report']['status']='B_DMA_SMOKE_PASS';context['save']()
        print('B_DMA_SMOKE_PASS: full segmentation frame matched; HDMI not started yet',flush=True)
    phase(context,'B_DMA_SMOKE_RUNNING',action)


def video_status(context):
    status={'mm2s':int(context['video'].axi_vdma.mmio.read(0x04)),
            's2mm':int(context['video'].axi_vdma.mmio.read(0x34))}
    require(not status['mm2s']&0x70,'Video MM2S internal/slave/decode error: '+str(status))
    require(context['video'].axi_vdma.writechannel.running,'Video output unexpectedly stopped')
    return status


def submit(context, image, label, record=True):
    require(image.shape==(720,1280,3) and image.dtype==np.uint8,'Expected 720p BGR24')
    frame=context['hdmi_out'].newframe();context['display_retained'].append(frame)
    require(frame.shape==image.shape and frame.dtype==image.dtype and frame.strides==(3840,3,1),'Wrong official display frame layout')
    require(frame.physical_address%8==0 and 0x100000<=frame.physical_address<=0x20000000-frame.nbytes,'Invalid video DDR frame')
    frame[:]=image
    context['hdmi_out'].writeframe(frame)
    # Ownership belongs to the original VDMA driver after successful writeframe.
    # Do not free or reuse this frame. On failure retain its Python reference.
    require(context['display_retained'].pop() is frame,'Display ownership ledger changed')
    status=video_status(context)
    if record:
        context['report']['display']['submissions'].append({'label':label,'sha256_bgr':hashlib.sha256(image.tobytes()).hexdigest(),'vdma_status':status})
    return status


def color_pattern():
    image=np.zeros((720,1280,3),dtype=np.uint8)
    image[:,:426]=[255,0,0];image[:,426:853]=[0,255,0];image[:,853:]=[0,0,255]
    image[:4]=255;image[-4:]=255;image[:,:4]=255;image[:,-4:]=255
    image[358:362]=255;image[:,638:642]=255
    return image


def start_hdmi_b(context):
    require(context['report']['status']=='B_DMA_SMOKE_PASS','Short algorithm test first')
    def action():
        assert_loaded(context)
        mode=context['video_mode_class'](1280,720,24,60)
        context['hdmi_out'].configure(mode,context['pixel_bgr']);context['hdmi_out'].start()
        image=color_pattern();submit(context,image,'BLUE_GREEN_RED_WITH_POSITION_LINES')
        from PIL import Image
        path=context['directory']/'b_color_pattern.png';Image.fromarray(image[:,:,::-1]).save(path)
        context['report']['display'].update(configured_mode={'width':1280,'height':720,'bpp':24,'requested_hz':60,'format':'BGR24'},color_reference={'name':path.name,'sha256':sha256_file(path)})
        context['report']['status']='B_COLOR_SUBMITTED';context['save']()
        print('B_COLOR_SUBMITTED: monitor should show BLUE | GREEN | RED, white border and cross; observation pending',flush=True)
    phase(context,'B_STARTING_OFFICIAL_HDMI',action)


def full_b(context):
    require(context['report']['status']=='B_COLOR_SUBMITTED','Start HDMI and observe color pattern before full test')
    def action():
        assert_loaded(context);video_status(context)
        for case in full_cases(): transfer_a4(context,*case)
        video_status(context);assert_loaded(context)
        context['report']['status']='B_61_SEGMENTATION_FRAMES_WITH_HDMI_RUNNING';context['save']()
        print('B_ALGORITHM_PASS: 61 complete frames matched while same-overlay HDMI running',flush=True)
    phase(context,'B_VERIFYING_ALGORITHM_WITH_HDMI_RUNNING',action)


def medical_canvas(output, index=0):
    require(output.shape==(512,512) and output.dtype==np.uint32,'Expected real 512x512 packed algorithm output')
    green=(output&255).astype(np.uint8);mask=((output>>16)&255).astype(np.uint8)
    require(np.all((mask==0)|(mask==255)),'Mask must remain binary')
    grey=np.repeat(green[:,:,None],3,axis=2);marked=grey.copy();marked[mask!=0]=[0,255,0]
    # PS layout only. Both panels derive directly from the actual FPGA output.
    image=np.full((720,1280,3),16,dtype=np.uint8)
    image[128:640,64:576]=grey;image[128:640,704:1216]=marked
    from PIL import Image,ImageDraw
    canvas=Image.fromarray(image[:,:,::-1]);draw=ImageDraw.Draw(canvas)
    draw.text((64,80),'RAW GREEN - FPGA OUTPUT',fill='white')
    draw.text((704,80),'FPGA VESSEL CANDIDATES - GREEN',fill='white')
    draw.text((64,665),'B: ONE OVERLAY / 512 x 512 / FIXED M0 ALGORITHM A',fill='white')
    image=np.asarray(canvas)[:,:,::-1].copy()
    x=16+(int(index)%100)*12;image[24:48,x:x+48]=255
    return image


def display_medical_b(context):
    require(context['report']['status']=='B_61_SEGMENTATION_FRAMES_WITH_HDMI_RUNNING','Complete digital suite first')
    def action():
        assert_loaded(context)
        path=context['directory']/'a4_output_stare_512_mode3.npy'
        actual=np.load(path,allow_pickle=False);source=make_pattern(512,'stare',0,context['directory'])
        require(np.array_equal(actual,segmentation_expected(source,3)),'Saved FPGA image changed')
        image=medical_canvas(actual);submit(context,image,'RAW_GREEN_AND_FPGA_MASK_OVERLAY')
        from PIL import Image
        from IPython.display import display
        preview=context['directory']/'b_medical_display.png';canvas=Image.fromarray(image[:,:,::-1]);canvas.save(preview);display(canvas)
        context['report']['display']['medical_reference']={'name':preview.name,'sha256':sha256_file(preview),'actual_output_name':path.name,'actual_output_sha256':sha256_file(path)}
        context['report']['status']='B_MEDICAL_DISPLAY_SUBMITTED';context['save']()
        print('B_MEDICAL_DISPLAY_SUBMITTED: left raw green; right same image with green FPGA candidates; photograph monitor',flush=True)
    phase(context,'B_COMPOSING_ACTUAL_FPGA_RESULT',action)


def timing_summary(durations_ns):
    samples=np.asarray(durations_ns,dtype=np.float64)/1e9
    require(samples.size>0 and np.all(np.isfinite(samples)) and np.all(samples>0),'Invalid monotonic timing samples')
    return {'count':int(samples.size),'sum_seconds':float(samples.sum()),'frames_per_sum_transaction_seconds':float(samples.size/samples.sum()),
        'mean_ms':float(samples.mean()*1000),'median_ms':float(np.median(samples)*1000),'p95_ms':float(np.percentile(samples,95)*1000)}


def measure_group(context,side,with_display,count=100,warmup=3):
    require(side in (256,512) and (not with_display or side==512) and count==100 and warmup==3,'Fixed B benchmark contract')
    assert_loaded(context);video_status(context)
    source=make_pattern(side,'stare',0,context['directory']);expected=segmentation_expected(source,3).reshape(-1)
    words=side*side;nbytes=words*4
    context['gpio'].channel1.write(3|(4 if side==256 else 0),0xffffffff)
    tx=context['allocate'](shape=(words,),dtype=np.uint32);context['retained'].append(tx)
    rx=context['allocate'](shape=(words,),dtype=np.uint32);context['retained'].append(rx)
    for buffer in (tx,rx):require(buffer.physical_address%8==0 and 0x100000<=buffer.physical_address<=0x20000000-nbytes,'Invalid algorithm DDR allocation')
    require(abs(tx.physical_address-rx.physical_address)>=nbytes,'Algorithm buffers overlap')
    tx[:]=source.reshape(-1);rx[:]=np.bitwise_not(expected);rx.flush()
    input_hash=hashlib.sha256(source.tobytes()).hexdigest();expected_hash=hashlib.sha256(expected.tobytes()).hexdigest()
    samples=[];loop_start=None;loop_end=None
    for index in range(warmup+count):
        if index==warmup:loop_start=time.perf_counter_ns()
        start=time.perf_counter_ns()
        context['dma'].recvchannel.transfer(rx);context['dma'].sendchannel.transfer(tx)
        statuses=wait_both_idle(context['dma']);context['dma'].sendchannel.wait();context['dma'].recvchannel.wait()
        dma_done=time.perf_counter_ns()
        require(context['dma'].sendchannel.transferred==nbytes and context['dma'].recvchannel.transferred==nbytes,'Benchmark byte count mismatch')
        require(np.array_equal(rx,expected),'Benchmark FPGA result mismatch')
        frame_status=int(context['gpio'].channel2.read());frames=(len(context['report']['transfers'])+1)&0x3fff
        require(frame_status==frames|(frames<<14),'Benchmark frame count/error mismatch')
        if with_display:
            image=medical_canvas(np.asarray(rx).reshape(side,side),index-warmup)
            status=submit(context,image,'BENCHMARK_FRAME',record=False)
            done=time.perf_counter_ns()
        else: status=video_status(context);done=dma_done
        record={'side':side,'mode':3,'pattern':'stare','words':words,'send_bytes':nbytes,'recv_bytes':nbytes,
            'tx_address':int(tx.physical_address),'rx_address':int(rx.physical_address),'dma_status':statuses,
            'frame_status':frame_status,'status':'PASS_EXACT_SEGMENTATION_WORDS','input_sha256':input_hash,
            'expected_sha256':expected_hash,'output_sha256':hashlib.sha256(np.asarray(rx).tobytes()).hexdigest(),
            'benchmark':{'warmup':index<warmup,'with_display':with_display,'sample_ns':done-start,'dma_ns':dma_done-start,'vdma_status':status}}
        context['report']['transfers'].append(record)
        if index>=warmup:samples.append(done-start)
        if index==warmup+count-1:loop_end=time.perf_counter_ns()
        if (index-warmup+1)>0 and (index-warmup+1)%20==0:print(f'B_TIMING_PROGRESS: {side}, display={with_display}, {index-warmup+1}/100',flush=True)
    rx.freebuffer();tx.freebuffer();context['retained'].clear();assert_loaded(context)
    summary=timing_summary(samples)
    clock=time.get_clock_info('perf_counter')
    require(clock.monotonic and loop_end>loop_start,'Timing clock must be monotonic and advance')
    summary.update(side=side,with_display=with_display,warmup=warmup,samples_ns=samples,
        loop_seconds=(loop_end-loop_start)/1e9,loop_fps=count/((loop_end-loop_start)/1e9),
        clock={'name':'perf_counter_ns','monotonic':clock.monotonic,'resolution_seconds':clock.resolution,'implementation':clock.implementation},
        meaning=('Completed DMA + word verification + PS layout + official newframe/writeframe submission' if with_display else 'Completed official DMA send/receive with cache operations and original 1 ms idle polling'),
        loop_includes='All per-frame checks, status reads, hashes, record construction and periodic progress printing; excludes allocation/golden generation/warmup/final JSON write',
        display_refresh_measurement='NOT_MEASURED; requested 720p60 is a configuration, not algorithm FPS')
    return summary


def performance_b(context):
    require(context['report']['status']=='B_MEDICAL_DISPLAY_SUBMITTED','Display actual result first')
    def action():
        measurements=[]
        for side,display in ((256,False),(512,False),(512,True)):
            result=measure_group(context,side,display);measurements.append(result)
            context['report']['performance']=measurements;context['save']()
            print(f"B_MEASURED: {side}, display={display}, transactions={result['frames_per_sum_transaction_seconds']:.3f} fps, complete_loop={result['loop_fps']:.3f} fps",flush=True)
        require(len(context['report']['transfers'])==370,'Incomplete B frame ledger')
        context['report']['status']='B_DIGITAL_AND_TIMING_COMPLETE_VISUAL_PENDING';context['save']()
        print('B_TIMING_COMPLETE: 61 validation + 309 benchmark frames matched; visual confirmation pending',flush=True)
    phase(context,'B_MEASURING_REAL_TRANSACTIONS',action)
    return context['report']


def finish_b(context):
    require(context['report']['status']=='B_DIGITAL_AND_TIMING_COMPLETE_VISUAL_PENDING','Finish measurements first')
    directory=context['directory'];bundle=directory/'b_results_bundle.zip'
    require(not bundle.exists(),'Bundle exists; preserve it')
    def action():
        assert_loaded(context);context['report']['display']['final_vdma_status']=video_status(context)
        context['hdmi_out'].close()
        context['report']['display']['closed']=True;context['report']['status']='B_RECORDS_READY_VISUAL_REVIEW_PENDING';context['save']()
        from zipfile import ZipFile,ZIP_DEFLATED
        names=['b_integration_result.json','b_color_pattern.png','b_medical_display.png']
        names+=sorted({r['saved_output']['name'] for r in context['report']['transfers'] if 'saved_output' in r})
        with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
            for name in names:archive.write(directory/name,arcname=name)
        print('B_RESULTS_READY: download b_results_bundle.zip and executed notebook; monitor observations archived separately',flush=True)
    phase(context,'B_CLOSING_OFFICIAL_DISPLAY_AND_PACKAGING',action)
