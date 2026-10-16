"""HOST ONLY regression. Native driver mock/HTTP are not physical board tests."""
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
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import tornado.httpserver
import tornado.netutil
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from pynq_w5b import service
from pynq_w5b.protocol import Inputs,RequestError,file_info,validate_package
from w5b_board import planned_cases,manual_cases,validate_w5b,automatic_w5b,summary_w5b,close_w5b,export_w5b,http
from verify_w5b_run import check_run
from verify_c7_w5b import verify
from browser_q4d_fixtures import HostHardware
PACKAGE=Path(os.environ.get('W5B_PACKAGE',str(ROOT/'build/deploy/c7_w5b_dev01/package')))
BASE=Path('D:/PLD/retina_fpga/build/deploy/q4d_c7_experimental_r1')


def observation(job,page='a'*32,start=1):
    return dict(client_nonce=job['request']['client_nonce'],config_id=job['config_id'],input_sha256=job['input']['sha256'],
        output_sha256=job['output']['sha256'],request_start_ms=start,result_received_ms=start+10,images_decoded_ms=start+20,
        render_done_ms=start+30,visibility='visible',user_agent='HOST_TEST_ONLY',loop_id=None,loop_index=None,loop_start_ms=None,page_id=page)


class PackageTests(unittest.TestCase):
    def test_baseline_and_processing_math_unchanged(self):
        validate_w5b(PACKAGE)
        for name in ('hardware.py','evaluation.py','quality_observer.py','__init__.py'):
            self.assertEqual((PACKAGE/'pynq_w5b'/name).read_bytes(),(BASE/'pynq_q4d'/name).read_bytes())
        old=json.loads((BASE/'q4d_manifest.json').read_bytes())
        self.assertTrue(all(file_info(BASE/k)==v for k,v in old['artifacts'].items()))
        def funcs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef)}
        for name in ('process_run','encode_png'):
            self.assertEqual(funcs(PACKAGE/'pynq_w5b/service.py')[name],funcs(BASE/'pynq_q4d/service.py')[name])
        for p in (PACKAGE/'pynq_w5b').glob('*.py'):
            for forbidden in ('software.reference','prepare_q4d_detector_vectors','expected_words('):
                self.assertNotIn(forbidden,p.read_text())

    def test_scope_schedule_no_gt_alias(self):
        m=validate_package(PACKAGE);self.assertEqual(len(planned_cases()),35);self.assertEqual(len(manual_cases()),7)
        for side in ('256','512'):
            a,b=m['images']['im0324'][side],m['images']['im0324_nogt'][side]
            self.assertEqual(a['input'],b['input']);self.assertEqual(a['input_word_sha256'],b['input_word_sha256'])
            self.assertTrue(a['evaluation_only']);self.assertEqual(b['evaluation_only'],{})
        inputs=Inputs(PACKAGE,m['images'])
        for i,case in enumerate(planned_cases()+manual_cases()):inputs.request(dict(case,client_nonce='host_case_%d'%i))

    def test_python310_seven_cells_and_extraction(self):
        for p in PACKAGE.rglob('*.py'):ast.parse(p.read_bytes(),feature_version=(3,10))
        nb=json.loads((PACKAGE.parent/'upload/c7_w5b_interaction.ipynb').read_bytes())
        cells=[c for c in nb['cells'] if c['cell_type']=='code'];self.assertEqual(len(cells),7)
        for c in cells:ast.parse(''.join(c['source']),feature_version=(3,10))
        code=''.join(cells[0]['source']);cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            try:
                os.chdir(td);shutil.copy2(PACKAGE.parent/'upload/c7_w5b_interaction_r1.zip',td)
                with contextlib.redirect_stdout(io.StringIO()):exec(code,{})
                validate_w5b(Path(td)/'c7_w5b_interaction_r1')
                with self.assertRaises(FileExistsError):exec(code,{})
            finally:os.chdir(cwd)

    def test_corrupted_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'package';shutil.copytree(PACKAGE,target)
            p=target/'ui/app.js';p.write_bytes(p.read_bytes()+b'\n//changed')
            with self.assertRaisesRegex(ValueError,'changed'):validate_w5b(target)


class LiveHost(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'package'
        shutil.copytree(PACKAGE,self.root)
        self.manifest=validate_package(self.root);self.hardware=HostHardware(self.root)
        executor=ThreadPoolExecutor(max_workers=1)
        await asyncio.get_running_loop().run_in_executor(executor,self.hardware.open)
        self.manager=service.Manager(self.root,self.manifest,self.hardware,executor)
        sockets=tornado.netutil.bind_sockets(0,'127.0.0.1')
        server=tornado.httpserver.HTTPServer(service.application(self.manager));server.add_sockets(sockets)
        self.ctx=dict(root=self.root,port=sockets[0].getsockname()[1],manager=self.manager,server=server,executor=self.manager.executor)

    async def asyncTearDown(self):
        if self.manager.pump:await self.manager.pump
        self.ctx['server'].stop();await self.ctx['server'].close_all_connections()
        self.manager.executor.shutdown(wait=True);self.temp.cleanup()

    async def test_complete_35_http_and_seven_manual_full_arrays_exports(self):
        with contextlib.redirect_stdout(io.StringIO()):await automatic_w5b(self.ctx)
        self.assertEqual(self.manager.status()['completed'],35)
        with self.assertRaises(ValueError):await automatic_w5b(self.ctx)
        with self.assertRaises(ValueError):summary_w5b(self.ctx)
        from w5b_board import wait_run
        for i,case in enumerate(manual_cases()):
            job=self.manager.submit(dict(case,client_nonce='manual_host_%02d'%i))
            job=await wait_run(self.ctx,job['run_id'])
            obs=observation(job,page=('b' if i==6 else 'a')*32,start=(1 if i==6 else i*100+1))
            bad=dict(obs,page_id='wrong')
            with self.assertRaises(RequestError):self.manager.browser_timing(job['run_id'],bad)
            self.manager.browser_timing(job['run_id'],obs)
            with self.assertRaises(service.BusyError):self.manager.browser_timing(job['run_id'],obs)
        result=summary_w5b(self.ctx);self.assertEqual(result['tasks'],42)
        original=self.manager.jobs[list(self.manager.jobs)[-1]]['browser_timing']['page_id']
        self.manager.jobs[list(self.manager.jobs)[-1]]['browser_timing']['page_id']='a'*32
        with self.assertRaisesRegex(ValueError,'reload'):summary_w5b(self.ctx)
        self.manager.jobs[list(self.manager.jobs)[-1]]['browser_timing']['page_id']=original
        with contextlib.redirect_stdout(io.StringIO()):
            await close_w5b(self.ctx);archive=await export_w5b(self.ctx)
        self.assertEqual(self.manager.status()['service_state'],'CLOSED')
        self.assertEqual(self.hardware.calls.count('tx.transfer'),42)
        with self.assertRaises(ValueError):await export_w5b(self.ctx)
        with zipfile.ZipFile(archive) as z:
            index=json.loads(z.read('w5b_bundle_manifest.json'))
            self.assertEqual(set(z.namelist()),set(index['files'])|{'w5b_bundle_manifest.json'})
            checks=[json.loads(x) for x in z.read('w5b_checks.jsonl').splitlines()]
            self.assertEqual(len(checks),51)
        # Real board gate must reject the native HOST evidence even with notebook markers.
        nb=json.loads((PACKAGE.parent/'upload/c7_w5b_interaction.ipynb').read_bytes());i=0
        markers=['W5B_PACKAGE_PASS','W5B_PRECHECK_PASS','BROWSER_SERVICE_READY','W5B_AUTO_COMPLETE','W5B_MANUAL_READY','W5B_CLOSED_IDLE','W5B_RESULTS_READY']
        for cell in nb['cells']:
            if cell['cell_type']=='code':
                output=markers[i]+'\n'
                if i==1:output+='Runtime: '+repr(self.hardware.environment)+'\n'
                cell['execution_count']=i+1;cell['outputs']=[dict(output_type='stream',name='stdout',text=[output])];i+=1
        path=self.root.parent/'host.ipynb';path.write_text(json.dumps(nb))
        with self.assertRaisesRegex(ValueError,'HOST'):verify(Path(archive),path,PACKAGE.parent)
        result=verify(Path(archive),path,PACKAGE.parent,host_fixture=True)
        self.assertEqual(result['status'],'HOST_FIXTURE_VALIDATED_NOT_BOARD')
        self.assertEqual(result['tasks'],42)
        if os.environ.get('W5B_KEEP_HOST_FIXTURE'):
            saved=Path(os.environ['W5B_KEEP_HOST_FIXTURE']);saved.mkdir(parents=True,exist_ok=False)
            shutil.copy2(archive,saved/'HOST_ONLY_results.zip');shutil.copy2(path,saved/'HOST_ONLY_notebook.ipynb')
            (saved/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        damaged=self.root.parent/'damaged.zip'
        with zipfile.ZipFile(archive) as original,zipfile.ZipFile(damaged,'x',zipfile.ZIP_DEFLATED) as altered:
            for name in original.namelist():
                data=original.read(name)
                if name=='w5b_summary.json':data+=b' '
                altered.writestr(name,data)
        with self.assertRaisesRegex(ValueError,'Hash mismatch'):verify(damaged,path,PACKAGE.parent,host_fixture=True)

    async def test_timeout_stops_and_retains_no_retry(self):
        self.hardware.fault='timeout'
        with contextlib.redirect_stdout(io.StringIO()),patch('w5b_board.planned_cases',return_value=planned_cases()):
            with self.assertRaises(ValueError):await automatic_w5b(self.ctx)
        self.assertIsNotNone(self.manager.error);self.assertTrue(self.hardware.retained)
        self.assertEqual(self.manager.status()['accepted'],1)
        with self.assertRaises(service.BusyError):self.manager.finish()
        with self.assertRaises(ValueError):await automatic_w5b(self.ctx)


if __name__=='__main__':unittest.main()
