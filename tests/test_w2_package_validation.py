"""Working-package checks without programming hardware or publishing a release."""
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
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'pynq_app'))
import package_w2_quality as packaging
import w2_quality_board_test as runner


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'draft'
        self.hardware=json.loads((ROOT/'build/w2_hardware_check_01.json').read_text())
        self.manifest=packaging.assemble(self.directory,self.hardware)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        for name in sorted(n for n in runner.FIXED if n.endswith('.py')):
            module=sys.modules[Path(name).stem]
            self.stack.enter_context(patch.object(module,'__file__',str(self.directory/name)))

    def test_complete_precheck_constructs_metadata_only_without_allocation_or_download(self):
        calls=[]
        class Overlay:
            def __init__(this,path,download):
                calls.append(('overlay',download));this.ip_dict=copy.deepcopy(self.hardware['ip_dict'])
            def download(this):raise AssertionError('No programming allowed during precheck')
        def allocate(*args,**kwargs):raise AssertionError('No allocation during precheck')
        pynq=types.ModuleType('pynq');pynq.__version__='3.0.1';pynq.Overlay=Overlay;pynq.allocate=allocate;pynq.Clocks=types.SimpleNamespace(fclk0_mhz=100.0)
        lib=types.ModuleType('pynq.lib');lib.DMA=type('DMA',(),{});lib.AxiGPIO=type('AxiGPIO',(),{})
        with patch.dict(sys.modules,{'pynq':pynq,'pynq.lib':lib}),patch.object(runner.platform,'machine',return_value='armv7l'),contextlib.redirect_stdout(io.StringIO()):
            context=runner.prepare_w2(self.directory,[])
        self.assertEqual(calls,[('overlay',False)])
        self.assertEqual(context['report']['status'],'W2_PRECHECK_FPGA_UNCHANGED')
        self.assertEqual(len(context['vectors']['cases']),80)

    def test_execution_output_autosave_allowed_but_code_change_rejected(self):
        path=self.directory/runner.NOTEBOOK;notebook=json.loads(path.read_text(encoding='utf-8'))
        code=next(c for c in notebook['cells'] if c['cell_type']=='code')
        code['execution_count']=1;code['outputs']=[{'output_type':'stream','name':'stdout','text':['autosaved\n']}]
        path.write_text(json.dumps(notebook),encoding='utf-8')
        runner.validate_package(self.directory,self.manifest)
        code['source'].append('print("changed")\n');path.write_text(json.dumps(notebook),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'Notebook code changed'):runner.validate_package(self.directory,self.manifest)

    def test_fixed_bit_hwh_and_script_tampering_rejected(self):
        for name in ('w2_quality.bit','w2_quality.hwh','quality_observer.py','w2_vectors.npz'):
            path=self.directory/name;before=path.read_bytes();path.write_bytes(before+b'changed')
            with self.assertRaisesRegex(RuntimeError,'Package mismatch'):runner.validate_package(self.directory,self.manifest)
            path.write_bytes(before)

    def test_stale_import_path_rejected(self):
        with patch.object(sys.modules['quality_observer'],'__file__',str(ROOT/'pynq_app/quality_observer.py')):
            with self.assertRaisesRegex(RuntimeError,'Stale imported'):runner.validate_package(self.directory,self.manifest)

    def test_manifest_missing_members_revision_and_clock_rejected(self):
        for field,value in (('revision','old'),('hardware_clock_hz',60_000_000),('artifacts',{})):
            bad=copy.deepcopy(self.manifest);bad[field]=value
            with self.assertRaises(RuntimeError):runner.validate_package(self.directory,bad)

    def test_release_manifest_is_not_run_and_notebook_has_seven_empty_ordered_cells(self):
        self.assertEqual(self.manifest['board_status'],'NOT_RUN')
        self.assertEqual(set(p.name for p in self.directory.iterdir()),runner.FIXED|{runner.NOTEBOOK,'w2_manifest.json'})
        notebook=packaging.notebook();cells=[c for c in notebook['cells'] if c['cell_type']=='code']
        self.assertEqual(len(cells),7)
        self.assertTrue(all(c['execution_count'] is None and c['outputs']==[] for c in cells))
        self.assertEqual(json.loads((ROOT/'notebooks/w2_quality_check.ipynb').read_text(encoding='utf-8')),notebook)

    def test_wrong_clock_rejected_immediately_after_single_load(self):
        calls=[]
        context=dict(report=dict(status='W2_PRECHECK_FPGA_UNCHANGED'),save=lambda:None,retained=[],
                     overlay=types.SimpleNamespace(download=lambda:calls.append('download')),
                     clocks=types.SimpleNamespace(fclk0_mhz=50.0))
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'FCLK0'):
            runner.load_w2(context)
        self.assertEqual(calls,['download']);self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')
        with self.assertRaises(RuntimeError):runner.load_w2(context)
        self.assertEqual(calls,['download'])

    def test_reset_identity_and_official_drivers_checked_before_transfers(self):
        from test_w2_board_runner import ObserverGPIO
        from test_a1_board_runner import FakeGPIO,FakeDMA
        gpio=FakeGPIO();gpio.channel1.setdirection=lambda v:None;gpio.channel2.setdirection=lambda v:None
        observer=ObserverGPIO();dma=FakeDMA(gpio);calls=[]
        # Separate GPIO subclasses are represented by the official driver's base tuple here.
        overlay=types.SimpleNamespace(download=lambda:calls.append('download'),axi_dma_0=dma,point_control=gpio,point_observe=observer)
        context=dict(report=dict(status='W2_PRECHECK_FPGA_UNCHANGED',manifest=self.manifest),save=lambda:None,retained=[],
                     overlay=overlay,clocks=types.SimpleNamespace(fclk0_mhz=100.0),dma_class=FakeDMA,gpio_class=(FakeGPIO,ObserverGPIO))
        with contextlib.redirect_stdout(io.StringIO()):runner.load_w2(context)
        self.assertEqual(calls,['download']);self.assertEqual(context['report']['status'],'W2_LOADED_NO_TRANSFER')
        self.assertEqual(context['report']['runtime_fclk0_mhz_register_readback'],100.0)
        self.assertEqual(observer.pages[4],0)


if __name__=='__main__':unittest.main()
