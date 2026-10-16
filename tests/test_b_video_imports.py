"""Reproduce the real video initializer's export boundary without FPGA access."""
import ast
import contextlib
import copy
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import b_integration_board_test as runner
import check_b_driver_imports as import_check


class BVideoImportTests(unittest.TestCase):
    def environment(self):
        snapshot=ROOT/'references/PYNQ/v3.0.1/pynq/lib/video'
        names=('pynq','pynq.ps','pynq.lib','pynq.lib.video','pynq.lib.video.common',
            'pynq.lib.video.clocks','pynq.lib.video.dma','pynq.lib.video.dvi',
            'pynq.lib.video.frontend','pynq.lib.video.hierarchies','pynq.lib.video.drm')
        modules={name:types.ModuleType(name) for name in names}
        for name in ('pynq','pynq.lib','pynq.lib.video'):
            modules[name].__path__=[];modules[name].__package__=name
        p=modules['pynq'];p.__version__='3.0.1';p.ps=modules['pynq.ps'];p.lib=modules['pynq.lib']
        p.ps.CPU_ARCH=p.ps.ZYNQ_ARCH='armv7l';p.ps.ZU_ARCH='aarch64'
        p.lib.video=modules['pynq.lib.video']
        for name in ('DMA','AxiGPIO'):setattr(p.lib,name,type(name,(),{}))
        modules['pynq.lib.video.dma'].AxiVDMA=type('AxiVDMA',(),{})
        for name in ('VideoOut','HDMIWrapper'):setattr(modules['pynq.lib.video.hierarchies'],name,type(name,(),{}))
        # Actual unmodified Common definitions and video __init__ are executed.
        # Only hardware/C-library dependencies are facades; no driver is bound.
        exec(compile((snapshot/'common.py').read_text(encoding='utf-8'),str(snapshot/'common.py'),'exec'),modules['pynq.lib.video.common'].__dict__)
        metadata=json.loads((ROOT/'results/b_integration_2017_4/host_metadata_final.json').read_text(encoding='utf-8'))
        calls=[]
        def overlay(path,download=True):
            calls.append(download)
            if download:raise AssertionError('Precheck must never download FPGA')
            return types.SimpleNamespace(ip_dict=copy.deepcopy(metadata['ip_dict']))
        def allocate(*args,**kwargs):raise AssertionError('Precheck must never allocate DMA buffers')
        p.Overlay=overlay;p.allocate=allocate
        patches=patch.dict(sys.modules,modules);patches.start();self.addCleanup(patches.stop)
        video=modules['pynq.lib.video']
        exec(compile((snapshot/'__init__.py').read_text(encoding='utf-8'),str(snapshot/'__init__.py'),'exec'),video.__dict__)
        for name in ('AxiVDMA','VideoOut','HDMIWrapper'):self.assertFalse(hasattr(video,name))
        return calls,modules

    def test_pinned_namespaces_accept_fix_and_reject_original_release(self):
        result=import_check.check(ROOT/'scripts/b_integration_board_test.py')
        self.assertEqual(len(result['resolved_imports']),5)
        self.assertEqual(result['board_status'],'NOT_RUN')
        with self.assertRaisesRegex(ValueError,'Missing official export: pynq.lib.video.AxiVDMA'):
            import_check.check(ROOT/'build/deploy/b_integration_2017_4_r1/b_integration_board_test.py')

    def test_actual_initializer_reproduces_original_import_error_before_overlay(self):
        calls,_=self.environment()
        old=ast.parse((ROOT/'build/deploy/b_integration_2017_4_r1/b_integration_board_test.py').read_text(encoding='utf-8'))
        function=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_b')
        namespace=vars(runner).copy();exec(compile(ast.Module(body=[function],type_ignores=[]),'original_r1_prepare','exec'),namespace)
        with self.assertRaisesRegex(ImportError,'AxiVDMA'):namespace['prepare_b']('.',[])
        self.assertEqual(calls,[])

    def test_corrected_precheck_completes_without_download_or_allocation(self):
        calls,modules=self.environment()
        baseline=ROOT/'build/deploy/b_integration_2017_4_r1'
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);manifest=json.loads((baseline/'b_manifest.json').read_text(encoding='utf-8'))
            for name in manifest['artifacts']:(directory/name).write_bytes((baseline/name).read_bytes())
            (directory/'b_integration_board_test.py').write_bytes((ROOT/'scripts/b_integration_board_test.py').read_bytes())
            manifest['revision']=runner.REVISION
            manifest['artifacts']['b_integration_board_test.py']={'sha256':runner.sha256_file(directory/'b_integration_board_test.py')}
            (directory/'b_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with patch.object(runner.platform,'machine',return_value='armv7l'),contextlib.redirect_stdout(io.StringIO()) as output:
                context=runner.prepare_b(directory,[])
            self.assertIn('B_PRECHECK_PASS',output.getvalue())
            self.assertEqual(calls,[False])
            self.assertEqual(context['report']['overlay_downloads'],0)
            self.assertEqual(context['report']['status'],'B_PRECHECK_FPGA_UNCHANGED')
            self.assertIs(context['vdma_class'],modules['pynq.lib.video.dma'].AxiVDMA)
            self.assertIs(context['video_out_class'],modules['pynq.lib.video.hierarchies'].VideoOut)
            self.assertIs(context['video_class'],modules['pynq.lib.video.hierarchies'].HDMIWrapper)
            self.assertTrue((directory/'b_integration_result.json').is_file())


if __name__=='__main__':unittest.main()
