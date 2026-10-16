"""GT scoring after a completed output, never called by the hardware adapter."""
import numpy as np

from .protocol import file_info, require


def score_completed(root, entry, output, fov, mode_code):
    if mode_code == 0:
        return {'source': 'BYPASS_NO_SEGMENTATION', 'vessel_pixels': None, 'fov_pixels': int(fov.sum()),
                'vessel_area_fraction': None, 'annotations': {}, 'quality_reason': 'Bypass mode has no segmentation mask'}
    prediction = ((output >> 16) & 255) != 0
    denominator = int(np.count_nonzero(fov))
    numerator = int(np.count_nonzero(prediction & fov))
    result = {'source': 'PS_COUNTS_OF_CURRENT_REAL_PL_MASK', 'vessel_pixels': numerator, 'fov_pixels': denominator,
              'vessel_area_fraction': numerator / denominator if denominator else None,
              'annotations': {}, 'quality_reason': None}
    for name, spec in entry.get('evaluation_only', {}).items():
        path = root / spec['path']
        require(file_info(path) == spec['file'], 'Evaluation label file changed')
        truth = np.load(path, allow_pickle=False)
        require(truth.dtype == np.bool_ and truth.shape == prediction.shape, 'Misaligned GT')
        tp = int(np.count_nonzero(prediction & truth & fov))
        fp = int(np.count_nonzero(prediction & ~truth & fov))
        fn = int(np.count_nonzero(~prediction & truth & fov))
        tn = int(np.count_nonzero(~prediction & ~truth & fov))
        result['annotations'][name] = {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'dice': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0,
            'iou': tp / (tp + fp + fn) if tp + fp + fn else 1.0,
            'scope': 'Current frame/mode, FOV only; not heldout macro accuracy or clinical acceptance'}
    if not result['annotations']:
        result['quality_reason'] = 'No matching annotation for this image; Dice/IoU are unavailable'
    return result
