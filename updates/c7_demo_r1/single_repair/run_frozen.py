"""Reproduce only this frozen single-image output, no candidate search."""
from software import *
import argparse
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=OUT/'input/input.npz');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    contract=json.loads((OUT/'frozen_algorithm.json').read_text())
    assert hashlib.sha256(a.input.read_bytes()).hexdigest()==contract['input_sha256'],'Frozen input differs'
    assert hashlib.sha256(Path(__file__).with_name('software.py').read_bytes()).hexdigest()==contract['source_sha256'],'Frozen algorithm differs'
    a.output.mkdir(parents=True,exist_ok=False)
    with np.load(a.input,allow_pickle=False) as f:rgb=f['rgb'];old=f['old'];fov=f['fov']
    r=decide(rgb,old,fov,contract['config'])
    with np.load(OUT/'selected/arrays.npz',allow_pickle=False) as f:
        assert all(np.array_equal(f[k],r[k]) for k in r)
    for key in ['added','final','uncertain']:Image.fromarray(r[key].astype('uint8')*255).save(a.output/(key+'_mask.png'))
    Image.fromarray(overlay(rgb,old,r['added'])).save(a.output/'final_overlay.png')
    Image.fromarray(overlay(rgb,old,r['added'],True)).save(a.output/'old_new_colors.png')
    np.savez_compressed(a.output/'arrays.npz',**r)
    print('FROZEN_SINGLE_IMAGE_REPRODUCED; BOARD_NOT_RUN')
if __name__=='__main__':main()
