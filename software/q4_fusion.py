"""Q4-r3 training-only multiscale C2 fusion. No labels or production imports.

Finite windows and one-pass connections are intended for a later PL feasibility
study only if the preregistered quality gates pass. This is NOT a board driver.
"""
from itertools import product

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_refinement import sample, bridge_gaps


def candidates():
    for lengths, ratio, retain_margin in product(((5, 9), (5, 9, 15)), (4, 8), (0, 1)):
        base = {'lengths': list(lengths), 'ratio': ratio, 'retain_margin': retain_margin}
        prefix = f"C5_l{'_'.join(map(str, lengths))}_r{ratio}_m{retain_margin}"
        yield dict(base, id=prefix + '_noadd', add_margin=0, gap=0)
        for add_margin, gap in product((2, 4), (1, 3)):
            yield dict(base, id=f'{prefix}_a{add_margin}_g{gap}', add_margin=add_margin, gap=gap)


def evidence(image, length):
    if image.dtype != np.uint8 or image.ndim != 2 or not all(image.shape) or length not in (5, 9, 15):
        raise ValueError('Expected a nonempty uint8 image and length 5/9/15')
    source = image.astype(np.int16)
    result = []
    for dy, dx in DIRECTIONS:
        pairs = []
        for distance in range(1, 6):
            left = np.zeros_like(source); right = np.zeros_like(source)
            positive_count = np.zeros(image.shape, np.uint8)
            for t in range(-(length // 2), length // 2 + 1):
                center = sample(source, t * dy, t * dx)
                l = sample(source, t * dy - distance * dx, t * dx + distance * dy) - center
                r = sample(source, t * dy + distance * dx, t * dx - distance * dy) - center
                left += l; right += r
                positive_count += (l > 0) & (r > 0)
                if t == 0:
                    central = (l > 0) & (r > 0)
            pairs.append((np.minimum(left, right), np.maximum(left, right), positive_count, central))
        result.append(pairs)
    return result


def scale_support(ev, length, ratio, margin, persistent):
    support = []
    for row in ev:
        passing = []
        for small, large, count, center in row:
            valid = (small >= max(1, length * margin)) & (large.astype(np.int32) <= ratio * small.astype(np.int32))
            if persistent:
                valid &= center & (count.astype(np.int16) * 3 >= length * 2)
            passing.append(valid)
        support.append(np.logical_or.reduce(passing))
    return support


def fusion_mask(feat, fov, c2_mask, cache, candidate):
    # The cache is local to one image/size in the existing evaluator.
    multiscale = cache.setdefault('r3_multiscale', {})
    for length in candidate['lengths']:
        if length not in multiscale:
            multiscale[length] = evidence(feat['filtered'], length)
    memo = cache.setdefault('r3_supports', {})
    def supports(length, margin, persistent):
        key = (length, candidate['ratio'], margin, persistent)
        if key not in memo:
            memo[key] = scale_support(multiscale[length], length, candidate['ratio'], margin, persistent)
        return memo[key]

    # Existing C2 pixels survive if ANY scale/direction has balanced support.
    retain = np.logical_or.reduce([plane for length in candidate['lengths']
                                   for plane in supports(length, candidate['retain_margin'], False)])
    seed = c2_mask & retain & fov
    if not candidate['gap']:
        return seed, seed, []
    # New pixels require EVERY selected scale in the SAME direction, positive
    # central bilateral contrast and >=2/3 supported centerline samples.
    per_scale = [supports(length, candidate['add_margin'], True) for length in candidate['lengths']]
    weak = [np.logical_and.reduce([planes[d] for planes in per_scale]) for d in range(4)]
    return_value, links = bridge_gaps(seed, weak, fov, candidate['gap'])
    # No subsequent dilation/closing: every added pixel is explicitly audited.
    return return_value, seed, links
