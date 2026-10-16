"""Fixed integer tree inference, exportable to PL; no sklearn runtime import."""
import math
import numpy as np


def export_forest(classifier, feature_names):
    trees = []
    for estimator in classifier.estimators_:
        t = estimator.tree_
        probabilities = t.value[:, 0, 1] / t.value[:, 0].sum(axis=1)
        trees.append({'left': t.children_left.tolist(), 'right': t.children_right.tolist(),
            'feature': t.feature.tolist(), 'threshold': [math.floor(x) for x in t.threshold],
            'leaf_q8': np.floor(probabilities * 255 + 0.5).astype(int).tolist(),
            'depth': int(t.max_depth)})
    return {'format': 'C7_INTEGER_FOREST_V1', 'features': list(feature_names), 'trees': trees,
            'rounding': 'round each leaf probability to uint8, then half-up average across trees',
            'inference_inputs': 'raw green local features only; no GT, image ID, coordinates or cached masks'}


def predict_integer(features, model):
    original_shape = features.shape[:-1]
    x = features.reshape(-1, features.shape[-1])
    if x.dtype != np.int16 or x.shape[1] != len(model['features']):
        raise ValueError('Feature schema differs')
    total = np.zeros(len(x), np.uint32)
    rows = np.arange(len(x))
    for tree in model['trees']:
        left = np.array(tree['left']); right = np.array(tree['right'])
        feature = np.array(tree['feature']); threshold = np.array(tree['threshold'])
        leaf = np.array(tree['leaf_q8'], np.uint32)
        node = np.zeros(len(x), np.int32)
        for _ in range(tree['depth']):
            active = left[node] != -1
            indices = rows[active]; current = node[active]
            go_left = x[indices, feature[current]] <= threshold[current]
            node[active] = np.where(go_left, left[current], right[current])
        if (left[node] != -1).any():
            raise ValueError('Tree traversal did not reach leaves')
        total += leaf[node]
    count = len(model['trees'])
    return ((total + count // 2) // count).astype(np.uint8).reshape(original_shape)
