"""Q4-r4 offline local-gradient compensation and endpoint-context study.

Image-only finite integer operations. No label, PYNQ, network or driver input.
This code is not a production segmentation fallback or a new FPGA result.
"""
from itertools import product

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_refinement import sample
from software.q4_fusion import evidence as plain_evidence, scale_support


def candidates():
    for ratio, retention in product((2, 4), ('gradient', 'union')):
        base = {'ratio': ratio, 'retention': retention}
        prefix = f'C6_r{ratio}_{retention}'
        yield dict(base, id=prefix + '_noadd', context=0, gap=0)
        for context, gap in product((1, 3, 5), (1, 3)):
            yield dict(base, id=f'{prefix}_e{context}_g{gap}', context=context, gap=gap)


def gradient_evidence(image, length):
    if image.dtype != np.uint8 or image.ndim != 2 or not all(image.shape) or length not in (5, 9):
        raise ValueError('Expected nonempty uint8 image and length5/9')
    source = image.astype(np.int32)
    result = []
    for dy, dx in DIRECTIONS:
        row = []
        for distance in range(1, 6):
            left = np.zeros(image.shape, np.int32); right = np.zeros_like(left)
            count = np.zeros(image.shape, np.uint8)
            for t in range(-(length//2), length//2+1):
                y, x = t*dy, t*dx
                py, px = -distance*dx, distance*dy
                center = sample(source, y, x)
                # Four times the detrended flank contrast. A linear grey ramp
                # cancels exactly in unclipped interior samples, no division.
                slope4 = sample(source, y-2*py, x-2*px)-sample(source, y+2*py, x+2*px)
                l = 4*(sample(source, y+py, x+px)-center)+slope4
                r = 4*(sample(source, y-py, x-px)-center)-slope4
                left += l; right += r
                count += (l > 0) & (r > 0)
                if t == 0:
                    central = (l > 0) & (r > 0)
            row.append((np.minimum(left, right), np.maximum(left, right), count, central))
        result.append(row)
    return result


def gradient_support(ev, length, ratio, margin, persistent):
    planes = []
    for row in ev:
        accepted = []
        for small, large, count, central in row:
            valid = (small >= 4*length*margin) & (large <= ratio*small)
            if persistent:
                valid &= central & (count.astype(np.int16)*3 >= length*2)
            accepted.append(valid)
        planes.append(np.logical_or.reduce(accepted))
    return planes


def context_bridges(seed, weak, fov, gap_max, context):
    """One pass, two original endpoints plus backward/forward seed context.

    Every interior point is absent and photometrically supported; every
    exterior context point is an original seed and supported in that direction.
    """
    if gap_max not in (0, 1, 3) or context not in (0, 1, 3, 5):
        raise ValueError('Outside preregistered context/gap grid')
    if gap_max and not context:
        raise ValueError('Nonzero gap requires endpoint context')
    added = np.zeros_like(seed); links = []
    for (dy, dx), plane in zip(DIRECTIONS, weak):
        valid = plane & fov; trusted = seed & valid
        for gap in range(1, gap_max+1):
            n = gap+1
            anchors = trusted & sample(trusted, n*dy, n*dx, 'constant')
            for t in range(1, n):
                anchors &= sample(~seed & valid, t*dy, t*dx, 'constant')
            for t in range(1, context):
                anchors &= sample(trusted, -t*dy, -t*dx, 'constant')
                anchors &= sample(trusted, (n+t)*dy, (n+t)*dx, 'constant')
            for t in range(1, n):
                added |= sample(anchors, -t*dy, -t*dx, 'constant')
            links.append((dy, dx, gap, anchors))
    return (seed | added) & fov, links


def gradient_mask(feat, fov, c2_mask, cache, candidate):
    if 'r4_evidence' not in cache:
        cache['r4_evidence'] = {n: gradient_evidence(feat['filtered'], n) for n in (5, 9)}
    memo = cache.setdefault('r4_support', {})
    def support(length, margin, persistent):
        key = (length, candidate['ratio'], margin, persistent)
        if key not in memo:
            memo[key] = gradient_support(cache['r4_evidence'][length], length, candidate['ratio'], margin, persistent)
        return memo[key]
    keep = np.logical_or.reduce([p for n in (5, 9) for p in support(n, 1, False)])
    if candidate['retention'] == 'union':
        if 'r4_plain_keep' not in cache:
            cache['r4_plain_keep'] = np.logical_or.reduce([p for n in (5, 9)
                for p in scale_support(plain_evidence(feat['filtered'], n), n, 8, 1, False)])
        keep |= cache['r4_plain_keep']
    seed = c2_mask & keep & fov
    if not candidate['gap']:
        return seed, seed, []
    per_scale = [support(n, 2, True) for n in (5, 9)]
    weak = [per_scale[0][d] & per_scale[1][d] for d in range(4)]
    final, links = context_bridges(seed, weak, fov, candidate['gap'], candidate['context'])
    return final, seed, links
