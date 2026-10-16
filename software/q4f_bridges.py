"""C7-protected directed short paths. Every gap needs two aligned seed arms."""
import numpy as np
from software.q4f_continuity import protection

DIRS=((0,1),(1,0),(1,1),(1,-1))


def sample(a,dy,dx):
    h,w=a.shape;p=max(abs(dy),abs(dx))
    if not p:return a
    padded=np.pad(a,p,mode='constant')
    return padded[p+dy:p+dy+h,p+dx:p+dx+w]


def directed_support(green,dy,dx,margin):
    g=green.astype(np.int16)
    valid=np.zeros(g.shape,bool)
    # Test each transverse scale in the SAME path direction.
    for distance in (1,2):
        l=sample(g,-dx*distance,dy*distance)
        r=sample(g,dx*distance,-dy*distance)
        point=(np.minimum(l,r)-g>=margin)&(l+r-2*g>=2)
        longitudinal=sum(sample(l-g,t*dy,t*dx) for t in (-2,-1,0,1,2))
        opposite=sum(sample(r-g,t*dy,t*dx) for t in (-2,-1,0,1,2))
        valid|=point&(longitudinal>=5)&(opposite>=5)
    return valid


def bridge_mask(green,fov,features,score,c5,parameters,threshold=112):
    seed=(score>=threshold)&fov;protected=protection(green,fov)
    result=seed.copy();links=[]
    low=max(1,threshold-parameters['score_offset'])
    for dy,dx in DIRS:
        supported=directed_support(green,dy,dx,parameters['margin'])
        eligible=(score>=low)&supported&~protected&fov
        for gap in range(1,parameters['max_gap']+1):
            # Both anchor arms must continue in this direction; prevents
            # joining across the normal direction of parallel vessels.
            starts=seed&sample(seed,-dy,-dx)&sample(seed,(gap+1)*dy,(gap+1)*dx)&sample(seed,(gap+2)*dy,(gap+2)*dx)
            for t in range(1,gap+1):
                starts&=sample(seed|eligible,t*dy,t*dx)
            if starts.any():
                links.append((dy,dx,gap,starts))
                for t in range(1,gap+1):result|=sample(starts,-t*dy,-t*dx)&eligible
    return result,dict(seed=seed,protected=protected,links=links)


def candidates(protocol):
    for offset in protocol['score_offsets']:
        for margin in protocol['bilateral_margins']:
            for gap in protocol['max_gaps']:
                yield dict(id=f'C8B_o{offset}_m{margin}_g{gap}',score_offset=offset,
                           margin=margin,max_gap=gap)
