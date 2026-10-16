"""Sixteen raster directions with fractional line contrast for thin vessels.

Every offset is a compile-time integer in the prospective PL. Signed means
are retained at 1/16 grayscale precision instead of rounding before contrast.
"""
import cv2
import numpy as np
from software.q4f_residual import residual_features

DIRS=((0,1),(1,3),(1,2),(2,3),(1,1),(3,2),(2,1),(3,1),
      (1,0),(3,-1),(2,-1),(3,-2),(1,-1),(2,-3),(1,-2),(1,-3))

def rounded_ratio(a,b):
    return (abs(a)+b//2)//b*(1 if a>=0 else -1)

def round_array(a,b):
    return np.where(a>=0,(a+b//2)//b,-((-a+b//2)//b))

def offsets(direction,length,distance=0):
    dy,dx=direction;major=max(abs(dy),abs(dx))
    py=rounded_ratio(-dx*distance,major);px=rounded_ratio(dy*distance,major)
    return [(rounded_ratio(t*dy,major)+py,rounded_ratio(t*dx,major)+px) for t in range(-length//2+1,length//2+1)]

def fine_features(green,old_features,c7_score):
    g=green.astype(np.int32);h,w=g.shape;p=np.pad(g,9,mode='edge')
    def at(dy,dx):return p[9+dy:9+dy+h,9+dx:9+dx+w]
    planes=[residual_features(old_features,c7_score)]
    names=[]
    for length in (5,9,15):
        sums=np.stack([sum(at(y,x) for y,x in offsets(d,length)) for d in DIRS])
        lo=sums.min(axis=0);hi=sums.max(axis=0)
        for width in (7,15):
            total=np.rint(cv2.boxFilter(g.astype(np.float64),cv2.CV_64F,(width,width),normalize=False,borderType=cv2.BORDER_REPLICATE)).astype(np.int32)
            val=round_array(16*(total*length-lo*width*width),width*width*length)
            planes.append(val[...,None].astype(np.int16));names.append(f'fine{length}_m{width}_contrast_q4')
        planes.append(round_array(16*(hi-lo),length)[...,None].astype(np.int16));names.append(f'fine{length}_spread_q4')
        planes.append(round_array(16*(lo-length*g),length)[...,None].astype(np.int16));names.append(f'fine{length}_offset_q4')
        if length==15:continue
        for distance in (1,2):
            small=[];imbalance=[];central=[]
            for j,d in enumerate(DIRS):
                l=sum(at(y,x) for y,x in offsets(d,length,distance))-sums[j]
                r=sum(at(y,x) for y,x in offsets(d,length,-distance))-sums[j]
                small.append(np.minimum(l,r));imbalance.append(np.abs(l-r))
                py,px=offsets(d,1,distance)[0]
                central.append(np.minimum(at(py,px),at(-py,-px))-g)
            winner=np.stack(small).argmax(axis=0)[None]
            pick=lambda values:np.take_along_axis(np.stack(values),winner,axis=0)[0]
            for label,value in [('minimum_q4',round_array(16*pick(small),length)),
                                ('imbalance_q4',round_array(16*pick(imbalance),length)),
                                ('central',pick(central))]:
                planes.append(value[...,None].astype(np.int16));names.append(f'fine{length}_d{distance}_{label}')
    return names,np.concatenate(planes,axis=-1)

def scalar_fine_tail(green,y,x):
    h,w=green.shape
    def at(dy,dx):return int(green[min(h-1,max(0,y+dy)),min(w-1,max(0,x+dx))])
    result=[];g=at(0,0)
    for n in (5,9,15):
        s=[sum(at(a,b) for a,b in offsets(d,n)) for d in DIRS];low=min(s)
        for width in (7,15):
            total=sum(at(a,b) for a in range(-width//2+1,width//2+1) for b in range(-width//2+1,width//2+1))
            result.append(rounded_ratio(16*(total*n-low*width*width),width*width*n))
        result.extend([rounded_ratio(16*(max(s)-low),n),rounded_ratio(16*(low-n*g),n)])
        if n==15:continue
        for distance in (1,2):
            rows=[]
            for j,d in enumerate(DIRS):
                l=sum(at(a,b) for a,b in offsets(d,n,distance))-s[j]
                r=sum(at(a,b) for a,b in offsets(d,n,-distance))-s[j]
                a,b=offsets(d,1,distance)[0];rows.append((min(l,r),abs(l-r),min(at(a,b),at(-a,-b))-g))
            a,b,c=max(enumerate(rows),key=lambda v:(v[1][0],-v[0]))[1]
            result.extend([rounded_ratio(16*a,n),rounded_ratio(16*b,n),c])
    return np.array(result,np.int16)
