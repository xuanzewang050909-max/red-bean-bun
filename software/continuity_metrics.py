"""Evaluation only. Annotation skeletons never enter a processing function."""
import numpy as np
from skimage.morphology import skeletonize

from software.q4_refinement import sample


def continuity(prediction, truth, fov):
    p, t = prediction & fov, truth & fov
    sp, st = skeletonize(p, method="zhang"), skeletonize(t, method="zhang")
    pc, tc = int(sp.sum()), int(st.sum())
    hit_p, hit_t = int((sp & t).sum()), int((st & p).sum())
    precision = hit_p / pc if pc else None
    recall = hit_t / tc if tc else None
    cldice = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and precision + recall else 0.0)
    if not tc:
        cldice = None
    edges, covered = 0, 0
    for dy, dx in ((0, 1), (1, -1), (1, 0), (1, 1)):
        e = st & sample(st, dy, dx, "constant")
        edges += int(e.sum())
        covered += int((e & p & sample(p, dy, dx, "constant")).sum())
    return {"prediction_skeleton_pixels": pc, "truth_skeleton_pixels": tc,
            "prediction_skeleton_inside_truth": hit_p, "truth_skeleton_inside_prediction": hit_t,
            "topology_precision": precision, "topology_recall": recall, "cldice": cldice,
            "truth_adjacent_edges": edges, "covered_adjacent_edges": covered,
            "adjacent_edge_coverage": covered / edges if edges else None}


def bridge_audit(final, seed, links, truth, region):
    added = final & ~seed & region
    total, supported, unsupported_between_true_ends = 0, 0, 0
    for dy, dx, gap, anchor in links:
        count = int(anchor.sum())
        if not count:
            continue
        ends = anchor & truth & sample(truth, (gap + 1) * dy, (gap + 1) * dx, "constant")
        full = ends.copy()
        for t in range(1, gap + 1):
            full &= sample(truth, t * dy, t * dx, "constant")
        total += count
        supported += int(full.sum())
        unsupported_between_true_ends += int((ends & ~full).sum())
    return {"added_tp": int((added & truth).sum()), "added_fp": int((added & ~truth).sum()),
            "links": total, "fully_annotation_supported_links": supported,
            "unsupported_interior_between_labeled_ends": unsupported_between_true_ends}
