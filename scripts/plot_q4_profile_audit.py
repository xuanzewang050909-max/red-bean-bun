"""Plot verified diagnostic histograms, not generated or FPGA segmentation images."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('experiment', type=Path)
    parser.add_argument('output', type=Path)
    a = parser.parse_args()
    if a.output.exists():
        raise RuntimeError('Preserve previous figure')
    report = json.loads((a.experiment/'feature_report.json').read_text())
    curves = [('A_response', 'Original A response', '#7b858a'),
              ('green_mf_small', 'Raw green: small dark-line', '#19769b'),
              ('green_mf_max', 'Raw green: two-scale maximum', '#bc6a20'),
              ('green_coherent_shape', 'Raw green: edge + direction ratio', '#207846')]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.2))
    for row, side in enumerate(('256', '512')):
        with np.load(a.experiment/f'pooled_{side}_histograms.npz', allow_pickle=False) as stored:
            for feature, label, color in curves:
                hist = stored[feature+'__bright_C2']
                tp, fp = np.cumsum(hist[0, ::-1]), np.cumsum(hist[1, ::-1])
                loss = (hist[0].sum()-tp)/report['bright_truth_totals'][side]
                reduction = 1-fp/hist[1].sum()
                axes[row, 0].plot(loss, reduction, color=color, label=label, lw=1.6)
                hist = stored[feature+'__outside_C2']
                levels = np.flatnonzero(hist.sum(axis=0))[::-1]
                tp, fp = np.cumsum(hist[0, levels]), np.cumsum(hist[1, levels])
                axes[row, 1].plot(tp/hist[0].sum(), tp/(tp+fp), color=color, label=label, lw=1.6, drawstyle='steps-post')
        ax = axes[row, 0]
        ax.axvline(.02, color='#9b3045', ls='--', lw=1)
        ax.axhline(.10, color='#9b3045', ls=':', lw=1)
        ax.set(xlim=(0, .12), ylim=(0, 1), title=f'{side}: removing existing C2 bright-band pixels',
               xlabel='Recall loss / all AH bright-band vessel pixels', ylabel='Bright-band FP reduction')
        ax.text(.023, .87, '2 pp recall-loss budget', fontsize=9, color='#9b3045')
        ax.text(.062, .12, '10% FP reduction reference', fontsize=8, color='#9b3045')
        ax = axes[row, 1]
        ax.axhline(.8, color='#9b3045', ls='--', lw=1)
        ax.set(xlim=(0, 1), ylim=(0, 1.02), title=f'{side}: adding pixels outside existing C2',
               xlabel='Fraction of AH vessel pixels outside C2 recovered', ylabel='Precision of proposed additions')
        ax.text(.32, .82, 'Original added-pixel precision requirement: 80%', fontsize=8, color='#9b3045')
    for ax in axes.ravel():
        ax.grid(alpha=.18)
        ax.spines[['top', 'right']].set_visible(False)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.5, .058), ncol=2, frameon=False, fontsize=9)
    fig.suptitle('Q4 D1: bright-edge discrimination and missed-vessel recovery', fontsize=15, y=.97)
    fig.text(.5, .025, 'Original 10 training images / AH only. Same-sample scalar-threshold diagnostics; no new segmentation or PL execution.',
             ha='center', fontsize=9)
    fig.subplots_adjust(top=.89, bottom=.20, hspace=.46, wspace=.30)
    fig.savefig(a.output, dpi=160, facecolor='white')
    print(json.dumps({'figure': str(a.output), 'matplotlib': matplotlib.__version__, 'numpy': np.__version__,
                      'data': 'verified pooled integer histograms', 'segmentation_or_PL': False}))


if __name__ == '__main__':
    main()
