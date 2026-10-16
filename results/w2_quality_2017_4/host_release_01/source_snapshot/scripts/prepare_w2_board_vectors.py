"""Host-only independent golden vectors; no annotation enters the PL test package."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from a4_segmentation_board_test import full_cases, make_pattern, segmentation_expected
from prepare_q2_quality_vectors import expected_words
from pynq_app.quality_observer import control_word


def digest(array):
    return hashlib.sha256(array.astype('<u4').tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    args.destination.mkdir(exist_ok=False, parents=True)
    frozen = ROOT / 'build/deploy/a4_segmentation_2017_4_r1'
    manifest = json.loads((frozen / 'a4_manifest.json').read_text(encoding='utf-8'))
    for side in (256, 512):
        name = f'stare_im0001_{side}.npy'
        assert hashlib.sha256((frozen/name).read_bytes()).hexdigest() == manifest['artifacts'][name]['sha256']
    candidate = json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_text(encoding='utf-8'))['candidate']
    cases = [(256, 3, 'A', 28, 'vessel_stripes')]
    cases += [(s, m, 'A', 28, p) for s, m, p in full_cases()]
    assert len(cases) == 61
    cases += [(256,3,'C2',28,'stare'), (512,3,'C2',28,'stare'),
              (256,1,'C2',27,'fov_edge'), (512,2,'C2',29,'fov_edge'),
              (256,3,'C2',1,'broken_line'), (512,3,'C2',255,'random'),
              (256,0,'C2',28,'vessel_stripes'), (512,3,'C2',28,'bright_cross'),
              (256,3,'C2',28,'checker'), (256,3,'C2',28,'impulse'),
              (512,3,'C2',28,'black')]
    # Same image, consecutive hardware algorithm/threshold changes.
    cases += [(512,3,a,t,'stare') for t in (27,28,29) for a in ('A','C2')]
    cases += [(256,3,'A',t,'stare') for t in (1,255)]
    records, arrays = [], {}
    for index, (side, stage, algorithm, threshold, pattern) in enumerate(cases):
        if pattern == 'bright_cross':
            y, x = np.indices((side,side), dtype=np.uint32)
            green = np.where((x>=side//3)&(x<2*side//3)&(y>=side//3)&(y<2*side//3),245,120+(x*3+y*5)%30)
            green = np.where(np.abs(y.astype(np.int32)-side//2)<=2,60,green).astype(np.uint32)
            source = (np.uint32(1)<<24)|(np.uint32(100)<<16)|(green<<8)|37
        else:
            source = make_pattern(side, pattern, index, frozen)
        expected = expected_words(source, stage, algorithm, threshold, candidate)
        if index < 61:
            assert np.array_equal(expected, segmentation_expected(source, stage)), 'Original A4 regression mismatch'
        key = f'case_{index:03d}'
        arrays[key+'_input'] = source
        arrays[key+'_expected'] = expected
        records.append(dict(index=index,side=side,stage=stage,algorithm=algorithm,threshold=threshold,
                            pattern=pattern,input_key=key+'_input',expected_key=key+'_expected',
                            control=control_word(side=side,stage=stage,algorithm=algorithm,threshold=threshold,tag=index+1),
                            words=source.size,input_sha256=digest(source),expected_sha256=digest(expected)))
    np.savez_compressed(args.destination/'w2_vectors.npz', **arrays)
    report = dict(status='HOST_GOLDEN_VECTORS_NOT_BOARD_OUTPUT',cases=records,candidate=candidate,
                  original_a4_cases=61,board_status='NOT_RUN',annotation_arrays_loaded=False,
                  heldout_decoded=False,scope='Exact arithmetic/transport/observer checks; Q3 full accuracy remains pending')
    (args.destination/'w2_vectors.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('W2_BOARD_VECTORS_READY:',len(records),'frames;',sum(c['words'] for c in records),'words; original 61 A4 cases independently matched')


if __name__ == '__main__':
    main()
