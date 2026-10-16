"""Image-only integer feature audit. No segmentation, labels or board fallback.

Gaussian dark-line / signed derivative kernels motivate the study, but this
quantized, direction-paired feature bank is not a reproduction of MF-FDOG.
"""
from functools import lru_cache
import math

import cv2
import numpy as np

SCALES = ((1.0, 5), (1.5, 9))
ANGLES = 8
EDGE_WINDOW = 31
COHERENCE_WINDOW = 7


@lru_cache(None)
def kernels():
    bank = []
    for sigma, length in SCALES:
        radius = math.ceil(math.hypot(3*sigma, length//2))
        y, x = np.mgrid[-radius:radius+1, -radius:radius+1]
        for direction in range(ANGLES):
            theta = direction*math.pi/ANGLES
            u = -y*math.cos(theta)+x*math.sin(theta)
            v = y*math.sin(theta)+x*math.cos(theta)
            area = (np.abs(u) <= 3*sigma+1e-12) & (np.abs(v) <= length//2+1e-12)
            g = np.exp(-u*u/(2*sigma*sigma))
            mf = np.where(area, g[area].mean()-g, 0.0)
            dog = np.where(area, u*g/(sigma*sigma), 0.0)
            def quantize(a):
                k = np.rint(a*256/a[a > 0].sum()).astype(np.int32)
                # Exact zero DC after rounding; inversion symmetry is preserved.
                k[radius, radius] -= int(k.sum())
                k.setflags(write=False)
                return k
            km, kd = quantize(mf), quantize(dog)
            bank.append({'sigma': sigma, 'length': length, 'direction': direction,
                         'mf': km, 'dog': kd})
    return tuple(bank)


def correlate_integer(image, kernel):
    # The largest integer sum is much smaller than 2**53; CV64 avoids int16 overflow.
    raw = cv2.filter2D(image.astype(np.float64), cv2.CV_64F,
                       kernel.astype(np.float64), borderType=cv2.BORDER_REPLICATE)
    rounded = np.rint(raw)
    if not np.allclose(raw, rounded, rtol=0, atol=1e-6):
        raise ArithmeticError('Non-integer convolution result')
    return rounded.astype(np.int32)


def normalized_response(image, kernel):
    total = correlate_integer(image, kernel).astype(np.int64)
    denominator = int(kernel[kernel > 0].sum())
    return ((total*256+denominator//2)//denominator).astype(np.int32)


def signed_mean(image, width):
    sums = correlate_integer(image, np.ones((width, width), np.int32))
    return ((sums.astype(np.int64)+width*width//2)//(width*width)).astype(np.int32)


def profile_features(image):
    """Return six uint16 maps in Q8 grey units, plus Q8 orientation coherence.

    Highest-MF direction/scale wins with first-index ties. Edge cost is absolute
    *after* signed spatial averaging, paired with that same direction/scale.
    """
    if image.dtype != np.uint8 or image.ndim != 2 or not all(image.shape):
        raise ValueError('Expected nonempty uint8 image')
    responses = []; edge_responses = []
    for item in kernels():
        responses.append(normalized_response(image, item['mf']))
        signed = normalized_response(image, item['dog'])
        edge_responses.append(np.abs(signed_mean(signed, EDGE_WINDOW)))
    values = np.stack(responses)
    winner = values.argmax(axis=0)
    mf = np.maximum(0, np.take_along_axis(values, winner[None], axis=0)[0])
    edge = np.take_along_axis(np.stack(edge_responses), winner[None], axis=0)[0]
    direction = winner % ANGLES
    coherent = np.zeros(image.shape, np.int32)
    for k in range(ANGLES):
        delta = (direction-k) % ANGLES
        near = ((delta <= 1) | (delta == ANGLES-1)) & (mf > 0)
        total = correlate_integer(near.astype(np.uint8), np.ones((COHERENCE_WINDOW,)*2, np.int32))
        coherent[direction == k] = total[direction == k]
    coherence = (coherent*256+24)//49
    shape = (mf.astype(np.int64)*256//(256+edge)).astype(np.int32)
    coherent_shape = ((shape.astype(np.int64)*coherence+128)//256).astype(np.int32)
    result = {'mf_small': np.maximum(0, values[:ANGLES].max(axis=0)),
              'mf_large': np.maximum(0, values[ANGLES:].max(axis=0)),
              'mf_max': mf, 'paired_edge': edge, 'shape': shape,
              'coherence': coherence, 'coherent_shape': coherent_shape}
    if any(a.min() < 0 or a.max() > 65535 for a in result.values()):
        raise ArithmeticError('Feature outside declared uint16 range')
    return {name: a.astype(np.uint16) for name, a in result.items()}
