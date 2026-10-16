"""Safety/statistics regressions. Fixtures are HOST TESTS, never board results."""
import asyncio
import copy
import json
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from system_bench import board, common
from scripts.verify_c7_w4_results import verify_hardware, execution_cells


class ProtocolTests(unittest.TestCase):
    def test_notebook_empty_tail_is_editor_artifact(self):
        original={'cells':[dict(cell_type='code',source=['x=1\n'],execution_count=None,outputs=[])]}
        actual=copy.deepcopy(original);actual['cells'][0]['execution_count']=1
        actual['cells'].append(dict(cell_type='code',source=[],execution_count=None,outputs=[]))
        cells,count=execution_cells(actual,original)
        self.assertEqual((len(cells),count),(1,1))
        for key,value in [('source',['x=2']),('execution_count',2),('outputs',[{'output_type':'stream','text':['x']}])]:
            bad=copy.deepcopy(actual);bad['cells'][-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):execution_cells(bad,original)
        actual['cells'][0]['source']=['x=2\n']
        with self.assertRaises(ValueError):execution_cells(actual,original)

    def test_alternate_order(self):
        self.assertEqual([common.group_order(i) for i in (1,2,3)], [('CPU','PL'),('PL','CPU'),('CPU','PL')])

    def test_statistics_actual_100(self):
        r=common.stats(list(range(1,101)))
        self.assertEqual(r['n'],100);self.assertEqual(r['median_ns'],50.5)
        self.assertAlmostEqual(r['p95_ns'],95.05)

    def test_incomplete_and_invalid_statistics(self):
        for values in ([1]*99,[1]*101,[0]*100,[-1]*100,[float('nan')]*100):
            with self.subTest(values=values[:2]), self.assertRaises(ValueError): common.stats(values)

    def test_summary_cannot_accept_partial(self):
        with self.assertRaises(ValueError): common.summarize([],[])

    def test_full_summary_separates_warmups_sizes_and_devices(self):
        rows=[];groups=[];clock=100
        for side in (256,512):
            for repeat in (1,2,3):
                for kind in common.group_order(repeat):
                    group=dict(side=side,repeat=repeat,kind=kind)
                    for i in range(103):
                        if i==3:group['measured_start_ns']=clock
                        duration=9999 if i<3 else i-2
                        row=dict(side=side,repeat=repeat,kind=kind,index=i,warmup=i<3,
                            iteration_start_ns=clock,call_start_ns=clock+1,call_end_ns=clock+1+duration,
                            process_start_ns=clock,process_end_ns=clock+duration,data_saved_ns=clock+duration+2,
                            hardware=dict(timing_ns={k:duration for k in ('pl_core_frame_ns','dma_transaction_ns','inference_ns','cpu_snapshot_ns')}))
                        rows.append(row);clock+=duration+5
                    group['measured_end_ns']=clock;groups.append(group)
        report=common.summarize(rows,groups)
        self.assertEqual(len(report['groups']),12)
        for group in report['groups']:
            self.assertEqual(group['metrics']['call']['median_ns'],50.5)
            self.assertEqual(group['metrics']['call']['max_ns'],100)
        with self.assertRaises(ValueError):common.summarize(rows,groups[:-1])
        bad=copy.deepcopy(rows);bad[3]['warmup']=True
        with self.assertRaises(ValueError):common.summarize(bad,groups)

    def test_freeze_protocol_and_manifest_pin(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); (p/'c7_baseline').mkdir();(p/'c7_baseline/q4d_manifest.json').write_text('{}')
            common.write_json(p/'w4_manifest.json',dict(revision=common.REVISION,board_status='BOARD_NOT_RUN'))
            with self.assertRaisesRegex(ValueError,'trusted C7'):common.validate(p)

    def test_no_cpu_fallback_in_production(self):
        for p in (ROOT/'pynq_q4d').glob('*.py'):
            self.assertNotIn('system_bench',p.read_text());self.assertNotIn('bench_reference',p.read_text())


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();p=Path(self.temp.name);(p/'raw').mkdir()
        self.hw=SimpleNamespace(state='IDLE',retained=[],downloads=1,sequence=0,last_attempt=None)
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.ctx=dict(base=dict(hardware=self.hw,executor=self.pool,sockets=[]),state='LOADED_IDLE',
            directory=p,session='HOST_TEST_ONLY',completed=[],inflight=None,rows=[],groups=[],model={},
            inputs={256:np.zeros((256,256),np.uint32)},protocol={'expected_output_sha256':{'im0001_256_C7':'0'*64}})

    async def asyncTearDown(self):
        self.pool.shutdown(wait=True);self.temp.cleanup()

    async def test_load_twice_rejected_without_open(self):
        with self.assertRaises(ValueError):await board.load(self.ctx)
        self.assertEqual(self.hw.downloads,1)

    async def test_measure_wrong_size_order_rejected(self):
        with self.assertRaises(ValueError):await board.measure(self.ctx,512)
        self.assertIsNone(self.ctx['inflight'])

    async def test_fault_cannot_measure_or_finish(self):
        self.ctx['state']='FAULT'
        with self.assertRaises(ValueError):await board.measure(self.ctx,256)
        with self.assertRaises(ValueError):board.finish_export(self.ctx)

    async def test_exception_preserves_reference_and_stops(self):
        token=object();self.hw.retained=[token]
        def fail():raise RuntimeError('in-flight fixture error')
        with self.assertRaises(RuntimeError):await board.bounded(self.ctx,fail)
        self.assertEqual(self.ctx['state'],'FAULT');self.assertIs(self.hw.retained[0],token)
        self.assertTrue((self.ctx['directory']/'failure.json').exists())
        self.assertIsNotNone(self.ctx['inflight'])

    async def test_timeout_does_not_cancel_owner(self):
        import threading
        gate=threading.Event()
        def work():gate.wait(2);return 42
        async def expire(future,timeout):raise asyncio.TimeoutError('HOST timeout fixture')
        try:
            with patch.object(board.asyncio,'wait_for',expire):
                with self.assertRaises(asyncio.TimeoutError):await board.bounded(self.ctx,work)
            self.assertFalse(self.ctx['inflight'].cancelled());self.assertEqual(self.ctx['state'],'FAULT')
        finally:gate.set()
        self.assertEqual(await self.ctx['inflight'],42)
        self.assertEqual(self.ctx['state'],'FAULT')

    async def test_cpu_branch_never_calls_dma(self):
        def reject(*args):raise AssertionError('DMA called during CPU comparator')
        self.hw.run=reject;self.ctx['cpu']=lambda words,model,t:words.copy()
        out,row=board.timed_call(self.ctx,'CPU',256)
        self.assertIsNone(row['hardware']);self.assertTrue(np.array_equal(out,self.ctx['inputs'][256]))
        self.assertIsNot(out,self.ctx['inputs'][256])

    async def test_wrong_pixels_saved_then_fail_without_next_call(self):
        calls=[]
        def wrong(words,model,t):calls.append(1);return words.copy()
        self.ctx['cpu']=wrong
        with self.assertRaisesRegex(ValueError,'whole-word'):await board.measure(self.ctx,256)
        self.assertEqual(len(calls),1);self.assertEqual(self.ctx['state'],'FAULT')
        self.assertTrue((self.ctx['directory']/'raw/256_r1_CPU_000.npy').exists())
        self.assertEqual(len((self.ctx['directory']/'samples.jsonl').read_text().splitlines()),1)
        with self.assertRaises(ValueError):await board.measure(self.ctx,256)


class DownloadVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=Path('D:/PLD/retina_fpga/build/board_results/q4d_quality_2026-10-15/q4d_results_bundle.zip')
        with zipfile.ZipFile(source) as z:
            for n in z.namelist():
                if not n.endswith('/record.json'):continue
                r=json.loads(z.read(n))
                if r['request']['algorithm']=='C7':
                    h=r['evidence'];m=h['raw_timestamps_ns']
                    cls.row=dict(hardware=h,side=r['request']['side'],call_start_ns=m['config_start_ns']-1,call_end_ns=m['observer_end_ns']+1)
                    cls.sequence=h['frame_count'];break

    def test_prior_actual_register_fixture(self):
        verify_hardware(self.row,self.sequence)

    def test_reject_parameter_cycle_counter_corruption(self):
        paths=[('hardware','hardware_latched_parameter_readback','raw_pages','3'),
               ('hardware','hardware_latched_parameter_readback','raw_pages','5'),
               ('hardware','send_bytes'),('hardware','frame_status_after'),
               ('hardware','applied_parameters','threshold'),('hardware','timing_ns','inference_ns')]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                row=copy.deepcopy(self.row);target=row
                for key in path[:-1]:target=target[key]
                target[path[-1]]+=1;verify_hardware(row,self.sequence)

    def test_reject_fake_pure_dma(self):
        row=copy.deepcopy(self.row);row['hardware']['timing_ns']['pure_dma_transport_ns']=1
        with self.assertRaises(ValueError):verify_hardware(row,self.sequence)

    def test_reject_mixed_cpu_evidence(self):
        row=copy.deepcopy(self.row);row['hardware']['evidence_kind']='HOST_MOCK'
        with self.assertRaises(ValueError):verify_hardware(row,self.sequence)


if __name__=='__main__':unittest.main(verbosity=2)
