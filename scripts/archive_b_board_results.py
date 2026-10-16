"""Independently verify B downloads; never execute notebook cells or alter raw evidence."""
import argparse
import base64
import io
import json
import math
import re
import stat
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZIP_STORED,ZipFile

import numpy as np
from PIL import Image

from archive_a4_board_results import require,digest,word_digest,recorded_cases,regenerate_input,independent_expected,write_json
from a1_point_board_test import notebook_code_hash
from b_integration_board_test import validate_b_package

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'results/b_integration_2017_4_r2/release_manifest.json'
ARRAY_NAMES={f'a4_output_stare_{side}_mode{mode}.npy' for side in (256,512) for mode in (1,2,3)}
BUNDLE_NAMES=ARRAY_NAMES|{'b_integration_result.json','b_color_pattern.png','b_medical_display.png'}
GROUPS=((256,False),(512,False),(512,True))


def flatten_text(value):
    # This Jupyter download nests some stream text lists. Read without editing.
    if isinstance(value,str):return value
    require(isinstance(value,list),'Unexpected notebook text value')
    return ''.join(flatten_text(v) for v in value)


def read_bundle(path):
    require(path.stat().st_size<=8_000_000,'Result ZIP exceeds size limit')
    with ZipFile(path) as archive:
        entries=archive.infolist()
        require(len(entries)==len(BUNDLE_NAMES) and {e.filename for e in entries}==BUNDLE_NAMES,
            'Missing, duplicate or unexpected ZIP member')
        require(sum(e.file_size for e in entries)<=6_000_000,'Uncompressed ZIP exceeds evidence limit')
        for e in entries:
            require(not e.is_dir() and not e.flag_bits&1 and stat.S_IFMT(e.external_attr>>16)!=stat.S_IFLNK
                and e.compress_type in (ZIP_STORED,ZIP_DEFLATED),'Unsupported ZIP member')
            require(0<e.file_size<=(1_100_000 if e.filename in ARRAY_NAMES else 500_000),'Unexpected member size')
        return {e.filename:archive.read(e) for e in entries}


def video_status(status):
    require(set(status)=={'mm2s','s2mm'} and all(type(v)==int and v>=0 for v in status.values()),'Wrong VDMA status shape')
    require(not status['mm2s']&0x71,'Video output halted or has internal/slave/decode error')
    # Input channel remains present and idle; it was not started in this test.
    require(status['s2mm']&1 and not status['s2mm']&0x70,'Unexpected input VDMA activity/error')


def verify_notebook(notebook,report,manifest):
    require(notebook_code_hash(notebook)==manifest['notebook_validation']['sha256'],'Notebook code changed')
    cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    require(len(cells)==9 and [c['execution_count'] for c in cells]==list(range(1,10)),'Notebook execution sequence differs')
    require(all(o.get('output_type')!='error' for c in cells for o in c['outputs']),'Notebook error output')
    streams=[''.join(flatten_text(o.get('text','')) for o in c['outputs'] if o.get('output_type')=='stream') for c in cells]
    markers={1:'B_PRECHECK_PASS:',2:'B_LOAD_PASS:',3:'B_DMA_SMOKE_PASS:',4:'B_COLOR_SUBMITTED:',
        5:'B_ALGORITHM_PASS:',6:'B_MEDICAL_DISPLAY_SUBMITTED:',7:'B_TIMING_COMPLETE:',8:'B_RESULTS_READY:'}
    all_text=''.join(streams)
    for index,marker in markers.items():
        require(streams[index].count(marker)==1 and all_text.count(marker)==1,'Missing, duplicated or misplaced stage marker')
    lines=[line.strip() for s in streams for line in s.splitlines() if line.startswith('SEGMENTATION_FRAME_PASS:')]
    expected=[f'SEGMENTATION_FRAME_PASS: {i+1}/61 {side} mode {mode} {pattern}' for i,(side,mode,pattern) in enumerate(recorded_cases())]
    require(lines==expected and expected[0] in streams[3] and all(s in streams[5] for s in expected[1:]),'Notebook validation frame sequence differs')
    progress=[line.strip() for line in streams[7].splitlines() if line.startswith('B_TIMING_PROGRESS:')]
    require(progress==[f'B_TIMING_PROGRESS: {side}, display={display}, {count}/100'
        for side,display in GROUPS for count in (20,40,60,80,100)],'Benchmark progress sequence differs')
    validation=report['package_validation'];contract=manifest['notebook_validation']
    require(validation['fixed_artifacts']=='PASS_EXACT_SHA256' and validation['notebook_code']=='PASS_CANONICAL_CODE_SHA256'
        and validation['notebook_code_sha256']==contract['sha256']
        and validation['original_notebook_sha256']==manifest['artifacts']['b_integration_check.ipynb']['sha256']
        and re.fullmatch('[0-9a-f]{64}',validation['current_notebook_sha256']) is not None,'Board package validation differs')
    return cells,streams


def close_number(actual,expected,label):
    require(type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-10),
        'Timing metric mismatch: '+label)


def verify_timing(report,streams):
    require(len(report['performance'])==3,'Incomplete timing groups')
    verified=[]
    for i,((side,display),summary) in enumerate(zip(GROUPS,report['performance'])):
        require((summary['side'],summary['with_display'],summary['warmup'],summary['count'])==(side,display,3,100),'Timing group contract changed')
        clock=summary['clock']
        require(clock['name']=='perf_counter_ns' and clock['monotonic'] is True and clock['implementation']=='clock_gettime(CLOCK_MONOTONIC)'
            and type(clock['resolution_seconds']) in (int,float) and 0<clock['resolution_seconds']<=1e-6,'Unexpected timing clock')
        group=report['transfers'][61+103*i:61+103*(i+1)]
        samples=[];dma_samples=[]
        for index,record in enumerate(group):
            b=record['benchmark']
            require(type(b['warmup'])==bool and b['warmup']==(index<3) and type(b['with_display'])==bool and b['with_display']==display,'Wrong warmup/display ledger')
            require(type(b['sample_ns'])==int and type(b['dma_ns'])==int and 0<b['dma_ns']<=b['sample_ns'],'Invalid raw timing duration')
            require(display or b['sample_ns']==b['dma_ns'],'DMA-only timing includes an extra phase')
            video_status(b['vdma_status'])
            if index>=3:samples.append(b['sample_ns']);dma_samples.append(b['dma_ns'])
        require(len(samples)==100 and summary['samples_ns']==samples,'Reported samples differ from frame ledger')
        seconds=np.asarray(samples,dtype=np.float64)/1e9;total=float(seconds.sum())
        metrics={'sum_seconds':total,'frames_per_sum_transaction_seconds':100/total,'mean_ms':float(seconds.mean()*1000),
            'median_ms':float(np.median(seconds)*1000),'p95_ms':float(np.percentile(seconds,95)*1000)}
        for name,value in metrics.items():close_number(summary[name],value,name)
        require(type(summary['loop_seconds']) in (int,float) and math.isfinite(summary['loop_seconds'])
            and summary['loop_seconds']>=total,'Invalid full loop duration')
        close_number(summary['loop_fps'],100/summary['loop_seconds'],'loop_fps')
        require(summary['display_refresh_measurement']=='NOT_MEASURED; requested 720p60 is a configuration, not algorithm FPS','Display refresh conflated with algorithm FPS')
        line=f"B_MEASURED: {side}, display={display}, transactions={metrics['frames_per_sum_transaction_seconds']:.3f} fps, complete_loop={summary['loop_fps']:.3f} fps"
        require(streams[7].count(line)==1,'Notebook timing numbers differ')
        require(len({r['tx_address'] for r in group})==len({r['rx_address'] for r in group})==1,'Benchmark allocation reuse differs')
        verified.append({**metrics,'side':side,'with_display':display,'timed_frames':100,'warmup_frames':3,
            'dma_mean_ms':sum(dma_samples)/1e8,'loop_seconds':summary['loop_seconds'],'loop_fps':summary['loop_fps'],
            'status':'PASS_RAW_NS_SAMPLES_AND_NOTEBOOK_METRICS_RECOMPUTED',
            'limits':'Individual transaction durations independently recomputed from frame ledger. Loop seconds are the original aggregate; start/end timestamps were not retained, so only its formula and Notebook agreement are checked. Display Hz and pure PL cycles not measured.'})
    return verified


def decode_png(data):
    with Image.open(io.BytesIO(data)) as image:
        require(image.format=='PNG' and image.mode=='RGB' and image.size==(1280,720),'Unexpected display PNG format')
        return np.asarray(image).copy()


def verify_display(cells,report,members,outputs):
    display=report['display']
    require(display['visual_status']=='PENDING_USER_OBSERVATION' and display['closed'] is True,'Original display record altered/not closed')
    require(display['configured_mode']=={'width':1280,'height':720,'bpp':24,'requested_hz':60,'format':'BGR24'},'Wrong video mode')
    submissions=display['submissions']
    require(len(submissions)==2 and [s['label'] for s in submissions]==['BLUE_GREEN_RED_WITH_POSITION_LINES','RAW_GREEN_AND_FPGA_MASK_OVERLAY'],'Wrong displayed frame sequence')
    for s in submissions:video_status(s['vdma_status'])
    video_status(display['final_vdma_status'])
    colors=decode_png(members['b_color_pattern.png'])
    expected=np.empty_like(colors);expected[:,:426]=[0,0,255];expected[:,426:853]=[0,255,0];expected[:,853:]=[255,0,0]
    expected[:4]=255;expected[-4:]=255;expected[:,:4]=255;expected[:,-4:]=255
    expected[358:362]=255;expected[:,638:642]=255
    require(np.array_equal(colors,expected),'Color order/border/cross pixels differ')
    require(display['color_reference']=={'name':'b_color_pattern.png','sha256':digest(members['b_color_pattern.png'])},'Color PNG hash differs')
    medical=decode_png(members['b_medical_display.png']);words=outputs[(512,3)]
    green=(words&255).astype(np.uint8);mask=((words>>16)&255).astype(np.uint8)
    grey=np.repeat(green[:,:,None],3,axis=2);marked=grey.copy();marked[mask!=0]=[0,255,0]
    base=np.full_like(medical,16);base[128:640,64:576]=grey;base[128:640,704:1216]=marked;base[24:48,16:64]=255
    compare=np.ones((720,1280),bool)
    # Platform fonts differ; captions are visually checked in the user photo.
    compare[76:110,60:690]=False;compare[76:110,700:1270]=False;compare[660:700,60:1270]=False
    require(np.array_equal(medical[compare],base[compare]),'Medical display pixels differ from real raw FPGA outputs')
    raw_name='a4_output_stare_512_mode3.npy'
    require(display['medical_reference']=={'name':'b_medical_display.png','sha256':digest(members['b_medical_display.png']),
        'actual_output_name':raw_name,'actual_output_sha256':digest(members[raw_name])},'Medical image provenance differs')
    for submission,pixels in zip(submissions,(colors,medical)):
        require(submission['sha256_bgr']==digest(pixels[:,:,::-1].tobytes()),'Submitted BGR framebuffer differs from PNG')
    embedded=[o['data']['image/png'] for o in cells[6]['outputs'] if o['output_type']=='display_data' and 'image/png' in o.get('data',{})]
    require(len(embedded)==1,'Unique medical notebook image missing')
    decoded=base64.b64decode(''.join(flatten_text(embedded[0]).split()),validate=True)
    require(np.array_equal(decode_png(decoded),medical),'Notebook image differs from result PNG')
    return {'status':'PASS_COLOR_PIXELS_MEDICAL_RAW_ARRAY_PANES_AND_NOTEBOOK_IMAGE',
        'color_png_sha256':digest(members['b_color_pattern.png']),'medical_png_sha256':digest(members['b_medical_display.png']),
        'display_size':[1280,720],'algorithm_panel_size':[512,512],
        'limit':'PNG and submitted-byte consistency is numerical; physical display observation comes from two user photographs, not from submission status. Font regions excluded only from independent layout regeneration; entire notebook/PNG pixels match.'}


def verify_records(notebook,report,manifest,package,members):
    require(report['manifest']==manifest,'Different release manifest')
    require(report['status']=='B_RECORDS_READY_VISUAL_REVIEW_PENDING' and not any(k in report for k in ('error','active_case','retained_buffers','retained_display_frames')),'Incomplete/failed board result')
    require((report['pynq'],report['python'],report['kernel'])==('3.0.1','3.10.4','5.15.19-xilinx-v2022.1'),'Unexpected board runtime')
    require(report['drivers']=={'dma':'pynq.lib.dma.DMA','gpio':'pynq.lib.axigpio.AxiGPIO',
        'video':'pynq.lib.video.hierarchies.HDMIWrapper','hdmi_out':'pynq.lib.video.hierarchies.VideoOut','vdma':'pynq.lib.video.dma.AxiVDMA'},'Wrong official drivers')
    require(type(report['overlay_downloads'])==int and report['overlay_downloads']==1,'Same-overlay single download not recorded')
    cells,streams=verify_notebook(notebook,report,manifest)
    require(len(report['transfers'])==370,'Incomplete B frame ledger')
    cases=recorded_cases()+[(side,3,'stare') for side,_ in GROUPS for _ in range(103)]
    frames=[];arrays=[];outputs={};cache={}
    for index,(case,record) in enumerate(zip(cases,report['transfers'])):
        side,mode,pattern=case;words=side*side;nbytes=words*4
        require((record['side'],record['mode'],record['pattern'])==case,'Frame order differs')
        require(record['status']=='PASS_EXACT_SEGMENTATION_WORDS' and (record['words'],record['send_bytes'],record['recv_bytes'])==(words,nbytes,nbytes),'Comparison/byte count differs')
        require(set(record['dma_status'])=={'mm2s','s2mm'} and all(v&2 and not v&0x771 for v in record['dma_status'].values()),'DMA halted/busy/error')
        addresses=(record['tx_address'],record['rx_address'])
        require(all(type(a)==int and a%8==0 and 0x100000<=a<=0x20000000-nbytes for a in addresses) and abs(addresses[0]-addresses[1])>=nbytes,'DDR address/alignment/overlap differs')
        require(record['frame_status']==((index+1)<<14)|(index+1),'FPGA frame count/error differs')
        require(('benchmark' in record)==(index>=61),'Unexpected benchmark record')
        key=(side,mode,pattern,index if pattern=='random' else None)
        if key not in cache:
            source=regenerate_input(side,pattern,index,package);expected=independent_expected(source,mode)
            cache[key]=(source,expected,word_digest(source),word_digest(expected))
        source,expected,input_hash,output_hash=cache[key]
        require(record['input_sha256']==input_hash and record['expected_sha256']==record['output_sha256']==output_hash,'Independent input/golden/output hash mismatch')
        frames.append({'frame':index+1,'side':side,'mode':mode,'pattern':pattern,'words':words,
            'input_sha256':input_hash,'expected_output_sha256':output_hash,'frame_status':record['frame_status'],'status':'PASS_INDEPENDENT_RECOMPUTE'})
        if index<61 and pattern=='stare':
            name=f'a4_output_stare_{side}_mode{mode}.npy'
            require(record['saved_output']=={'name':name,'sha256':digest(members[name])},'Raw saved file hash differs')
            raw=np.load(io.BytesIO(members[name]),allow_pickle=False)
            require(raw.dtype==np.dtype('<u4') and raw.shape==(side,side),'Raw array dtype/shape differs')
            require(np.array_equal(raw,expected) and word_digest(raw)==output_hash,'Downloaded raw FPGA array differs from independent model')
            outputs[(side,mode)]=raw
            arrays.append({'name':name,'shape':list(raw.shape),'dtype':str(raw.dtype),'words':words,'file_sha256':digest(members[name]),
                'word_sha256':word_digest(raw),'mismatched_words':0,'mask_byte_values':[int(v) for v in np.unique((raw>>16)&255)],
                'final_mask_outside_fov_pixels':int(np.count_nonzero(((raw>>16)&255)[(source>>24)==0])) if mode==3 else None})
        else:require('saved_output' not in record,'Unexpected saved output entry')
    require(sum(f['words'] for f in frames)==70647808 and {a['name'] for a in arrays}==ARRAY_NAMES,'Word count/raw array coverage differs')
    return {'frames':frames,'raw_arrays':arrays,'timing':verify_timing(report,streams),
        'display':verify_display(cells,report,members,outputs)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('notebook',type=Path);parser.add_argument('bundle',type=Path)
    for name in ('package','destination','raw-destination','color-photo','medical-photo'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    require(not args.destination.exists() and not args.raw_destination.exists(),'Preserve earlier archive')
    manifest_data=(args.package/'b_manifest.json').read_bytes();require(manifest_data==RELEASE.read_bytes(),'Release differs from archive')
    manifest=json.loads(manifest_data);validate_b_package(args.package,manifest)
    require(args.notebook.stat().st_size<=4_000_000,'Notebook exceeds evidence limit')
    notebook_data=args.notebook.read_bytes();bundle_data=args.bundle.read_bytes();members=read_bundle(args.bundle)
    report=json.loads(members['b_integration_result.json'])
    checks=verify_records(json.loads(notebook_data),report,manifest,args.package,members)
    require(args.bundle.read_bytes()==bundle_data and args.notebook.read_bytes()==notebook_data,'Downloads changed during verification')
    photos={'monitor_color_photo.jpg':args.color_photo.read_bytes(),'monitor_medical_photo.jpg':args.medical_photo.read_bytes()}
    for data in photos.values():
        with Image.open(io.BytesIO(data)) as im:require(im.format=='JPEG' and min(im.size)>=700,'Invalid monitor photo');im.verify()
    args.destination.mkdir(parents=True);args.raw_destination.mkdir(parents=True)
    raw={'b_integration_check_executed.ipynb':notebook_data,'b_results_bundle.zip':bundle_data,**members,**photos}
    records={}
    for name,data in raw.items():
        path=args.raw_destination/name;path.write_bytes(data);require(path.read_bytes()==data,'Raw byte preservation failed')
        records[name]={'path':str(path.resolve()),'bytes':len(data),'sha256':digest(data)}
    (args.destination/'b_integration_result.json').write_bytes(members['b_integration_result.json'])
    for key in ('frames','raw_arrays','timing','display'):write_json(args.destination/(key+'_verification.json'),checks[key])
    summary={'status':'PASS_B_BOARD_RECORDS_RAW_ARRAYS_DISPLAY_REFERENCES_AND_TIMING_VERIFIED','verified_host_utc':datetime.now(timezone.utc).isoformat(),
        'revision':manifest['revision'],'release_manifest_sha256':digest(manifest_data),'board_clock_utc_unverified':report['board_clock_utc_unverified'],
        'overlay_downloads':1,'frames_verified':370,'validation_frames':61,'benchmark_frames':309,'timed_frames':300,
        'input_words_verified':70647808,'raw_output_words_verified':983040,'notebook_code_sha256':notebook_code_hash(json.loads(notebook_data)),
        'raw_files':records,'source_paths':{'notebook':str(args.notebook.resolve()),'bundle':str(args.bundle.resolve())},
        'physical_visual_assessment':'Separate host review of supplied photographs; original JSON PENDING value retained',
        'limits':'370 output hashes independently recomputed, six actual saved STARE buffers compared word by word; other buffers not downloaded. Timing is repeated fixed-input host-visible transactions, not measured scan refresh, PL-only cycles or complete file-to-screen latency. No new medical quality PASS.',
        'local_archive_policy':'Original output-bearing notebook/ZIP/PNG/arrays and photos kept under ignored build/board_results; original JSON and verification metadata tracked.'}
    write_json(args.destination/'archive_manifest.json',summary)
    print('B_BOARD_RECORDS_AND_TIMING_ARCHIVED: 370 frames, 70647808 words; six raw arrays, 983040 words; 300 raw timing samples')


if __name__=='__main__':main()
