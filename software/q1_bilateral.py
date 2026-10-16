"""Q1-r1 integer candidate, OFFLINE RESEARCH ONLY; never a production fallback.

The frozen protocol is docs/q1_bilateral_protocol_r1.json. This module accepts
images/features only. Training annotations belong in the separate evaluator.
"""
from itertools import product

import numpy as np

from software.reference import segment

DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def candidates():
    for length, distances, margin, persistence in product(
            (5, 9), ((1,), (2,), (3,), (1, 2, 3)), (0, 1, 2, 4),
            ("none", "majority")):
        yield {"id": f"C_l{length}_d{''.join(map(str, distances))}_m{margin}_{persistence}",
               "length": length, "distances": distances, "margin": margin,
               "persistence": persistence}


def directional_evidence(enhanced, length, distance):
    """Exact signed flank sums and positive-pair counts, four grid directions.

    Each int16 sum is in [-2295,2295]; pointwise differences are [-255,255].
    Image padding replicates independently on both axes. No FOV is changed.
    """
    if (enhanced.ndim != 2 or enhanced.dtype != np.uint8 or
            not all(enhanced.shape) or length not in (5, 9) or distance not in (1, 2, 3)):
        raise ValueError("Expected nonempty uint8 image, length5/9, distance1/2/3")
    h, w = enhanced.shape
    radius = length // 2 + distance
    padded = np.pad(enhanced.astype(np.int16), radius, mode="edge")

    def shifted(dy, dx):
        return padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w]

    results = []
    for dy, dx in DIRECTIONS:
        py, px = -dx, dy
        left_sum = np.zeros((h, w), np.int16)
        right_sum = np.zeros((h, w), np.int16)
        count = np.zeros((h, w), np.uint8)
        for t in range(-(length // 2), length // 2 + 1):
            center = shifted(t * dy, t * dx)
            left = shifted(t * dy + distance * py, t * dx + distance * px) - center
            right = shifted(t * dy - distance * py, t * dx - distance * px) - center
            left_sum += left
            right_sum += right
            count += (left > 0) & (right > 0)
        results.append((np.minimum(left_sum, right_sum), count))
    return results


def support_mask(evidence_by_distance, length, distances, margin, persistence):
    if (length not in (5, 9) or tuple(distances) not in ((1,), (2,), (3,), (1, 2, 3))
            or margin not in (0, 1, 2, 4) or persistence not in ("none", "majority")):
        raise ValueError("Outside preregistered Q1-r1 grid")
    shape = evidence_by_distance[distances[0]][0][0].shape
    passing = np.zeros(shape, bool)
    for distance in distances:
        for support, count in evidence_by_distance[distance]:
            accepted = support > 0 if margin == 0 else support >= length * margin
            if persistence == "majority":
                accepted &= count >= (length + 1) // 2
            passing |= accepted
    return passing


def candidate_mask(response, fov, support):
    if (response.ndim != 2 or response.dtype != np.uint8 or
            fov.dtype != np.bool_ or support.dtype != np.bool_ or
            response.shape != fov.shape or response.shape != support.shape):
        raise ValueError("Expected aligned uint8 response and bool FOV/support")
    return segment(np.where(support, response, np.uint8(0)), fov, 28)
