"""Derive the staged board harness from A2; standard driver/cache logic retained."""
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_function(source, name, body, next_name):
    start = source.index("def " + name + "(")
    end = source.index("def " + next_name + "(", start)
    return source[:start] + body.rstrip() + "\n\n\n" + source[end:]


def main():
    original = (ROOT / "scripts/a2_gaussian_board_test.py").read_text(encoding="utf-8")
    new = original.replace("A2", "A3").replace("a2_gaussian", "a3_background").replace("_a2", "_a3")
    new = new.replace("SHA356", "SHA256")
    new = new.replace("a2_manifest.json", "a3_manifest.json").replace("a2_output_stare_", "a3_output_stare_")
    new = new.replace("Gaussian", "Background").replace("GAUSSIAN", "BACKGROUND")
    new = new.replace("gaussian_expected", "background_expected").replace("r1_vendor_filter", "r1_vendor_box").replace("37", "45")
    new = new.replace('"a1_point_board_test.py","a0_dma_board_test.py"', '"a2_gaussian_board_test.py","a1_point_board_test.py","a0_dma_board_test.py"')
    new = new.replace("from a1_point_board_test import notebook_code_hash", "from a1_point_board_test import notebook_code_hash\nfrom a2_gaussian_board_test import gaussian_expected as gaussian_stage_expected, make_pattern as shared_pattern")
    new = replace_function(new, "background_expected", '''def background_expected(words,mode):
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
''', "make_pattern")
    new = replace_function(new, "make_pattern", '''def make_pattern(side,pattern,index,directory=None):
    if side not in (256,512): raise ValueError("Only complete 256/512 frames")
    if pattern not in ("vessel_stripes","rounding"): return shared_pattern(side,pattern,index,directory)
    y,x=np.indices((side,side),dtype=np.uint32)
    green=np.where((x%31<5)|(y%43<3),12,190).astype(np.uint32) if pattern=="vessel_stripes" else (x*13+y*7+9)%80
    position=y*side+x
    return (((x+y)&1)<<24)|(((position*7)&255)<<16)|(green<<8)|((position*13)&255)
''', "full_cases")
    new = replace_function(new, "full_cases", '''def full_cases():
    cases=[(s,m,p) for s in (256,512) for m in (0,1,2,3) for p in ("gradient","random")]
    cases += [(s,m,p) for s in (256,512) for m in (2,3) for p in ("checker","impulse","black","white","stare")]
    cases += [(s,m,p) for s in (256,512) for m in (2,3) for p in ("vessel_stripes","rounding")]
    return cases
''', "prepare_a3")
    new = new.replace('transfer_a3(context,256,2,"gradient")', 'transfer_a3(context,256,3,"vessel_stripes")')
    new = new.replace("full 256x256 Background frame matched", "full 256x256 background/response frame matched")
    new = new.replace("Background/center G/FOV/LUT only; no vessel segmentation, final HDMI or FPS PASS",
                      "Gaussian/LUT/15x15 background/response and center G/FOV diagnostics; no full vessel segmentation, final HDMI or FPS PASS")
    start = new.index("def show_a3_results(")
    new = new[:start] + '''def show_a3_results(context):
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
'''
    target = ROOT / "scripts/a3_background_board_test.py"
    if target.exists():
        raise ValueError("Preserve earlier derived runner")
    target.write_text(new, encoding="utf-8", newline="\n")
    (ROOT / "results/a3_background_2017_4/a2_to_a3_runner.diff").write_text("".join(difflib.unified_diff(
        original.splitlines(True), new.splitlines(True), fromfile="a2_gaussian_board_test.py", tofile=target.name)),
        encoding="utf-8", newline="\n")
    print("A3_RUNNER_DERIVED; DMA/cache/buffer retention/phase checks unchanged")


if __name__ == "__main__":
    main()
