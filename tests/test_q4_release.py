"""Q4 release/ABI/numeric provenance checks; no new board evidence."""
import ast, json, unittest, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from pynq_q4.protocol import file_info, validate_package, Inputs, sha
from pynq_q4.quality_observer import control_word, QualityObserver, IDENTITY
from q4_board import validate_q4, planned_requests
from scripts.prepare_q4_refined_vectors import expected_words
from test_w2_quality_observer import GPIO
PACKAGE=ROOT/'build/deploy/q4_c5_experimental_r1'
class ReleaseTests(unittest.TestCase):
    def test_fixed_inventory_120_unique_requests_and_hashes(self):
        _,p=validate_q4(PACKAGE);q=planned_requests(p)
        self.assertEqual(len(q),120);self.assertEqual(len({x['client_nonce'] for x in q}),120)
        self.assertEqual(sum(x['side']**2 for x in q),19660800)
        self.assertEqual(set(x['algorithm'] for x in q),{'A','C2','C5'})
        self.assertEqual(p['decision_commit'],'237d58d');self.assertEqual(len(p['original_strict_failures']),6)
    def test_all_input_and_gt_bytes_preserved(self):
        m=validate_package(PACKAGE);old=ROOT/'build/deploy/q3_full_quality_r1'
        prior=json.loads((old/'browser_manifest.json').read_bytes())
        self.assertEqual(m['images'],prior['images'])
        for name in m['artifacts']:
            if name.startswith(('inputs/','labels/')):self.assertEqual(file_info(PACKAGE/name),file_info(old/name))
    def test_source_quality_reuse_only_top_interfaces_removed(self):
        original=(ROOT/'hls/retina_quality_hls.cpp').read_text().replace('void retina_quality_hls(','void retina_refined_base(')
        expected='// Exact original quality pipeline, only top interfaces removed for hierarchical reuse.\n'+''.join(l for l in original.splitlines(True) if not l.startswith('#pragma HLS INTERFACE '))
        self.assertEqual(expected,(ROOT/'hls/retina_refined_base.cpp').read_text())
    def test_no_runtime_medical_reference_imports(self):
        release,_=validate_q4(PACKAGE)
        for name in release['artifacts']:
            self.assertFalse(any(x in name for x in ('software/','golden','reference.py','expected.npy')))
            if name.endswith('.py'):
                for node in ast.walk(ast.parse((PACKAGE/name).read_bytes(),feature_version=(3,10))):
                    if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('software','cv2','prepare_q4')))
    def test_rq51_control_bits_and_invalid_controls(self):
        for alg,bits in [('A',0),('C2',8),('C5',24)]:
            for side in [256,512]:
                for mode in range(4):
                    for t in [1,27,28,29,255]:
                        word=control_word(side=side,stage=mode,algorithm=alg,threshold=t,tag=65535)
                        self.assertEqual(word,(65535<<16)|(t<<8)|bits|(4 if side==256 else 0)|mode)
        c=control_word(side=256,stage=3,algorithm='C5',threshold=28,tag=1)
        pages={0:IDENTITY,1:2,3:c,4:1,5:70000,6:70020,7:10,8:25,9:65536,10:65536,11:1,12:32}
        gpio=GPIO(pages);reader=QualityObserver(gpio,verified_clock_hz=100000000)
        self.assertEqual(reader.completed(expected_control=c,previous_sequence=0,expected_words=65536)['latched_control'],c)
        for corrupt in [c^8,c|32,c|64,c|128]:
            with self.assertRaises(RuntimeError):reader.completed(expected_control=corrupt,previous_sequence=0,expected_words=65536)
        gpio.pages[0]=0x52513231
        with self.assertRaises(RuntimeError):QualityObserver(gpio,verified_clock_hz=100000000)
    def test_candidate_training_masks_match_frozen_r3_exactly(self):
        _,p=validate_q4(PACKAGE)
        candidate=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
        for name in p['split']['train']:
            for side in [256,512]:
                words=np.load(PACKAGE/f'inputs/{name}_{side}.npy',allow_pickle=False)
                actual=expected_words(words,3,'C5',28,candidate)
                z=np.load(ROOT/f'build/q4_fusion_2026-10-14_r3/{name}_{side}_offline_masks.npz',allow_pickle=False)
                frozen=z['C5_l5_9_r8_m1_a4_g3']
                if frozen.shape!=words.shape:frozen=np.unpackbits(frozen)[:words.size].reshape(words.shape)
                np.testing.assert_array_equal((actual>>16)&255,frozen.astype(np.uint32)*255)
                self.assertEqual(sha(actual.tobytes()),p['expected_output_sha256'][f'{name}_{side}_C5'])
    def test_c5_threshold_and_stage_roles_do_not_fake_visual_changes(self):
        c=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
        words=np.load(PACKAGE/'inputs/im0001_256.npy')
        for mode in [0,1,2]:
            np.testing.assert_array_equal(expected_words(words,mode,'C5',28,c),expected_words(words,mode,'C2',28,c))
        outputs=[expected_words(words,3,'C5',t,c) for t in [20,28,36]]
        self.assertFalse(np.array_equal(outputs[0],outputs[1]));self.assertFalse(np.array_equal(outputs[1],outputs[2]))
        for o in outputs[1:]:np.testing.assert_array_equal(o&65535,outputs[0]&65535)
    def test_ui_reuses_rendering_and_labels_experimental_mode(self):
        html=(PACKAGE/'ui/index.html').read_text(encoding='utf-8')
        self.assertIn('C5 · 多尺度实验',html);self.assertIn('模式1/2显示原C2',html)
        self.assertEqual((PACKAGE/'ui/style.css').read_bytes(),(ROOT/'ui_w4a/style.css').read_bytes())
        a=(ROOT/'ui_w4a/app.js').read_text(encoding='utf-8').replace('A/C2','A/C2/C5')
        self.assertEqual((PACKAGE/'ui/app.js').read_text(encoding='utf-8'),a)
