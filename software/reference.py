"""Integer golden models. No GT argument and no floating convolution."""
import numpy as np

LUT = np.minimum(255, (np.arange(256, dtype=np.uint16) * 255 + 96) // 192).astype(np.uint8)
CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


def correlate(image, kernel):
    """Signed int32 accumulate; replicate borders, identical for every model."""
    h, w = image.shape
    kh, kw = kernel.shape
    padded = np.pad(image.astype(np.int32), ((kh // 2, kh // 2), (kw // 2, kw // 2)), mode="edge")
    result = np.zeros((h, w), np.int32)
    for y, x in zip(*np.nonzero(kernel)):
        result += padded[y:y + h, x:x + w] * int(kernel[y, x])
    return result


def gaussian3(green):
    kernel = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.int32)
    return ((correlate(green, kernel) + 8) >> 4).astype(np.uint8)


def box_mean15(image):
    # Equivalent to summing 225 uint8 samples, with half-up integer rounding.
    padded = np.pad(image.astype(np.int64), 7, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    total = integral[15:, 15:] - integral[:-15, 15:] - integral[15:, :-15] + integral[:-15, :-15]
    return ((total + 112) // 225).astype(np.uint8)


def sparse_line_response(image):
    responses = []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        kernel = np.zeros((7, 7), np.int32)
        for t in range(-3, 4):
            kernel[3 + t * dy, 3 + t * dx] -= 6
        # Three samples on each parallel flank; all offsets remain inside 7x7.
        py, px = -dx, dy
        for sign in (-1, 1):
            for t in (-1, 0, 1):
                kernel[3 + t * dy + sign * 2 * py, 3 + t * dx + sign * 2 * px] += 7
        assert kernel.sum() == 0
        responses.append(np.clip((correlate(image, kernel) * 4 + 21) // 42, 0, 255))
    return np.maximum.reduce(responses).astype(np.uint8)


def morphology(mask, structure, dilate):
    h, w = mask.shape
    r = structure.shape[0] // 2
    padded = np.pad(mask, r, mode="constant", constant_values=False)
    windows = [padded[y:y + h, x:x + w] for y, x in zip(*np.nonzero(structure))]
    return np.logical_or.reduce(windows) if dilate else np.logical_and.reduce(windows)


def segment(response, fov, threshold):
    if not 1 <= threshold <= 255:
        raise ValueError("Threshold must be 1..255")
    initial = (response >= threshold) & fov
    # Standard cross closing repairs small gaps. Reject single isolated pixels.
    closed = morphology(morphology(initial, CROSS, True), CROSS, False)
    neighbours = correlate(closed.astype(np.uint8), np.ones((3, 3), np.int32))
    return closed & (neighbours >= 2) & fov


def features(rgb, fov, algorithm="A"):
    if algorithm not in ("A", "B") or rgb.shape[:2] != fov.shape:
        raise ValueError("Bad algorithm or shape")
    green = rgb[:, :, 1]
    filtered = gaussian3(green)
    enhanced = LUT[filtered]
    background = box_mean15(enhanced)
    local = np.clip((background.astype(np.int16) - enhanced.astype(np.int16)) * 4, 0, 255).astype(np.uint8)
    response = local if algorithm == "A" else np.maximum(local, sparse_line_response(enhanced))
    return {"green": green, "filtered": filtered, "enhanced": enhanced,
            "background": background, "response": response}


def analyze(rgb, fov, algorithm="A", threshold=28):
    result = features(rgb, fov, algorithm)
    result["mask"] = segment(result["response"], fov, threshold)
    result["fov_pixels"] = int(np.count_nonzero(fov))
    result["vessel_pixels"] = int(np.count_nonzero(result["mask"]))
    result["packed"] = (result["green"].astype(np.uint32)
                        | (result["enhanced"].astype(np.uint32) << 8)
                        | (result["mask"].astype(np.uint32) * 255 << 16)
                        | (result["response"].astype(np.uint32) << 24))
    return result
