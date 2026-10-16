"""Diagnostic collector integrity only; no board execution or recovery."""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_c7_showcase_failure import collect, os_snapshot


class CollectionTests(unittest.TestCase):
    def test_partial_evidence_preserved_and_repeat_is_new_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package = root/'c7_showcase_r1'
            run = package/'browser_results'/'session'/'partial_run'; run.mkdir(parents=True)
            originals = {root/'c7_showcase.ipynb': b'{"cells":[]}',
                package/'showcase_manifest.json': b'{}',
                run/'output_packed.npy': b'\x93NUMPY\x00\xffHOST partial evidence',
                run/'record.json': b'{"status":"RUNNING"}'}
            for p, data in originals.items(): p.write_bytes(data)
            first = collect(root, snapshot=lambda: {'HOST_ONLY': 'synthetic OS evidence'})
            second = collect(root, snapshot=lambda: {'HOST_ONLY': 'synthetic OS evidence'})
            self.assertNotEqual(first, second)
            with zipfile.ZipFile(first) as z:
                m = json.loads(z.read('failure_collection_manifest.json'))
                self.assertEqual(m['status'], 'INTERRUPTED_DIAGNOSTICS_ONLY_NOT_PASS')
                self.assertEqual(set(z.namelist()), set(m['files'])|{'failure_collection_manifest.json'})
                for name, meta in m['files'].items():
                    raw = z.read(name)
                    self.assertEqual(len(raw), meta['bytes'])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['sha256'])
                for p, data in originals.items():
                    self.assertEqual(p.read_bytes(), data)
                    self.assertEqual(z.read('evidence/'+p.relative_to(root).as_posix()), data)

    def test_wrong_root_rejected_without_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): collect(td, snapshot=lambda: {})
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_missing_os_tools_are_recorded_without_install_or_recovery(self):
        with patch('collect_c7_showcase_failure.subprocess.run', side_effect=FileNotFoundError('HOST unavailable')):
            result = os_snapshot()
        self.assertIn('FileNotFoundError', result['dmesg']['error'])
        self.assertIn('no PL access', result['scope'])

if __name__ == '__main__': unittest.main()
