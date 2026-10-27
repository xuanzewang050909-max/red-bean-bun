"""Read only original evidence; no labels are loaded and no board is contacted."""
import sys, json, hashlib, shutil
from pathlib import Path
sys.path.append('D:/PLD/retina_fpga/.venv/Lib/site-packages')
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/three_repair_r1'
IDS=('im0004','im0291','im0319')
INDEX=Path('D:/PLD/retina_c7_isolated_recovery/results/atomic_bridge_quality_repair_r1/output_index.json')
WEB=Path('D:/PLD/retina_c7_system/build/deploy/c7_showcase_ui_r2/package')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p): return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def main():
    out=OUT/'input';out.mkdir(parents=True,exist_ok=False)
    task=Path('C:/Users/Gabriel/Downloads/CODEX_ThreeImage_VesselCompletion_PreBoard.md')
    shutil.copy2(task,OUT/'TASK.md')
    idx=json.loads(INDEX.read_text());wm=json.loads((WEB/'browser_manifest.json').read_text())
    rows=[]
    for name in IDS:
        row=next(x for x in idx if x['key']=='STARE/'+name and x['side']==512)
        sr=row['sources']['pair'];p=Path(sr['path'])
        assert p.stat().st_size==sr['bytes'] and sha(p)==sr['sha256']
        with np.load(p,allow_pickle=False) as a:
            iw=a['input_words'];ow=a['output_words']  # deliberately never load GT/ROI/thin
        web=wm['images'][name]['512'];wp=WEB/web['input']
        assert sha(wp)==web['input_file']['sha256']
        assert np.array_equal(iw,np.load(wp,allow_pickle=False))
        assert hashlib.sha256(iw.tobytes()).hexdigest()==web['input_word_sha256']
        assert iw.dtype==ow.dtype==np.uint32 and iw.shape==ow.shape==(512,512)
        rgb=np.stack([(iw>>s).astype('uint8') for s in (16,8,0)],-1)
        fov=(iw>>24)!=0;old=((ow>>16)&255)!=0;q7=(ow>>24).astype('uint8')
        assert set(np.unique(iw>>24))<={0,1}
        assert set(np.unique((ow>>16)&255))<={0,255}
        assert np.array_equal(old,(q7>=112)&fov)
        np.savez_compressed(out/(name+'.npz'),rgb=rgb,old=old,fov=fov,input_words=iw,output_words=ow)
        overlay=rgb.copy();overlay[old]=[0,255,0]
        for k,v in [('original',rgb),('old_mask',old.astype('uint8')*255),('old_overlay',overlay)]:Image.fromarray(v).save(out/(name+'_'+k+'.png'))
        rows.append(dict(id=name,processing_shape=[512,512],source=sr,web_input=ref(wp),geometry=web['geometry'],input=ref(out/(name+'.npz')),
            original_mask_pixels=int(old.sum()),display_unpack='M7 = output[23:16] != 0, exact T112/FOV match',
            input_mapping='existing packed RGB/FOV used unchanged; no rotation, new scaling or channel swap',historical_role=row['original_role'],current_role='three-image targeted visual development only'))
    (OUT/'source_manifest.json').write_text(json.dumps(dict(parent_commit='4d33090',task=ref(task),index=ref(INDEX),web_manifest=ref(WEB/'browser_manifest.json'),frames=rows,board_operations=0),indent=2))
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
