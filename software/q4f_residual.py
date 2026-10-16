"""Frozen C7 plus normalized residual detector. Integer-only reference."""
import numpy as np
from software.q4f_continuity import protection

NORMALIZED=(1,2,3,6,7,8,10,13,16,19,20,21,23,26,29,32,33,34)

def residual_features(features,score):
    # Q12 reciprocal of local contrast range+8. Only a 256-entry constant LUT
    # and shared multiplies; truncation and clipping explicit for PL.
    dynamic_range=features[...,4].astype(np.int32)+features[...,5].astype(np.int32)
    reciprocal=(4096*32)//(dynamic_range+8)
    columns=[features,score[...,None].astype(np.int16)]
    for index in NORMALIZED:
        product=features[...,index].astype(np.int32)*reciprocal
        value=np.where(product>=0,(product+2048)//4096,-((-product+2048)//4096))
        columns.append(np.clip(value,-255,255).astype(np.int16)[...,None])
    return np.concatenate(columns,axis=-1)

def combine(green,fov,c7_score,residual_score,threshold=160,base_threshold=112):
    seed=(c7_score>=base_threshold)&fov
    return seed|((residual_score>=threshold)&~protection(green,fov)&fov)
