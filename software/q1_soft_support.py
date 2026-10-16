"""Q1-r2 OFFLINE candidate. No GT and no import by the production service."""
from itertools import product

import numpy as np

from software.q1_bilateral import DIRECTIONS, directional_evidence as r1_evidence


def candidates():
    for length, distances, margin, penalty in product(
            (5, 9), ((1, 2, 3), (1, 2, 3, 4, 5)), (0, 1), (4, 8, 16, 28)):
        yield {"id": f"C2_l{length}_d{''.join(map(str, distances))}_m{margin}_p{penalty}",
               "length": length, "distances": distances, "margin": margin,
               "persistence": "none", "penalty": penalty}


def directional_evidence(enhanced, length, distance):
    if distance in (1, 2, 3):
        return r1_evidence(enhanced, length, distance)
    if (distance not in (4, 5) or length not in (5, 9) or enhanced.ndim != 2 or
            enhanced.dtype != np.uint8 or not all(enhanced.shape)):
        raise ValueError("Expected uint8 image and preregistered r2 offsets")
    h, w = enhanced.shape
    radius = length // 2 + distance
    padded = np.pad(enhanced.astype(np.int16), radius, mode="edge")

    def shifted(dy, dx):
        return padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w]

    result = []
    for dy, dx in DIRECTIONS:
        left_sum = np.zeros((h, w), np.int16)
        right_sum = np.zeros((h, w), np.int16)
        count = np.zeros((h, w), np.uint8)
        for t in range(-(length // 2), length // 2 + 1):
            center = shifted(t * dy, t * dx)
            left = shifted(t * dy - distance * dx, t * dx + distance * dy) - center
            right = shifted(t * dy + distance * dx, t * dx - distance * dy) - center
            left_sum += left
            right_sum += right
            count += (left > 0) & (right > 0)
        result.append((np.minimum(left_sum, right_sum), count))
    return result


def softened_response(response, cache, candidate):
    length, margin, penalty = candidate["length"], candidate["margin"], candidate["penalty"]
    distances = tuple(candidate["distances"])
    if (length not in (5, 9) or margin not in (0, 1) or penalty not in (4, 8, 16, 28)
            or distances not in ((1, 2, 3), (1, 2, 3, 4, 5)) or candidate["persistence"] != "none"
            or response.ndim != 2 or response.dtype != np.uint8):
        raise ValueError("Outside preregistered r2 grid")
    supported = np.zeros(response.shape, bool)
    for distance in distances:
        for support, _count in cache[length][distance]:
            supported |= support > 0 if margin == 0 else support >= length * margin
    return np.maximum(0, response.astype(np.int16) - (~supported).astype(np.int16) * penalty).astype(np.uint8)
