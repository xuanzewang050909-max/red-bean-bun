"""Q3 release/collection/failure tests. HOST TEST outputs never count as board evidence."""
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

from browser_w4a_fixtures import ROOT, HostHardware
from pynq_w4a.protocol import Inputs, file_info, validate_package, write_json
from pynq_w4a.service import Manager, BusyError
from q3_board import validate_q3, planned_requests, collect_q3, export_q3
from verify_browser_w4a_archive import check_run
from verify_q3_archive import verify, quality_report, independent_metrics, independent_regions, summarize, assess_candidate
from software.preprocessing import read_archive, prepare_sample, pack_input
from scripts.evaluate_q1_bilateral import diagnostic_regions
from scripts.package_q3_quality import startup_notebook

PACKAGE=ROOT/'build/deploy/q3_full_quality_r1'
UPLOAD=ROOT/'build/deploy/q3_quality_upload_r1'


class ReleaseTests(unittest.TestCase):
    def test_complete_frozen_inventory_and_unique_80_cohort(self):
        release, protocol=validate_q3(PACKAGE)
        plan=planned_requests(protocol)
        self.assertEqual(len(plan),80)
        self.assertEqual(len({(r['image_id'],r['side'],r['algorithm']) for r in plan}),80)
        self.assertEqual(len({r['client_nonce'] for r in plan}),80)
        self.assertEqual(sum(r['side']**2 for r in plan),13107200)
        original=json.loads((ROOT/'results/m0_stare_2026-10-11/evaluation.json').read_bytes())
        self.assertEqual(protocol['split'],original['split'])
        for name,info in protocol['frozen_files'].items():self.assertEqual(file_info(ROOT/name),info)

    def test_all_inputs_labels_geometry_match_original_preprocessing(self):
        m=validate_package(PACKAGE);raw=ROOT/'data/raw/stare'
        images=read_archive(raw/'stare-images.tar','')
        labels={k:read_archive(raw/('labels-'+k.lower()+'.tar'),'.'+k.lower()) for k in ('AH','VK')}
        for image in images:
            for side in (256,512):
                rgb,gt,geometry=prepare_sample(images[image]['pixels'],{k:v[image]['pixels']!=0 for k,v in labels.items()},side)
                e=m['images'][image][str(side)]
                self.assertEqual(e['geometry'],geometry)
                np.testing.assert_array_equal(np.load(PACKAGE/e['input']),pack_input(rgb,gt['fov']))
                for k in labels:np.testing.assert_array_equal(np.load(PACKAGE/e['evaluation_only'][k]['path']),gt[k])
        # Original two-image board evidence must retain identical input/label bytes.
        prior=ROOT/'build/deploy/browser_w4a_png_r1'
        pm=validate_package(prior)
        for image,sizes in pm['images'].items():
            for side,e in sizes.items():
                self.assertEqual(e['input_file'],m['images'][image][side]['input_file'])
                for k in labels:self.assertEqual(e['evaluation_only'][k]['file'],m['images'][image][side]['evaluation_only'][k]['file'])

    def test_hardware_runtime_js_and_css_unchanged(self):
        prior=ROOT/'build/deploy/browser_w4a_png_r1'
        for name in ['w2_quality.bit','w2_quality.hwh','w2_manifest.json','a0_dma_board_test.py','ui/app.js','ui/style.css']+[p.relative_to(prior).as_posix() for p in (prior/'pynq_w4a').glob('*.py')]:
            self.assertEqual(file_info(PACKAGE/name),file_info(prior/name))
        html=(PACKAGE/'ui/index.html').read_text(encoding='utf-8')
        self.assertIn('ETHERNET / Q3',html)
        self.assertIn('value="fast" selected',html)

    def test_no_medical_reference_or_golden_shipped(self):
        release,protocol=validate_q3(PACKAGE)
        self.assertFalse(any(any(x in name for x in ('reference.py','golden','expected','software/','tests/')) for name in release['artifacts']))
        tree=ast.parse((PACKAGE/'q3_board.py').read_bytes(),feature_version=(3,10))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('software','cv2','prepare_q2')))
        self.assertEqual(file_info(PACKAGE/'q3_board.py'),file_info(ROOT/'scripts/q3_board.py'))

    def test_paired_notebook_extraction_works_and_has_seven_cells(self):
        nb=json.loads((UPLOAD/'q3_quality_start.ipynb').read_bytes())
        cells=[c for c in nb['cells'] if c['cell_type']=='code']
        self.assertEqual(len(cells),7)
        for c in cells:
            ast.parse(''.join(c['source']),feature_version=(3,10))
            self.assertIsNone(c['execution_count']);self.assertEqual(c['outputs'],[])
        import os
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copyfile(UPLOAD/'q3_full_quality_r1.zip',Path(tmp)/'q3_full_quality_r1.zip')
            old=Path.cwd()
            try:
                os.chdir(tmp)
                with contextlib.redirect_stdout(io.StringIO()):exec(''.join(cells[0]['source']),{})
                validate_q3(Path(tmp)/'q3_full_quality_r1')
            finally:os.chdir(old)

    def test_altered_package_rejected_before_fpga(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'pkg';shutil.copytree(PACKAGE,dst,ignore=shutil.ignore_patterns('browser_results'))
            (dst/'q3_protocol.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Q3 bytes changed'):validate_q3(dst)

    def test_modified_threshold_or_duplicate_cohort_rejected(self):
        _,p=validate_q3(PACKAGE)
        for changed in ({'threshold':48},{'sizes':[512]},{'algorithms':['C2']},{'split':{'train':p['split']['train'],'heldout':p['split']['train']}}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):planned_requests({**p,**changed})

    def test_independent_regions_match_frozen_diagnostic_rules_including_empty(self):
        from software.reference import features
        m=validate_package(PACKAGE)
        for side in ('256','512'):
            e=m['images']['im0001'][side];words=np.load(PACKAGE/e['input']);fov=words>>24!=0
            from pynq_w4a.protocol import rgb_from_input
            feat=features(rgb_from_input(words),fov,'A')
            for observer in ('AH','VK'):
                truth=np.load(PACKAGE/e['evaluation_only'][observer]['path'])
                a=independent_regions(feat,truth,fov);b=diagnostic_regions(feat,fov,truth)
                for key in a:np.testing.assert_array_equal(a[key],b[key])
        blank=np.zeros((8,8),bool)
        score=independent_metrics(blank,blank,blank)
        self.assertIsNone(score['recall']);self.assertEqual(score['region_pixels'],0)

    def test_quality_gate_failure_is_reported_not_overridden(self):
        _,p=validate_q3(PACKAGE)
        good={};bad={}
        truth=np.ones((8,8),bool)
        for side in ('256','512'):
            good[side]={'per_image':{'synthetic':{scope:independent_metrics(truth,truth,truth) for scope in ('fov','full_image','bright_core','bright_band','thin_label_proxy','fov_edge')}}}
            bad[side]={'per_image':{'synthetic':{scope:independent_metrics(~truth,truth,truth) for scope in ('fov','full_image','bright_core','bright_band','thin_label_proxy','fov_edge')}}}
            for x in (good,bad):x[side]['summary']=summarize(x[side]['per_image'])
        result=assess_candidate(bad,good,p['comparison_gates'])
        self.assertFalse(result['eligible_for_Q2_feasibility']);self.assertIn('512:macro_recall',result['failed_gates'])

    def test_quality_report_separates_splits_observers_and_reports_empty_regions(self):
        _,protocol=validate_q3(PACKAGE)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);truth=np.ones((4,4),bool);np.save(root/'label.npy',truth)
            source=np.full((4,4),1<<24,dtype=np.uint32)
            catalog={name:{str(side):{'evaluation_only':{k:{'path':'label.npy'} for k in ('AH','VK')}} for side in (256,512)} for name in protocol['split']['train']+protocol['split']['heldout']}
            records=[]
            with zipfile.ZipFile(root/'synthetic.zip','w') as z:
                for index,q in enumerate(planned_requests(protocol)):
                    rid=str(index);records.append({'run_id':rid,'request':q})
                    output=np.full((4,4),255<<16 if q['algorithm']=='A' else 0,dtype=np.uint32)
                    for name,array in [('input_packed.npy',source),('output_packed.npy',output)]:
                        buf=io.BytesIO();np.save(buf,array,allow_pickle=False);z.writestr(rid+'/'+name,buf.getvalue())
            with zipfile.ZipFile(root/'synthetic.zip') as z:report=quality_report(z,root,{'images':catalog},protocol,records)
            self.assertEqual(set(report['groups']),{'train_AH','train_VK','heldout_AH','heldout_VK'})
            self.assertFalse(report['all_group_gates_met'])
            for group in report['groups'].values():
                self.assertFalse(group['meets_prespecified_protection_gates'])
                self.assertEqual(group['deltas']['512']['dice'],-1.0)
                self.assertEqual(len(group['scores']['A']['512']['per_image']),10)
                self.assertIsNone(group['scores']['C2']['512']['summary']['pooled']['bright_band']['recall'])


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'pkg'
        shutil.copytree(PACKAGE,self.root,ignore=shutil.ignore_patterns('browser_results'))
        self.release,self.protocol=validate_q3(self.root)
        self.hardware=HostHardware(self.root)
        from concurrent.futures import ThreadPoolExecutor
        self.executor=ThreadPoolExecutor(max_workers=1)
        await asyncio.get_running_loop().run_in_executor(self.executor,self.hardware.open)
        self.manager=Manager(self.root,validate_package(self.root),self.hardware,self.executor)
        self.context={'root':self.root,'manager':self.manager,'q3_protocol':self.protocol}

    async def asyncTearDown(self):
        if self.manager.pump:await self.manager.pump
        self.executor.shutdown(wait=True)
        self.tmp.cleanup()

    async def test_full_80_single_load_exclusive_gate_export_and_independent_all_words_png(self):
        emitted=io.StringIO()
        async def collect():
            with contextlib.redirect_stdout(emitted):return await collect_q3(self.context)
        task=asyncio.create_task(collect())
        await asyncio.sleep(0.02)
        with self.assertRaises(BusyError):self.manager.submit({**planned_requests(self.protocol)[0],'client_nonce':'unexpected_user_task'})
        with self.assertRaises(BusyError):await self.manager.export()
        with self.assertRaises(BusyError):self.manager.finish()
        result=await task
        self.assertEqual(result['completed'],80)
        self.assertEqual(self.hardware.downloads,1);self.assertEqual(self.hardware.sequence,80)
        self.assertFalse(self.hardware.retained)
        self.assertEqual(emitted.getvalue().count('Q3_FRAME_SAVED:'),80)
        with self.assertRaises(ValueError):await collect_q3(self.context)
        with contextlib.redirect_stdout(io.StringIO()):await export_q3(self.context,self.root/'HOST_TEST_q3.zip')
        with zipfile.ZipFile(self.root/'HOST_TEST_q3.zip') as z:
            journal=json.loads(z.read('q3_collection.json'))
            self.assertEqual(journal['evidence_kind'],'HOST_TEST_DOUBLE_NOT_BOARD')
            words=pngs=values=0
            for run_id in journal['run_ids']:
                record=json.loads(z.read(run_id+'/record.json'))
                checked=check_run(z,record,self.root,self.manager.manifest)
                words+=checked['matched_words'];pngs+=checked['matched_png_images'];values+=checked['matched_png_values']
            self.assertEqual(words,13107200);self.assertEqual(pngs,400);self.assertEqual(values,117964800)
            nb=json.loads((UPLOAD/'q3_quality_start.ipynb').read_bytes())
            for c in nb['cells']:
                if c['cell_type']=='code':c['execution_count']=1
            write_json(self.root/'host.ipynb',nb)
            with self.assertRaisesRegex(ValueError,'HOST TEST preview is not board evidence'):
                verify(self.root/'HOST_TEST_q3.zip',self.root/'host.ipynb',self.root)
        self.manager.finish()

    async def test_dma_failure_retains_buffers_journal_and_blocks_more_work(self):
        self.hardware.fault='timeout'
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):await collect_q3(self.context)
        self.assertEqual(self.hardware.state,'FAULT');self.assertEqual(len(self.hardware.retained),2)
        journal=json.loads((self.manager.directory/'q3_collection.json').read_bytes())
        self.assertEqual(journal['status'],'FAILED_OR_INTERRUPTED');self.assertEqual(len(journal['run_ids']),1)
        with self.assertRaises(BusyError):self.manager.finish()
        with self.assertRaises(ValueError):await collect_q3(self.context)
        with self.assertRaises(ValueError):await export_q3(self.context,self.root/'bad.zip')

    async def test_timeout_does_not_cancel_native_worker_or_release_inflight(self):
        self.hardware.delay=0.25
        with self.assertRaises(TimeoutError):await collect_q3(self.context,timeout_seconds=0)
        self.assertIsNotNone(self.manager.pump)
        self.assertFalse(self.manager.pump.cancelled())
        with self.assertRaises(BusyError):self.manager.finish()
        await self.manager.pump
        self.assertIsNotNone(self.manager.error)
        self.assertEqual(self.hardware.downloads,1)

    async def test_prior_manual_run_prevents_contamination_of_cohort(self):
        self.manager.submit(planned_requests(self.protocol)[0])
        await self.manager.pump
        with self.assertRaisesRegex(ValueError,'fresh idle session'):await collect_q3(self.context)
        self.assertFalse((self.manager.directory/'q3_collection.json').exists())
