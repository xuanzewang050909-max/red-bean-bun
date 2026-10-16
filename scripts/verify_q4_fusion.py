"""Independent dense-filter Q4-r3 oracle; does not import q4_fusion."""
import sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_q4_training import DIRS, kernel_sum, bridges, main


def shifted(image, dy, dx):
    # Explicit coordinates rather than the candidate's padding/slicing helper.
    y = np.clip(np.arange(image.shape[0]) + dy, 0, image.shape[0]-1)
    x = np.clip(np.arange(image.shape[1]) + dx, 0, image.shape[1]-1)
    return image[y[:, None], x[None, :]]


def dense_evidence(im, length):
    im = im.astype(np.int16)
    rows = []
    for dy, dx in DIRS:
        offsets = [(t*dy, t*dx) for t in range(-(length//2), length//2+1)]
        center = kernel_sum(im, offsets, cv2.BORDER_REPLICATE).astype(np.int32)
        row = []
        for d in range(1, 6):
            l = kernel_sum(im, [(y-d*dx, x+d*dy) for y, x in offsets], cv2.BORDER_REPLICATE).astype(np.int32)-center
            r = kernel_sum(im, [(y+d*dx, x-d*dy) for y, x in offsets], cv2.BORDER_REPLICATE).astype(np.int32)-center
            central = (shifted(im, -d*dx, d*dy) > im) & (shifted(im, d*dx, -d*dy) > im)
            # At diagonal borders the comparison must clamp each source sample
            # before comparing; filtering a padded central bool would differ.
            count = sum(((shifted(im, y-d*dx, x+d*dy) > shifted(im, y, x)) &
                         (shifted(im, y+d*dx, x-d*dy) > shifted(im, y, x))).astype(np.int16)
                        for y, x in offsets)
            row.append((l, r, count, central))
        rows.append(row)
    return rows


def oracle(z, fov, c2, cache, c):
    for length in c['lengths']:
        if length not in cache:
            cache[length] = dense_evidence(z['filtered'], length)
    keep = np.zeros_like(c2); per_scale = []
    for length in c['lengths']:
        planes = []
        for row in cache[length]:
            weak = np.zeros_like(c2)
            for l, r, count, center in row:
                balanced = (l <= c['ratio']*r) & (r <= c['ratio']*l)
                keep |= balanced & (l >= max(1, length*c['retain_margin'])) & (r >= max(1, length*c['retain_margin']))
                weak |= balanced & (l >= length*c['add_margin']) & (r >= length*c['add_margin']) & center & (count*3 >= length*2)
            planes.append(weak)
        per_scale.append(planes)
    seed = c2 & keep & fov
    weak = [np.logical_and.reduce([row[d] for row in per_scale]) for d in range(4)]
    return bridges(seed, weak, fov, c['gap']), seed


if __name__ == '__main__':
    main(oracle)
