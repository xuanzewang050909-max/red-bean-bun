"""Q4 release/collection/failure tests. HOST TEST outputs never count as board evidence."""
import asyncio
import ast
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np

from browser_q4_fixtures import ROOT, HostHardware
from pynq_q4.protocol import Inputs, file_info, validate_package, write_json
from pynq_q4.service import Manager, BusyError
from q4_board import validate_q4, planned_requests, collect_q4, export_q4
from verify_q4_run import check_run
from verify_q4_archive import verify
from software.preprocessing import read_archive, prepare_sample, pack_input
from scripts.evaluate_q1_bilateral import diagnostic_regions
from scripts.package_q4_quality import startup_notebook

PACKAGE=ROOT/'build/deploy/q4_c5_experimental_r1'
UPLOAD=ROOT/'build/deploy/q4_c5_upload_r1'


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'pkg'
        shutil.copytree(PACKAGE,self.root,ignore=shutil.ignore_patterns('browser_results'))
        self.release,self.protocol=validate_q4(self.root)
        self.hardware=HostHardware(self.root)
        from concurrent.futures import ThreadPoolExecutor
        self.executor=ThreadPoolExecutor(max_workers=1)
        await asyncio.get_running_loop().run_in_executor(self.executor,self.hardware.open)
        self.manager=Manager(self.root,validate_package(self.root),self.hardware,self.executor)
        self.context={'root':self.root,'manager':self.manager,'q4_protocol':self.protocol}

    async def asyncTearDown(self):
        if self.manager.pump:await self.manager.pump
        self.executor.shutdown(wait=True)
        self.tmp.cleanup()

    async def test_full_120_single_load_exclusive_gate_export_and_independent_all_words_png(self):
        emitted=io.StringIO()
        async def collect():
            with contextlib.redirect_stdout(emitted):return await collect_q4(self.context)
        task=asyncio.create_task(collect())
        await asyncio.sleep(0.02)
        with self.assertRaises(BusyError):self.manager.submit({**planned_requests(self.protocol)[0],'client_nonce':'unexpected_user_task'})
        with self.assertRaises(BusyError):await self.manager.export()
        with self.assertRaises(BusyError):self.manager.finish()
        result=await task
        self.assertEqual(result['completed'],120)
        self.assertEqual(self.hardware.downloads,1);self.assertEqual(self.hardware.sequence,120)
        self.assertFalse(self.hardware.retained)
        self.assertEqual(emitted.getvalue().count('Q4_FRAME_SAVED:'),120)
        with self.assertRaises(ValueError):await collect_q4(self.context)
        with contextlib.redirect_stdout(io.StringIO()):await export_q4(self.context,self.root/'HOST_TEST_q4.zip')
        with zipfile.ZipFile(self.root/'HOST_TEST_q4.zip') as z:
            journal=json.loads(z.read('q4_collection.json'))
            self.assertEqual(journal['evidence_kind'],'HOST_TEST_DOUBLE_NOT_BOARD')
            words=pngs=values=0
            for run_id in journal['run_ids']:
                record=json.loads(z.read(run_id+'/record.json'))
                checked=check_run(z,record,self.root,self.manager.manifest)
                words+=checked['matched_words'];pngs+=checked['matched_png_images'];values+=checked['matched_png_values']
            self.assertEqual(words,19660800);self.assertEqual(pngs,600);self.assertEqual(values,176947200)
            nb=json.loads((UPLOAD/'q4_quality_start.ipynb').read_bytes())
            for c in nb['cells']:
                if c['cell_type']=='code':c['execution_count']=1
            write_json(self.root/'host.ipynb',nb)
            with self.assertRaisesRegex(ValueError,'HOST TEST preview is not board evidence'):
                verify(self.root/'HOST_TEST_q4.zip',self.root/'host.ipynb',self.root)
        self.manager.finish()

    async def test_dma_failure_retains_buffers_journal_and_blocks_more_work(self):
        self.hardware.fault='timeout'
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):await collect_q4(self.context)
        self.assertEqual(self.hardware.state,'FAULT');self.assertEqual(len(self.hardware.retained),2)
        journal=json.loads((self.manager.directory/'q4_collection.json').read_bytes())
        self.assertEqual(journal['status'],'FAILED_OR_INTERRUPTED');self.assertEqual(len(journal['run_ids']),1)
        with self.assertRaises(BusyError):self.manager.finish()
        with self.assertRaises(ValueError):await collect_q4(self.context)
        with self.assertRaises(ValueError):await export_q4(self.context,self.root/'bad.zip')

    async def test_timeout_does_not_cancel_native_worker_or_release_inflight(self):
        self.hardware.delay=0.25
        with self.assertRaises(TimeoutError):await collect_q4(self.context,timeout_seconds=0)
        self.assertIsNotNone(self.manager.pump)
        self.assertFalse(self.manager.pump.cancelled())
        with self.assertRaises(BusyError):self.manager.finish()
        await self.manager.pump
        self.assertIsNotNone(self.manager.error)
        self.assertEqual(self.hardware.downloads,1)

    async def test_prior_manual_run_prevents_contamination_of_cohort(self):
        self.manager.submit(planned_requests(self.protocol)[0])
        await self.manager.pump
        with self.assertRaisesRegex(ValueError,'fresh idle session'):await collect_q4(self.context)
        self.assertFalse((self.manager.directory/'q4_collection.json').exists())

    async def test_reference_mismatch_stops_collection_preserves_actual_output_and_no_retry(self):
        self.protocol['expected_output_sha256']['im0001_256_A']='0'*64
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError,'Actual PL words differ'):
            await collect_q4(self.context)
        self.assertEqual(len(self.manager.jobs),1)
        self.assertEqual(self.hardware.downloads,1)
        self.assertEqual(self.hardware.sequence,1)
        journal=json.loads((self.manager.directory/'q4_collection.json').read_bytes())
        self.assertEqual(journal['status'],'FAILED_OR_INTERRUPTED')
        self.assertTrue((self.manager.directory/journal['run_ids'][0]/'output_packed.npy').exists())
        self.assertIsNotNone(self.manager.error)
        with self.assertRaises(ValueError):await collect_q4(self.context)
