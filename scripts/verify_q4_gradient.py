"""Independent dense-kernel Q4-r4 oracle. No candidate module import."""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_q4_training import DIRS, kernel_sum, main
from scripts.verify_q4_fusion import shifted, dense_evidence


def dense_gradient(im, length):
    image = im.astype(np.int16); output = []
    for dy, dx in DIRS:
        coordinates = [(t*dy, t*dx) for t in range(-(length//2), length//2+1)]
        center = kernel_sum(image, coordinates, cv2.BORDER_REPLICATE).astype(np.int32)
        row = []
        for d in range(1, 6):
            def line(k):
                return kernel_sum(image, [(y-k*d*dx, x+k*d*dy) for y, x in coordinates], cv2.BORDER_REPLICATE).astype(np.int32)
            tilt = line(-2)-line(2)
            l = 4*line(1)-4*center+tilt; r = 4*line(-1)-4*center-tilt
            count = np.zeros(image.shape, np.int16)
            for y, x in coordinates:
                cc = shifted(image, y, x).astype(np.int32)
                delta = shifted(image, y+2*d*dx, x-2*d*dy).astype(np.int32)-shifted(image, y-2*d*dx, x+2*d*dy).astype(np.int32)
                ll = 4*(shifted(image, y-d*dx, x+d*dy).astype(np.int32)-cc)+delta
                rr = 4*(shifted(image, y+d*dx, x-d*dy).astype(np.int32)-cc)-delta
                count += (ll > 0) & (rr > 0)
                if y == 0 and x == 0:
                    central = (ll > 0) & (rr > 0)
            row.append((l, r, count, central))
        output.append(row)
    return output


def dense_context(seed, weak, fov, gap_max, context):
    result = seed.copy()
    for (dy, dx), plane in zip(DIRS, weak):
        valid = plane & fov; trusted = seed & valid
        for gap in range(1, gap_max+1):
            n = gap+1
            outer = [(-t*dy, -t*dx) for t in range(context)] + [((n+t)*dy, (n+t)*dx) for t in range(context)]
            endpoints = kernel_sum(trusted, outer) == 2*context
            interior = [(t*dy, t*dx) for t in range(1, n)]
            missing = kernel_sum(seed, interior) == 0
            supported = kernel_sum(valid, interior) == gap
            anchors = endpoints & missing & supported
            result |= kernel_sum(anchors, [(-y, -x) for y, x in interior]) > 0
    return result & fov


def oracle(z, fov, c2, cache, c):
    if not cache:
        cache['gradient'] = {n: dense_gradient(z['filtered'], n) for n in (5, 9)}
        cache['plain'] = {n: dense_evidence(z['filtered'], n) for n in (5, 9)}
    keep = np.zeros_like(c2); per_scale = []
    for length, ev in cache['gradient'].items():
        planes = []
        for row in ev:
            weak = np.zeros_like(c2)
            for l, r, count, central in row:
                balanced = (l <= c['ratio']*r) & (r <= c['ratio']*l)
                keep |= balanced & (l >= 4*length) & (r >= 4*length)
                weak |= balanced & (l >= 8*length) & (r >= 8*length) & central & (count*3 >= length*2)
            planes.append(weak)
        per_scale.append(planes)
    if c['retention'] == 'union':
        for length, ev in cache['plain'].items():
            for row in ev:
                for l, r, _, _ in row:
                    keep |= (l >= length) & (r >= length) & (l <= 8*r) & (r <= 8*l)
    seed = c2 & keep & fov
    weak = [per_scale[0][d] & per_scale[1][d] for d in range(4)]
    return dense_context(seed, weak, fov, c['gap'], c['context']), seed


if __name__ == '__main__':
    main(oracle)
