import unittest
import copy
import json
from pathlib import Path
import numpy as np
from software.q4_refinement import flank_features
from software.q4_ridge import candidates,directional_scores,directional_growth

class RidgeTests(unittest.TestCase):
    def test_grid_unique(self):
        grid=list(candidates());self.assertEqual(len(grid),27);self.assertEqual(len({c['id'] for c in grid}),27)

    def test_actual_response_bright_line_not_flat_or_step(self):
        im=np.full((31,31),230,np.uint8);im[15]=224
        s=directional_scores(flank_features(im),4,8)
        self.assertGreaterEqual(int(s[0][15,15]),28)
        for image in (np.full_like(im,230),np.where(np.indices(im.shape)[0]>=15,230,100).astype(np.uint8)):
            self.assertFalse(np.any([v[10:21,10:21] for v in directional_scores(flank_features(image),4,8)]))

    def test_growth_is_bounded_and_directional(self):
        scores=[np.zeros((17,17),np.uint8) for _ in range(4)]
        scores[0][8,2:15]=20;scores[0][8,8]=40;scores[0][7,8]=20
        final,seed=directional_growth(scores,np.ones((17,17),bool),14,4)
        self.assertEqual(int(seed.sum()),1);self.assertEqual(int(final.sum()),9)
        self.assertTrue(final[8,4:13].all());self.assertFalse(final[7,8]);self.assertFalse(final[8,3])

    def test_unseeded_noise_and_fov_stop_growth(self):
        scores=[np.full((11,11),20,np.uint8) for _ in range(4)];fov=np.ones((11,11),bool)
        self.assertFalse(directional_growth(scores,fov,14,4)[0].any())
        scores[0][5,5]=40;fov[:,6]=False
        final,_=directional_growth(scores,fov,14,4)
        self.assertFalse(final[:,6:].any())

    def test_integer_rounding_saturation(self):
        small=np.array([[1,9,2295]],np.int16)
        ev=[[(small,small)]*5]*4
        np.testing.assert_array_equal(directional_scores(ev,4,8)[0],[[1,8,255]])

    def test_joint_gates_reject_good_dice_with_recall_loss(self):
        from scripts.evaluate_q4_refinement import assess_new
        p=json.loads(Path('docs/q4_ridge_protocol_r2.json').read_text())
        baseline={s:{'summary':{'macro_fov':{'dice':.6,'recall':.7,'precision':.6,'iou':.45},
            'macro_continuity':{'cldice':.6,'topology_precision':.6,'topology_recall':.7,'adjacent_edge_coverage':.6},
            'pooled':{'bright_band':{'recall':.7,'fp':100},'thin_label_proxy':{'recall':.5}},
            'bridges':{'added_precision':None}},'per_image':{'example':{'fov':{'recall':.7},'continuity':{'topology_recall':.7}}}}
                  for s in ('256','512')}
        c=copy.deepcopy(baseline)
        for s in c:
            c[s]['summary']['macro_fov']['dice']=.62
            c[s]['summary']['macro_continuity']['cldice']=.62
            c[s]['summary']['pooled']['bright_band']['fp']=80
            c[s]['summary']['pooled']['thin_label_proxy']['recall']=.52
        self.assertTrue(assess_new(c,baseline,baseline,p)['eligible_for_PL_feasibility'])
        c['512']['summary']['pooled']['thin_label_proxy']['recall']=.3
        self.assertIn('512:thin_recall',assess_new(c,baseline,baseline,p)['failed_gates'])

    def test_added_precision_gate_has_no_rounded_pass(self):
        from scripts.evaluate_q4_refinement import assess_new
        p=json.loads(Path('docs/q4_ridge_protocol_r2.json').read_text())
        # Reuse the real frozen C2 scores only as gate inputs, not a candidate evaluation.
        r=json.loads(Path('results/q4_refinement_2026-10-14/r1/training_report.json').read_text())
        c=copy.deepcopy(r['scores']['C2'])
        c['512']['summary']['bridges']['added_precision']=.79999
        self.assertIn('512:bridge_added_precision',assess_new(c,r['scores']['A'],r['scores']['C2'],p)['failed_gates'])

if __name__=='__main__':unittest.main()
