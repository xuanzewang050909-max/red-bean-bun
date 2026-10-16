"""Q4a offline research: balanced flanks and bounded, supported gap filling.

No labels, annotation-dependent regions, service imports, or board fallback.
All new operations use integer arithmetic and finite local windows.
"""
from itertools import product

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.reference import segment


def candidates():
    for feature, ratio, margin, gap in product(
            ("enhanced", "filtered"), (2, 4), (1, 2), (0, 1, 3)):
        yield {"id": f"C3_{feature}_r{ratio}_m{margin}_g{gap}",
               "feature": feature, "ratio": ratio, "margin": margin, "gap": gap}
    for gap in (1, 3):
        yield {"id": f"C2_bridge_g{gap}", "feature": "C2", "ratio": None,
               "margin": None, "gap": gap}


def sample(image, dy, dx, mode="edge"):
    """Return image[y+dy,x+dx], with independent edge/zero padding."""
    r = max(abs(dy), abs(dx))
    if not r:
        return image
    padded = np.pad(image, r, mode=mode)
    h, w = image.shape
    return padded[r + dy:r + dy + h, r + dx:r + dx + w]


def flank_features(image, length=9):
    if image.dtype != np.uint8 or image.ndim != 2 or length != 9:
        raise ValueError("Q4 expects uint8 image and length 9")
    source = image.astype(np.int16)
    result = []
    for dy, dx in DIRECTIONS:
        center = sum(sample(source, t * dy, t * dx) for t in range(-4, 5))
        pairs = []
        for d in range(1, 6):
            # Sum-then-shift is not identical to coordinate replication at a
            # diagonal border. Directly sum the flank there (and everywhere).
            left = sum(sample(source, t * dy - d * dx, t * dx + d * dy)
                       for t in range(-4, 5)) - center
            right = sum(sample(source, t * dy + d * dx, t * dx - d * dy)
                        for t in range(-4, 5)) - center
            pairs.append((np.minimum(left, right), np.maximum(left, right)))
        result.append(pairs)
    return result


def balanced_support(flanks, ratio, margin):
    if ratio not in (2, 4) or margin not in (1, 2):
        raise ValueError("Outside frozen grid")
    return [np.logical_or.reduce([(small >= 9 * margin) &
                                   (large.astype(np.int32) <= ratio * small.astype(np.int32))
                                   for small, large in pairs]) for pairs in flanks]


def bridge_gaps(mask, weak_directions, fov, max_gap):
    """Single pass. Two original foreground endpoints; every interior pixel
    missing, in the FOV, and photometrically supported in the same direction.
    New pixels never seed another connection. Returns masks for link auditing.
    """
    if (mask.dtype != np.bool_ or fov.dtype != np.bool_ or mask.shape != fov.shape
            or max_gap not in (0, 1, 3) or len(weak_directions) != 4):
        raise ValueError("Invalid mask/FOV/gap")
    added = np.zeros_like(mask)
    links = []
    for (dy, dx), weak in zip(DIRECTIONS, weak_directions):
        valid = weak & fov
        for gap in range(1, max_gap + 1):
            distance = gap + 1
            anchor = mask & valid & sample(mask & valid, distance * dy, distance * dx, "constant")
            for t in range(1, distance):
                anchor &= sample(~mask & valid, t * dy, t * dx, "constant")
            for t in range(1, distance):
                added |= sample(anchor, -t * dy, -t * dx, "constant")
            links.append((dy, dx, gap, anchor))
    return (mask | added) & fov, links


def refined_mask(feat, fov, c2_mask, cache, candidate):
    if candidate["feature"] == "C2":
        seed = c2_mask
    else:
        support = np.logical_or.reduce(balanced_support(
            cache[candidate["feature"]], candidate["ratio"], candidate["margin"]))
        response = np.maximum(0, feat["response"].astype(np.int16) - (~support) * 28).astype(np.uint8)
        seed = segment(response, fov, 28)
    weak = balanced_support(cache["filtered"], 4, 1)
    final, links = bridge_gaps(seed, weak, fov, candidate["gap"])
    return final, seed, links
