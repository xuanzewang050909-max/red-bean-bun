"""Reverify preserved W2 bytes and report a diagnostic pair, without tuning."""
import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verify_w2_board_results import verify
from pynq_app.evaluation import score_completed
from pynq_app.protocol import file_info, write_json
from software.reference import gaussian3


def summarize():
    raw = ROOT / 'build/board_results/w2_quality_2026-10-14'
    target = ROOT / 'results/w2_quality_2017_4/board_execution_2026-10-14'
    target.mkdir(parents=True, exist_ok=True)
    archive, notebook = raw / 'w2_results_bundle.zip', raw / 'w2_quality_check.ipynb'
    checked = verify(archive, notebook, ROOT / 'build/deploy/w2_quality_2017_4_r1')
    write_json(target / 'verification.json', checked)
    with zipfile.ZipFile(archive) as z:
        report_bytes = z.read('w2_result.json')
        report = json.loads(report_bytes)
        (target / 'w2_result.json').write_bytes(report_bytes)
        (target / 'w2_quality_check.ipynb').write_bytes(notebook.read_bytes())
        package = ROOT / 'build/deploy/browser_a4_w1_r1'
        entry = json.loads((package / 'browser_manifest.json').read_bytes())['images']['im0001']['512']
        source = np.load(package / entry['input'], allow_pickle=False)
        fov = (source >> 24) != 0
        roi = np.zeros(source.shape, bool); roi[145:385, 180:340] = True; roi &= fov
        core = roi & (gaussian3(((source >> 8) & 255).astype(np.uint8)) >= 192)
        band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~core & roi
        ah = np.load(package / entry['evaluation_only']['AH']['path'], allow_pickle=False)
        vk = np.load(package / entry['evaluation_only']['VK']['path'], allow_pickle=False)
        pair = []
        for index in (74, 75):
            rec = report['transfers'][index]
            output = np.load(io.BytesIO(z.read(rec['saved_output']['name'])), allow_pickle=False)
            mask = ((output >> 16) & 255) != 0
            pair.append(dict(index=index, algorithm=rec['algorithm'], threshold=rec['threshold'],
                quality=score_completed(package, entry, output, fov, 3),
                illustrative_band_pixels=int(band.sum()), band_candidates=int((mask & band).sum()),
                band_candidates_negative_in_both=int((mask & band & ~ah & ~vk).sum()),
                core_ms=rec['hardware']['pl_core_frame_ns']/1e6,
                dma_ms=rec['timing_ns']['dma_transaction']/1e6,
                inference_ms=rec['timing_ns']['full_inference']/1e6))
    summary = dict(scope='Actual im0001 training-image DMA diagnostic only; frozen C2 not retuned. Not Q3/full-dataset acceptance.',
        frames=pair, original_archive=file_info(archive), notebook=file_info(notebook),
        diagnostic_region='Original Q0 rectangle x=[180,340),y=[145,385), G3>=192 core and 15x15 dilation minus core in original FOV; not lesion annotation or PL exclusion rule',
        board_clock='Original uncalibrated 2022 timestamp retained',
        timing_scope='Two individual samples; W2 config/DMA/snapshot excludes allocation/file IO/verification. Core includes stream stalls. Pure DMA/browser FPS remain null.')
    write_json(target / 'diagnostic_pair.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    summarize()
