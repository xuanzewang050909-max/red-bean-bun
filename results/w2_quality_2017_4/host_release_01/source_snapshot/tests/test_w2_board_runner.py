"""Host-only W2 fault injection. Simulated transfers are NEVER board evidence."""
import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'pynq_app'))
import w2_quality_board_test as runner
from test_a0_board_runner import Buffer
from test_a1_board_runner import FakeDMA, FakeGPIO


class ObserverGPIO:
    def __init__(self):
        self.page=0;self.pages={0:0x52513231,1:0,4:0,11:0,12:32}
        self.channel1=types.SimpleNamespace(setdirection=lambda v:None,write=self.select)
        self.channel2=types.SimpleNamespace(setdirection=lambda v:None,read=lambda:self.pages.get(self.page,0))
    def select(self,value,mask): self.page=value


class VectorDMA(FakeDMA):
    def send(self,buffer):
        index=self.gpio.control>>16; case=self.cases[index-1]
        with np.load(self.path,allow_pickle=False) as vectors:
            np.testing.assert_array_equal(buffer,vectors[case['input_key']].reshape(-1))
            self.rx[:]=vectors[case['expected_key']].reshape(-1)
        if self.corrupt:self.rx[8]^=np.uint32(1)
        self.sendchannel.transferred=buffer.nbytes
        self.recvchannel.transferred=buffer.nbytes-(4 if self.bad_length else 0)
        self.gpio.status=index|(index<<14)|(1<<28 if self.counter_error else 0)
        n=buffer.size
        self.observe.pages.update({1:2,3:self.gpio.control,4:index,5:n+100,6:n+130,7:10,8:40,9:n,10:n,11:index})
        if self.observer_error:self.observe.pages[3]^=256


class W2RunnerTests(unittest.TestCase):
    def context(self,**faults):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);directory=Path(temp.name)
        src=ROOT/'build/w2_board_vectors_01'
        shutil.copy2(src/'w2_vectors.npz',directory)
        vectors=json.loads((src/'w2_vectors.json').read_text())
        gpio=FakeGPIO();observe=ObserverGPIO();buffers=[]
        dma=VectorDMA(gpio,**{k:v for k,v in faults.items() if k!='observer_error'})
        dma.path=directory/'w2_vectors.npz';dma.cases=vectors['cases'];dma.observe=observe;dma.observer_error=faults.get('observer_error',False)
        def allocate(shape,dtype):
            buf=Buffer(shape,dtype);buf.physical_address=0x10000000+(len(buffers)%2)*0x200000
            buffers.append(buf);return buf
        context=dict(directory=directory,gpio=gpio,dma=dma,allocate=allocate,retained=[],vectors=vectors,
                     observer=runner.QualityObserver(observe,verified_clock_hz=100_000_000),
                     report=dict(status='W2_LOADED_NO_TRANSFER',transfers=[]))
        context['save']=lambda:(directory/'w2_result.json').write_text(json.dumps(context['report']))
        return context,buffers

    def test_all_80_host_transfers_control_observer_timing_and_release(self):
        context,buffers=self.context()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_w2(context);runner.baseline_w2(context);runner.candidate_w2(context)
        records=context['report']['transfers']
        self.assertEqual(len(records),80);self.assertEqual(sum(r['words'] for r in records),13303808)
        self.assertEqual(context['retained'],[]);self.assertTrue(all(b.freed for b in buffers))
        for index,record in enumerate(records):
            self.assertEqual(record['hardware']['task_tag'],index+1)
            self.assertEqual(record['output_sha256'],record['expected_sha256'])
            t=record['timing_ns'];self.assertEqual(t['full_inference'],t['snapshot_end']-t['config_start'])
            self.assertLessEqual(t['dma_transaction'],t['full_inference'])
        for action in (runner.smoke_w2,runner.baseline_w2,runner.candidate_w2):
            with self.assertRaises(RuntimeError):action(context)

    def test_output_byte_count_native_and_observer_failures_retain(self):
        for fault in ('corrupt','bad_length','counter_error','observer_error'):
            with self.subTest(fault=fault):
                context,buffers=self.context(**{fault:True})
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):runner.smoke_w2(context)
                self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')
                self.assertEqual(len(context['retained']),2);self.assertFalse(any(b.freed for b in buffers))
                self.assertEqual(context['report']['transfers'],[])
                with self.assertRaises(RuntimeError):runner.smoke_w2(context)

    def test_dma_timeout_keeps_both_inflight_buffers(self):
        context,buffers=self.context()
        with patch.object(runner,'wait_both_idle',side_effect=TimeoutError('injected host timeout')):
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TimeoutError):runner.smoke_w2(context)
        self.assertEqual(len(context['retained']),2);self.assertFalse(any(b.freed for b in buffers))
        self.assertEqual(context['report']['failed_stage'],'W2_SMOKE_RUNNING')

    def test_partial_allocation_failure_keeps_first_buffer(self):
        context,buffers=self.context();allocate=context['allocate']
        def fail_second(*args,**kwargs):
            if buffers:raise MemoryError('injected')
            return allocate(*args,**kwargs)
        context['allocate']=fail_second
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(MemoryError):runner.smoke_w2(context)
        self.assertEqual(len(context['retained']),1);self.assertFalse(buffers[0].freed)

    def test_vector_digest_control_and_sequence_fail_before_allocation(self):
        for key,value in [('input_sha256','bad'),('expected_sha256','bad'),('control',0),('index',2)]:
            with self.subTest(key=key):
                context,buffers=self.context();context['vectors']['cases'][0][key]=value
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):runner.smoke_w2(context)
                self.assertEqual(buffers,[]);self.assertEqual(context['gpio'].control,0)

    def test_preview_reads_dma_files_and_rejects_corruption_and_reexecution(self):
        context,_=self.context()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_w2(context);runner.baseline_w2(context);runner.candidate_w2(context)
        previews=[];display=types.ModuleType('IPython.display');display.display=previews.append
        with patch.dict(sys.modules,{'IPython.display':display}),contextlib.redirect_stdout(io.StringIO()):runner.finish_w2(context)
        pixels=np.asarray(previews[0]);self.assertEqual(pixels.shape,(560,1024,3))
        for row,index in enumerate(context['report']['preview_frames']):
            path=context['directory']/context['report']['transfers'][index]['saved_output']['name']
            actual=np.load(path);mask=((actual>>16)&255).astype(np.uint8)[1::2,1::2]
            np.testing.assert_array_equal(pixels[row*280+24:row*280+280,512:768,0],mask)
        from zipfile import ZipFile
        with ZipFile(context['directory']/'w2_results_bundle.zip') as archive:
            self.assertEqual(len(archive.namelist()),82)
            self.assertTrue(all('expected' not in n for n in archive.namelist()))
        before=(context['directory']/'w2_results_bundle.zip').read_bytes()
        with self.assertRaises(RuntimeError):runner.finish_w2(context)
        self.assertEqual((context['directory']/'w2_results_bundle.zip').read_bytes(),before)
        context['report']['status']='W2_CANDIDATE_PASSED'
        (context['directory']/'w2_results_bundle.zip').unlink()
        (context['directory']/context['report']['transfers'][context['report']['preview_frames'][1]]['saved_output']['name']).write_bytes(b'corrupted')
        with patch.dict(sys.modules,{'IPython.display':display}),self.assertRaises(RuntimeError):runner.finish_w2(context)

    def test_phase_order_rejects_before_access(self):
        context,buffers=self.context()
        for action in (runner.baseline_w2,runner.candidate_w2,runner.finish_w2):
            with self.assertRaises(RuntimeError):action(context)
        self.assertEqual(buffers,[])


if __name__=='__main__':unittest.main()
