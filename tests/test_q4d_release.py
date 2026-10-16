import os
"""C7 ABI, deployment isolation, exact derivation and frozen-reference checks; HOST only."""
import ast
import json
import unittest
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from pynq_q4d.protocol import Inputs,RequestError,validate_package,file_info,sha
from pynq_q4d.quality_observer import QualityObserver,control_word,IDENTITY
from test_w2_quality_observer import GPIO
from scripts.q4d_board import planned_requests,validate_q4d
from scripts.fit_q4d_final import header
PACKAGE=Path(os.environ.get('Q4D_TEST_PACKAGE',str(ROOT/'build/deploy/q4d_c7_experimental_r1')))

class CoreTests(unittest.TestCase):
    def test_existing_c5_arithmetic_exact_except_external_top_interface(self):
        original=(ROOT/'hls/retina_refined_hls.cpp').read_text().replace('#include "retina_refined_hls.hpp"','#include "retina_detector_hls.hpp"').replace('void retina_refined_hls(','void retina_detector_c5(')
        expected=''.join(l for l in original.splitlines(True) if not l.startswith('#pragma HLS INTERFACE '))
        self.assertEqual(expected,(ROOT/'hls/retina_detector_c5.cpp').read_text())
    def test_model_constants_are_same_integer_model_as_frozen_final_fit(self):
        model=json.loads((ROOT/'software/models/c7_d6_r1.json').read_bytes())
        self.assertEqual(header(model),(ROOT/'hls/retina_c7_model.hpp').read_text())
        self.assertEqual(file_info(ROOT/'software/models/c7_d6_r1.json'),file_info(ROOT/'build/q4d_final_2026-10-15_r1/c7_model.json'))
        self.assertEqual(len(model['trees']),8);self.assertTrue(all(t['depth']<=6 for t in model['trees']))
    def test_all_algorithms_sizes_modes_thresholds_tag_controls(self):
        for alg,bits in [('A',0),('C2',8),('C5',24),('C7',56)]:
            for side in (256,512):
                for stage in range(4):
                    for t in (1,28,96,112,128,255):
                        self.assertEqual(control_word(side=side,stage=stage,algorithm=alg,threshold=t,tag=65535),
                            (65535<<16)|(t<<8)|bits|(4 if side==256 else 0)|stage)
        word=control_word(side=256,stage=3,algorithm='C7',threshold=112,tag=1)
        pages={0:IDENTITY,1:2,3:word,4:1,5:70000,6:70020,7:10,8:25,9:65536,10:65536,11:1,12:32}
        gpio=GPIO(pages);reader=QualityObserver(gpio,verified_clock_hz=100000000)
        self.assertEqual(reader.completed(expected_control=word,previous_sequence=0,expected_words=65536)['latched_control'],word)
        for corrupt in (word^8,word^16,word|64,word|128,word&0xffff00ff):
            with self.assertRaises(RuntimeError):reader.completed(expected_control=corrupt,previous_sequence=0,expected_words=65536)
        gpio.pages[0]=0x52513531
        with self.assertRaises(RuntimeError):QualityObserver(gpio,verified_clock_hz=100000000)
    def test_c7_intermediate_rejected_and_no_labels_or_boolean_thresholds(self):
        old=json.loads((ROOT/'build/deploy/q3_full_quality_r1/browser_manifest.json').read_bytes())
        inputs=Inputs(ROOT,old['images'])
        req=dict(image_id='im0001',side=512,mode='final',algorithm='C7',threshold=112,png_profile='fast',client_nonce='c7_test_0001')
        self.assertEqual(inputs.request(req)['mode_code'],3)
        for change in ({'mode':'threshold_candidate'},{'mode':'closed_candidate'},{'ground_truth':'AH'},{'threshold':True},{'threshold':0},{'threshold':256}):
            with self.assertRaises(RequestError):inputs.request({**req,**change})
    def test_fixed_cohort_c7_threshold_is_distinct_and_has_no_labels(self):
        p=json.loads((ROOT/'docs/q4d_board_protocol_r1.json').read_bytes());q=planned_requests(p)
        self.assertEqual(len(q),160);self.assertEqual(len({r['client_nonce'] for r in q}),160)
        self.assertEqual(sum(r['side']**2 for r in q),26214400)
        for r in q:
            self.assertEqual(r['threshold'],112 if r['algorithm']=='C7' else 28)
            self.assertFalse(any(k in r for k in ('truth','ground_truth','labels')))
    def test_frozen_model_score_and_threshold_masks_are_monotonic(self):
        ref=ROOT/'build/q4d_board_references_01'
        for side in (256,512):
            words=np.load(ref/f'im0001_{side}_C7_words.npy',allow_pickle=False)
            score=(words>>24).astype(np.uint8)
            final=np.load(ROOT/f'build/q4d_final_2026-10-15_r1/im0001_{side}_score.npy',allow_pickle=False)
            np.testing.assert_array_equal(score,final)
            masks=[score>=t for t in (96,112,128)]
            self.assertTrue((masks[2]<=masks[1]).all() and (masks[1]<=masks[0]).all())
            self.assertGreater(int(masks[0].sum()),int(masks[2].sum()))
    def test_runtime_contains_no_classifier_features_or_label_inference(self):
        for p in (ROOT/'pynq_q4d').glob('*.py'):
            tree=ast.parse(p.read_bytes(),feature_version=(3,10))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('software','sklearn','cv2','prepare_q4d')))
                if isinstance(node,ast.Import):self.assertFalse(any(n.name.startswith(('software','sklearn','cv2')) for n in node.names))

class PackageTests(unittest.TestCase):
    def test_exact_package_inventory_and_source_pairing(self):
        release,p=validate_q4d(PACKAGE);m=validate_package(PACKAGE)
        self.assertEqual(len(p['expected_output_sha256']),160)
        original=json.loads((ROOT/'build/deploy/q3_full_quality_r1/browser_manifest.json').read_bytes())
        self.assertEqual(m['images'],original['images'])
        for name in release['artifacts']:
            self.assertFalse(any(x in name for x in ('software/','golden','model.json','expected.npy')))
            if name.startswith('pynq_q4d/'):self.assertEqual(file_info(PACKAGE/name),file_info(ROOT/name))
    def test_c7_ui_threshold_selection_distinct(self):
        html=(PACKAGE/'ui/index.html').read_text(encoding='utf-8');js=(PACKAGE/'ui/app.js').read_text(encoding='utf-8')
        self.assertIn('C7 · 多特征检测实验',html);self.assertIn('value="112"',html)
        self.assertIn('c7 ? "112" : "28"',js);self.assertIn('["final", "bypass"]',js)
        self.assertEqual((PACKAGE/'ui/style.css').read_bytes(),(ROOT/'ui_w4a/style.css').read_bytes())

if __name__=='__main__':unittest.main()
