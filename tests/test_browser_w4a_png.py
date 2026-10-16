"""Lossless delivery regressions against actual downloaded W3 output, not board FPS."""
import ast
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from test_browser_w4a import ROOT, PACKAGE, request
from pynq_w4a.protocol import PNG_PROFILES, Inputs, RequestError, file_info, validate_package
from pynq_w4a.service import encode_png, process_run
from browser_w4a_fixtures import HostHardware
from verify_browser_w4a_archive import check_run


class PngTests(unittest.TestCase):
    def test_actual_downloaded_w3_images_all_pixels_preserved_by_both_profiles(self):
        path = ROOT/'build/board_results/browser_w3_2026-10-14/browser_w3_session_bundle.zip'
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as z:
            checked = 0
            for name in z.namelist():
                if not name.endswith('.png'): continue
                pixels = np.array(Image.open(io.BytesIO(z.read(name))))
                untouched = pixels.copy()
                for profile in PNG_PROFILES:
                    target = Path(tmp)/(profile+'.png'); detail = {}
                    info = encode_png(target, pixels, profile, detail)
                    np.testing.assert_array_equal(np.array(Image.open(target)), pixels)
                    np.testing.assert_array_equal(pixels, untouched)
                    self.assertEqual(info, file_info(target))
                    self.assertEqual(detail['options'], PNG_PROFILES[profile])
                    points = detail['raw_timestamps_ns']
                    self.assertEqual(points, sorted(points))
                    self.assertEqual(sum(detail[k] for k in ('fromarray_ns','save_ns','file_hash_ns')), points[-1]-points[0])
                checked += 1
            self.assertEqual(checked,147)

    def test_baseline_passes_exact_original_save_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            pixels = np.arange(64,dtype=np.uint8).reshape(8,8)
            for profile in PNG_PROFILES:
                fake = type('FakeImage',(),{'mode':'L','save':lambda *_a,**_k:None})()
                with patch('pynq_w4a.service.Image.fromarray',return_value=fake), patch.object(fake,'save') as save, patch('pynq_w4a.service.file_info',return_value={'bytes':1,'sha256':'test'}):
                    encode_png(Path(tmp)/'x.png',pixels,profile,{})
                    self.assertEqual(save.call_args.kwargs, {'format':'PNG',**PNG_PROFILES[profile]})

    def test_bad_profiles_rejected_before_hardware(self):
        inputs = Inputs(PACKAGE,validate_package(PACKAGE)['images'])
        for profile in (None,0,True,{},'jpeg','PNG','fastest'):
            with self.subTest(profile=profile), self.assertRaises(RequestError):
                inputs.request(request(png_profile=profile))

    def test_hardware_observer_and_evaluation_are_byte_identical_to_board_tested_w3(self):
        for name in ('hardware.py','quality_observer.py','evaluation.py','__init__.py'):
            self.assertEqual((ROOT/'pynq_w4a'/name).read_bytes(),(ROOT/'pynq_w3'/name).read_bytes())
        m=validate_package(PACKAGE)
        old=ROOT/'build/deploy/browser_w3_c2_r1'
        for name in ('w2_quality.bit','w2_quality.hwh','w2_manifest.json','a0_dma_board_test.py'):
            self.assertEqual(file_info(PACKAGE/name),file_info(old/name))
        self.assertFalse(any('expected' in name or 'vectors' in name for name in m['artifacts']))

    def test_new_profile_changes_delivery_identity_not_native_control_or_output(self):
        from pynq_w4a.service import Manager
        import time
        with tempfile.TemporaryDirectory() as tmp:
            inputs=Inputs(PACKAGE,validate_package(PACKAGE)['images'])
            hardware=HostHardware(PACKAGE);hardware.open(); records=[]
            for index, profile in enumerate(PNG_PROFILES):
                q=inputs.request(request(png_profile=profile))
                folder=Path(tmp)/str(index);folder.mkdir()
                record=process_run(PACKAGE,inputs,hardware,{'request':q,'run_id':str(index),'accepted_server_ns':time.perf_counter_ns()},folder)
                records.append(record)
            self.assertEqual(records[0]['output']['sha256'],records[1]['output']['sha256'])
            self.assertEqual(records[0]['quality'],records[1]['quality'])
            self.assertEqual(records[0]['evidence']['requested_control_word']&65535,records[1]['evidence']['requested_control_word']&65535)
            self.assertEqual(hardware.sequence,2)
            self.assertEqual(hardware.retained,[])
            for kind in records[0]['images']:
                np.testing.assert_array_equal(np.array(Image.open(Path(tmp)/'0'/(kind+'.png'))),np.array(Image.open(Path(tmp)/'1'/(kind+'.png'))))

    def test_source_package_and_python310_syntax(self):
        m=validate_package(PACKAGE)
        for path in (ROOT/'pynq_w4a').glob('*.py'):
            self.assertEqual(file_info(path),m['artifacts']['pynq_w4a/'+path.name])
            tree=ast.parse(path.read_bytes(),feature_version=(3,10))
            imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertFalse(any(n.startswith(('software','prepare_','tests','cv2')) for n in imports))
        nb=json.loads((ROOT/'notebooks/browser_w4a_start.ipynb').read_bytes())
        cells=[c for c in nb['cells'] if c['cell_type']=='code']
        self.assertEqual(len(cells),6)
        for c in cells:
            self.assertIsNone(c['execution_count']);self.assertFalse(c['outputs'])
            ast.parse(''.join(c['source']),feature_version=(3,10))


if __name__=='__main__': unittest.main(verbosity=2)
