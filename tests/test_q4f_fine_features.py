import unittest
import numpy as np
from software.q4d_features import integer_features
from software.q4f_fine_features import fine_features,scalar_fine_tail,DIRS,offsets

class FineFeatureTests(unittest.TestCase):
    def test_exact_scalar_random_and_edges(self):
        rng=np.random.default_rng(850)
        for g in [rng.integers(0,256,(31,33),dtype=np.uint8),np.full((31,33),120,np.uint8)]:
            _,f=integer_features(g);names,x=fine_features(g,f,np.zeros_like(g))
            self.assertEqual(len(names),24);self.assertEqual(x.shape[-1],79)
            for y,z in [(0,0),(0,32),(30,0),(30,32),(15,16)]+[tuple(v) for v in rng.integers(0,30,(12,2))]:
                np.testing.assert_array_equal(x[y,z,55:],scalar_fine_tail(g,y,z))
            self.assertGreaterEqual(int(x.min()),-8192);self.assertLessEqual(int(x.max()),8191)

    def test_offsets_bound_unique_symmetric(self):
        for d in DIRS:
            for n in (5,9,15):
                p=offsets(d,n)
                self.assertEqual(len(set(p)),n)
                self.assertEqual(p,[(-a,-b) for a,b in p[::-1]])
                for side in (-2,-1,0,1,2):
                    self.assertLessEqual(max(abs(v) for pair in offsets(d,n,side) for v in pair),9)

if __name__=='__main__':unittest.main()
