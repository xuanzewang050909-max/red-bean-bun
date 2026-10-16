"""Q4 final package extraction and required manual evidence coverage; HOST only."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from verify_q4_archive import manual_coverage
from q4_board import validate_q4

ROOT=Path(__file__).resolve().parents[1]
UPLOAD=ROOT/'build/deploy/q4_c5_upload_r1'


def evidence_fixture():
    records=[dict(run_id=f'batch_{i}',request={}) for i in range(120)]
    observations=[]
    def add(image='im0001',algorithm='C5',threshold=28,loop_id=None):
        rid=f'host_{len(records)}'
        records.append(dict(run_id=rid,request=dict(image_id=image,algorithm=algorithm,
            threshold=threshold,side=512,mode='final',png_profile='fast')))
        observations.append(dict(run_id=rid,visibility='visible',loop_id=loop_id))
    for image in ('im0001','im0002','im0324'):
        for algorithm in ('C2','C5'):add(image,algorithm)
    for threshold in (20,36):add(threshold=threshold)
    for _ in range(3):add()
    for _ in range(20):add(loop_id='HOST_LOOP')
    loops={'HOST_LOOP':dict(index=20,visible=True,verified_fps=1.0)}
    return records,observations,loops


class CoverageTests(unittest.TestCase):
    def test_complete_pairs_parameters_warmup_and_twenty_frames(self):
        data=evidence_fixture()
        result=manual_coverage(*data)
        self.assertTrue(result['display_complete'])
        self.assertEqual(len(result['paired_previews']),6)
        self.assertEqual(len(result['qualified_browser_loops']['HOST_LOOP']['warmup_run_ids']),3)
        self.assertEqual(len(data[0]),151)

    def test_missing_pair_or_threshold_is_rejected_even_with_full_loop(self):
        for index in (120,122,124,126,127):
            with self.subTest(index=index):
                records,observations,loops=evidence_fixture()
                observations=[o for o in observations if o['run_id']!=records[index]['run_id']]
                with self.assertRaisesRegex(ValueError,'manual preview missing'):
                    manual_coverage(records,observations,loops)

    def test_unrelated_algorithm_loop_or_hidden_warmup_cannot_pass(self):
        for problem in ('other_algorithm','hidden_warmup','missing_warmup','nineteen'):
            with self.subTest(problem=problem):
                records,observations,loops=evidence_fixture()
                if problem=='other_algorithm':
                    for r in records[-20:]:r['request']['algorithm']='C2'
                elif problem=='hidden_warmup':observations[-21]['visibility']='hidden'
                elif problem=='missing_warmup':records.pop(129)
                else:loops['HOST_LOOP']['index']=19
                with self.assertRaisesRegex(ValueError,'3-warmup'):
                    manual_coverage(records,observations,loops)

    def test_diagnostic_incomplete_is_explicit_and_extra_manual_runs_preserved(self):
        records,observations,loops=evidence_fixture()
        result=manual_coverage(records,observations,{},allow_incomplete_display=True)
        self.assertFalse(result['display_complete'])
        extra=copy.deepcopy(records[120]);extra['run_id']='extra'
        records.append(extra);observations.append(dict(run_id='extra',visibility='visible',loop_id=None))
        result=manual_coverage(records,observations,loops)
        self.assertEqual(len(result['paired_previews']['im0001_C2']),2)

    def test_hidden_parameter_preview_preserves_actual_run_but_reports_incomplete(self):
        records,observations,loops=evidence_fixture()
        observations[6]['visibility']='hidden'  # T20 task still executed.
        with self.assertRaisesRegex(ValueError,'manual preview missing'):
            manual_coverage(records,observations,loops)
        result=manual_coverage(records,observations,loops,allow_incomplete_manual=True)
        self.assertFalse(result['manual_complete']);self.assertTrue(result['display_complete'])
        self.assertEqual(result['missing_manual'],[dict(
            required=dict(side=512,mode='final',png_profile='fast',image_id='im0001',algorithm='C5',threshold=20),
            reason='NO_MATCHING_VISIBLE_MANUAL_OBSERVATION',actual_runs=[dict(run_id=records[126]['run_id'],visibility='hidden')])])
        self.assertEqual(result['threshold_previews']['20'],[])

    def test_manual_diagnostic_does_not_allow_incomplete_foreground_loop(self):
        records,observations,loops=evidence_fixture()
        observations[6]['visibility']='hidden';loops['HOST_LOOP']['visible']=False
        with self.assertRaisesRegex(ValueError,'3-warmup'):
            manual_coverage(records,observations,loops,allow_incomplete_manual=True)


class NotebookTests(unittest.TestCase):
    def extract(self,tamper=False):
        notebook=json.loads((UPLOAD/'q4_quality_start.ipynb').read_bytes())
        code=next(''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'q4_c5_experimental_r1.zip'
            shutil.copy2(UPLOAD/path.name,path)
            if tamper:
                with path.open('ab') as stream:stream.write(b'HOST_TAMPER')
            previous=Path.cwd()
            try:
                os.chdir(tmp)
                namespace={}
                if tamper:
                    with self.assertRaisesRegex(ValueError,'Wrong download bytes'):exec(code,namespace)
                    self.assertFalse((Path(tmp)/'q4_c5_experimental_r1').exists())
                    return
                output=io.StringIO()
                with contextlib.redirect_stdout(output):exec(code,namespace)
                root=namespace['browser_package_root']
                release,_=validate_q4(root)
                self.assertEqual(len(release['artifacts'])+1,138)
                self.assertIn('PACKAGE_BYTES_PASS',output.getvalue())
                self.assertEqual((root/'q4_board.py').read_bytes(),(ROOT/'scripts/q4_board.py').read_bytes())
                with self.assertRaisesRegex(RuntimeError,'Already extracted'):exec(code,namespace)
            finally:os.chdir(previous)

    def test_current_upload_notebook_extracts_exact_package_and_rejects_rerun(self):self.extract()
    def test_current_upload_tamper_rejected_before_extract_or_hardware(self):self.extract(tamper=True)
