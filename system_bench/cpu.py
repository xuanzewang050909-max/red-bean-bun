"""Same-output CPU comparator, used ONLY by the explicit PS benchmark.

Do not execute discarded C5 intermediates just to make the CPU slower. C7 final
words contain raw G, enhanced G, C7 mask and C7 score; compute exactly those.
The unchanged frozen feature/forest/reference sources live in bench_reference.
Model parsing is setup; feature extraction and output allocation are timed.
"""
import numpy as np
from bench_reference.q4d_features import integer_features
from bench_reference.q4d_forest import predict_integer
from bench_reference.reference import gaussian3, LUT


def compute(words, model, threshold=112):
    if words.dtype != np.uint32 or words.shape not in ((256, 256), (512, 512)):
        raise ValueError('Expected frozen 256/512 uint32 input')
    if threshold != 112:
        raise ValueError('This performance protocol fixes C7 threshold 112')
    raw = ((words >> 8) & 255).astype(np.uint8)
    enhanced = LUT[gaussian3(raw)]
    names, features = integer_features(raw)
    if names != model['features']:
        raise ValueError('Frozen model schema mismatch')
    score = predict_integer(features, model)
    mask = (score >= threshold) & ((words >> 24) != 0)
    return (raw.astype(np.uint32) | (enhanced.astype(np.uint32) << 8) |
            (mask.astype(np.uint32) * 255 << 16) | (score.astype(np.uint32) << 24))
