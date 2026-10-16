"""C7 mandatory foreground visual/parameter coverage; synthetic records are HOST only."""
import unittest
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.verify_q4d_archive import manual_coverage

def evidence():
    records=[dict(run_id=f'fixed_{i}',request={}) for i in range(160)];observations=[]
    def add(image='im0001',alg='C7',t=112,loop=None):
        rid=f'HOST_{len(records)}'
        records.append(dict(run_id=rid,request=dict(image_id=image,side=512,mode='final',png_profile='fast',algorithm=alg,threshold=t)))
        observations.append(dict(run_id=rid,visibility='visible',loop_id=loop))
    for image in ('im0001','im0002','im0324'):
        add(image,'C5',28);add(image,'C7',112)
    for alg,ts in [('C7',(96,128)),('C5',(20,36))]:
        for t in ts:add(alg=alg,t=t)
    for _ in range(3):add()
    for _ in range(20):add(loop='HOST_LOOP')
    return records,observations,{'HOST_LOOP':dict(index=20,visible=True,verified_fps=1.0)}

class CoverageTests(unittest.TestCase):
    def test_all_pairs_both_threshold_families_and_warmup(self):
        records,obs,loops=evidence();self.assertEqual(len(records),193)
        result=manual_coverage(records,obs,loops)
        self.assertEqual(set(result['threshold_previews']),{'C7_96','C7_128','C5_20','C5_36'})
        self.assertEqual(len(result['paired_previews']),6)
        self.assertEqual(len(result['qualified_browser_loops']['HOST_LOOP']['warmup_run_ids']),3)
    def test_each_distinct_manual_configuration_requires_visible_observation(self):
        # im0001/C7/112 is also displayed by three valid visible warmup requests.
        for i in (0,2,3,4,5,6,7,8,9):
            records,obs,loops=evidence();obs[i]['visibility']='hidden'
            with self.subTest(i=i),self.assertRaisesRegex(ValueError,'manual preview missing'):manual_coverage(records,obs,loops)
    def test_wrong_algorithm_or_threshold_cannot_count_as_c7_performance(self):
        for field,value in [('algorithm','C5'),('threshold',28)]:
            records,obs,loops=evidence()
            for r in records[-20:]:r['request'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'3-warmup'):manual_coverage(records,obs,loops)
    def test_hidden_warmup_and_missing_frame_fail(self):
        for change in ('warmup','nineteen'):
            records,obs,loops=evidence()
            if change=='warmup':obs[-21]['visibility']='hidden'
            else:loops['HOST_LOOP']['index']=19
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'3-warmup'):manual_coverage(records,obs,loops)

if __name__=='__main__':unittest.main()
