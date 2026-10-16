"""C7-protected bounded recovery with residual confidence and raw dark ridges."""
import numpy as np
from software.q4f_continuity import protection,bounded_reconstruct
from software.q4f_bridges import DIRS,directed_support

def mask(green,fov,c7_score,residual_score,parameters):
    seed=(c7_score>=112)&fov
    ridge=np.zeros_like(fov)
    for dy,dx in DIRS:ridge|=directed_support(green,dy,dx,parameters['margin'])
    eligible=(residual_score>=parameters['threshold'])&ridge&~protection(green,fov)&fov
    return bounded_reconstruct(seed,eligible,parameters['steps'])

def candidates(protocol):
    for n in protocol['trees']:
        for threshold in protocol['thresholds']:
            for steps in protocol['steps']:
                for margin in protocol['margins']:
                    yield dict(id=f'C8P_n{n}_d8_t{threshold}_s{steps}_m{margin}',trees=n,depth=8,
                               threshold=threshold,steps=steps,margin=margin)
