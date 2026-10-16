import unittest
import cv2
import numpy as np
from software.q4f_continuity import protection, bounded_reconstruct, candidate_mask
from software.reference import gaussian3


class ProtectedContinuityTests(unittest.TestCase):
    def test_protection_contains_original_region_random_and_extremes(self):
        rng=np.random.default_rng(816)
        for g in [rng.integers(0,256,(65,65),dtype=np.uint8),
                  np.full((65,65),191,np.uint8),np.full((65,65),192,np.uint8)]:
            fov=np.ones_like(g,bool);fov[:3]=False
            original=cv2.dilate((gaussian3(g)>=192).astype(np.uint8),np.ones((15,15),np.uint8)).astype(bool)&fov
            self.assertFalse(np.any(original&~protection(g,fov)))

    def test_impulse_boundary_conservative_coverage(self):
        g=np.zeros((49,49),np.uint8);g[24,24]=255
        p=protection(g,np.ones_like(g,bool))
        self.assertTrue(p[16:33,16:33].all())
        self.assertFalse(p[15,24])

    def test_synchronous_bounded_path_and_unconnected_noise(self):
        seed=np.zeros((31,31),bool);seed[15,3]=True
        eligible=np.zeros_like(seed);eligible[15,4:24]=True;eligible[3:6,20:23]=True
        p=bounded_reconstruct(seed,eligible,8)
        self.assertTrue(p[15,3:12].all());self.assertFalse(p[15,12:].any())
        self.assertFalse(p[3:6,20:23].any())

    def test_protected_gap_cannot_be_crossed(self):
        s=np.zeros((20,20),bool);s[10,4]=True
        e=np.zeros_like(s);e[10,5:17]=True;e[10,8]=False
        p=bounded_reconstruct(s,e,8)
        self.assertTrue(p[10,4:8].all());self.assertFalse(p[10,8:].any())

    def test_independent_scalar_flood_oracle(self):
        rng=np.random.default_rng(817)
        for n in (0,1,4,8):
            seed=rng.random((17,19))<.05;e=rng.random(seed.shape)<.65
            expected=seed.copy()
            for _ in range(n):
                last=expected.copy()
                for y in range(17):
                    for x in range(19):
                        expected[y,x]=seed[y,x] or (e[y,x] and last[max(0,y-1):min(17,y+2),max(0,x-1):min(19,x+2)].any())
            np.testing.assert_array_equal(expected,bounded_reconstruct(seed,e,n))

    def test_candidate_preserves_all_seed_and_protected_pixels(self):
        rng=np.random.default_rng(818);g=rng.integers(0,200,(64,64),dtype=np.uint8)
        f=rng.integers(-10,15,(64,64,36),dtype=np.int16);scores=rng.integers(0,256,g.shape,dtype=np.uint8)
        fov=np.ones_like(g,bool);fov[:3]=False
        cfg=dict(score_offset=48,margin=1,steps=8,include_c5=True)
        for t in (1,112,255):
            p,d=candidate_mask(g,fov,f,scores,scores>150,cfg,t)
            self.assertFalse((d['seed']&~p).any())
            np.testing.assert_array_equal(p[d['protected']],d['seed'][d['protected']])
            self.assertFalse((p&~fov).any())

if __name__=='__main__':unittest.main()
