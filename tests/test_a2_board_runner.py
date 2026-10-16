"""A2 host runner/reference/package regressions; fake DMA is not board proof."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import types
from unittest.mock import patch
from zipfile import ZipFile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import a2_gaussian_board_test as runner
from software.reference import gaussian3,LUT
from test_a0_board_runner import Buffer
from test_a1_board_runner import FakeGPIO,FakeDMA


class GaussianFakeDMA(FakeDMA):
    def send(self,buffer):
        side=int(round(np.sqrt(buffer.size)))
        words=np.asarray(buffer).reshape(side,side)
        mode=self.gpio.control&3
        green=((words>>8)&255).astype(np.uint8)
        value=green if mode==1 else gaussian3(green)
        if mode==3:value=LUT[value]
        expected=words if mode==0 else ((words&0xff000000)|green.astype(np.uint32)|(value.astype(np.uint32)<<8))
        self.rx[:]=expected.reshape(-1)
        if self.corrupt:self.rx[0]^=np.uint32(1)
        self.sendchannel.transferred=buffer.nbytes
        self.recvchannel.transferred=buffer.nbytes-(4 if self.bad_length else 0)
        count=(self.gpio.status&0x3fff)+1
        self.gpio.status=count|(count<<14)|(1<<28 if self.counter_error else 0)


class GaussianRunnerTests(unittest.TestCase):
    def context(self,**faults):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        directory=Path(temp.name)
        for side in (256,512):np.save(directory/f"stare_im0001_{side}.npy",runner.make_pattern(side,"gradient",0))
        gpio=FakeGPIO(); buffers=[]
        def allocate(shape,dtype):
            b=Buffer(shape,dtype); b.physical_address=0x10000000+(len(buffers)%2)*0x00200000; buffers.append(b); return b
        return {"directory":directory,"gpio":gpio,"dma":GaussianFakeDMA(gpio,**faults),"allocate":allocate,
                "retained":[],"save":lambda:None,"report":{"status":"A2_LOADED_NO_TRANSFER","transfers":[]}},buffers

    def test_separable_reference_matches_m0_correlation_all_modes_and_center_fov(self):
        rng=np.random.default_rng(32)
        words=rng.integers(0,1<<24,(17,19),dtype=np.uint32)|(rng.integers(0,2,(17,19),dtype=np.uint32)<<24)
        green=((words>>8)&255).astype(np.uint8); gaussian=gaussian3(green)
        for mode,value in ((1,green),(2,gaussian),(3,LUT[gaussian])):
            expected=(words&0xff000000)|green.astype(np.uint32)|(value.astype(np.uint32)<<8)
            np.testing.assert_array_equal(runner.gaussian_expected(words,mode),expected)
        np.testing.assert_array_equal(runner.gaussian_expected(words,0),words)

    def test_edge_rounding_constant_and_impulse_exact(self):
        for pattern in ("black","white","impulse","checker"):
            words=runner.make_pattern(256,pattern,0)
            expected=gaussian3(((words>>8)&255).astype(np.uint8))
            np.testing.assert_array_equal((runner.gaussian_expected(words,2)>>8)&255,expected)

    def test_37_frames_require_smoke_and_release_only_complete_buffers(self):
        c,buffers=self.context()
        with self.assertRaises(RuntimeError):runner.full_a2(c)
        with contextlib.redirect_stdout(io.StringIO()):runner.smoke_a2(c); runner.full_a2(c)
        self.assertEqual(len(c["report"]["transfers"]),37)
        self.assertEqual(c["report"]["status"],"A2_PASS_37_GAUSSIAN_FRAMES_NOT_FULL_SEGMENTATION")
        self.assertEqual(len([r for r in c["report"]["transfers"] if "saved_output" in r]),4)
        self.assertEqual(c["retained"],[]); self.assertTrue(all(b.freed for b in buffers))

    def test_faults_retain_buffers_and_block_full_suite(self):
        for fault in ("corrupt","bad_length","counter_error"):
            with self.subTest(fault=fault):
                c,buffers=self.context(**{fault:True})
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(AssertionError):runner.smoke_a2(c)
                self.assertEqual(c["report"]["status"],"FAILED_OR_INTERRUPTED")
                self.assertEqual(len(c["retained"]),2); self.assertFalse(any(b.freed for b in buffers))
                with self.assertRaises(RuntimeError):runner.full_a2(c)

    def test_wrong_geometry_mode_and_stare_fov_rejected(self):
        c,b=self.context()
        for side,mode in ((17,2),(256,4)):
            with self.assertRaises(ValueError):runner.transfer_a2(c,side,mode,"gradient")
        self.assertEqual(b,[])
        np.save(c["directory"]/"stare_im0001_256.npy",np.full((256,256),0xff000000,np.uint32))
        with self.assertRaises(ValueError):runner.make_pattern(256,"stare",0,c["directory"])

    def test_preview_bundle_contains_returned_arrays_and_repeat_keeps_evidence(self):
        c,_=self.context()
        c["save"]=lambda:(c["directory"]/"a2_gaussian_result.json").write_text(json.dumps(c["report"]),encoding="utf-8")
        module=types.ModuleType("IPython.display"); displayed=[]; module.display=displayed.append
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_a2(c); runner.full_a2(c)
            with patch.dict(sys.modules,{"IPython.display":module}):runner.show_a2_results(c)
        self.assertEqual(displayed[0].size,(768,280))
        bundle=c["directory"]/"a2_results_bundle.zip"
        with ZipFile(bundle) as archive:
            self.assertEqual(len(archive.namelist()),6)
            for name in archive.namelist():self.assertEqual(archive.read(name),(c["directory"]/name).read_bytes())
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in c["directory"].iterdir()}
        with patch.dict(sys.modules,{"IPython.display":module}),self.assertRaises(RuntimeError):runner.show_a2_results(c)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in c["directory"].iterdir()})

    def test_saved_notebook_passes_while_code_or_fixed_artifact_change_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            for name in runner.FIXED:(directory/name).write_bytes(b"fixed")
            nb={"nbformat":4,"cells":[{"cell_type":"code","source":["x=1\n"],"metadata":{},"execution_count":None,"outputs":[]}],"metadata":{}}
            p=directory/runner.NOTEBOOK; p.write_text(json.dumps(nb),encoding="utf-8")
            manifest={"revision":runner.REVISION,"artifacts":{p.name:{"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in directory.iterdir()},
                      "notebook_validation":{"algorithm":"sha256-code-cells-v1","sha256":runner.notebook_code_hash(nb)}}
            nb["cells"][0].update(execution_count=1,outputs=[{"output_type":"stream","text":"saved"}]); p.write_text(json.dumps(nb),encoding="utf-8")
            runner.validate_a2_package(directory,manifest)
            nb["cells"][0]["source"]=["x=2\n"]; p.write_text(json.dumps(nb),encoding="utf-8")
            with self.assertRaises(ValueError):runner.validate_a2_package(directory,manifest)
            nb["cells"][0]["source"]=["x=1\n"]; p.write_text(json.dumps(nb),encoding="utf-8")
            (directory/"a2_gaussian.bit").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):runner.validate_a2_package(directory,manifest)


if __name__=="__main__":unittest.main()
