"""W3 host-only release and observer fault checks; no board measurements."""
import ast
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from browser_w3_fixtures import HostHardware, ObserverGPIO
from test_browser_w3 import PACKAGE, request
from pynq_w3.hardware import PynqHardware, check_metadata
from pynq_w3.protocol import Inputs, file_info, validate_package
from pynq_w3.quality_observer import check_observer_metadata


class ContractTests(unittest.TestCase):
    def test_source_release_and_runtime_reference_separation(self):
        manifest = validate_package(PACKAGE)
        for path in (ROOT / 'pynq_w3').glob('*.py'):
            self.assertEqual(file_info(path), manifest['artifacts']['pynq_w3/' + path.name])
            tree = ast.parse(path.read_bytes(), feature_version=(3, 10))
            imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
            imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
            self.assertFalse(any(i.startswith(('software', 'prepare_', 'cv2', 'tests', 'references')) or 'video' in i for i in imports))
        self.assertFalse(any('vectors' in n or 'expected' in n for n in manifest['artifacts']))

    def test_exact_w2_pair_observer_and_unchanged_w1_sources(self):
        manifest = validate_package(PACKAGE)
        for name in ('w2_quality.bit', 'w2_quality.hwh', 'a0_dma_board_test.py', 'w2_manifest.json'):
            self.assertEqual(file_info(PACKAGE / name), file_info(ROOT / 'build/deploy/w2_quality_2017_4_r1' / name))
        original = json.loads((ROOT / 'build/deploy/browser_a4_w1_r1/browser_manifest.json').read_bytes())
        for name, info in original['artifacts'].items():
            if name.startswith(('pynq_app/', 'ui/')):
                self.assertEqual(file_info(ROOT / name), info)
        for name in ('evaluation.py', 'quality_observer.py', '__init__.py'):
            self.assertEqual((ROOT / 'pynq_w3' / name).read_bytes(), (ROOT / 'pynq_app' / name).read_bytes())

    def test_open_checks_clock_identity_and_reset_before_frames(self):
        for failure in (None, 'clock', 'identity', 'reset'):
            with self.subTest(failure=failure):
                h = PynqHardware(PACKAGE)
                gpio = ObserverGPIO()
                control = types.SimpleNamespace(channel1=types.SimpleNamespace(setdirection=lambda d: None),
                    channel2=types.SimpleNamespace(setdirection=lambda d: None, read=lambda: 0))
                if failure == 'identity': gpio.pages[0] = 0
                if failure == 'reset': gpio.pages[4] = 1
                dma = object()
                h.state = 'PRECHECK_FPGA_UNCHANGED'
                h.dma_type, h.gpio_type = object, (ObserverGPIO, types.SimpleNamespace)
                h.overlay = types.SimpleNamespace(download=lambda: None, axi_dma_0=dma, point_control=control, point_observe=gpio)
                h.clocks = types.SimpleNamespace(fclk0_mhz=50 if failure == 'clock' else 100)
                h.environment = {}
                if failure:
                    with self.assertRaises((ValueError, RuntimeError)): h.open()
                    self.assertEqual(h.state, 'FAULT')
                    with self.assertRaises(ValueError): h.open()
                else:
                    h.open()
                    self.assertEqual(h.state, 'IDLE')
                self.assertEqual(h.downloads, 1)
                self.assertEqual(h.retained, [])

    def test_prior_observer_mismatch_stops_before_allocation(self):
        h = HostHardware(PACKAGE); h.open()
        inputs = Inputs(PACKAGE, validate_package(PACKAGE)['images'])
        config = inputs.request(request()); words, _ = inputs.load(config)
        h.observe.pages[4] = 1
        with self.assertRaisesRegex(ValueError, 'Prior observer'): h.run(words, config)
        self.assertEqual(h.buffers, [])
        self.assertEqual(h.state, 'FAULT')

    def test_response_and_gpio_mutations_are_detected_offline(self):
        # Check the actual downloaded W2 data against the production observer.
        import zipfile
        from pynq_w3.quality_observer import QualityObserver
        raw = ROOT / 'build/board_results/w2_quality_2026-10-14/w2_results_bundle.zip'
        with zipfile.ZipFile(raw) as z:
            report = json.loads(z.read('w2_result.json'))
        for record in report['transfers']:
            reader = object.__new__(QualityObserver); reader.clock_hz = 100000000
            reader.read_word = lambda p: record['hardware']['raw_pages'][str(p)]
            self.assertEqual(reader.completed(expected_control=record['control'], previous_sequence=record['index'], expected_words=record['words']), record['hardware'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
