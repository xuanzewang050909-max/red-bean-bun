"""Affected lifecycle checks using the actual sealed HTTP/Manager/launch code.

Only hardware.prepare/open are substitutes. No frame/model/driver is executed.
All files are new host-only copies, retained for inspection.
"""
import argparse
import asyncio
import ast
import hashlib
import importlib
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
import uuid
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('--root',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
ROOT=args.root.resolve()
sys.path.insert(0,str(ROOT))
import c7_demo as demo_module
sys.path.insert(0,str(ROOT/'app'))
from pynq_showcase import launch
from tornado.httpclient import AsyncHTTPClient


class HostHardware:
    opens=0
    prepares=0
    fail_open=False
    evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
    def __init__(self,root):
        self.state='NOT_LOADED';self.retained=[];self.downloads=0;self.last_status=0
        self.environment=dict(evidence_kind=self.evidence_kind)
    def prepare(self):
        HostHardware.prepares+=1;self.state='PRECHECK_FPGA_UNCHANGED'
    def open(self):
        HostHardware.opens+=1
        if HostHardware.fail_open:raise RuntimeError('CONSTRUCTED_START_FAILURE')
        self.downloads+=1;self.state='IDLE'
    def run(self,*a,**kw):raise AssertionError('NO_FRAME_EXECUTION_AUTHORIZED_IN_TEST')
    def refine(self,*a,**kw):raise AssertionError('NO_FRAME_EXECUTION_AUTHORIZED_IN_TEST')


class Owner:
    def __init__(self):self.closed=False
    def close(self):self.closed=True


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.boot=str(uuid.uuid4());self.port=unused_port();self.instances=[]
        HostHardware.opens=0;HostHardware.prepares=0;HostHardware.fail_open=False
        self.patches=[patch.object(demo_module,'_boot_id',lambda:self.boot),
            patch.object(demo_module,'_acquire_owner',lambda p:Owner()),
            patch.object(launch,'IntegratedHardware',HostHardware),
            patch.object(launch.platform,'python_version_tuple',lambda:('3','10','0')),
            patch.object(launch.subprocess,'check_output',lambda *a,**kw:'127.0.0.1')]
        for p in self.patches:p.start()
    def tearDown(self):
        # Host-only sockets/executors are test resources, no device exists.
        for d in self.instances:
            if d.context:
                if d.context.get('server'):d.context['server'].stop()
                for s in d.context.get('sockets',[]):s.close()
                d.context['executor'].shutdown(wait=True)
            if d.owner:d.owner.close()
        for p in reversed(self.patches):p.stop()
        self.assertNotIn('pynq',sys.modules)
    def instance(self):
        d=demo_module.Demo(ROOT);self.instances.append(d);return d
    async def start(self,d):return await d.start(demo_module.CONFIRMATION,port=self.port)

    async def test_normal_repeat_actual_server_export_and_unique_records(self):
        d=self.instance();first=await self.start(d)
        response=await AsyncHTTPClient().fetch(first['urls'][0]+'api/status')
        self.assertEqual(json.loads(response.body)['session_id'],first['session_id'])
        again=await self.start(d)
        self.assertTrue(again['reused_running_service']);self.assertEqual(HostHardware.opens,1)
        exported=Path(await d.finish())
        with zipfile.ZipFile(exported) as z:self.assertIsNone(z.testzip())
        old={p:demo_module.info(p) for base in (d.attempt,d.context['manager'].directory)
             for p in base.rglob('*') if p.is_file()}
        self.assertEqual(await d.finish(),str(exported))
        second=await self.start(d)
        self.assertNotEqual(first['session_id'],second['session_id'])
        self.assertEqual(HostHardware.opens,2)
        await d.finish()
        self.assertTrue(all(demo_module.info(p)==v for p,v in old.items()))

    async def test_busy_start_idempotent_and_stop_refused(self):
        d=self.instance();await self.start(d);d.context['manager'].active='HOST_BUSY'
        self.assertTrue((await self.start(d))['reused_running_service'])
        with self.assertRaisesRegex(RuntimeError,'NOT_IDLE'):await d.finish()
        self.assertEqual(HostHardware.opens,1)
        self.assertFalse((d.attempt/'closed.json').exists())
        d.context['manager'].active=None;await d.finish()

    async def test_fault_preserved_export_allowed_no_reload(self):
        d=self.instance();await self.start(d)
        d.context['manager'].error={'type':'HOST_CONSTRUCTED_FAULT'}
        d.context['hardware'].state='FAULT';d.context['hardware'].retained=[object()]
        with self.assertRaisesRegex(RuntimeError,'FAULT'):await self.start(d)
        with self.assertRaisesRegex(RuntimeError,'NOT_IDLE'):await d.finish()
        self.assertTrue(Path(await d.export()).exists())
        self.assertEqual(HostHardware.opens,1)
        self.assertEqual(len(d.context['hardware'].retained),1)

    async def test_same_boot_lost_python_context_blocks_before_prepare(self):
        d=self.instance();await self.start(d)
        other=self.instance()
        with self.assertRaisesRegex(RuntimeError,'UNFINISHED_SAME_BOOT'):await self.start(other)
        self.assertEqual(HostHardware.prepares,1);await d.finish()

    async def test_new_boot_keeps_prior_unfinished_records(self):
        d=self.instance();await self.start(d)
        old_path=d.attempt/'start_intent.json';identity=demo_module.info(old_path)
        # Simulated OS lifecycle only. Close substitute server, never a real board.
        d.context['server'].stop();await d.context['server'].close_all_connections()
        d.context['executor'].shutdown(wait=True)
        self.boot=str(uuid.uuid4());other=self.instance();await self.start(other)
        self.assertEqual(demo_module.info(old_path),identity)
        self.assertFalse((d.attempt/'closed.json').exists())
        await other.finish()

    async def test_start_failure_preservation_and_no_retry(self):
        d=self.instance();HostHardware.fail_open=True
        with self.assertRaisesRegex(RuntimeError,'CONSTRUCTED_START_FAILURE'):await self.start(d)
        self.assertTrue((d.attempt/'failure.json').exists())
        saved=demo_module.info(ROOT/'app/browser_startup_failure.json')
        with self.assertRaisesRegex(RuntimeError,'FAULT_PRESERVED'):await self.start(d)
        self.assertEqual(HostHardware.opens,1)
        for s in d.context['sockets']:s.close()
        d.context['executor'].shutdown(wait=True)
        self.boot=str(uuid.uuid4());HostHardware.fail_open=False
        other=self.instance();await self.start(other)
        self.assertEqual(demo_module.info(other.attempt/'prior_browser_startup_failure.json'),saved)
        await other.finish()

    async def test_port_busy_never_calls_hardware_prepare_or_open(self):
        d=self.instance()
        with socket.socket() as sock:
            sock.bind(('0.0.0.0',self.port));sock.listen(1)
            with self.assertRaises(OSError):await self.start(d)
        self.assertEqual(HostHardware.prepares,0);self.assertEqual(HostHardware.opens,0)

    async def test_manual_confirmation_required(self):
        d=self.instance()
        with self.assertRaisesRegex(RuntimeError,'CONFIRMATION'):await d.start('not authorized')
        self.assertIsNone(d.attempt);self.assertEqual(HostHardware.prepares,0)

    async def test_concurrent_start_one_real_lifecycle(self):
        d=self.instance()
        a,b=await asyncio.gather(self.start(d),self.start(d))
        self.assertEqual(a['session_id'],b['session_id'])
        self.assertEqual(HostHardware.opens,1);await d.finish()

    async def test_open_demo_keeps_live_object_and_immutable_file_guard(self):
        d=demo_module.open_demo(ROOT);self.instances.append(d)
        self.assertIs(d,demo_module.open_demo(ROOT))
        with patch.object(demo_module,'info',lambda p:dict(bytes=0,sha256='0'*64)):
            with self.assertRaisesRegex(RuntimeError,'IDENTITY_MISMATCH'):await self.start(d)
        self.assertEqual(HostHardware.prepares,0)

    async def test_export_snapshots_do_not_overwrite(self):
        d=self.instance();await self.start(d)
        first=Path(await d.export());identity=demo_module.info(first)
        second=Path(await d.export());self.assertNotEqual(first,second)
        self.assertEqual(demo_module.info(first),identity);await d.finish()

    async def test_owner_conflict_blocks_before_prepare(self):
        d=self.instance()
        with patch.object(demo_module,'_acquire_owner',side_effect=RuntimeError('OWNER_BUSY')):
            with self.assertRaisesRegex(RuntimeError,'OWNER_BUSY'):await self.start(d)
        self.assertEqual(HostHardware.prepares,0)


class OfflineNotebookTests(unittest.TestCase):
    def test_delivered_notebook_syntax_and_package_identity(self):
        notebook=json.loads((ROOT.parent/'C7_Demo_r1.ipynb').read_bytes())
        cells=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code']
        self.assertEqual(len(cells),4)
        for c in cells:compile(c,'delivered_notebook','exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        # Payload folder is already available at ROOT; first-cell installation is
        # separately exercised below with its untouched actual ZIP and no modules.
        self.assertNotIn('pynq',sys.modules)
        with zipfile.ZipFile(ROOT.parent/'C7_Demo_r1.zip') as z:
            for name in z.namelist():self.assertEqual(z.read(name),(ROOT/name).read_bytes())


if __name__=='__main__':
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                 status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL',
                 actual_board_operations=0,model_forwards=0,image_frames=0,
                 scope='Actual original launch/HTTP/Manager/export with hardware and Linux lock/boot test doubles')
    args.output.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary));sys.exit(0 if result.wasSuccessful() else 1)
