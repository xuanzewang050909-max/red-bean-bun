"""Affected host-only integration tests. Cached captures are test doubles, NOT PL runs."""
import asyncio
import contextlib
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[1]
PACKAGE = Path(os.environ.get('C7_WEB_PACKAGE', REPO/'build/deploy/c7_three_image_web_dev1')).resolve()
sys.path.insert(0,str(PACKAGE))
from pynq_showcase import single_image as si, service
from pynq_showcase.protocol import validate_package, file_info

import io
CFG = json.loads((PACKAGE/'integration.json').read_bytes())
FRAMES={}
FROZEN_SOURCE=Path('D:/PLD/retina_c7_three_image_completion')
for key in ('im0004','im0291','im0319','im0324'):
    if key=='im0324':
        source=Path('D:/PLD/retina_c7_single_image_repair/results/single_repair_r1/input/input.npz')
        with zipfile.ZipFile(CFG['preserved_im0324_capture']['path']) as z:
            actual=np.load(io.BytesIO(z.read('native_actual.npy')),allow_pickle=False)
    else:
        source=FROZEN_SOURCE/'results/three_repair_r1/input'/(key+'.npz')
        actual=np.load(FROZEN_SOURCE/'results/three_web_r1/board_capture'/(key+'_actual.npy'),allow_pickle=False)
    with np.load(source,allow_pickle=False) as a:
        words=a['input_words'];c7=a['output_words']
    target=CFG['targets'][key]
    assert si.sha(words.tobytes())==target['input_word_sha256'] and si.sha(c7.tobytes())==target['c7_output_word_sha256']
    assert si.sha(actual[:6*words.size].tobytes())==target['expected_workspace_raw_sha256']
    FRAMES[key]=dict(words=words,c7=c7,actual=actual,target=target)
WORDS=FRAMES['im0004']['words'];C7=FRAMES['im0004']['c7'];ACTUAL=FRAMES['im0004']['actual'];TARGET=FRAMES['im0004']['target']
SOURCE=dict(old=((C7>>16)&255)!=0)
REQUEST=dict(image_id='im0004',algorithm='C7',side=512,mode='final',mode_code=3,threshold=112,
             client_nonce='host_fixture_001',png_profile='fast')
def find_frame(words):
    key=next(k for k,v in FRAMES.items() if si.sha(v['words'].tobytes())==si.sha(words.tobytes()))
    return FRAMES[key]


class FakeBase:
    """No hardware imports; supplies a known cached C7 frame for software wiring."""
    opens = 0
    runs = 0  # Cumulative across overlay-restoration objects in this host test.
    def __init__(self,root):
        self.root=Path(root);self.state='NOT_LOADED';self.retained=[];self.last_attempt=None
        self.last_status=0;self.downloads=0;self.environment={'evidence_kind':'HOST_TEST_DOUBLE_NOT_BOARD'}
    def prepare(self): self.state='PRECHECK_FPGA_UNCHANGED'
    def open(self):
        self.owner=threading.get_ident();self.state='IDLE';self.downloads+=1;FakeBase.opens+=1
    def run(self,words,request):
        assert self.owner==threading.get_ident() and self.state=='IDLE'
        self.last_attempt=dict(request=request,phase='HOST_BASE_DONE',raw_timestamps_ns={})
        start=time.perf_counter_ns()
        output=words.copy() if request['mode_code']==0 else find_frame(words)['c7'].copy()
        assert output.shape==words.shape
        end=time.perf_counter_ns();self.last_status+=1;FakeBase.runs+=1
        observed=dict(pl_core_cycles=1,pl_drain_cycles=1,latched_control=0,sequence=self.last_status)
        evidence=dict(evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD',output_sha256=si.sha(output.tobytes()),
          applied_parameters=dict(algorithm=request['algorithm'],threshold=request['threshold'],side=request['side'],mode_code=request['mode_code'],task_tag=self.last_status),
          hardware_latched_parameter_readback=observed,frame_count=self.last_status,
          send_bytes=words.nbytes,recv_bytes=words.nbytes,
          raw_timestamps_ns=dict(config_start_ns=start,config_end_ns=start,dma_start_ns=start,dma_end_ns=end,snapshot_start_ns=end,snapshot_end_ns=end,observer_end_ns=end),
          timing_ns=dict(config_ns=0,dma_transaction_ns=end-start,cpu_snapshot_ns=0,inference_ns=end-start,pl_core_frame_ns=10,pl_core_cycles=1,observer_readback_ns=0,pure_dma_transport_ns=None))
        return output,evidence


class FakeBuffer(np.ndarray):
    def __new__(cls,shape,dtype):
        obj=np.empty(shape,dtype).view(cls);obj.physical_address=0x1000000;obj.freed=False;obj.flushes=0;obj.invalidates=0
        return obj
    def flush(self): self.flushes+=1
    def invalidate(self): self.invalidates+=1
    def freebuffer(self): self.freed=True


@contextlib.contextmanager
def host_runtime(fault=None):
    state=dict(ops=[],buffers=[],loads=0,clock=50.,failure=fault,profiles=[],payloads=[])
    class IP:
        def __init__(self): self.regs={}
        def write(self,reg,value):
            self.regs[reg]=value
            if reg==0:
                op=self.regs[0x20];state['ops'].append(op)
                if op==0:
                    b=state['buffers'][-1];n=WORDS.size
                    f=next(f for f in FRAMES.values() if si.sha(b[:n].tobytes())==f['target']['refinement_input_raw_sha256'])
                    self.frame=f
                    np.testing.assert_array_equal(b[:n],si.pack_live_input(f['words'],f['c7'],f['target']).ravel())
                    assert np.all(b[n:]==np.uint32(0xdeadbeef)), 'No answer mask in device input'
                    assert self.regs.get(0x40)==f['target']['profile'], 'Actual profile register wrong'
                    state['profiles'].append(self.regs.get(0x40))
                if op==4:
                    state['buffers'][-1][:]=self.frame['actual']
                    if fault=='numeric':state['buffers'][-1][100]^=np.uint32(1)
                    if fault=='guard':state['buffers'][-1][-1]=0
        def read(self,reg):
            if reg==0:return 2
            if reg==0x10:return 3 if fault=='op' else 0
            if reg==0x28 and fault=='control':return 0
            return self.regs.get(reg,0)
    class Overlay:
        def __init__(self,path,download):
            assert not download
            state['payloads'].append(str(path))
            self.ip_dict={'repair_0':dict(type='xilinx.com:hls:valley_repair:1.0',phys_addr=0x43c00000)}
            self.clock_dict={0:dict(enable=1,divisor0=5,divisor1=4)};self.repair_0=IP()
        def download(self):state['loads']+=1
        def is_loaded(self):return True
    def allocate(shape,dtype):
        b=FakeBuffer(shape,dtype);state['buffers'].append(b);return b
    module=types.SimpleNamespace(__version__='3.0.1',Overlay=Overlay,allocate=allocate,
                                 Clocks=types.SimpleNamespace(fclk0_mhz=100 if fault=='clock' else 50))
    contract=json.loads((PACKAGE/'refinement/runtime_contract.json').read_bytes())
    original_inspect=inspect.getfile;original_info=si.file_info
    def getfile(obj):
        if obj is Overlay:return contract['Overlay']['path']
        if obj is allocate:return contract['allocate']['path']
        return original_inspect(obj)
    def fileinfo(p):
        for ref in contract.values():
            if str(p)==ref['path']:
                return dict(bytes=ref['bytes'],sha256=('0'*64 if fault=='runtime' else ref['sha256']))
        return original_info(p)
    # Load frozen helpers before patching the test runtime provenance responses.
    board=si.helpers(PACKAGE)
    with patch.dict(sys.modules,{'pynq':module}), patch.object(si,'PynqHardware',FakeBase), \
         patch.object(si.inspect,'getfile',getfile), patch.object(si,'file_info',fileinfo), \
         patch.object(si.platform,'machine',lambda:'armv7l'), \
         patch.object(board.evidence_io,'boot_context',lambda:dict(boot_id='HOST_TEST',pid=os.getpid())):
        yield state


class WiringTests(unittest.TestCase):
    def test_all_four_targets_profile_and_overlay_switch(self):
        with host_runtime() as hw,tempfile.TemporaryDirectory() as td:
            h=si.IntegratedHardware(PACKAGE);h.prepare();h.open()
            for key in ('im0004','im0291','im0319','im0324','im0004'):
                f=FRAMES[key];req={**REQUEST,'image_id':key}
                dest=Path(td)/str(len(hw['profiles']));dest.mkdir()
                output,_=h.run(f['words'],req)
                result=h.refine(f['words'],output,req,dest)
                self.assertEqual(result['record']['target_image'],key)
                self.assertEqual(si.sha(result['mask'].tobytes()),f['target']['expected_final_mask_raw_sha256'])
                self.assertEqual(h.retained,[])
            self.assertEqual(hw['profiles'],[0,1,2,None,0])
            self.assertEqual(h.downloads,10)
            self.assertEqual(len(hw['ops']),100)
            self.assertIn('refinement_single',hw['payloads'][3])
            self.assertTrue(all('refinement_single' not in hw['payloads'][i] for i in (0,1,2,4)))

    def test_package_unchanged_hardware(self):
        m=validate_package(PACKAGE)
        base=Path(CFG['baseline_manifest']['path']).parent
        for name in ['pynq_showcase/hardware.py','q4d_detector.bit','q4d_detector.hwh','pynq_showcase/quality_observer.py']:
            self.assertEqual(file_info(PACKAGE/name),file_info(base/name))
        self.assertEqual(len(m['images']),21)

    def test_exact_dispatch_and_alias(self):
        self.assertTrue(si.eligible(WORDS,REQUEST,CFG))
        self.assertTrue(si.eligible(WORDS,{**REQUEST,'image_id':'renamed_input_alias'},CFG))
        for key,value in [('threshold',113),('side',256),('mode_code',0),('algorithm','A')]:
            self.assertFalse(si.eligible(WORDS,{**REQUEST,key:value},CFG))
        other=WORDS.copy();other[0,0]^=np.uint32(1)
        self.assertFalse(si.eligible(other,REQUEST,CFG))

    def test_live_packing_exact_and_parent_rejection(self):
        np.testing.assert_array_equal(si.pack_live_input(WORDS,C7,TARGET),np.load(PACKAGE/'refinement/im0004_input.npy'))
        altered=C7.copy();altered[128,128]^=np.uint32(1<<16)
        with self.assertRaisesRegex(ValueError,'PARENT_MISMATCH'):si.pack_live_input(WORDS,altered,TARGET)

    def test_capture_mask_exact(self):
        final,added,uncertain=si.decode_workspace(ACTUAL,WORDS,C7,TARGET)
        self.assertEqual((int(final.sum()),int(added.sum()),int(uncertain.sum())),(7820,3812,2288))
        self.assertFalse(np.any(SOURCE['old']&~final))

    def test_real_dispatch_code_twenty_operations_and_next_request(self):
        with host_runtime() as hw, tempfile.TemporaryDirectory() as td:
            h=si.IntegratedHardware(PACKAGE);h.prepare();h.open();h.run(WORDS,REQUEST)
            result=h.refine(WORDS,C7,REQUEST,td)
            self.assertEqual(hw['ops'],[0,1,2]+[3]*16+[4])
            self.assertEqual((hw['buffers'][0].flushes,hw['buffers'][0].invalidates),(1,1))
            self.assertTrue(hw['buffers'][0].freed);self.assertEqual(h.retained,[])
            self.assertEqual(h.downloads,2);self.assertEqual(result['record']['added_pixels'],3812)
            h.run(WORDS,{**REQUEST,'mode_code':0})
            self.assertEqual(h.downloads,3);self.assertEqual(h.overlay_mode,'C7')
            self.assertIsNone(h.refine(WORDS,WORDS,{**REQUEST,'mode_code':0},td))
            self.assertEqual(hw['loads'],1)
            lines=[json.loads(x) for x in (Path(td)/'events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(x['event']=='OP_DONE' for x in lines),20)

    def test_failure_stops_without_restore_free_or_retry(self):
        for fault in ['runtime','clock','control','op','numeric','guard']:
            with self.subTest(fault=fault),host_runtime(fault) as hw,tempfile.TemporaryDirectory() as td:
                h=si.IntegratedHardware(PACKAGE);h.prepare();h.open();h.run(WORDS,REQUEST)
                with self.assertRaises((ValueError,RuntimeError)):h.refine(WORDS,C7,REQUEST,td)
                self.assertEqual(h.state,'FAULT');before=h.downloads
                with self.assertRaises(ValueError):h.run(WORDS,REQUEST)
                self.assertEqual(h.downloads,before)
                self.assertTrue((Path(td)/'refinement_FAULT.json').exists())
                if hw['buffers']:self.assertFalse(hw['buffers'][0].freed)

    def test_mismatched_live_parent_before_overlay(self):
        with host_runtime() as hw,tempfile.TemporaryDirectory() as td:
            h=si.IntegratedHardware(PACKAGE);h.prepare();h.open();h.run(WORDS,REQUEST)
            c=C7.copy();c[10,10]^=np.uint32(1)
            with self.assertRaises(ValueError):h.refine(WORDS,c,REQUEST,td)
            self.assertEqual(hw['loads'],0);self.assertEqual(hw['buffers'],[])

    def test_no_production_answer_load_or_algorithm_rename(self):
        source=(PACKAGE/'pynq_showcase/single_image.py').read_text(encoding='utf8')
        self.assertNotIn('np.load(',source)
        self.assertIn("buffer[:n] = packed.ravel()",source)
        self.assertNotIn('evaluation_only',source)
        self.assertEqual(REQUEST['algorithm'],'C7')


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_cancels_pending_request(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'package';shutil.copytree(PACKAGE,root)
            with host_runtime('op') as hw,patch.object(si,'helpers',lambda ignored:sys.modules['board_run']):
                hardware=si.IntegratedHardware(root);hardware.prepare()
                hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
                manager=service.Manager(root,validate_package(root),hardware)
                await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
                body={k:v for k,v in REQUEST.items() if k!='mode_code'}
                baseline=manager.submit(body);await manager.pump
                self.assertEqual(manager.get(baseline['run_id'])['status'],'COMPLETED')
                self.assertEqual(hw['ops'],[])
                first=manager.submit_refinement(baseline['run_id'],{'client_nonce':'failure_refinement_001'})
                second=manager.submit({**body,'client_nonce':'queued_after_failure'})
                await manager.pump
                self.assertEqual(manager.get(first['run_id'])['status'],'FAILED')
                self.assertEqual(manager.get(second['run_id'])['status'],'CANCELLED')
                self.assertEqual(hw['ops'],[0])
                self.assertEqual(hw['loads'],1)
                self.assertEqual(hardware.downloads,2)
                self.assertFalse(hw['buffers'][0].freed)
                with self.assertRaises(service.BusyError):manager.submit({**body,'client_nonce':'retry_not_allowed'})
                archive=await manager.export()
                with zipfile.ZipFile(archive) as z:
                    self.assertIn(first['run_id']+'/refinement_FAULT.json',z.namelist())
                    self.assertIn(first['run_id']+'/output_packed.npy',z.namelist())
                manager.executor.shutdown(wait=True)

    async def test_process_export_nonce_and_no_gt_read(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'package';shutil.copytree(PACKAGE,root)
            # Frozen helper modules intentionally keep their original source path in
            # this host fixture; production launch requires its exact package path.
            with host_runtime() as hw,patch.object(si,'helpers',lambda ignored:sys.modules['board_run']):
                hardware=si.IntegratedHardware(root);hardware.prepare()
                hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
                manager=service.Manager(root,validate_package(root),hardware)
                await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
                body={k:v for k,v in REQUEST.items() if k!='mode_code'}
                with patch.object(service,'score_completed',side_effect=AssertionError('Target must not open AH/VK')):
                    job=manager.submit(body);same=manager.submit(body)
                    self.assertEqual(job['run_id'],same['run_id'])
                    await manager.pump
                    original=manager.get(job['run_id']);self.assertEqual(original['status'],'COMPLETED',original)
                    self.assertEqual(original['presentation_stage'],'C7_ORIGINAL');self.assertFalse(original['refinement']['applied'])
                    self.assertEqual(original['output']['sha256'],TARGET['c7_output_word_sha256'])
                    self.assertEqual(hw['ops'],[]);self.assertEqual(hardware.base.last_status,1)
                    child=manager.submit_refinement(job['run_id'],{'client_nonce':'host_refine_001'})
                    duplicate=manager.submit_refinement(job['run_id'],{'client_nonce':'host_refine_001'})
                    self.assertEqual(child['run_id'],duplicate['run_id'])
                    await manager.pump
                complete=manager.get(child['run_id']);self.assertEqual(complete['status'],'COMPLETED',complete)
                self.assertEqual(complete['c7_parent']['run_id'],original['run_id']);self.assertEqual(hardware.base.last_status,1)
                self.assertEqual(complete['timing_ns']['c7_inference_ns'],0);self.assertEqual(complete['timing_ns']['dma_transaction_ns'],0)
                with self.assertRaises(service.BusyError):manager.submit_refinement(job['run_id'],{'client_nonce':'second_refine_not_allowed'})
                self.assertEqual(complete['output']['sha256'],TARGET['expected_final_mask_raw_sha256'])
                self.assertEqual(complete['c7_output']['sha256'],TARGET['c7_output_word_sha256'])
                self.assertEqual(complete['quality']['annotations'],{})
                self.assertEqual(complete['refinement']['added_pixels'],3812)
                self.assertEqual(complete['request']['algorithm'],'C7')
                dest=manager.directory/child['run_id']
                np.testing.assert_array_equal(np.load(dest/'output_packed.npy'),C7)
                from PIL import Image
                png=np.array(Image.open(dest/'mask.png'))
                self.assertEqual(si.sha((png!=0).tobytes()),TARGET['expected_final_mask_raw_sha256'])
                self.assertEqual(set(['before','added'])-set(complete['images']),set())
                archive=await manager.export(child['run_id'])
                with zipfile.ZipFile(archive) as z:
                    self.assertIn(child['run_id']+'/refinement_actual.npy',z.namelist())
                    self.assertIn(child['run_id']+'/events.jsonl',z.namelist())
                    self.assertIn(child['run_id']+'/c7_parent_record.json',z.namelist())
                manager.finish();manager.executor.shutdown(wait=True)

    async def test_parent_tamper_rejected_without_refinement(self):
        for tamper in ('record','array'):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)/'package';shutil.copytree(PACKAGE,root)
                with host_runtime() as hw,patch.object(si,'helpers',lambda ignored:sys.modules['board_run']):
                    hardware=si.IntegratedHardware(root);hardware.prepare();hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
                    manager=service.Manager(root,validate_package(root),hardware)
                    await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
                    parent=manager.submit({k:v for k,v in REQUEST.items() if k!='mode_code'});await manager.pump
                    if tamper=='record':
                        with (manager.directory/parent['run_id']/'record.json').open('ab') as f:f.write(b' ')
                        with self.assertRaises(service.BusyError):manager.submit_refinement(parent['run_id'],{'client_nonce':'tampered_parent_test'})
                    else:
                        array=manager.directory/parent['run_id']/'output_packed.npy'
                        data=np.load(array);data[0,0]^=np.uint32(1);np.save(array,data)
                        child=manager.submit_refinement(parent['run_id'],{'client_nonce':'tampered_parent_test'});await manager.pump
                        self.assertEqual(manager.get(child['run_id'])['status'],'FAILED')
                    self.assertEqual(hw['ops'],[]);self.assertEqual(hw['loads'],0);self.assertEqual(hardware.base.last_status,1)
                    manager.executor.shutdown(wait=True)

    async def test_all_four_original_then_refinement(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'package';shutil.copytree(PACKAGE,root)
            with host_runtime() as hw,patch.object(si,'helpers',lambda ignored:sys.modules['board_run']):
                hardware=si.IntegratedHardware(root);hardware.prepare();hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
                manager=service.Manager(root,validate_package(root),hardware)
                await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
                for name in ('im0004','im0291','im0319','im0324'):
                    ops_before=len(hw['ops']);base_before=FakeBase.runs
                    body={k:v for k,v in REQUEST.items() if k!='mode_code'};body.update(image_id=name,client_nonce='original_'+name)
                    parent=manager.submit(body)
                    with self.assertRaises(service.BusyError):manager.submit_refinement(parent['run_id'],{'client_nonce':'premature_'+name})
                    await manager.pump;parent=manager.get(parent['run_id']);self.assertEqual(parent['status'],'COMPLETED',parent)
                    self.assertFalse(parent['refinement']['applied']);self.assertTrue(parent['refinement_available'])
                    self.assertEqual(parent['presentation_stage'],'C7_ORIGINAL')
                    self.assertEqual(len(hw['ops']),ops_before);self.assertEqual(FakeBase.runs,base_before+1)
                    self.assertEqual(parent['output']['sha256'],FRAMES[name]['target']['c7_output_word_sha256'])
                    child=manager.submit_refinement(parent['run_id'],{'client_nonce':'refined_'+name});await manager.pump
                    child=manager.get(child['run_id']);self.assertEqual(child['status'],'COMPLETED',child)
                    self.assertEqual(child['presentation_stage'],'TARGETED_REFINEMENT')
                    self.assertEqual(child['output']['sha256'],FRAMES[name]['target']['expected_final_mask_raw_sha256'])
                    self.assertEqual(FakeBase.runs,base_before+1)
                    self.assertEqual(len(hw['ops']),ops_before+20)
                    self.assertEqual(child['timing_ns']['c7_inference_ns'],0)
                    if name=='im0324':
                        self.assertIsNone(child['refinement']['profile'])
                        self.assertEqual(child['refinement']['added_pixels'],3083)
                        self.assertEqual(child['refinement']['final_pixels'],9540)
                    with self.assertRaises(service.BusyError):manager.submit_refinement(parent['run_id'],{'client_nonce':'duplicate_'+name})
                self.assertEqual(hw['profiles'],[0,1,2,None]);self.assertEqual(len(manager.jobs),8)
                manager.finish();manager.executor.shutdown(wait=True)

    async def test_im0324_hidden_gt_alias_staged_without_gt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'package';shutil.copytree(PACKAGE,root)
            with host_runtime() as hw,patch.object(si,'helpers',lambda ignored:sys.modules['board_run']):
                hardware=si.IntegratedHardware(root);hardware.prepare();hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
                manager=service.Manager(root,validate_package(root),hardware)
                await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
                body={k:v for k,v in REQUEST.items() if k!='mode_code'};body.update(image_id='im0324_nogt',client_nonce='alias_original')
                with patch.object(service,'score_completed',side_effect=AssertionError('No GT read')):
                    parent=manager.submit(body);await manager.pump
                    parent=manager.get(parent['run_id']);self.assertEqual(parent['status'],'COMPLETED',parent)
                    self.assertTrue(parent['refinement_available']);self.assertEqual(hw['ops'],[])
                    child=manager.submit_refinement(parent['run_id'],{'client_nonce':'alias_refinement'});await manager.pump
                    child=manager.get(child['run_id']);self.assertEqual(child['status'],'COMPLETED',child)
                self.assertEqual(child['output']['sha256'],FRAMES['im0324']['target']['expected_final_mask_raw_sha256'])
                self.assertEqual(hw['profiles'],[None]);self.assertEqual(hardware.base.last_status,1)
                manager.finish();manager.executor.shutdown(wait=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
