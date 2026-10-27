"""Read-only source identification; never imports model or board software."""
from pathlib import Path
import json, hashlib, sys
sys.path.append('D:/PLD/retina_fpga/.venv/Lib/site-packages')
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/single_repair_r1/identity'
OLD=Path('D:/PLD/retina_c7_isolated_recovery')
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir(parents=True,exist_ok=False)
    rows=json.loads((OLD/'results/atomic_bridge_quality_repair_r1/output_index.json').read_text())
    refs=[]
    for row in rows:
        if row['key']!='STARE/im0324':continue
        ref=row['sources']['pair'];p=Path(ref['path'])
        assert p.stat().st_size==ref['bytes'] and digest(p)==ref['sha256']
        with np.load(p,allow_pickle=False) as a:
            iw=a['input_words'];ow=a['output_words']
            print(row['side'],a.files,iw.shape)
        rgb=np.stack([(iw>>s).astype('uint8') for s in (16,8,0)],-1)
        mask=((ow>>16)&255)!=0;fov=(iw>>24)!=0
        assert np.array_equal(mask,((ow>>24)>=112)&fov)
        overlay=rgb.copy();overlay[mask]=[0,255,0]
        for name,v in [('rgb',rgb),('mask',mask.astype('uint8')*255),('overlay',overlay)]:
            Image.fromarray(v).save(OUT/f'{row["side"]}_{name}.png')
        refs.append(dict(side=row['side'],source=ref))
    (OUT/'references.json').write_text(json.dumps(refs,indent=2))
if __name__=='__main__':main()
