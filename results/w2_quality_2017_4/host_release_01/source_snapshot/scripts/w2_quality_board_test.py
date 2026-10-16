"""W2/Q2 real-board staged validation. Reference arrays ONLY compare, never display.

Official PYNQ DMA/allocate/GPIO; no CPU segmentation, no HDMI, no auto recovery.
Only successful, completed DMA snapshots are eligible for result visualization.
"""
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from a0_dma_board_test import guarded_phase, sha256_file, wait_both_idle
from a1_point_board_test import notebook_code_hash
from quality_observer import QualityObserver, check_observer_metadata, control_word, require

REVISION = 'w2_q2_c2_observer_r1'
NOTEBOOK = 'w2_quality_check.ipynb'
FIXED = {'w2_quality.bit','w2_quality.hwh','w2_quality_board_test.py','quality_observer.py',
         'a0_dma_board_test.py','a1_point_board_test.py','w2_vectors.npz','w2_vectors.json','使用说明.txt'}


def array_sha(array):
    return hashlib.sha256(array.astype('<u4',copy=False).tobytes()).hexdigest()


def validate_package(directory, manifest):
    require(manifest.get('revision') == REVISION and set(manifest.get('artifacts',{})) == FIXED|{NOTEBOOK}, 'Wrong/incomplete W2 package')
    require(manifest.get('hardware_clock_hz') == 100_000_000, 'Missing paired hardware clock')
    for name in sorted(FIXED):
        require(sha256_file(directory/name) == manifest['artifacts'][name]['sha256'], 'Package mismatch: '+name)
    code_hash = notebook_code_hash(json.loads((directory/NOTEBOOK).read_text(encoding='utf-8')))
    require(manifest.get('notebook_validation') == {'algorithm':'sha256-code-cells-v1','sha256':code_hash}, 'Notebook code changed')
    # The running interpreter must not silently reuse old imported helpers.
    for name in sorted(n for n in FIXED if n.endswith('.py')):
        module = sys.modules.get(Path(name).stem)
        require(module is not None and Path(module.__file__).resolve() == (directory/name).resolve(), 'Stale imported module: '+name)
        require(sha256_file(module.__file__) == manifest['artifacts'][name]['sha256'], 'Imported file changed: '+name)
    return {'fixed_sha256':'PASS','notebook_code_sha256':code_hash,'executed_notebook_sha256':sha256_file(directory/NOTEBOOK)}


def prepare_w2(directory, retained):
    import pynq
    from pynq import Overlay, allocate, Clocks
    from pynq.lib import DMA, AxiGPIO
    require(pynq.__version__ == '3.0.1' and platform.machine() in ('armv7l','armv7'), 'Run on measured PYNQ-Z2 3.0.1')
    require(not retained, 'Earlier buffers remain; stop')
    directory = Path(directory).resolve()
    for name in ('w2_result.json','w2_results_bundle.zip','w2_actual_outputs'):
        require(not (directory/name).exists(), 'Use a fresh folder; preserve earlier results: '+name)
    manifest = json.loads((directory/'w2_manifest.json').read_text(encoding='utf-8'))
    validation = validate_package(directory,manifest)
    vectors = json.loads((directory/'w2_vectors.json').read_text(encoding='utf-8'))
    overlay = Overlay(str(directory/'w2_quality.bit'), download=False)
    dma = overlay.ip_dict['axi_dma_0']; gpio = overlay.ip_dict['point_control']
    require(dma['type']=='xilinx.com:ip:axi_dma:7.1' and dma['phys_addr']==0x40400000,'Wrong DMA mapping')
    expected = {'c_include_sg':0,'c_micro_dma':0,'c_sg_length_width':23,'c_m_axis_mm2s_tdata_width':32,
                'c_s_axis_s2mm_tdata_width':32,'c_m_axi_mm2s_data_width':64,'c_m_axi_s2mm_data_width':32}
    require(all(int(dma['parameters'][k])==v for k,v in expected.items()),'Wrong DMA parameters')
    require(gpio['type']=='xilinx.com:ip:axi_gpio:2.0' and gpio['phys_addr']==0x41200000,'Wrong control GPIO')
    expected_gpio = {'C_IS_DUAL':1,'C_GPIO_WIDTH':32,'C_GPIO2_WIDTH':32,'C_ALL_OUTPUTS':1,'C_ALL_INPUTS_2':1,'C_INTERRUPT_PRESENT':0}
    require(all(int(gpio['parameters'][k])==v for k,v in expected_gpio.items()),'Wrong control GPIO parameters')
    check_observer_metadata(overlay.ip_dict['point_observe'])
    report = dict(status='W2_PRECHECK_FPGA_UNCHANGED',revision=REVISION,manifest=manifest,validation=validation,
                  pynq=pynq.__version__,python=platform.python_version(),kernel=platform.release(),
                  board_clock_utc_unverified=datetime.now(timezone.utc).isoformat(),transfers=[],
                  scope='W2/Q2 exact PL output and hardware observers; not full dataset quality, browser FPS or stability acceptance')
    def save():
        temp = directory/'w2_result.json.tmp'
        temp.write_text(json.dumps(report,indent=2),encoding='utf-8'); temp.replace(directory/'w2_result.json')
    save()
    print('W2_PRECHECK_PASS: paired files and official metadata; FPGA unchanged',flush=True)
    return dict(directory=directory,overlay=overlay,allocate=allocate,dma_class=DMA,gpio_class=AxiGPIO,
                report=report,save=save,retained=retained,vectors=vectors,clocks=Clocks)


def load_w2(context):
    require(context['report']['status']=='W2_PRECHECK_FPGA_UNCHANGED','Precheck must pass first')
    def action():
        overlay = context['overlay']; overlay.download()
        clock_mhz=float(context['clocks'].fclk0_mhz)
        require(abs(clock_mhz-100.0)<0.000001,'Actual FCLK0 register readback is not 100 MHz')
        context['report']['runtime_fclk0_mhz_register_readback']=clock_mhz
        dma,gpio,observe = overlay.axi_dma_0,overlay.point_control,overlay.point_observe
        require(isinstance(dma,context['dma_class']) and all(isinstance(g,context['gpio_class']) for g in (gpio,observe)),'Official drivers did not bind')
        gpio.channel1.setdirection('out'); gpio.channel2.setdirection('in')
        require(gpio.channel2.read()==0,'Native frame state not reset')
        observer = QualityObserver(observe,verified_clock_hz=context['report']['manifest']['hardware_clock_hz'])
        require(observer.read_word(1)==0 and observer.read_word(4)==0 and observer.read_word(11)==0,'Observer not reset')
        context.update(dma=dma,gpio=gpio,observer=observer)
        context['report'].update(status='W2_LOADED_NO_TRANSFER',drivers={n:type(o).__module__+'.'+type(o).__name__ for n,o in [('dma',dma),('control',gpio),('observer',observe)]})
        context['save'](); print('W2_LOAD_PASS: single overlay, official drivers, observer identity/reset',flush=True)
    guarded_phase(context,'W2_PROGRAMMING',action)


def transfer_case(context, case):
    index = len(context['report']['transfers'])
    require(case['index']==index and not context['retained'],'Unexpected sequence or retained buffer')
    with np.load(context['directory']/'w2_vectors.npz',allow_pickle=False) as archive:
        source=archive[case['input_key']]; expected=archive[case['expected_key']]
    shape=(case['side'],case['side'])
    require(source.dtype==np.uint32 and expected.dtype==np.uint32 and source.shape==shape and expected.shape==shape,'Wrong vector layout')
    require(array_sha(source)==case['input_sha256'] and array_sha(expected)==case['expected_sha256'],'Vector digest mismatch')
    cfg=control_word(side=case['side'],stage=case['stage'],algorithm=case['algorithm'],threshold=case['threshold'],tag=index+1)
    require(cfg==case['control'] and case['words']==source.size,'Vector control mismatch')
    count=source.size; nbytes=count*4
    tx=context['allocate'](shape=(count,),dtype=np.uint32); context['retained'].append(tx)
    rx=context['allocate'](shape=(count,),dtype=np.uint32); context['retained'].append(rx)
    for buf in (tx,rx):
        require(buf.physical_address%8==0 and 0x100000<=buf.physical_address<=0x20000000-nbytes,'Invalid DDR buffer')
    require(abs(tx.physical_address-rx.physical_address)>=nbytes,'DDR buffers overlap')
    tx[:]=source.reshape(-1); rx[:]=np.bitwise_not(expected.reshape(-1)); rx.flush()
    context['report']['active_case']=case; context['save']()
    dma=context['dma']; observer=context['observer']
    require(observer.read_word(4)==index and observer.read_word(1)==(0 if index==0 else 2),'Prior frame observer mismatch')
    start=time.perf_counter_ns()
    context['gpio'].channel1.write(cfg,0xffffffff)
    dma_start=time.perf_counter_ns()
    dma.recvchannel.transfer(rx); dma.sendchannel.transfer(tx)
    statuses=wait_both_idle(dma); dma.sendchannel.wait(); dma.recvchannel.wait()
    dma_end=time.perf_counter_ns()
    require(dma.sendchannel.transferred==nbytes and dma.recvchannel.transferred==nbytes,'DMA byte count mismatch')
    actual=np.array(rx,dtype=np.uint32,copy=True).reshape(shape)
    snapshot_end=time.perf_counter_ns()
    hardware=observer.completed(expected_control=cfg,previous_sequence=index,expected_words=count)
    require(np.array_equal(actual,expected),'Actual PL output differs from independent reference')
    native=int(context['gpio'].channel2.read()); frame=(index+1)&0x3fff
    require(native==frame|(frame<<14),'Native error/frame state mismatch')
    outdir=context['directory']/'w2_actual_outputs'; outdir.mkdir(exist_ok=True)
    name=f'w2_actual_outputs/frame_{index:03d}.npy'
    np.save(context['directory']/name,actual,allow_pickle=False)
    record=dict(case,send_bytes=int(dma.sendchannel.transferred),recv_bytes=int(dma.recvchannel.transferred),
                dma_status=statuses,native_status=native,hardware=hardware,status='PASS_EXACT_REAL_DMA_WORDS',
                output_sha256=array_sha(actual),saved_output=dict(name=name,sha256=sha256_file(context['directory']/name)),
                tx_address=int(tx.physical_address),rx_address=int(rx.physical_address),
                timing_ns=dict(config_start=start,dma_start=dma_start,dma_end=dma_end,snapshot_end=snapshot_end,
                               dma_transaction=dma_end-dma_start,full_inference=snapshot_end-start,snapshot=snapshot_end-dma_end),
                timing_scope='Diagnostic config to DMA completion and CPU snapshot; input IO/allocation/comparison/export excluded; DMA overlaps PL; not browser FPS')
    context['report']['transfers'].append(record); context['report'].pop('active_case'); context['save']()
    rx.freebuffer(); tx.freebuffer(); context['retained'].clear()
    print(f"W2_FRAME_PASS: {index+1}/{len(context['vectors']['cases'])} {case['side']} {case['algorithm']} T={case['threshold']} stage={case['stage']} {case['pattern']}",flush=True)


def smoke_w2(context):
    require(context['report']['status']=='W2_LOADED_NO_TRANSFER','Load once before smoke')
    def action():
        transfer_case(context,context['vectors']['cases'][0])
        context['report']['status']='W2_SMOKE_PASSED'; context['save']()
        print('W2_SMOKE_PASS: one complete 256 frame and hardware cycle/parameter snapshot matched',flush=True)
    guarded_phase(context,'W2_SMOKE_RUNNING',action)


def baseline_w2(context):
    require(context['report']['status']=='W2_SMOKE_PASSED','Smoke first')
    def action():
        for case in context['vectors']['cases'][1:61]: transfer_case(context,case)
        context['report']['status']='W2_BASELINE_PASSED'; context['save']()
        print('W2_BASELINE_PASS: all original 61 A4 cases reproduced on new PL',flush=True)
    guarded_phase(context,'W2_BASELINE_RUNNING',action)


def candidate_w2(context):
    require(context['report']['status']=='W2_BASELINE_PASSED','Baseline first')
    def action():
        for case in context['vectors']['cases'][61:]: transfer_case(context,case)
        context['report']['status']='W2_CANDIDATE_PASSED'; context['save']()
        print('W2_CANDIDATE_PASS: C2/A switches, real thresholds and all exact output words matched',flush=True)
    guarded_phase(context,'W2_CANDIDATE_RUNNING',action)


def finish_w2(context):
    require(context['report']['status']=='W2_CANDIDATE_PASSED' and not context['retained'],'Complete all frames first')
    require(len(context['report']['transfers'])==len(context['vectors']['cases']),'Incomplete frame suite')
    directory=context['directory']; bundle=directory/'w2_results_bundle.zip'
    require(not bundle.exists(),'Preserve existing bundle; do not rerun')
    from PIL import Image,ImageDraw
    from IPython.display import display
    from zipfile import ZipFile,ZIP_DEFLATED
    chosen=[]
    for algorithm in ('A','C2'):
        records=[r for r in context['report']['transfers'] if (r['side'],r['stage'],r['algorithm'],r['threshold'],r['pattern'])==(512,3,algorithm,28,'stare')]
        record=records[-1]; path=directory/record['saved_output']['name']
        require(sha256_file(path)==record['saved_output']['sha256'],'Actual DMA file changed')
        actual=np.load(path,allow_pickle=False)
        require(array_sha(actual)==record['output_sha256'],'Actual DMA pixel digest changed')
        chosen.append((record,actual))
    require(chosen[0][0]['input_sha256']==chosen[1][0]['input_sha256'],'Comparison inputs differ')
    canvas=Image.new('RGB',(1024,560),'white'); draw=ImageDraw.Draw(canvas)
    for row,(record,actual) in enumerate(chosen):
        green=(actual&255).astype(np.uint8); enhanced=((actual>>8)&255).astype(np.uint8)
        mask=((actual>>16)&255).astype(np.uint8)
        overlay=np.repeat(green[:,:,None],3,axis=2); overlay[mask!=0]=[0,255,0]
        for col,(label,arr) in enumerate((('Raw green',green),('PL enhanced',enhanced),('PL mask',mask),('PL overlay',overlay))):
            canvas.paste(Image.fromarray(arr).resize((256,256),resample=Image.NEAREST),(col*256,row*280+24))
            draw.text((col*256+4,row*280+5),record['algorithm']+' / '+label,fill='black')
    preview=directory/'w2_actual_comparison.png'; canvas.save(preview); display(canvas)
    context['report'].update(status='W2_BOARD_EXACT_OUTPUT_COMPLETE_Q3_PENDING',preview=dict(name=preview.name,sha256=sha256_file(preview)),
                             preview_frames=[r['index'] for r,_ in chosen],retained_buffers=0,
                             quality_status='NOT_FULL_DATASET_EVALUATED',browser_fps=None,pure_dma_transport_ns=None)
    context['save']()
    names=['w2_result.json',preview.name]+[r['saved_output']['name'] for r in context['report']['transfers']]
    with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
        for name in names: archive.write(directory/name,arcname=name)
    print('W2_RESULTS_READY: download w2_results_bundle.zip and the executed notebook',flush=True)
