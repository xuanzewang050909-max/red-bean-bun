"""HOST ONLY: storage, protocol, reference audit and native mock failures."""
import ast
import asyncio
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from pynq_w5a import service
from pynq_w5a.protocol import RequestError,file_info,validate_package
from w5a_board import validate_w5a
from verify_c7_w5a import CompactArchive,verify_schedule,verify
from verify_w5a_run import check_run
from restore_c7_w5a import restore
from browser_q4d_fixtures import HostHardware,expected_words
PACKAGE=Path(os.environ.get('W5A_PACKAGE',str(ROOT/'build/deploy/c7_w5a_dev02/package')))
BASE=Path('D:/PLD/retina_fpga/build/deploy/q4d_c7_experimental_r1')
SUITE='host_test_suite_0001'


def request(i=0):
    images=sorted(json.loads((PACKAGE/'browser_manifest.json').read_bytes())['images'])
    return dict(**service.w5a_config(i,images),client_nonce=f'w5a_{SUITE}_{i}')


def resource_mock(directory):
    return dict(server_ns=service.time.perf_counter_ns(),rss_bytes=60*1024**2,available_bytes=200*1024**2,
                cma_free_bytes=120*1024**2,disk_free_bytes=4*1024**3)


def observation(job,index=0):
    start=index*2000+1
    return dict(client_nonce=job['request']['client_nonce'],config_id=job['config_id'],
        input_sha256=job['input']['sha256'],output_sha256=job['output']['sha256'],
        request_start_ms=start,result_received_ms=start+100,images_decoded_ms=start+110,render_done_ms=start+120,
        visibility='visible',user_agent='HOST_TEST_ONLY',loop_id=None,loop_index=None,loop_start_ms=None)


def synthetic_schedule():
    images=sorted(json.loads((PACKAGE/'browser_manifest.json').read_bytes())['images'])
    records=[]
    for i in range(1000):
        req=request(i);req['mode_code']=3
        r=dict(run_id=str(i),session_id='HOST_ONLY',request=req,config_id='x',input={'sha256':'a'},output={'sha256':'b'},
            accepted_server_ns=i*2_000_000_000+1,storage_end_ns=i*2_000_000_000+100_000_000,
            storage_dedup_ns=10_000_000,raw_timestamps_ns={'worker_result_ready_ns':i*2_000_000_000+90_000_000},
            resources=dict(server_ns=i*2_000_000_000+110_000_000,rss_bytes=60*1024**2+i*1000,available_bytes=200*1024**2))
        o=observation(r,i);o.update(run_id=str(i),session_id='HOST_ONLY',input_sha256='a',output_sha256='b',
            evidence_kind='PYNQ_PL_DMA',request_to_render_ms=120,result_received_to_render_ms=20,browser_actual_fps=None)
        # Metadata-only adversarial fixture; no archive or board acceptance is produced.
        r['browser_timing']=o;records.append(r)
    return records,images


class Protocol(unittest.TestCase):
    def test_trusted_bytes_and_no_cpu_algorithm_deployment(self):
        m=validate_w5a(PACKAGE)
        for name in ('hardware.py','evaluation.py','quality_observer.py','__init__.py'):
            self.assertEqual((PACKAGE/'pynq_w5a'/name).read_bytes(),(BASE/'pynq_q4d'/name).read_bytes())
        for name in m['artifacts']:
            if name.startswith(('inputs/','labels/')) or name.endswith(('.bit','.hwh')) or name in ('q4d_hardware_manifest.json','a0_dma_board_test.py'):
                self.assertEqual((PACKAGE/name).read_bytes(),(BASE/name).read_bytes())
        for p in (PACKAGE/'pynq_w5a').glob('*.py'):
            for forbidden in ('software.reference','bench_reference','prepare_q4d_detector_vectors'):
                self.assertNotIn(forbidden,p.read_text())
            tree=ast.parse(p.read_bytes())
            self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='expected_words' for n in ast.walk(tree)))

    def test_native_processor_math_preserved_and_python310(self):
        def funcs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef)}
        a=funcs(BASE/'pynq_q4d/service.py');b=funcs(PACKAGE/'pynq_w5a/service.py')
        for name in ('process_run','encode_png'):self.assertEqual(a[name],b[name])
        for p in PACKAGE.rglob('*.py'):ast.parse(p.read_bytes(),feature_version=(3,10))
        nb=json.loads((PACKAGE.parent/'upload/c7_w5a_stability.ipynb').read_bytes())
        cells=[c for c in nb['cells'] if c['cell_type']=='code'];self.assertEqual(len(cells),7)
        for c in cells:ast.parse(''.join(c['source']),feature_version=(3,10))

    def test_extraction_bytes_inventory_and_no_overwrite(self):
        upload=PACKAGE.parent/'upload';nb=json.loads((upload/'c7_w5a_stability.ipynb').read_bytes())
        code=''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source']);cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            try:
                os.chdir(td);shutil.copy2(upload/'c7_w5a_stability_r1.zip',td)
                with contextlib.redirect_stdout(io.StringIO()):exec(code,{})
                validate_w5a(Path(td)/'c7_w5a_stability_r1')
                with self.assertRaises(FileExistsError):exec(code,{})
                p=Path('c7_w5a_stability_r1.zip');p.write_bytes(p.read_bytes()+b'changed')
                with self.assertRaises(ValueError):exec(code,{})
            finally:os.chdir(cwd)

    def test_schedule_1000_and_distinct_blocks(self):
        records,images=synthetic_schedule();s=verify_schedule(records,images)
        self.assertEqual(s['tasks'],1000);self.assertGreater(s['server_elapsed_seconds'],1800)
        self.assertEqual(len({r['request']['image_id'] for r in records}),20)
        for i in (0,9,10,199,200,999):
            self.assertEqual(records[i]['request']['side'],512 if ((i//10)//20)%2==0 else 256)
        for x in (-1,1000,True,1.5):
            with self.assertRaises(RequestError):service.w5a_config(x,images)

    def test_schedule_rejects_wrong_parameter_hidden_and_missing(self):
        records,images=synthetic_schedule()
        for field,value in [('threshold',28),('algorithm','C5'),('side',512),('image_id','unknown')]:
            bad=copy.deepcopy(records);bad[200]['request'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):verify_schedule(bad,images)
        bad=copy.deepcopy(records);bad[123]['browser_timing']['visibility']='hidden'
        with self.assertRaises(ValueError):verify_schedule(bad,images)
        with self.assertRaises(ValueError):verify_schedule(records[:-1],images)

    def test_schedule_rejects_short_duration_clock_gap_and_memory(self):
        records,images=synthetic_schedule()
        for kind in ('short','gap','memory'):
            bad=copy.deepcopy(records)
            if kind=='short':
                for r in bad:
                    for k in ('accepted_server_ns','storage_end_ns','storage_dedup_ns'):r[k]//=2
                    r['raw_timestamps_ns']['worker_result_ready_ns']//=2;r['resources']['server_ns']//=2
            elif kind=='gap':bad[600]['accepted_server_ns']+=65_000_000_000
            else:bad[-1]['resources']['rss_bytes']+=100*1024**2
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_schedule(bad,images)

    def test_storage_hardlinks_preserve_actual_data_and_reject_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'one';b=root/'two';a.mkdir();b.mkdir()
            for d in (a,b):(d/'output.npy').write_bytes(b'actual unique frame bytes')
            files={'output.npy':file_info(a/'output.npy')}
            first=service.deduplicate_files(a,files);second=service.deduplicate_files(b,files)
            self.assertEqual(first,second);self.assertEqual((a/'output.npy').stat().st_ino,(b/'output.npy').stat().st_ino)
            self.assertEqual((b/'output.npy').read_bytes(),b'actual unique frame bytes')
            (root/first['output.npy']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):service.deduplicate_files(b,files)

    def test_failed_link_keeps_original(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'run';d.mkdir();p=d/'output.npy';p.write_bytes(b'actual data')
            with patch('os.link',side_effect=OSError('HOST injected link failure')),self.assertRaises(OSError):
                service.deduplicate_files(d,{'output.npy':file_info(p)})
            self.assertEqual(p.read_bytes(),b'actual data')


class Native(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'package';shutil.copytree(PACKAGE,self.root)
        self.hw=HostHardware(self.root,delay=.004)
        self.m=service.Manager(self.root,validate_package(self.root),self.hw)
        await asyncio.get_running_loop().run_in_executor(self.m.executor,self.hw.open)
        self.resources=patch.object(service,'resource_sample',side_effect=resource_mock);self.resources.start()
        source,_=self.m.inputs.load(self.m.inputs.request(request()))
        self.golden=expected_words(source,3,'C7',96)
        self.cached=patch('browser_q4d_fixtures.expected_words',return_value=self.golden);self.cached.start()

    async def asyncTearDown(self):
        if self.m.pump:await self.m.pump
        self.resources.stop();self.cached.stop();self.m.executor.shutdown(wait=True);self.temp.cleanup()

    async def completed(self,i):
        job=self.m.submit(request(i));await self.m.pump;job=self.m.get(job['run_id'])
        self.assertEqual(job['status'],'COMPLETED',job.get('error'))
        return job

    async def test_two_frames_are_real_calls_and_storage_dedup_only(self):
        first=await self.completed(0);self.m.browser_timing(first['run_id'],observation(first,0))
        second=await self.completed(1)
        self.assertEqual(self.hw.sequence,2);self.assertEqual(len(self.hw.buffers),4)
        self.assertEqual(first['storage_refs'],second['storage_refs'])
        self.assertEqual(len(list((self.m.directory/'objects').iterdir())),7)
        class Files:
            def read(_,name):return (self.m.directory/name).read_bytes()
        checked=check_run(Files(),second,self.root,self.m.manifest)
        self.assertEqual(checked['matched_words'],512*512)
        self.assertEqual(checked['matched_png_images'],5)

    async def test_wrong_order_parameter_and_no_prior_render(self):
        for req in [request(1),dict(request(),threshold=112)]:
            with self.assertRaises(RequestError):self.m.submit(req)
        job=await self.completed(0)
        with self.assertRaises(RequestError):self.m.submit(request(1))
        self.assertEqual(self.m.submit(request())['run_id'],job['run_id'])
        self.assertEqual(self.hw.sequence,1)
        with self.assertRaises(RequestError):self.m.browser_timing(job['run_id'],dict(observation(job),visibility='hidden'))

    async def test_dma_timeout_preserves_fault_and_buffers(self):
        self.hw.fault='timeout';job=self.m.submit(request());await self.m.pump
        self.assertIsNotNone(self.m.error);self.assertTrue(self.hw.retained)
        with self.assertRaises((service.BusyError,RequestError)):self.m.submit(request(1))
        with self.assertRaises(service.BusyError):self.m.finish()
        self.assertTrue((self.m.directory/job['run_id']/'failure.json').exists())
        self.assertEqual(self.hw.downloads,1)

    async def test_storage_failure_stops_without_rerunning_hardware(self):
        with patch.object(service,'deduplicate_files',side_effect=OSError('HOST disk failure')):
            job=self.m.submit(request());await self.m.pump
        self.assertIsNotNone(self.m.error);self.assertEqual(self.hw.sequence,1)
        self.assertTrue((self.m.directory/job['run_id']/'output_packed.npy').exists())
        with self.assertRaises((service.BusyError,RequestError)):self.m.submit(request(1))

    async def test_low_disk_stops_before_dma(self):
        with patch.object(service.shutil,'disk_usage',return_value=types.SimpleNamespace(free=511*1024**2)):
            self.m.submit(request());await self.m.pump
        self.assertIsNotNone(self.m.error)
        self.assertEqual(self.hw.sequence,0);self.assertEqual(self.hw.buffers,[])
        with self.assertRaises(service.BusyError):self.m.finish()

    async def test_summary_refuses_partial_and_export_requires_closed(self):
        await self.completed(0)
        with self.assertRaises(ValueError):self.m.endurance_summary()
        with self.assertRaises(ValueError):await self.m.export()

    async def test_repeated_config_changed_output_stops_and_preserves_raw(self):
        job=await self.completed(0);self.m.browser_timing(job['run_id'],observation(job))
        altered=self.golden.copy()
        index=np.argwhere(((altered>>16)&255)!=0)[0]
        altered[tuple(index)] ^= np.uint32(255<<16)
        self.cached.stop();self.cached=patch('browser_q4d_fixtures.expected_words',return_value=altered);self.cached.start()
        second=self.m.submit(request(1));await self.m.pump
        self.assertIsNotNone(self.m.error);self.assertEqual(self.hw.sequence,2)
        self.assertIn('Same configuration',self.m.error['message'])
        raw=np.load(self.m.directory/second['run_id']/'output_packed.npy')
        self.assertTrue(np.array_equal(raw,altered))

    async def test_compact_export_roundtrip_and_host_label(self):
        job=await self.completed(0);self.m.browser_timing(job['run_id'],observation(job))
        self.m.finish()
        with patch.object(self.m,'endurance_summary',return_value={'HOST_TEST_ONLY':True}):
            (self.m.directory/'w5a_summary.json').write_text('{"HOST_TEST_ONLY":true}')
            archive=await self.m.export()
        with zipfile.ZipFile(archive) as z:
            session=json.loads(z.read('session.json'))
            self.assertEqual(session['status']['evidence_kind'],'HOST_TEST_DOUBLE_NOT_BOARD')
            record=json.loads(z.read(job['run_id']+'/record.json'))
            adapter=CompactArchive(z,[record])
            for name in record['files']:
                self.assertEqual(adapter.read(job['run_id']+'/'+name),(self.m.directory/job['run_id']/name).read_bytes())
            self.assertFalse(any(n.endswith('.npy') for n in z.namelist()))
            self.assertIsNone(z.testzip())
        restored=Path(self.temp.name)/'restored'
        self.assertEqual(restore(archive,restored),1)
        for name in job['files']:
            self.assertEqual((restored/job['run_id']/name).read_bytes(),(self.m.directory/job['run_id']/name).read_bytes())
        with self.assertRaises(ValueError):restore(archive,restored)
        nb=json.loads((PACKAGE.parent/'upload/c7_w5a_stability.ipynb').read_bytes())
        markers=['W5A_PACKAGE_PASS','W5A_PRECHECK_PASS','BROWSER_SERVICE_READY','W5A_BROWSER_READY',
                 'W5A_COLLECTION_COMPLETE','W5A_CLOSED_IDLE','W5A_RESULTS_READY']
        for i,c in enumerate(c for c in nb['cells'] if c['cell_type']=='code'):
            c.update(execution_count=i+1,outputs=[dict(output_type='stream',name='stdout',text=[markers[i]])])
        executed=Path(self.temp.name)/'HOST_ONLY.ipynb';executed.write_text(json.dumps(nb))
        with self.assertRaisesRegex(ValueError,'HOST evidence'):
            verify(archive,executed,PACKAGE.parent)


if __name__=='__main__':unittest.main()
