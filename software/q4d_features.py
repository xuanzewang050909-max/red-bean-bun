"""C7 image-only integer local features. No labels, coordinates or image IDs.

All neighborhoods fit in a 17x17 raw-green window with replicate boundaries.
Integer half-up means and first-direction ties are part of the hardware spec.
"""
import cv2
import numpy as np

DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def shift(padded, shape, dy, dx):
    h, w = shape
    return padded[8 + dy:8 + dy + h, 8 + dx:8 + dx + w]


def integer_features(green):
    if green.dtype != np.uint8 or green.ndim != 2 or not all(green.shape):
        raise ValueError('Expected nonempty uint8 green plane')
    g = green.astype(np.int32)
    p = np.pad(g, 8, mode='edge')
    names, planes = [], []
    def add(name, value):
        if value.min() < -255 or value.max() > 255:
            raise ArithmeticError('Feature outside signed 10-bit range: ' + name)
        names.append(name); planes.append(value.astype(np.int16))
    means = {}
    add('green', g)
    for width in (3, 7, 15):
        total = cv2.boxFilter(g.astype(np.float64), cv2.CV_64F, (width, width),
                             normalize=False, borderType=cv2.BORDER_REPLICATE)
        means[width] = (np.rint(total).astype(np.int32) + width * width // 2) // (width * width)
        add(f'mean{width}_minus_green', means[width] - g)
    kernel = np.ones((15, 15), np.uint8)
    add('max15_minus_green', cv2.dilate(green, kernel, borderType=cv2.BORDER_REPLICATE).astype(np.int32) - g)
    add('green_minus_min15', g - cv2.erode(green, kernel, borderType=cv2.BORDER_REPLICATE).astype(np.int32))
    for length in (5, 9, 15):
        center_sums = []
        for dy, dx in DIRECTIONS:
            center_sums.append(sum(shift(p, g.shape, t * dy, t * dx)
                                   for t in range(-length // 2 + 1, length // 2 + 1)))
        centers = [(x + length // 2) // length for x in center_sums]
        smallest = np.minimum.reduce(centers); largest = np.maximum.reduce(centers)
        add(f'line{length}_mean7_contrast', means[7] - smallest)
        add(f'line{length}_mean15_contrast', means[15] - smallest)
        add(f'line{length}_direction_spread', largest - smallest)
        add(f'line{length}_center_offset', smallest - g)
        if length == 15:
            continue
        for distance in (1, 2, 4):
            smalls, imbalances, central_support = [], [], []
            for (dy, dx), center in zip(DIRECTIONS, center_sums):
                left = sum(shift(p, g.shape, t * dy - distance * dx, t * dx + distance * dy)
                           for t in range(-length // 2 + 1, length // 2 + 1)) - center
                right = sum(shift(p, g.shape, t * dy + distance * dx, t * dx - distance * dy)
                            for t in range(-length // 2 + 1, length // 2 + 1)) - center
                smalls.append(np.minimum(left, right))
                imbalances.append(np.abs(left - right))
                central_support.append(np.minimum(shift(p, g.shape, -distance * dx, distance * dy),
                                                   shift(p, g.shape, distance * dx, -distance * dy)) - g)
            smalls = np.stack(smalls)
            winner = smalls.argmax(axis=0)[None]
            choose = lambda x: np.take_along_axis(np.stack(x), winner, axis=0)[0]
            prefix = f'bilateral{length}_d{distance}_'
            add(prefix + 'minimum', (np.take_along_axis(smalls, winner, axis=0)[0] + length // 2) // length)
            add(prefix + 'imbalance', (choose(imbalances) + length // 2) // length)
            add(prefix + 'central', choose(central_support))
    return names, np.stack(planes, axis=-1)


def scalar_features(green, y, x):
    """Independent small-window oracle; intentionally no vectorized operations."""
    h, w = green.shape
    def at(dy, dx):
        return int(green[min(h - 1, max(0, y + dy)), min(w - 1, max(0, x + dx))])
    center = at(0, 0)
    means = {s: (sum(at(i, j) for i in range(-s // 2 + 1, s // 2 + 1)
                     for j in range(-s // 2 + 1, s // 2 + 1)) + s * s // 2) // (s * s) for s in (3, 7, 15)}
    region = [at(i, j) for i in range(-7, 8) for j in range(-7, 8)]
    result = [center, *(means[s] - center for s in (3, 7, 15)), max(region) - center, center - min(region)]
    for length in (5, 9, 15):
        positions = range(-(length // 2), length // 2 + 1)
        centers = [sum(at(t * dy, t * dx) for t in positions) for dy, dx in DIRECTIONS]
        line_means = [(s + length // 2) // length for s in centers]
        low = min(line_means)
        result += [means[7] - low, means[15] - low, max(line_means) - low, low - center]
        if length == 15:
            continue
        for d in (1, 2, 4):
            records = []
            for (dy, dx), c in zip(DIRECTIONS, centers):
                l = sum(at(t * dy - d * dx, t * dx + d * dy) for t in positions) - c
                r = sum(at(t * dy + d * dx, t * dx - d * dy) for t in positions) - c
                records.append((min(l, r), abs(l - r), min(at(-d * dx, d * dy), at(d * dx, -d * dy)) - center))
            best = max(range(4), key=lambda i: records[i][0])
            a, b, c = records[best]
            result += [(a + length // 2) // length, (b + length // 2) // length, c]
    return np.array(result, np.int16)
