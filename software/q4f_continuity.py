"""C8 image-only conservative C7 extension; CPU reference, not board inference.

The raw 17x17 maximum protects a superset of Gaussian3>=192 dilated by
radius seven: every such Gaussian has a raw sample >=192 within radius one.
No new pixels are allowed inside this superset, even during propagation.
No input to inference is an annotation, image ID, coordinate, or manual ROI.
"""
import cv2
import numpy as np


def protection(green, fov):
    k = np.ones((17, 17), np.uint8)
    high = cv2.dilate(green, k, borderType=cv2.BORDER_REPLICATE)
    inner = cv2.erode(fov.astype(np.uint8), k,
                     borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    return (high >= 192) | ~inner


def eligible_pixels(features, score, c5, protected, low, margin, include_c5):
    # Winning bilateral direction must have both longitudinal and central
    # support. Reuse frozen C7 features; no new classifier or label fitting.
    supported = ((features[..., 10] >= margin) & (features[..., 12] >= 0)) | \
                ((features[..., 13] >= margin) & (features[..., 15] >= 0))
    weak = (score >= low) | (c5 if include_c5 else False)
    return weak & supported & ~protected


def bounded_reconstruct(seed, eligible, steps):
    if steps < 0 or steps > 8:
        raise ValueError('Fixed bounded reconstruction permits 0..8 steps')
    current = seed.copy()
    k = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        adjacent = cv2.dilate(current.astype(np.uint8), k,
                              borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
        current = seed | (eligible & adjacent)
    return current


def candidate_mask(green, fov, features, score, c5, parameters, threshold=112):
    seed = (score >= threshold) & fov
    protected = protection(green, fov)
    # Low threshold is a fixed offset from the interactive C7 high threshold.
    low = max(1, threshold - parameters['score_offset'])
    eligible = eligible_pixels(features, score, c5, protected, low,
                               parameters['margin'], parameters['include_c5'])
    result = bounded_reconstruct(seed, eligible, parameters['steps']) & fov
    return result, dict(seed=seed, protected=protected, eligible=eligible)


def candidates(protocol):
    for offset in protocol['score_offsets']:
        for margin in protocol['bilateral_margins']:
            for steps in protocol['propagation_steps']:
                for include_c5 in protocol['include_c5_options']:
                    yield dict(id=f'C8_o{offset}_m{margin}_s{steps}_c{int(include_c5)}',
                               score_offset=offset, margin=margin, steps=steps,
                               include_c5=include_c5)
