from software import *
import shutil
def main():
    chosen='v08';src=OUT/'candidates'/chosen;dest=OUT/'selected';dest.mkdir(exist_ok=False)
    rec=json.loads((src/'record.json').read_text())
    for p in src.iterdir():shutil.copy2(p,dest/p.name)
    findings={
      'v01':'Long lower-left branch recovered, right-lower trunk still broken; scattered short fragments.',
      'v02':'Right-lower continuation recovered, too many weak short spurs on left; rejected.',
      'v03':'Higher tolerance thickens some responses and misses lower-right tail; rejected.',
      'v04':'Fractional binomial response and wider scale recover right-lower tail, reduce quantization speckle.',
      'v05':'Longer filter loses curved lower-left branch continuity; rejected.',
      'v06':'Higher seed threshold loses small supported side branches; not preferred.',
      'v07':'Longest/widest filter reduces thin curved branch coverage; not preferred.',
      'v08':'Selected: retains visible lower-left long branch and right-lower trunk; anisotropy removes some nondirectional fragments. No area-fill or uniform thickening observed. Residual faint paths remain uncertain.',
      'v09':'Stricter anisotropy removes some weak supported ends without a clear whole-image advantage.',
      'v10':'Broader ridge tolerance adds small local twigs; no clear advantage.',
      'v11':'Larger support requirement breaks long slender lower branches; rejected.'}
    ledger=json.loads((OUT/'candidate_ledger.json').read_text())
    reviews=[]
    for r in ledger:reviews.append(dict(candidate=r['name'],finding=findings[r['name']],whole_and_example_crops_viewed=True))
    cfg=rec['config']
    frozen=dict(schema='single-image-vessel-valley-v1',selected=chosen,config=cfg,input_sha256=hashlib.sha256((OUT/'input/input.npz').read_bytes()).hexdigest(),
        reference_sha256=rec['arrays_sha256'],source_sha256=hashlib.sha256(Path(__file__).with_name('software.py').read_bytes()).hexdigest(),
        inputs=['RGB uint8','old_mask bool','FOV bool'],manual_hints=False,regional_inference_parameters=False,
        output='old_mask OR added_mask',GT_used=False,board_operations=0,software_candidates=len(ledger),physical_builds=0,
        numeric=dict(green_binomial_sum='unsigned12 Q4, no rounding before response',line_sum='unsigned16 max53040',score='signed32 during subtraction; nonnegative result',
          offsets='fixed rounded integer geometry, ties to even from Python generation',threshold_scale=208,
          border='image-edge replication for samples; additions restricted to 25x25 all-FOV; outside FOV rejected',tie='first direction wins strict >; orthogonal=(direction+4)%8',
          hysteresis='16 synchronous 8-neighbor updates (not in-place raster growth)',support='9x9 zero padded sum >=8'),
        limits=['Single image visually reviewed, not independent annotated validation.','Faint vessel ends and low-contrast intersection interiors remain uncertain and may be absent.',
                'Old C7 false labels retained by explicit add-only requirement.','No claim of per-pixel accuracy, complete topology safety or clinical annotation validity.'])
    (OUT/'frozen_algorithm.json').write_text(json.dumps(frozen,indent=2))
    (OUT/'visual_review.json').write_text(json.dumps(reviews,indent=2))
    note='''# Single image progress\n\nInput: im0324, original 700x605, existing native 512x512 letterbox. Screenshot registration: 373px display at (7,1), RGB MAE 1.224. True old C7 M7 used, no GT arrays loaded.\n\n11 candidates, one route, two refinement rounds complete. Selected v08: 3083 added pixels, 6457 original preserved; 2441 uncertain candidate pixels kept separate. Whole images and two example windows actually viewed for all candidates. No uniform dilation, output lookup, learned model or manual hints.\n\nNext: exact C/HLS implementation, simulation, actual 50MHz independent overlay integration/route (<=3 physical builds). No board operations. BOARD_NOT_RUN.\n'''
    (OUT/'PROGRESS.md').write_text(note)
    print(chosen,rec['added_pixels'],'SOFTWARE_FROZEN')
if __name__=='__main__':main()
