"""Finite candidate registry and image views; inference takes RGB/old/FOV only."""
from identify import ROOT,OUT,IDS,sha
from reference import response,shift,DIRECTIONS,panel,overlay
import numpy as np, cv2, json,time
from PIL import Image

def decide_cached(rgb,old,fov,cfg,cache=None):
    if cache is None:cache=response(rgb,fov,cfg['mode'],cfg['length'],tuple(cfg['widths']),True)
    g,score,direction,safe,orth=cache
    count=(2*cfg['length']+1)*16
    ridge=np.zeros_like(old)
    for k,(dx,dy) in enumerate(DIRECTIONS):
        norm=np.hypot(dx,dy);ny=int(round(dx/norm));nx=int(round(-dy/norm))
        ridge|=(direction==k)&(g<=shift(g,ny,nx)+cfg['ridge_tolerance'])&(g<=shift(g,-ny,-nx)+cfg['ridge_tolerance'])
    weak=(score>=cfg['low']*count)&ridge&safe&(score-orth>=cfg['anisotropy']*count)
    strong=(score>=cfg['high']*count)&weak
    rawweak=weak.copy()
    if cfg.get('coherence',0):
        accepted=np.zeros_like(weak)
        for k,(dx,dy) in enumerate(DIRECTIONS):
            norm=max(abs(dx),abs(dy));hyp=np.hypot(dx,dy)
            ny=int(round(dx/hyp));nx=int(round(-dy/hyp))
            dd=(direction.astype('int32')-k)%8
            aligned=weak&((dd<=1)|(dd>=7))
            hits=np.zeros_like(score)
            for t in range(-8,9):
                y=int(round(t*dy/norm));x=int(round(t*dx/norm))
                hits+=(shift(aligned,y,x)|shift(aligned,y+ny,x+nx)|shift(aligned,y-ny,x-nx))
            accepted|=(direction==k)&(hits>=cfg['coherence'])
        if cfg.get('coherence_seed_only',False):strong&=accepted
        else:weak&=accepted;strong&=weak
    active=strong.copy()
    for _ in range(cfg['grow_steps']):active=weak&(cv2.dilate(active.astype('uint8'),np.ones((3,3),'uint8'))!=0)
    support=cv2.boxFilter(active.astype('int32'),cv2.CV_32S,(9,9),normalize=False,borderType=cv2.BORDER_CONSTANT)
    added=active&(support>=cfg['min_support'])&~old
    return dict(score=score,direction=direction,smoothed=g,added=added,final=old|added,uncertain=rawweak&~added&~old)

def render(dst,name,rgb,old,r):
    dst.mkdir(parents=True,exist_ok=False)
    before=overlay(rgb,old,np.zeros_like(old));color=overlay(rgb,old,r['added'],True)
    arrays=dict(original=rgb,old_mask=old,added_mask=r['added'],final_mask=r['final'],uncertain_mask=r['uncertain'],final_overlay=overlay(rgb,old,r['added']),old_new_colors=color)
    for k,a in arrays.items():Image.fromarray(a.astype('uint8')*255 if a.dtype==bool else a).save(dst/(k+'.png'))
    panel([Image.fromarray(a) for a in [rgb,before,color]],['RGB','C7 old','Green old / cyan added'],dst/'comparison.png')
    rois=json.loads((ROOT/'three_repair/roi_views.json').read_text())[name]
    for key,box in rois.items():
        size=((box[2]-box[0])*2,(box[3]-box[1])*2)
        panel([Image.fromarray(a).crop(box).resize(size,Image.Resampling.NEAREST) for a in [rgb,before,color]],['RGB','C7 old','After'],dst/(key+'.png'))

def run(name,cfg,reason,stage):
    ledger=OUT/'candidate_ledger.json';rows=json.loads(ledger.read_text()) if ledger.exists() else []
    assert len(rows)<20 and name not in [x['name'] for x in rows]
    dst=OUT/'candidates'/name;dst.mkdir(parents=True,exist_ok=False)
    row=dict(name=name,config=cfg,reason=reason,stage=stage,frames=[],status='RUNNING');rows.append(row)
    ledger.write_text(json.dumps(rows,indent=2)) # register before execution
    for ident in IDS:
        t=time.perf_counter()
        effective=cfg.get('profiles',{}).get(ident,cfg)
        with np.load(OUT/'input'/f'{ident}.npz') as a:rgb=a['rgb'];old=a['old'];fov=a['fov']
        key=f"{ident}_{effective['mode']}_L{effective['length']}_W{'-'.join(map(str,effective['widths']))}"
        cp=OUT/'response_cache'/f'{key}.npz';cp.parent.mkdir(exist_ok=True)
        if cp.exists():
            with np.load(cp) as a:cache=tuple(a[str(i)] for i in range(5))
        else:
            cache=response(rgb,fov,effective['mode'],effective['length'],tuple(effective['widths']),True)
            np.savez_compressed(cp,**{str(i):v for i,v in enumerate(cache)})
        r=decide_cached(rgb,old,fov,effective,cache)
        assert not np.any(old&~r['final']) and not np.any(r['added']&~fov)
        render(dst/ident,ident,rgb,old,r);np.savez_compressed(dst/ident/'arrays.npz',**r)
        # Distance is a descriptive aid, not a success criterion or inference input.
        far=cv2.dilate(old.astype('uint8'),np.ones((7,7),'uint8'))==0
        row['frames'].append(dict(id=ident,old=int(old.sum()),added=int(r['added'].sum()),added_farther_than_3px=int((r['added']&far).sum()),uncertain=int(r['uncertain'].sum()),seconds=time.perf_counter()-t,array_sha256=sha(dst/ident/'arrays.npz'),visual_review='PENDING'))
    row['status']='GENERATED';ledger.write_text(json.dumps(rows,indent=2));(dst/'record.json').write_text(json.dumps(row,indent=2));print(json.dumps(row))

if __name__=='__main__':
    base=dict(mode='valley',length=6,widths=[2,4,6],fraction=True,low=2,high=4,ridge_tolerance=2,grow_steps=16,min_support=8,anisotropy=1)
    for name,updates,reason in [('v01',{},'Reference baseline; test existing integer line filter on all three.'),('v02',{'high':3},'More independent seeds on low contrast long branches, same weak floor.'),('v03',{'low':1.5,'high':3,'anisotropy':0.75},'Recover faint whole segments; inspect background texture especially im0291.'),('v04',{'low':1,'high':3,'anisotropy':0.75},'Test weak branch extension; inspect lighting and radial texture.')]:
        cfg=base.copy();cfg.update(updates);run(name,cfg,reason,'route1_initial')
