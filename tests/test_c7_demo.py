"""HOST orchestration/export regression, never board or reboot evidence."""
import ast, asyncio, copy, io, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
os.environ['W5B_PACKAGE']=str(ROOT/'build/deploy/c7_w5b_interaction_r1/package')
import test_c7_w5b as support
observation=support.observation
PACKAGE=support.PACKAGE
from w5b_board import manual_cases, wait_run
from c7_demo_board import demo_summary,close_demo,export_demo
from verify_c7_demo import verify
REF=ROOT/'build/deploy/c7_delivery_demo_dev01/upload/c7_delivery_demo.ipynb'

class DemoTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=support.LiveHost.asyncSetUp
    asyncTearDown=support.LiveHost.asyncTearDown

    async def test_export_audit_and_fault_guards(self):
        self.ctx['demo_boot']=dict(boot_id='12345678-1234-1234-1234-123456789abc',uptime_seconds=20,
            scope='HOST ONLY synthetic boot; not physical restart')
        with self.assertRaises(ValueError):demo_summary(self.ctx)
        for i,case in enumerate(manual_cases()):
            job=self.manager.submit(dict(case,client_nonce='demo_host_%02d'%i))
            job=await wait_run(self.ctx,job['run_id'])
            self.manager.browser_timing(job['run_id'],observation(job,page=('b' if i==6 else 'a')*32,start=(1 if i==6 else i*100+1)))
        self.assertEqual(demo_summary(self.ctx)['tasks'],7)
        self.manager.error='synthetic fault'
        with self.assertRaises(ValueError):demo_summary(self.ctx)
        self.manager.error=None
        jobs=list(self.manager.jobs.values());page=jobs[-1]['browser_timing']['page_id']
        jobs[-1]['browser_timing']['page_id']='a'*32
        with self.assertRaises(ValueError):demo_summary(self.ctx)
        jobs[-1]['browser_timing']['page_id']=page
        with patch('c7_demo_board.Path.read_text',return_value=self.ctx['demo_boot']['boot_id']):
            await close_demo(self.ctx)
        archive=Path(await export_demo(self.ctx))
        self.assertEqual(self.hardware.calls.count('tx.transfer'),7)
        with self.assertRaises(ValueError):await export_demo(self.ctx)
        nb=json.loads(REF.read_bytes());markers=['W5B_PACKAGE_PASS','DEMO_PRECHECK_PASS','BROWSER_SERVICE_READY','DEMO_MANUAL_READY','DEMO_CLOSED_IDLE','DEMO_RESULTS_READY','DEMO_FINISHED']
        for i,c in enumerate(c for c in nb['cells'] if c['cell_type']=='code'):
            c['execution_count']=i+1;c['outputs']=[dict(output_type='stream',name='stdout',text=[markers[i]+' HOST ONLY\n'])]
        executed=self.root.parent/'host.ipynb';executed.write_text(json.dumps(nb))
        with self.assertRaises(ValueError):verify(archive,executed,REF,PACKAGE)
        result=verify(archive,executed,REF,PACKAGE,host_fixture=True)
        self.assertEqual(result['status'],'HOST_DEMO_FIXTURE_NOT_BOARD')
        self.assertEqual(result['matched_words'],7*512*512)
        out=ROOT/'results/c7_delivery_r1';out.mkdir(parents=True,exist_ok=True)
        (out/'host_demo_audit.json').write_text(json.dumps(result,indent=2))
        nb['cells'][2]['source']=['print("tampered")\n'];executed.write_text(json.dumps(nb))
        with self.assertRaises(ValueError):verify(archive,executed,REF,PACKAGE,host_fixture=True)

class NotebookTests(unittest.TestCase):
    def test_frozen_package_and_fresh_extraction(self):
        upload=REF.parent
        self.assertEqual((upload/'c7_w5b_interaction_r1.zip').read_bytes(),(PACKAGE.parent/'upload/c7_w5b_interaction_r1.zip').read_bytes())
        nb=json.loads(REF.read_bytes());codes=[c for c in nb['cells'] if c['cell_type']=='code'];self.assertEqual(len(codes),7)
        for c in codes:ast.parse(''.join(c['source']),feature_version=(3,10))
        from contextlib import redirect_stdout
        from w5b_board import validate_w5b
        cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            try:
                os.chdir(td);shutil.copy2(upload/'c7_w5b_interaction_r1.zip',td)
                with redirect_stdout(io.StringIO()):exec(''.join(codes[0]['source']),{})
                validate_w5b(Path(td)/'c7_w5b_interaction_r1')
                with self.assertRaises(FileExistsError):exec(''.join(codes[0]['source']),{})
            finally:os.chdir(cwd)

if __name__=='__main__':unittest.main()
