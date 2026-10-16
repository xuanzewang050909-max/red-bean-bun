"""View frozen grouped OOF comparisons without selecting parameters from heldout data."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
source = ROOT / 'build/q4_fusion_2026-10-14_r3'
run = ROOT / 'build/q4d_detector_2026-10-15_r1'
p = json.loads((ROOT / 'docs/q4d_detector_protocol_r1.json').read_bytes())
for image in ('im0001', 'im0003', 'im0077'):
    with np.load(source / f'{image}_512_offline_masks.npz', allow_pickle=False) as z:
        rgb = z['rgb']; truth = z['truth_AH'].astype(bool); fov=z['fov'].astype(bool)
        c5 = np.unpackbits(z[p['c5_key']])[:fov.size].reshape(fov.shape).astype(bool)
    masks=[c5]+[(np.load(run / f'{image}_512_d{d}_oof_score.npy')>=t)&fov for d,t in ((6,96),(6,112),(8,112))]
    names=['C5 / T28','C7 d6 / T96 OOF','C7 d6 / T112 OOF','C7 d8 / T112 OOF']
    fig,axes=plt.subplots(3,5,figsize=(16,10))
    for row, sl in enumerate(((slice(None),slice(None)),(slice(145,385),slice(180,340)),(slice(270,430),slice(40,220)))):
        axes[row,0].imshow(rgb[sl]); axes[row,0].set_title(image+' input')
        for col,(mask,name) in enumerate(zip(masks,names),1):
            canvas=rgb.astype(float)*0.25
            canvas[mask&truth]=[0,240,80]; canvas[mask&~truth]=[255,30,40]; canvas[~mask&truth]=[40,130,255]
            axes[row,col].imshow(canvas[sl].astype(np.uint8),interpolation='nearest'); axes[row,col].set_title(name)
        for ax in axes[row]: ax.axis('off')
    fig.suptitle('TRAIN grouped OOF; CPU reference only. Green TP / red FP / blue FN. Fixed crops, no mask editing.')
    fig.tight_layout(); fig.savefig(run / f'{image}_oof_comparison.png',dpi=130); plt.close(fig)
print('OOF_REVIEW_IMAGES_READY')
