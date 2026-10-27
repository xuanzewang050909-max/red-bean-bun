"""Image-only bounded directional valley filter. No labels, scores or coordinates."""
import sys
sys.path.append('D:/PLD/retina_fpga/.venv/Lib/site-packages')
from pathlib import Path
import numpy as np, cv2, json, hashlib, time
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/three_repair_r1'
# All geometry is finite; generated constants are shared with C/HLS.
DIRECTIONS=[(4,0),(4,2),(3,3),(2,4),(0,4),(-2,4),(-3,3),(-4,2)]
def shift(a,dy,dx):
    h,w=a.shape;p=np.pad(a,16,mode='edge');return p[16+dy:16+dy+h,16+dx:16+dx+w]
def offsets(dx,dy,length,width):
    norm=max(abs(dx),abs(dy));n=np.hypot(dx,dy)
    center=[(int(round(t*dy/norm)),int(round(t*dx/norm))) for t in range(-length,length+1)]
    ny=int(round(width*dx/n));nx=int(round(-width*dy/n))
    return center,(ny,nx)
def response(rgb,fov,mode='valley',length=4,widths=(2,3,4),fraction=False):
    g=rgb[:,:,1].astype('int32')
    # Exact separable [1,2,1]^2 kernel, round nearest toward +infinity at half.
    s=sum(shift(g,dy,dx)*wy*wx for dy,wy in [(-1,1),(0,2),(1,1)] for dx,wx in [(-1,1),(0,2),(1,1)])
    g=s if fraction else (s+8)//16
    best=np.zeros_like(g);direction=np.zeros_like(g,dtype='uint8');perdir=[]
    for k,(dx,dy) in enumerate(DIRECTIONS):
        ds=np.zeros_like(g)
        for width in widths:
            off,(ny,nx)=offsets(dx,dy,length,width)
            c=sum(shift(g,y,x) for y,x in off)
            l=sum(shift(g,y+ny,x+nx) for y,x in off)
            r=sum(shift(g,y-ny,x-nx) for y,x in off)
            v=np.minimum(l,r)-c if mode=='valley' else (l+r)//2-c
            # Suppress broad slopes: both flanks must be brighter, for both routes.
            v=np.where(np.minimum(l,r)>c,v,0)
            ds=np.maximum(ds,v)
            update=v>best;best=np.maximum(best,v);direction[update]=k
        perdir.append(ds)
    safe=cv2.erode(fov.astype('uint8'),np.ones((25,25),'uint8'),borderType=cv2.BORDER_CONSTANT,borderValue=0)>0
    best[~safe]=0
    orth=np.choose((direction.astype('int32')+4)%8,perdir)
    return g,best,direction,safe,orth
def decide(rgb,old,fov,cfg):
    fraction=cfg.get('fraction',False)
    g,score,direction,safe,orth=response(rgb,fov,cfg['mode'],cfg['length'],tuple(cfg['widths']),fraction)
    count=(cfg['length']*2+1)*(16 if fraction else 1)
    # Cross-line local maxima keep slender ridges. No dependence on old-mask connectivity.
    ridge=np.zeros_like(old)
    for k,(dx,dy) in enumerate(DIRECTIONS):
        n=np.hypot(dx,dy);ny=int(round(dx/n));nx=int(round(-dy/n))
        ridge|=(direction==k)&(g<=shift(g,ny,nx)+cfg['ridge_tolerance'])&(g<=shift(g,-ny,-nx)+cfg['ridge_tolerance'])
    weak=(score>=cfg['low']*count)&ridge&safe&(score-orth>=cfg.get('anisotropy',0)*count)
    strong=(score>=cfg['high']*count)&weak
    active=strong.copy()
    for _ in range(cfg['grow_steps']):active=weak&(cv2.dilate(active.astype('uint8'),np.ones((3,3),'uint8'))!=0)
    # Reject isolated fragments by finite 9x9 support; not by contact with C7.
    support=cv2.boxFilter(active.astype('int32'),cv2.CV_32S,(9,9),normalize=False,borderType=cv2.BORDER_CONSTANT)
    added=active&(support>=cfg['min_support'])&~old
    uncertain=weak&~added&~old
    return dict(score=score,direction=direction,smoothed=g,added=added,final=old|added,uncertain=uncertain)
def overlay(rgb,old,added,color=False):
    a=rgb.copy();a[old]=[0,255,0];a[added]=[0,210,255] if color else [0,255,0];return a
def panel(images,labels,path):
    w,h=images[0].size;canvas=Image.new('RGB',(w*len(images),h+24),(28,28,28));d=ImageDraw.Draw(canvas)
    for i,(im,label) in enumerate(zip(images,labels)):canvas.paste(im,(i*w,24));d.text((i*w+5,5),label,fill='white')
    canvas.save(path)