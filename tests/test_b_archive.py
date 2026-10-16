"""B real-record verification and corruption rejection; no new board execution."""
import copy
import json
import stat
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile,ZipInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import archive_b_board_results as archive

RAW=ROOT/'build/board_results/b_integration_2026-10-12'
PACKAGE=ROOT/'build/deploy/b_integration_2017_4_r2'


class BundleBoundaryTests(unittest.TestCase):
    def bundle(self,names,symlink=False,large=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'evidence.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with ZipFile(path,'w') as z:
                for i,name in enumerate(names):
                    if symlink and i==0:
                        entry=ZipInfo(name);entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
                        z.writestr(entry,b'target')
                    else:z.writestr(name,b'x'*(500001 if large and name=='b_integration_result.json' else 1))
        return path

    def test_duplicate_member(self):
        names=sorted(archive.BUNDLE_NAMES);names[-1]=names[0]
        with self.assertRaisesRegex(ValueError,'ZIP member'):archive.read_bundle(self.bundle(names))

    def test_traversal_member(self):
        names=sorted(archive.BUNDLE_NAMES);names[0]='../b_integration_result.json'
        with self.assertRaisesRegex(ValueError,'ZIP member'):archive.read_bundle(self.bundle(names))

    def test_missing_member(self):
        with self.assertRaisesRegex(ValueError,'ZIP member'):archive.read_bundle(self.bundle(sorted(archive.BUNDLE_NAMES)[:-1]))

    def test_symlink(self):
        with self.assertRaisesRegex(ValueError,'Unsupported ZIP'):archive.read_bundle(self.bundle(sorted(archive.BUNDLE_NAMES),symlink=True))

    def test_oversized_json(self):
        with self.assertRaisesRegex(ValueError,'member size'):archive.read_bundle(self.bundle(sorted(archive.BUNDLE_NAMES),large=True))


@unittest.skipUnless((RAW/'b_results_bundle.zip').is_file(),'Real B raw data remain in ignored local storage')
class ActualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members=archive.read_bundle(RAW/'b_results_bundle.zip')
        cls.report=json.loads(cls.members['b_integration_result.json'])
        cls.notebook=json.loads((RAW/'b_integration_check_executed.ipynb').read_bytes())
        cls.manifest=json.loads((PACKAGE/'b_manifest.json').read_bytes())
        archive.validate_b_package(PACKAGE,cls.manifest)

    def verify(self,report=None,notebook=None,members=None):
        return archive.verify_records(self.notebook if notebook is None else notebook,self.report if report is None else report,
            self.manifest,PACKAGE,self.members if members is None else members)

    def test_actual_complete_records_raw_arrays_and_timings(self):
        r=self.verify()
        self.assertEqual(sum(x['words'] for x in r['frames']),70647808)
        self.assertEqual(sum(x['words'] for x in r['raw_arrays']),983040)
        self.assertEqual(len(r['timing']),3)
        self.assertAlmostEqual(r['timing'][2]['loop_fps'],1.6006497113241138)

    def test_mutable_notebook_metadata_and_markdown(self):
        n=copy.deepcopy(self.notebook);n['metadata']['host_probe']=True
        next(c for c in n['cells'] if c['cell_type']=='markdown')['source']=['Changed commentary']
        self.verify(notebook=n)

    def test_changed_code(self):
        n=copy.deepcopy(self.notebook);next(c for c in n['cells'] if c['cell_type']=='code')['source']+=['\nprint("changed")']
        with self.assertRaisesRegex(ValueError,'code changed'):self.verify(notebook=n)

    def test_error_output(self):
        n=copy.deepcopy(self.notebook);next(c for c in n['cells'] if c['cell_type']=='code')['outputs'].append({'output_type':'error'})
        with self.assertRaisesRegex(ValueError,'error output'):self.verify(notebook=n)

    def test_execution_order(self):
        n=copy.deepcopy(self.notebook);next(c for c in n['cells'] if c['cell_type']=='code')['execution_count']=20
        with self.assertRaisesRegex(ValueError,'execution sequence'):self.verify(notebook=n)

    def test_partial_suite(self):
        r=copy.deepcopy(self.report);r['transfers'].pop()
        with self.assertRaisesRegex(ValueError,'frame ledger'):self.verify(report=r)

    def test_wrong_release(self):
        r=copy.deepcopy(self.report);r['manifest']['revision']='wrong'
        with self.assertRaisesRegex(ValueError,'release manifest'):self.verify(report=r)

    def test_wrong_runtime(self):
        r=copy.deepcopy(self.report);r['pynq']='2.2.1'
        with self.assertRaisesRegex(ValueError,'runtime'):self.verify(report=r)

    def test_reload_cannot_claim_same_overlay(self):
        r=copy.deepcopy(self.report);r['overlay_downloads']=2
        with self.assertRaisesRegex(ValueError,'single download'):self.verify(report=r)

    def test_nonofficial_video_binding(self):
        r=copy.deepcopy(self.report);r['drivers']['vdma']='fake.Driver'
        with self.assertRaisesRegex(ValueError,'official drivers'):self.verify(report=r)

    def test_wrong_frame_counter(self):
        r=copy.deepcopy(self.report);r['transfers'][0]['frame_status']=0
        with self.assertRaisesRegex(ValueError,'frame count'):self.verify(report=r)

    def test_dma_error(self):
        r=copy.deepcopy(self.report);r['transfers'][0]['dma_status']['s2mm']|=0x20
        with self.assertRaisesRegex(ValueError,'DMA halted'):self.verify(report=r)

    def test_overlapping_ddr(self):
        r=copy.deepcopy(self.report);r['transfers'][0]['rx_address']=r['transfers'][0]['tx_address']
        with self.assertRaisesRegex(ValueError,'DDR address'):self.verify(report=r)

    def test_independent_hash_detects_fabricated_golden_and_output(self):
        r=copy.deepcopy(self.report);r['transfers'][0]['expected_sha256']=r['transfers'][0]['output_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Independent input'):self.verify(report=r)

    def test_raw_array_hash(self):
        m=dict(self.members);name=next(iter(archive.ARRAY_NAMES));m[name]=m[name][:-1]+bytes([m[name][-1]^1])
        with self.assertRaisesRegex(ValueError,'saved file hash'):self.verify(members=m)

    def test_raw_timing_sample_not_bound_to_summary(self):
        r=copy.deepcopy(self.report);r['transfers'][64]['benchmark']['sample_ns']+=1;r['transfers'][64]['benchmark']['dma_ns']+=1
        with self.assertRaisesRegex(ValueError,'samples differ'):self.verify(report=r)

    def test_zero_duration(self):
        r=copy.deepcopy(self.report);r['transfers'][61]['benchmark']['dma_ns']=0
        with self.assertRaisesRegex(ValueError,'raw timing duration'):self.verify(report=r)

    def test_warmup_exclusion(self):
        r=copy.deepcopy(self.report);r['transfers'][61]['benchmark']['warmup']=False
        with self.assertRaisesRegex(ValueError,'warmup/display'):self.verify(report=r)

    def test_fps_cannot_be_changed(self):
        r=copy.deepcopy(self.report);r['performance'][0]['frames_per_sum_transaction_seconds']+=10
        with self.assertRaisesRegex(ValueError,'Timing metric mismatch'):self.verify(report=r)

    def test_loop_fps_cannot_be_changed(self):
        r=copy.deepcopy(self.report);r['performance'][0]['loop_fps']+=1
        with self.assertRaisesRegex(ValueError,'loop_fps'):self.verify(report=r)

    def test_display_error(self):
        r=copy.deepcopy(self.report);r['display']['final_vdma_status']['mm2s']|=0x20
        with self.assertRaisesRegex(ValueError,'Video output halted'):self.verify(report=r)

    def test_submitted_frame_does_not_match_png(self):
        r=copy.deepcopy(self.report);r['display']['submissions'][1]['sha256_bgr']='0'*64
        with self.assertRaisesRegex(ValueError,'BGR framebuffer'):self.verify(report=r)

    def test_notebook_medical_image_missing(self):
        n=copy.deepcopy(self.notebook);cell=[c for c in n['cells'] if c['cell_type']=='code'][6]
        cell['outputs']=[o for o in cell['outputs'] if o['output_type']!='display_data']
        with self.assertRaisesRegex(ValueError,'medical notebook image'):self.verify(notebook=n)

    def test_raw_json_visual_pending_must_remain_original(self):
        r=copy.deepcopy(self.report);r['display']['visual_status']='PASS'
        with self.assertRaisesRegex(ValueError,'Original display record'):self.verify(report=r)


if __name__=='__main__':unittest.main()
