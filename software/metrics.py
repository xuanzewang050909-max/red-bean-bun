"""Offline GT evaluation; never called by FPGA input/algorithm preparation."""
import numpy as np


def evaluate(prediction, truth, region):
    if prediction.shape != truth.shape or truth.shape != region.shape:
        raise ValueError("Misaligned evaluation")
    p, t = prediction.astype(bool), truth.astype(bool)
    tp = int(np.count_nonzero(p & t & region))
    fp = int(np.count_nonzero(p & ~t & region))
    fn = int(np.count_nonzero(~p & t & region))
    tn = int(np.count_nonzero(~p & ~t & region))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "dice": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0,
            "iou": tp / (tp + fp + fn) if tp + fp + fn else 1.0,
            "precision": tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0),
            "recall": tp / (tp + fn) if tp + fn else 1.0}
