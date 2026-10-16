import unittest
import numpy as np
from software.q4d_features import integer_features
from software.q4f_residual import residual_features,NORMALIZED,combine
from software.q4f_continuity import protection

class ResidualFeaturesTests(unittest.TestCase):
    def test_integer_normalization_scalar_extremes(self):
        rng=np.random.default_rng(830);g=rng.integers(0,256,(31,31),dtype=np.uint8)
        _,f=integer_features(g);score=rng.integers(0,256,g.shape,dtype=np.uint8)
        x=residual_features(f,score)
        self.assertEqual(x.shape,(31,31,55))
        for y in (0,15,30):
            for z in (0,15,30):
                r=131072//(int(f[y,z,4])+int(f[y,z,5])+8)
                for j,i in enumerate(NORMALIZED):
                    q=int(f[y,z,i])*r
                    expected=(abs(q)+2048)//4096*(1 if q>=0 else -1)
                    self.assertEqual(int(x[y,z,37+j]),min(255,max(-255,expected)))

    def test_highest_residual_cannot_modify_protected_baseline(self):
        rng=np.random.default_rng(831);g=np.full((49,49),100,np.uint8);g[24,24]=240
        fov=np.ones_like(g,bool);base=rng.integers(0,256,g.shape,dtype=np.uint8)
        result=combine(g,fov,base,np.full_like(g,255),160)
        p=protection(g,fov);seed=base>=112
        np.testing.assert_array_equal(result[p],seed[p]);self.assertFalse((seed&~result).any())

if __name__=='__main__':unittest.main()
