"""Synthetic archive fault tests, never placed in board-evidence directories."""
import contextlib
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED
import test_w2_board_runner as fixtures

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import package_w2_quality as packaging
import w2_quality_board_test as runner
from verify_w2_board_results import verify


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        helper=fixtures.W2RunnerTests();self.addCleanup(helper.doCleanups)
        self.context,_=helper.context();directory=self.context['directory']
        hardware=json.loads((ROOT/'build/w2_hardware_check_01.json').read_text())
        self.release=directory/'draft_release';manifest=packaging.assemble(self.release,hardware)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_w2(self.context);runner.baseline_w2(self.context);runner.candidate_w2(self.context)
        self.context['report'].update(revision=runner.REVISION,manifest=manifest,pynq='3.0.1',
            runtime_fclk0_mhz_register_readback=100.0,
            drivers={'dma':'pynq.lib.dma.DMA','control':'pynq.lib.axigpio.AxiGPIO','observer':'pynq.lib.axigpio.AxiGPIO'})
        # Deliberately synthetic monotonic boundaries; not measured performance.
        for index,record in enumerate(self.context['report']['transfers']):
            start=(index+1)*10_000_000
            record['timing_ns']=dict(config_start=start,dma_start=start+100_000,dma_end=start+6_100_000,snapshot_end=start+7_000_000,
                                     dma_transaction=6_000_000,full_inference=7_000_000,snapshot=900_000)
        display=types.ModuleType('IPython.display');display.display=lambda image:None
        with patch.dict(sys.modules,{'IPython.display':display}),contextlib.redirect_stdout(io.StringIO()):runner.finish_w2(self.context)
        nb=packaging.notebook();codes=[c for c in nb['cells'] if c['cell_type']=='code']
        for i,(cell,marker) in enumerate(zip(codes,('', 'W2_PRECHECK_PASS','W2_LOAD_PASS','W2_SMOKE_PASS','W2_BASELINE_PASS','W2_CANDIDATE_PASS','W2_RESULTS_READY')),1):
            cell.update(execution_count=i,outputs=[dict(output_type='stream',name='stdout',text=marker+'\n')])
        self.executed=directory/'executed.ipynb';self.executed.write_text(json.dumps(nb),encoding='utf-8')
        self.bundle=directory/'w2_results_bundle.zip'

    def test_all_words_preview_timing_and_observer_reconcile(self):
        result=verify(self.bundle,self.executed,self.release)
        self.assertEqual(result['words'],13303808);self.assertEqual(result['frames'],80)
        self.assertIsNone(result['browser_fps']);self.assertEqual(result['full_dataset_quality'],'PENDING_Q3')

    def altered_report(self,mutation):
        output=self.context['directory']/'corrupt.zip'
        with ZipFile(self.bundle) as src,ZipFile(output,'w',ZIP_DEFLATED) as dst:
            for name in src.namelist():
                data=src.read(name)
                if name=='w2_result.json':
                    report=json.loads(data);mutation(report);data=json.dumps(report).encode()
                dst.writestr(name,data)
        return output

    def test_observer_parameter_timing_frame_count_and_completion_tampering_rejected(self):
        mutations=[lambda r:r['transfers'][0]['hardware']['raw_pages'].__setitem__('3',0),
                   lambda r:r['transfers'][0]['timing_ns'].__setitem__('full_inference',1),
                   lambda r:r['transfers'].pop(),lambda r:r.__setitem__('retained_buffers',2)]
        for mutate in mutations:
            with self.subTest(mutation=mutate),self.assertRaises((ValueError,RuntimeError)):
                verify(self.altered_report(mutate),self.executed,self.release)

    def test_changed_notebook_code_rejected(self):
        nb=json.loads(self.executed.read_text());next(c for c in nb['cells'] if c['cell_type']=='code')['source'].append('print("changed")\n')
        self.executed.write_text(json.dumps(nb))
        with self.assertRaises(ValueError):verify(self.bundle,self.executed,self.release)


if __name__=='__main__':unittest.main()
