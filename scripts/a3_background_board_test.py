"""A3 board validation: reused vendor Background, standard PYNQ DMA/GPIO."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from a0_dma_board_test import guarded_phase, sha256_file, wait_both_idle
from a1_point_board_test import notebook_code_hash
from a2_gaussian_board_test import gaussian_expected as gaussian_stage_expected, make_pattern as shared_pattern

REVISION="a3_background_r1_vendor_box"
NOTEBOOK="a3_background_check.ipynb"
FIXED={"a3_background.bit","a3_background.hwh","a3_background_board_test.py",
       "a2_gaussian_board_test.py","a1_point_board_test.py","a0_dma_board_test.py","使用说明.txt",
       "stare_im0001_256.npy","stare_im0001_512.npy"}


def validate_a3_package(directory,manifest):
    directory=Path(directory)
    if manifest.get("revision")!=REVISION or set(manifest.get("artifacts",{}))!=FIXED|{NOTEBOOK}:
        raise ValueError("Wrong or incomplete A3 release")
    for name in sorted(FIXED):
        if sha256_file(directory/name)!=manifest["artifacts"][name]["sha256"]:
            raise ValueError("Package mismatch: "+name)
    contract=manifest.get("notebook_validation",{})
    if contract.get("algorithm")!="sha256-code-cells-v1": raise ValueError("Missing notebook code contract")
    code_hash=notebook_code_hash(json.loads((directory/NOTEBOOK).read_text(encoding="utf-8")))
    if code_hash!=contract.get("sha256"): raise ValueError("Notebook code mismatch")
    return {"fixed_artifacts":"PASS_EXACT_SHA256","notebook_code":"PASS_CANONICAL_CODE_SHA256",
            "notebook_code_sha256":code_hash,"current_notebook_sha256":sha256_file(directory/NOTEBOOK),
            "original_notebook_sha256":manifest["artifacts"][NOTEBOOK]["sha256"]}


def background_expected(words,mode):
    words=np.asarray(words)
    if words.ndim!=2 or words.dtype!=np.uint32 or mode not in (0,1,2,3): raise ValueError("Expected uint32 image and mode 0..3")
    if mode==0: return words.copy()
    gaussian_stage=gaussian_stage_expected(words,3)
    enhanced=((gaussian_stage>>8)&255).astype(np.uint32)
    # Independent integral-image sum, not the vendor separable BoxFilter.
    p=np.pad(enhanced,7,mode="edge")
    integral=np.pad(p,((1,0),(1,0))).cumsum(0,dtype=np.uint32).cumsum(1,dtype=np.uint32)
    total=integral[15:,15:]+integral[:-15,:-15]-integral[:-15,15:]-integral[15:,:-15]
    background=(total+112)//225
    response=np.clip((background.astype(np.int16)-enhanced.astype(np.int16))*4,0,255).astype(np.uint32)
    return ((words>>8)&255)|(enhanced<<8)|(np.uint32(0) if mode==1 else background<<16)|(response<<24 if mode==3 else words&np.uint32(0xff000000))


def make_pattern(side,pattern,index,directory=None):
    if side not in (256,512): raise ValueError("Only complete 256/512 frames")
    if pattern not in ("vessel_stripes","rounding"): return shared_pattern(side,pattern,index,directory)
    y,x=np.indices((side,side),dtype=np.uint32)
    green=np.where((x%31<5)|(y%43<3),12,190).astype(np.uint32) if pattern=="vessel_stripes" else (x*13+y*7+9)%80
    position=y*side+x
    return (((x+y)&1)<<24)|(((position*7)&255)<<16)|(green<<8)|((position*13)&255)


def full_cases():
    cases=[(s,m,p) for s in (256,512) for m in (0,1,2,3) for p in ("gradient","random")]
    cases += [(s,m,p) for s in (256,512) for m in (2,3) for p in ("checker","impulse","black","white","stare")]
    cases += [(s,m,p) for s in (256,512) for m in (2,3) for p in ("vessel_stripes","rounding")]
    return cases


def prepare_a3(directory,retained):
    import pynq
    from pynq import Overlay,allocate
    from pynq.lib import DMA,AxiGPIO
    if pynq.__version__!="3.0.1" or platform.machine() not in ("armv7l","armv7"): raise RuntimeError("Run on measured PYNQ-Z2 3.0.1")
    if retained: raise RuntimeError("Earlier buffers remain; stop")
    directory=Path(directory).resolve()
    output=directory/"a3_background_result.json"
    if output.exists(): raise RuntimeError("Use a new folder; preserve earlier A3 result")
    manifest=json.loads((directory/"a3_manifest.json").read_text(encoding="utf-8"))
    validation=validate_a3_package(directory,manifest)
    overlay=Overlay(str(directory/"a3_background.bit"),download=False)
    dma=overlay.ip_dict["axi_dma_0"]; gpio=overlay.ip_dict["point_control"]
    if dma["type"]!="xilinx.com:ip:axi_dma:7.1" or dma["phys_addr"]!=0x40400000: raise ValueError("Wrong DMA mapping")
    expected={"c_include_sg":0,"c_micro_dma":0,"c_sg_length_width":23,"c_m_axis_mm2s_tdata_width":32,
              "c_s_axis_s2mm_tdata_width":32,"c_m_axi_mm2s_data_width":64,"c_m_axi_s2mm_data_width":32}
    if any(int(dma["parameters"][key])!=value for key,value in expected.items()): raise ValueError("Wrong DMA parameters")
    if gpio["type"]!="xilinx.com:ip:axi_gpio:2.0" or gpio["phys_addr"]!=0x41200000: raise ValueError("Wrong GPIO mapping")
    for key,value in {"C_IS_DUAL":1,"C_GPIO_WIDTH":32,"C_GPIO2_WIDTH":32,"C_ALL_OUTPUTS":1,"C_ALL_INPUTS_2":1,"C_INTERRUPT_PRESENT":0}.items():
        if int(gpio["parameters"][key])!=value: raise ValueError("Wrong GPIO parameters")
    report={"status":"A3_PRECHECK_FPGA_UNCHANGED","manifest":manifest,"package_validation":validation,
            "pynq":pynq.__version__,"python":platform.python_version(),"kernel":platform.release(),
            "board_clock_utc_unverified":datetime.now(timezone.utc).isoformat(),"transfers":[],
            "scope":"Gaussian/LUT/15x15 background/response and center G/FOV diagnostics; no full vessel segmentation, final HDMI or FPS PASS"}
    def save():
        temp=output.with_suffix(".json.tmp"); temp.write_text(json.dumps(report,indent=2),encoding="utf-8"); temp.replace(output)
    save()
    print("A3_PRECHECK_PASS: hashes/metadata; FPGA unchanged",flush=True)
    return {"directory":directory,"overlay":overlay,"allocate":allocate,"dma_class":DMA,"gpio_class":AxiGPIO,
            "report":report,"save":save,"retained":retained}


def load_a3(context):
    if context["report"]["status"]!="A3_PRECHECK_FPGA_UNCHANGED": raise RuntimeError("Precheck must pass first")
    def action():
        context["overlay"].download()
        dma=context["overlay"].axi_dma_0; gpio=context["overlay"].point_control
        if not isinstance(dma,context["dma_class"]) or not isinstance(gpio,context["gpio_class"]): raise RuntimeError("Official drivers did not bind")
        context.update(dma=dma,gpio=gpio)
        gpio.channel1.setdirection("out"); gpio.channel2.setdirection("in")
        if gpio.channel2.read()!=0: raise RuntimeError("Frame state not reset")
        context["report"].update(status="A3_LOADED_NO_TRANSFER",drivers={"dma":type(dma).__module__+"."+type(dma).__name__,
            "gpio":type(gpio).__module__+"."+type(gpio).__name__})
        context["save"](); print("A3_LOAD_PASS: official drivers and reset state checked",flush=True)
    guarded_phase(context,"A3_PROGRAMMING_OVERLAY",action)


def transfer_a3(context,side,mode,pattern):
    if side not in (256,512) or mode not in (0,1,2,3): raise ValueError("Complete frames and valid modes only")
    index=len(context["report"]["transfers"])
    source=make_pattern(side,pattern,index,context["directory"])
    expected=background_expected(source,mode).reshape(-1)
    count=side*side; nbytes=count*4
    context["gpio"].channel1.write(mode|(4 if side==256 else 0),0xffffffff)
    tx=context["allocate"](shape=(count,),dtype=np.uint32); context["retained"].append(tx)
    rx=context["allocate"](shape=(count,),dtype=np.uint32); context["retained"].append(rx)
    for buffer in (tx,rx):
        if buffer.physical_address%8 or not (0x100000<=buffer.physical_address<=0x20000000-nbytes): raise RuntimeError("Invalid DDR buffer")
    if abs(tx.physical_address-rx.physical_address)<nbytes: raise RuntimeError("Buffers overlap")
    tx[:]=source.reshape(-1); rx[:]=np.bitwise_not(expected); rx.flush()
    context["report"]["active_case"]={"side":side,"mode":mode,"pattern":pattern}; context["save"]()
    dma=context["dma"]
    dma.recvchannel.transfer(rx); dma.sendchannel.transfer(tx)
    statuses=wait_both_idle(dma); dma.sendchannel.wait(); dma.recvchannel.wait()
    if dma.sendchannel.transferred!=nbytes or dma.recvchannel.transferred!=nbytes: raise AssertionError("DMA byte count mismatch")
    mismatch=np.flatnonzero(rx!=expected)
    if mismatch.size: raise AssertionError("Background mismatch at pixel "+str(int(mismatch[0])))
    status=int(context["gpio"].channel2.read()); frames=(index+1)&0x3fff
    if status != frames|(frames<<14): raise AssertionError("Frame counters or error flags mismatch")
    record={"side":side,"mode":mode,"pattern":pattern,"words":count,"send_bytes":int(dma.sendchannel.transferred),
            "recv_bytes":int(dma.recvchannel.transferred),"tx_address":int(tx.physical_address),"rx_address":int(rx.physical_address),
            "dma_status":statuses,"frame_status":status,"status":"PASS_EXACT_BACKGROUND_WORDS",
            "input_sha256":hashlib.sha256(source.tobytes()).hexdigest(),"expected_sha256":hashlib.sha256(expected.tobytes()).hexdigest(),
            "output_sha256":hashlib.sha256(np.asarray(rx).tobytes()).hexdigest()}
    if pattern=="stare":
        name=f"a3_output_stare_{side}_mode{mode}.npy"
        np.save(context["directory"]/name,np.asarray(rx).reshape(side,side)); record["saved_output"]={"name":name,"sha256":sha256_file(context["directory"]/name)}
    context["report"]["transfers"].append(record); context["report"].pop("active_case"); context["save"]()
    rx.freebuffer(); tx.freebuffer(); context["retained"].clear()
    print(f"BACKGROUND_FRAME_PASS: {index+1}/45 {side} mode {mode} {pattern}",flush=True)


def smoke_a3(context):
    if context["report"]["status"]!="A3_LOADED_NO_TRANSFER": raise RuntimeError("Load once before smoke")
    def action():
        transfer_a3(context,256,3,"vessel_stripes")
        context["report"]["status"]="A3_SMOKE_PASS_FULL_PENDING"; context["save"]()
        print("A3_SMOKE_PASS: full 256x256 background/response frame matched",flush=True)
    guarded_phase(context,"A3_SMOKE_RUNNING",action)


def full_a3(context):
    if context["report"]["status"]!="A3_SMOKE_PASS_FULL_PENDING": raise RuntimeError("Smoke must pass first")
    def action():
        for case in full_cases(): transfer_a3(context,*case)
        context["report"]["status"]="A3_PASS_45_BACKGROUND_FRAMES_NOT_FULL_SEGMENTATION"; context["save"]()
        print("A3 BACKGROUND PASS: 45 complete frames matched; no full segmentation/HDMI/FPS PASS",flush=True)
    guarded_phase(context,"A3_FULL_SUITE_RUNNING",action)
    return context["report"]


def show_a3_results(context):
    if context["report"]["status"]!="A3_PASS_45_BACKGROUND_FRAMES_NOT_FULL_SEGMENTATION": raise RuntimeError("Full suite must pass first")
    from PIL import Image,ImageDraw
    from IPython.display import display
    from zipfile import ZipFile,ZIP_DEFLATED
    directory=context["directory"]
    bundle=directory/"a3_results_bundle.zip"
    if bundle.exists(): raise RuntimeError("Bundle already exists; preserve it, do not rerun preview")
    output=np.load(directory/"a3_output_stare_512_mode3.npy",allow_pickle=False)
    canvas=Image.new("RGB",(1024,280),"white"); draw=ImageDraw.Draw(canvas)
    for i,(name,shift) in enumerate((("Raw green",0),("FPGA enhanced",8),("FPGA background",16),("FPGA response",24))):
        array=((output>>shift)&255).astype(np.uint8)
        canvas.paste(Image.fromarray(array).resize((256,256)),(i*256,24)); draw.text((i*256+5,5),name,fill="black")
    preview=directory/"a3_preview.png"; canvas.save(preview); display(canvas)
    context["report"]["preview"]={"file":preview.name,"sha256":sha256_file(preview)}; context["save"]()
    names=["a3_background_result.json",preview.name]+[item["saved_output"]["name"] for item in context["report"]["transfers"] if "saved_output" in item]
    with ZipFile(bundle,"w",ZIP_DEFLATED) as archive:
        for name in names: archive.write(directory/name,arcname=name)
    print("A3_RESULTS_READY: download a3_results_bundle.zip and executed notebook",flush=True)
