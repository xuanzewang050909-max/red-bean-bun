"""RGB-only FOV generation and shared image/mask letterbox geometry."""
import gzip
import hashlib
import io
import re
import tarfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def read_archive(path, suffix):
    result = {}
    with tarfile.open(path, "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                raise ValueError("Unexpected non-file tar entry")
            name = Path(member.name).name
            match = re.fullmatch(r"(im\d{4})" + re.escape(suffix) + r"\.ppm\.gz", name)
            if not match or name != member.name or match[1] in result:
                raise ValueError("Unexpected/duplicate STARE archive member: " + member.name)
            compressed = archive.extractfile(member).read()
            pixels = np.array(Image.open(io.BytesIO(gzip.decompress(compressed))))
            result[match[1]] = {"pixels": pixels, "member": name,
                                "member_sha256": hashlib.sha256(compressed).hexdigest()}
    return result


def fov_from_rgb(rgb):
    """Largest bright component, fill holes; never accepts vessel labels."""
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("Expected uint8 RGB")
    bright = (np.max(rgb, axis=2) > 20).astype(np.uint8)
    count, components, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    if count == 1:
        return np.zeros(rgb.shape[:2], dtype=bool)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    region = (components == largest).astype(np.uint8)
    padded = np.pad(region, 1)
    cv2.floodFill(padded, None, (0, 0), 2)
    return padded[1:-1, 1:-1] != 2


def letterbox(rgb, masks, size):
    h, w = rgb.shape[:2]
    if size not in (256, 512) or any(mask.shape != (h, w) for mask in masks.values()):
        raise ValueError("Only aligned 256/512 inputs supported")
    scale = size / max(w, h)
    new_w, new_h = round(w * scale), round(h * scale)
    left, top = (size - new_w) // 2, (size - new_h) // 2
    out = np.zeros((size, size, 3), np.uint8)
    out[top:top + new_h, left:left + new_w] = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    aligned = {}
    for name, mask in masks.items():
        target = np.zeros((size, size), np.uint8)
        target[top:top + new_h, left:left + new_w] = cv2.resize(
            mask.astype(np.uint8), (new_w, new_h), interpolation=cv2.INTER_NEAREST_EXACT)
        aligned[name] = target.astype(bool)
    geometry = {"source_width": w, "source_height": h, "size": size,
                "nominal_scale": scale, "resized_width": new_w, "resized_height": new_h,
                "pad_left": left, "pad_top": top,
                "pad_right": size - left - new_w, "pad_bottom": size - top - new_h,
                "effective_scale_x": new_w / w, "effective_scale_y": new_h / h,
                "image_interpolation": "OpenCV INTER_LINEAR",
                "mask_interpolation": "OpenCV INTER_NEAREST_EXACT",
                "inverse_pixel_center": "x=(dst_x-left+0.5)*source_width/resized_width-0.5; y likewise"}
    return out, aligned, geometry


def prepare_sample(rgb, labels, size):
    if "fov" in labels:
        raise ValueError("FOV is derived from RGB; labels may not override it")
    masks = {"fov": fov_from_rgb(rgb), **labels}
    resized, aligned, geometry = letterbox(rgb, masks, size)
    # Fixed 3-pixel exclusion removes the visible retina/background transition.
    aligned["fov"] = cv2.erode(aligned["fov"].astype(np.uint8), np.ones((7, 7), np.uint8),
                                borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    geometry["fov_definition"] = "RGB max>20, largest 8-component, holes filled; resized then 7x7 erosion"
    return resized, aligned, geometry


def pack_input(rgb, fov):
    """Little-endian pixel: B, G, R, FOV byte 0/1. Labels cannot enter this API."""
    if rgb.dtype != np.uint8 or fov.dtype != np.bool_ or fov.shape != rgb.shape[:2]:
        raise ValueError("Misaligned RGB/FOV")
    return (rgb[:, :, 2].astype(np.uint32) | (rgb[:, :, 1].astype(np.uint32) << 8)
            | (rgb[:, :, 0].astype(np.uint32) << 16) | (fov.astype(np.uint32) << 24))
