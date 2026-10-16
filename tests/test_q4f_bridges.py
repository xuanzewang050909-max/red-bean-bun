import unittest
import numpy as np
from software.q4f_bridges import bridge_mask

class DirectedPathsTests(unittest.TestCase):
    def inputs(self):
        g=np.full((49,49),120,np.uint8);g[24,10:39]=80
        s=np.zeros_like(g);s[24,10:39]=150;s[24,22:27]=80
        return g,np.ones(g.shape,bool),s

    def test_aligned_dark_gap_recovers_only_supported_path(self):
        g,f,s=self.inputs();cfg=dict(score_offset=48,margin=1,max_gap=5)
        p,d=bridge_mask(g,f,None,s,None,cfg)
        self.assertTrue(p[24,10:39].all())
        self.assertEqual(int(p.sum()),29)

    def test_bright_guard_preserves_gap(self):
        g,f,s=self.inputs();g[23,24]=230
        p,d=bridge_mask(g,f,None,s,None,dict(score_offset=48,margin=1,max_gap=5))
        np.testing.assert_array_equal(p[d['protected']],d['seed'][d['protected']])
        self.assertFalse(p[24,22:27].any())

    def test_no_unconditional_bridge_of_unobserved_path(self):
        g,f,s=self.inputs();s[24,24]=0
        p,d=bridge_mask(g,f,None,s,None,dict(score_offset=48,margin=1,max_gap=5))
        self.assertFalse(p[24,22:27].any())

    def test_crossing_parallel_lines_without_aligned_arms_not_joined(self):
        g=np.full((49,49),120,np.uint8);g[23,10:39]=80;g[27,10:39]=80;g[24:27,24]=80
        s=np.zeros_like(g);s[23,10:39]=150;s[27,10:39]=150;s[24:27,24]=80
        p,d=bridge_mask(g,np.ones(g.shape,bool),None,s,None,dict(score_offset=48,margin=1,max_gap=7))
        self.assertFalse(p[24:27,24].any())

if __name__=='__main__':unittest.main()
