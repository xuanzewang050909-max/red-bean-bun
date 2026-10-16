"""Offline Q4-r2: build new unsaturated directional ridge responses, not mask repair."""
from itertools import product

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_refinement import sample
from software.reference import segment


def candidates():
    for ratio, gain, (low, steps) in product((2,4,8),(4,8,12),((0,0),(14,4),(21,4))):
        yield {'id':f'C4_r{ratio}_k{gain}_lo{low}_s{steps}', 'ratio':ratio,'gain':gain,
               'low':low,'steps':steps,'gap':steps}


def directional_scores(flanks, ratio, gain):
    scores=[]
    for row in flanks:
        best=np.maximum.reduce([np.where((small>0)&(large.astype(np.int32)<=ratio*small.astype(np.int32)),small,0)
                                for small,large in row]).astype(np.int32)
        scores.append(np.minimum(255,(best*gain+4)//9).astype(np.uint8))
    return scores


def directional_growth(scores,fov,low,steps):
    seeds=[(s>=28)&fov for s in scores]
    grown=[]
    for (dy,dx),s,seed in zip(DIRECTIONS,scores,seeds):
        current=seed.copy();weak=(s>=low)&fov
        for _ in range(steps):
            current |= weak & (sample(current,dy,dx,'constant') | sample(current,-dy,-dx,'constant'))
        grown.append(current)
    return np.logical_or.reduce(grown),np.logical_or.reduce(seeds)


def ridge_mask(feat,fov,c2_mask,cache,candidate):
    scores=directional_scores(cache['filtered'],candidate['ratio'],candidate['gain'])
    grown,seed=directional_growth(scores,fov,candidate['low'],candidate['steps'])
    return segment(grown.astype(np.uint8)*255,fov,28),segment(seed.astype(np.uint8)*255,fov,28),[]
