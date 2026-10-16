"""HOST ONLY: real service lifecycle with native DMA fixture; never board proof."""
import ast, asyncio, contextlib, io, json, os, shutil, sys, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import tornado.httpserver, tornado.netutil
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from pynq_showcase import service
from pynq_showcase.protocol import validate_package, file_info
from showcase_board import validate_showcase, summary_showcase, close_showcase, export_showcase, EXAMPLES
from verify_c7_showcase import verify
from browser_q4d_fixtures import HostHardware
from test_c7_w5b import observation
from w5b_board import wait_run, config
PACKAGE=Path(os.environ.get('SHOWCASE_PACKAGE',str(ROOT/'build/deploy/c7_showcase_dev01/package')))
REF=PACKAGE.parent/'upload/c7_showcase.ipynb'
BASE=ROOT/'build/deploy/c7_w5b_interaction_r1/package'


class PackageTests(unittest.TestCase):
    def test_pair_and_frozen_math(self):
        validate_showcase(PACKAGE)
        for name in ('hardware.py','evaluation.py','quality_observer.py','__init__.py'):
            self.assertEqual((PACKAGE/'pynq_showcase'/name).read_bytes(),(BASE/'pynq_w5b'/name).read_bytes())
        old=json.loads((BASE/'browser_manifest.json').read_bytes())
        for name,info in old['artifacts'].items():
            if not name.startswith(('ui/','pynq_w5b/')): self.assertEqual(file_info(PACKAGE/name), info)
        def funcs(p): return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef)}
        for name in ('process_run','encode_png'):
            self.assertEqual(funcs(PACKAGE/'pynq_showcase/service.py')[name],funcs(BASE/'pynq_w5b/service.py')[name])
        m=validate_package(PACKAGE)
        self.assertEqual(len([x for x in m['images'] if not x.endswith('_nogt')]),20)
        self.assertEqual(len(set(EXAMPLES)),8)
        for p in PACKAGE.rglob('*.py'): ast.parse(p.read_bytes(),feature_version=(3,10))
        for p in (PACKAGE/'pynq_showcase').glob('*.py'):
            self.assertNotIn('expected_words(',p.read_text())

    def test_notebook_extraction_and_integrity(self):
        nb=json.loads(REF.read_bytes()); codes=[c for c in nb['cells'] if c['cell_type']=='code']
        self.assertEqual(len(codes),7)
        for c in codes: ast.parse(''.join(c['source']),feature_version=(3,10))
        cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            try:
                os.chdir(td); shutil.copy2(REF.parent/'c7_showcase_r1.zip',td)
                with contextlib.redirect_stdout(io.StringIO()): exec(''.join(codes[0]['source']),{})
                target=Path(td)/'c7_showcase_r1'; validate_showcase(target)
                with self.assertRaises(FileExistsError): exec(''.join(codes[0]['source']),{})
                (target/'ui/app.js').write_bytes(b'changed')
                with self.assertRaises(ValueError): validate_showcase(target)
            finally: os.chdir(cwd)


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)/'package'
        shutil.copytree(PACKAGE,self.root)
        self.hardware=HostHardware(self.root); executor=ThreadPoolExecutor(max_workers=1)
        await asyncio.get_running_loop().run_in_executor(executor,self.hardware.open)
        self.m=service.Manager(self.root,validate_package(self.root),self.hardware,executor)
        sockets=tornado.netutil.bind_sockets(0,'127.0.0.1')
        server=tornado.httpserver.HTTPServer(service.application(self.m)); server.add_sockets(sockets)
        self.ctx=dict(root=self.root,manager=self.m,server=server,executor=executor,
                      showcase_boot=dict(boot_id='12345678-1234-1234-1234-123456789abc',uptime_seconds=1))

    async def asyncTearDown(self):
        if self.m.pump: await self.m.pump
        self.ctx['server'].stop(); await self.ctx['server'].close_all_connections()
        self.m.executor.shutdown(wait=True); self.temp.cleanup()

    async def test_27_frames_variable_close_export_and_audit(self):
        with self.assertRaises(ValueError): summary_showcase(self.ctx)
        cases=[config(n) for n in self.m.manifest['images'] if not n.endswith('_nogt')]
        cases += [config('im0324',side=256), config('im0324_nogt'),config('im0324',mode='bypass'),
                  config(algorithm='C2',mode='threshold_candidate',threshold=28),config(algorithm='C2',mode='closed_candidate',threshold=28),
                  config('im0319'), config('im0324')]
        for i,case in enumerate(cases):
            body=dict(case,client_nonce='host_showcase_%02d'%i)
            job=self.m.submit(body)
            if i==0:
                with self.assertRaises(ValueError): summary_showcase(self.ctx)
            job=await wait_run(self.ctx,job['run_id'])
            self.m.browser_timing(job['run_id'],observation(job,start=i*100+1))
            self.assertEqual(summary_showcase(self.ctx)['tasks'],i+1)
            self.assertEqual(self.m.submit(body)['run_id'],job['run_id'])
        self.assertEqual(self.hardware.calls.count('tx.transfer'),27)
        self.assertEqual(len(summary_showcase(self.ctx)['observed_run_ids']),27)
        first=next(iter(self.m.jobs.values())); obs=first.pop('browser_timing')
        self.assertEqual(summary_showcase(self.ctx)['unobserved_run_ids'],[first['run_id']])
        first['browser_timing']=obs
        self.m.error='HOST synthetic failure'
        with self.assertRaises(ValueError): summary_showcase(self.ctx)
        self.m.error=None
        with patch('pynq_showcase.service.shutil.disk_usage') as disk:
            disk.return_value.free=511*1024**2
            with self.assertRaisesRegex(service.BusyError,'512'): self.m.submit(dict(config(),client_nonce='low_space'))
        with patch('pynq_showcase.service.MAX_RUNS',27):
            with self.assertRaisesRegex(service.BusyError,'100'): self.m.submit(dict(config(),client_nonce='over_cap'))
        with patch('showcase_board.Path.read_text',return_value=self.ctx['showcase_boot']['boot_id']): await close_showcase(self.ctx)
        archive=Path(await export_showcase(self.ctx))
        with self.assertRaises(ValueError): await export_showcase(self.ctx)
        nb=json.loads(REF.read_bytes())
        markers=['SHOWCASE_PACKAGE_PASS','SHOWCASE_PRECHECK_PASS','BROWSER_SERVICE_READY','SHOWCASE_MANUAL_READY','SHOWCASE_CLOSED_IDLE','SHOWCASE_RESULTS_READY','SHOWCASE_FINISHED']
        for i,(cell,marker) in enumerate(zip((c for c in nb['cells'] if c['cell_type']=='code'),markers)):
            cell['execution_count']=i+1; cell['outputs']=[dict(output_type='stream',name='stdout',text=[marker+' HOST ONLY\n'])]
        executed=self.root.parent/'host.ipynb'; executed.write_text(json.dumps(nb))
        with self.assertRaises(ValueError): verify(archive,executed,REF,PACKAGE)
        result=verify(archive,executed,REF,PACKAGE,host_fixture=True)
        self.assertEqual(result['tasks'],27); self.assertEqual(result['coverage']['visible_frames'],27)
        self.assertEqual(len(result['coverage']['images_c7_final_t112']),20)
        self.assertEqual(result['coverage']['sides'],[256,512])
        self.assertTrue(result['coverage']['no_gt'] and result['coverage']['bypass'])
        out=ROOT/'results/c7_showcase_r1';out.mkdir(exist_ok=True)
        (out/'host_audit.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__': unittest.main()
