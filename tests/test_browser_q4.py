"""Application/native ownership/API/GT/timing tests; never a board PASS."""
import asyncio
import copy
import io
import ast
import contextlib
import os
import json
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
import tornado.httpserver
import tornado.netutil
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

from browser_q4_fixtures import ROOT, HostHardware, expected_words
from pynq_q4.protocol import Inputs, RequestError, file_info, validate_package
from pynq_q4.evaluation import score_completed
from pynq_q4.service import BusyError, Manager, application
from verify_q4_run import check_run
from verify_q4_archive import verify

PACKAGE = ROOT / 'build/deploy/q4_c5_experimental_r1'


def request(image='im0001', side=256, mode='final', nonce='testnonce01', algorithm='A', threshold=28, png_profile='baseline'):
    return {'image_id': image, 'side': side, 'threshold': threshold, 'algorithm': algorithm, 'mode': mode, 'client_nonce': nonce, 'png_profile': png_profile}


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = validate_package(PACKAGE)
        self.inputs = Inputs(PACKAGE, self.manifest['images'])

    def hardware(self, fault=None):
        hardware = HostHardware(PACKAGE, fault=fault)
        hardware.open()
        return hardware

    def test_new_catalog_matches_original_tested_geometry_and_is_gt_independent(self):
        self.assertEqual(len(self.inputs.public_images()), 20)
        for side in (256, 512):
            words, entry = self.inputs.load(self.inputs.request(request(side=side)))
            np.testing.assert_array_equal(words, np.load(ROOT / 'build/deploy/a4_segmentation_2017_4_r1' / ('stare_im0001_' + str(side) + '.npy')))
            self.assertFalse(words.flags.writeable)
            self.assertNotIn('evaluation_only', self.inputs.request(request()))

    def test_request_rejects_unsupported_threshold_algorithm_invalid_types_and_paths(self):
        for change in ({'threshold': 0}, {'threshold': True}, {'side': True}, {'side': 1024},
                       {'mode': 'algorithm_B'}, {'image_id': '../../labels'}, {'client_nonce': 'short'}, {'side': 256.0}):
            with self.subTest(change=change), self.assertRaises(RequestError):
                self.inputs.request({**request(), **change})
        with self.assertRaises(RequestError):
            self.inputs.request({**request(), 'ground_truth': 'AH'})

    def test_two_images_two_sizes_all_modes_real_native_order_and_readonly_snapshot(self):
        hardware = self.hardware()
        for image in ('im0001', 'im0002'):
            for side in (256, 512):
                for mode in ('bypass', 'threshold_candidate', 'closed_candidate', 'final'):
                    config = self.inputs.request(request(image=image, side=side, mode=mode, algorithm='C5'))
                    words, _ = self.inputs.load(config)
                    hardware.calls.clear()
                    output, record = hardware.run(words, config)
                    np.testing.assert_array_equal(output, expected_words(words, config['mode_code'], 'C5'))
                    self.assertFalse(output.flags.writeable)
                    self.assertFalse(np.shares_memory(output, hardware.buffers[-1]))
                    self.assertEqual(hardware.calls, ['rx.flush', 'rx.transfer', 'tx.flush', 'tx.transfer', 'bounded.poll', 'rx.invalidate', 'rx.free', 'tx.free'])
                    self.assertEqual(record['send_bytes'], side * side * 4)
                    self.assertEqual(record['recv_bytes'], record['send_bytes'])
                    self.assertGreater(record['timing_ns']['pl_core_frame_ns'], 0)
                    self.assertEqual(record['applied_parameters']['threshold'], 28)
                    self.assertEqual(hardware.retained, [])
        self.assertEqual(hardware.downloads, 1)

    def test_a_c2_threshold_sequence_reaches_gpio_and_actual_output(self):
        hardware = self.hardware()
        outputs = []
        for algorithm, threshold in [('A',28), ('C2',28), ('C5',40), ('A',28)]:
            config = self.inputs.request(request(algorithm=algorithm, threshold=threshold))
            words, _ = self.inputs.load(config)
            output, record = hardware.run(words, config)
            np.testing.assert_array_equal(output, expected_words(words, 3, algorithm, threshold))
            self.assertEqual(record['applied_parameters']['algorithm'], algorithm)
            self.assertEqual(record['applied_parameters']['threshold'], threshold)
            self.assertEqual(record['hardware_latched_parameter_readback']['sequence'], len(outputs)+1)
            outputs.append(output)
        self.assertFalse(np.array_equal(outputs[0], outputs[1]))
        self.assertFalse(np.array_equal(outputs[1], outputs[2]))
        np.testing.assert_array_equal(outputs[0], outputs[3])

    def test_threshold_endpoints_and_tag_wrap(self):
        hardware = self.hardware()
        hardware.sequence = 65535
        hardware.observe.pages.update({1:2,4:65535,11:65535})
        for threshold in (1,255):
            config = self.inputs.request(request(algorithm='C2', threshold=threshold))
            words, _ = self.inputs.load(config)
            output, rec = hardware.run(words, config)
            self.assertEqual(rec['applied_parameters']['task_tag'], (hardware.sequence & 65535))
            np.testing.assert_array_equal(output, expected_words(words, 3, 'C2', threshold))
        for value in (0,256,28.0,True,'28'):
            with self.assertRaises(RequestError): self.inputs.request(request(threshold=value))
        with self.assertRaises(RequestError): self.inputs.request(request(algorithm='B'))

    def test_counter_wrap_and_consecutive_frames(self):
        hardware = self.hardware()
        hardware.gpio.status = 0x3fff | (0x3fff << 14)
        config = self.inputs.request(request())
        words, _ = self.inputs.load(config)
        _, record = hardware.run(words, config)
        self.assertEqual(record['frame_status_after'], 0)
        self.assertTrue(record['frame_counter_wrapped'])
        _, record = hardware.run(words, config)
        self.assertEqual(record['frame_count'], 1)

    def test_faults_keep_all_native_references_and_prohibit_new_transfers(self):
        for fault in ('raw_corrupt', 'nonbinary', 'outside_fov', 'counter', 'bytes', 'dma_error', 'timeout',
                      'alignment', 'overlap', 'free_rx', 'free_tx', 'allocation', 'overlay', 'observer_control', 'observer_sequence', 'observer_words', 'observer_overflow'):
            with self.subTest(fault=fault):
                hardware = self.hardware(fault)
                config = self.inputs.request(request())
                words, _ = self.inputs.load(config)
                with self.assertRaises((ValueError, RuntimeError, TimeoutError)):
                    hardware.run(words, config)
                self.assertEqual(hardware.state, 'FAULT')
                self.assertEqual(len(hardware.retained), 0 if fault == 'overlay' else 1 if fault in ('free_tx', 'allocation') else 2)
                self.assertTrue(all(not buffer.freed for buffer in hardware.retained))
                self.assertIn('error', hardware.last_attempt)
                old_calls = list(hardware.calls)
                with self.assertRaises(ValueError):
                    hardware.run(words, config)
                self.assertEqual(old_calls, hardware.calls)

    def test_snapshot_exception_retains_dma_buffers(self):
        hardware = self.hardware()
        config = self.inputs.request(request())
        words, _ = self.inputs.load(config)
        with patch('pynq_q4.hardware.np.copyto', side_effect=RuntimeError('HOST copy fault')), self.assertRaises(RuntimeError):
            hardware.run(words, config)
        self.assertEqual(len(hardware.retained), 2)

    def test_other_thread_cannot_access_gpio_or_dma(self):
        hardware = self.hardware()
        config = self.inputs.request(request())
        words, _ = self.inputs.load(config)
        errors = []
        def worker():
            try:
                hardware.run(words, config)
            except ValueError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start(); thread.join()
        self.assertIn('single hardware worker', errors[0])
        self.assertEqual(hardware.buffers, [])

    def test_gt_missing_bypass_and_scores_recomputed_only_from_current_output(self):
        config = self.inputs.request(request())
        words, entry = self.inputs.load(config)
        output = expected_words(words, 3)
        fov = (words >> 24) != 0
        result = score_completed(PACKAGE, entry, output, fov, 3)
        self.assertEqual(set(result['annotations']), {'AH', 'VK'})
        self.assertEqual(result['vessel_pixels'], int(np.count_nonzero(((output >> 16) & 255) & fov)))
        empty = score_completed(PACKAGE, {**entry, 'evaluation_only': {}}, output, fov, 3)
        self.assertEqual(empty['annotations'], {})
        self.assertIsNotNone(empty['quality_reason'])
        bypass = score_completed(PACKAGE, entry, words, fov, 0)
        self.assertIsNone(bypass['vessel_area_fraction'])
        changed = output.copy(); changed &= np.uint32(0xff00ffff)
        score = score_completed(PACKAGE, entry, changed, fov, 3)
        self.assertNotEqual(score['annotations']['AH']['dice'], result['annotations']['AH']['dice'])

    def test_changed_package_bytes_fail_before_hardware_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'package'
            shutil.copytree(PACKAGE, target, ignore=shutil.ignore_patterns('browser_results', '__pycache__'))
            for name in ('pynq_q4/hardware.py', 'ui/app.js', 'q4_refined.bit', 'labels/im0001_256_AH.npy'):
                path = target / name
                original = path.read_bytes()
                path.write_bytes(original + b'X')
                with self.assertRaisesRegex(ValueError, 'Package mismatch'):
                    validate_package(target)
                path.write_bytes(original)

    def test_startup_notebook_safely_extracts_verified_inventory_before_any_fpga_import(self):
        release = json.loads((ROOT / 'notebooks/q4_quality_start.ipynb').read_bytes())
        code = [''.join(cell['source']) for cell in release['cells'] if cell['cell_type'] == 'code']
        for source in code:
            ast.parse(source, feature_version=(3, 10))
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                bundle = Path('q4_c5_experimental_r1.zip')
                shutil.copyfile(ROOT / 'build/deploy/q4_c5_upload_r1' / bundle.name, bundle)
                scope = {}
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code[0], 'HOST_TEST_startup', 'exec'), scope)
                self.assertEqual(len(validate_package(scope['browser_package_root'])['artifacts']), 134)
                self.assertNotIn('browser_context', scope)
                with self.assertRaisesRegex(RuntimeError, 'Already extracted'):
                    exec(compile(code[0], 'HOST_TEST_startup', 'exec'), scope)
                bundle.write_bytes(bundle.read_bytes() + b'X')
                with self.assertRaisesRegex(ValueError, 'Wrong download bytes'):
                    exec(compile(code[0], 'HOST_TEST_startup', 'exec'), {})
            finally:
                os.chdir(original_directory)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / 'package'
        shutil.copytree(PACKAGE, self.root, ignore=shutil.ignore_patterns('browser_results', '__pycache__'))
        self.manifest = validate_package(self.root)
        self.hardware = HostHardware(self.root, delay=0.04)
        self.manager = Manager(self.root, self.manifest, self.hardware)
        await asyncio.get_running_loop().run_in_executor(self.manager.executor, self.hardware.open)
        sockets = tornado.netutil.bind_sockets(0, address='127.0.0.1')
        self.port = sockets[0].getsockname()[1]
        self.server = tornado.httpserver.HTTPServer(application(self.manager))
        self.server.add_sockets(sockets)
        self.client = AsyncHTTPClient()

    async def asyncTearDown(self):
        if self.manager.pump:
            await self.manager.pump
        self.server.stop()
        await self.server.close_all_connections()
        self.manager.executor.shutdown(wait=True)
        self.client.close()
        self.temporary.cleanup()

    async def http(self, path, body=None):
        value = await self.client.fetch(HTTPRequest('http://127.0.0.1:' + str(self.port) + path,
            method='GET' if body is None else 'POST', body=None if body is None else json.dumps(body),
            headers={} if body is None else {'Content-Type': 'application/json'}), raise_error=False)
        return value, json.loads(value.body) if 'json' in value.headers.get('Content-Type', '') else value.body

    async def completed(self, nonce='testnonce01', **kwargs):
        response, job = await self.http('/api/runs', request(nonce=nonce, **kwargs))
        self.assertEqual(response.code, 202)
        await self.manager.pump
        return self.manager.get(job['run_id'])

    def observation(self, job, start=10, loop_id=None, index=None, loop_start=None):
        return {'client_nonce': job['request']['client_nonce'], 'config_id': job['config_id'],
            'input_sha256': job['input']['sha256'], 'output_sha256': job['output']['sha256'],
            'request_start_ms': start, 'result_received_ms': start + 100, 'images_decoded_ms': start + 110,
            'render_done_ms': start + 120, 'visibility': 'visible', 'user_agent': 'HOST_TEST',
            'loop_id': loop_id, 'loop_index': index, 'loop_start_ms': loop_start}

    async def test_http_invalid_requests_never_allocate_or_change_config(self):
        response, value = await self.http('/api/runs', {**request(), 'threshold': 0})
        self.assertEqual(response.code, 422)
        self.assertEqual(self.hardware.buffers, [])
        self.assertEqual(self.hardware.gpio.control, 0)

    async def test_bounded_queue_is_responsive_and_nonce_retries_do_not_add_frames(self):
        first = self.manager.submit(request(nonce='firstnonce'))
        self.manager.submit(request(nonce='secondnonce', image='im0002'))
        self.assertEqual(len(self.manager.queue), 1)
        self.assertEqual(self.manager.active, first['run_id'])
        self.assertIs(self.manager.submit(request(nonce='firstnonce')), first)
        with self.assertRaises(BusyError):
            self.manager.submit(request(nonce='thirdnonce'))
        with self.assertRaises(BusyError):
            self.manager.submit(request(nonce='firstnonce', side=512))
        response, status = await self.http('/api/status')
        self.assertEqual(response.code, 200)
        self.assertLessEqual(status['pending'], 1)
        await self.manager.pump
        self.assertEqual(self.manager.status()['completed'], 2)
        self.assertEqual(self.hardware.last_status & 0x3fff, 2)
        self.assertEqual(len({job['run_id'] for job in self.manager.jobs.values()}), 2)

    async def test_images_same_frame_match_real_packed_channels_and_headers(self):
        job = await self.completed()
        directory = self.manager.directory / job['run_id']
        words = np.load(directory / 'output_packed.npy')
        for kind, expected in (('enhanced', ((words >> 8) & 255).astype(np.uint8)), ('mask', ((words >> 16) & 255).astype(np.uint8))):
            response, pixels = await self.http('/api/runs/' + job['run_id'] + '/images/' + kind)
            self.assertEqual(response.headers['X-Run-Id'], job['run_id'])
            self.assertEqual(response.headers['X-Output-SHA256'], job['output']['sha256'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            np.testing.assert_array_equal(np.array(Image.open(directory / (kind + '.png'))), expected)
        self.assertEqual(job['evidence_kind'], 'HOST_TEST_DOUBLE_NOT_BOARD')

    async def test_bypass_exposes_no_stale_enhanced_mask_or_scores(self):
        previous = await self.completed(nonce='firstnonce')
        job = await self.completed(nonce='nextnonce0', mode='bypass')
        self.assertEqual(set(job['images']), {'original'})
        self.assertIsNone(job['quality']['vessel_area_fraction'])
        response, _ = await self.http('/api/runs/' + job['run_id'] + '/images/mask')
        self.assertEqual(response.code, 404)
        self.assertNotEqual(job['run_id'], previous['run_id'])

    async def test_stale_replayed_nonfinite_or_nonmonotonic_client_observations_rejected(self):
        job = await self.completed()
        for change in ({'output_sha256': 'stale'}, {'request_start_ms': float('nan')}, {'images_decoded_ms': 9},
                       {'loop_id': 'loopnonce0', 'loop_index': 2, 'loop_start_ms': 10}):
            response, _ = await self.http('/api/runs/' + job['run_id'] + '/browser-timing', {**self.observation(job), **change})
            self.assertEqual(response.code, 422)
        response, value = await self.http('/api/runs/' + job['run_id'] + '/browser-timing', self.observation(job))
        self.assertEqual(value['request_to_render_ms'], 120)
        self.assertIsNone(value['browser_actual_fps'])
        response, _ = await self.http('/api/runs/' + job['run_id'] + '/browser-timing', self.observation(job))
        self.assertEqual(response.code, 409)

    async def test_fps_counts_unique_consecutive_results_and_hidden_interval_invalidates_loop(self):
        for index, visibility in ((1, 'visible'), (2, 'visible'), (3, 'hidden'), (4, 'visible')):
            job = await self.completed(nonce='loopnonce' + str(index))
            observed = {**self.observation(job, start=10 + 200 * (index - 1), loop_id='loopid012', index=index, loop_start=10), 'visibility': visibility}
            timing = self.manager.browser_timing(job['run_id'], observed)
            self.assertEqual(timing['browser_actual_fps'], 2 * 1000 / 320 if index == 2 else None)

    async def test_continuous_group_rejects_parameter_change(self):
        first = await self.completed(nonce='firstnonce')
        self.manager.browser_timing(first['run_id'], self.observation(first,loop_id='loopnonce0',index=1,loop_start=10))
        second = await self.completed(nonce='nextnonce0', algorithm='C2')
        with self.assertRaises(RequestError):
            self.manager.browser_timing(second['run_id'], self.observation(second,start=210,loop_id='loopnonce0',index=2,loop_start=10))

    async def test_fault_cancels_pending_preserves_native_refs_and_blocks_close_or_retry(self):
        self.hardware.fault = 'timeout'
        first = self.manager.submit(request(nonce='firstnonce'))
        pending = self.manager.submit(request(nonce='secondnonce'))
        await self.manager.pump
        self.assertEqual(first['status'], 'FAILED')
        self.assertEqual(pending['status'], 'CANCELLED')
        self.assertEqual(len(self.hardware.retained), 2)
        with self.assertRaises(BusyError):
            self.manager.finish()
        response, _ = await self.http('/api/runs', request(nonce='thirdnonce'))
        self.assertEqual(response.code, 409)
        self.assertEqual(self.hardware.downloads, 1)
        path = await self.manager.export()
        with zipfile.ZipFile(path) as archive:
            self.assertIn(first['run_id'] + '/record.json', archive.namelist())

    async def test_export_preserves_native_arrays_browser_observation_and_null_timing_csv(self):
        job = await self.completed()
        self.manager.browser_timing(job['run_id'], self.observation(job))
        path = await self.manager.export()
        with zipfile.ZipFile(path) as archive:
            prefix = job['run_id'] + '/'
            self.assertEqual(archive.read(prefix + 'output_packed.npy'), (self.manager.directory / prefix / 'output_packed.npy').read_bytes())
            self.assertIn(prefix + 'browser_timing.json', archive.namelist())
            self.assertIn('pl_core_frame_ns', archive.read('measurements.csv').decode('utf-8-sig'))
            self.assertNotIn(b'None', archive.read('measurements.csv'))
        with patch.object(self.manager, 'exporting', True), self.assertRaises(BusyError):
            self.manager.submit(request(nonce='secondnonce'))
        self.manager.finish()
        self.assertTrue(self.manager.closed)

    async def test_offline_verifier_checks_all_words_and_detects_rehashed_tampering(self):
        job = await self.completed()
        path = await self.manager.export()
        with zipfile.ZipFile(path) as archive:
            checked = check_run(archive, job, self.root, self.manifest)
            self.assertEqual(checked['matched_words'], 65536)
            saved = {name: archive.read(name) for name in archive.namelist()}
        changed = copy.deepcopy(job)
        prefix = job['run_id'] + '/'
        output = np.load(io.BytesIO(saved[prefix + 'output_packed.npy']))
        output[128, 128] ^= np.uint32(255 << 16)
        stream = io.BytesIO(); np.save(stream, output, allow_pickle=False)
        data = stream.getvalue()
        from pynq_q4.protocol import sha
        changed['files']['output_packed.npy'] = {'bytes': len(data), 'sha256': sha(data)}
        changed['output']['sha256'] = changed['evidence']['output_sha256'] = sha(output.tobytes())
        saved[prefix + 'output_packed.npy'] = data
        altered = self.root / 'HOST_TEST_tampered.zip'
        with zipfile.ZipFile(altered, 'w') as archive:
            for name, value in saved.items():
                archive.writestr(name, value)
        with zipfile.ZipFile(altered) as archive, self.assertRaisesRegex(ValueError, 'independent A/C2'):
            check_run(archive, changed, self.root, self.manifest)

    async def test_host_preview_cannot_be_accepted_as_new_board_evidence(self):
        await self.completed()
        path = await self.manager.export()
        notebook = json.loads((ROOT / 'notebooks/q4_quality_start.ipynb').read_bytes())
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                cell['execution_count'] = index
        target = self.root / 'HOST_TEST_synthetic_execution.ipynb'
        target.write_text(json.dumps(notebook), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'HOST TEST preview is not board evidence'):
            verify(path, target, self.root)

    async def test_storage_fault_keeps_protection_and_cancels_pending_even_when_journaling_fails(self):
        self.hardware.fault = 'timeout'
        first = self.manager.submit(request(nonce='firstnonce'))
        pending = self.manager.submit(request(nonce='secondnonce'))
        with patch('pynq_q4.service.write_json', side_effect=OSError('HOST full SD card')):
            await self.manager.pump
        self.assertEqual(self.manager.status()['service_state'], 'FAULT')
        self.assertEqual(first['status'], 'FAILED')
        self.assertEqual(pending['status'], 'CANCELLED')
        self.assertEqual(self.manager.queue, __import__('collections').deque())
        self.assertEqual(len(self.hardware.retained), 2)
        self.assertIn('record_write_error', self.manager.error)

    async def test_cross_origin_posts_rejected_without_hardware_access(self):
        response = await self.client.fetch(HTTPRequest('http://127.0.0.1:' + str(self.port) + '/api/runs',
            method='POST', body=json.dumps(request()), headers={'Content-Type': 'application/json', 'Origin': 'http://different-origin.invalid'}), raise_error=False)
        self.assertEqual(response.code, 422)
        self.assertEqual(self.hardware.buffers, [])

    async def test_interrupted_async_wait_does_not_restart_free_or_hide_native_operation(self):
        self.hardware.delay = 0.2
        job = self.manager.submit(request())
        while len(self.hardware.retained) < 2:
            await asyncio.sleep(0.001)
        self.manager.pump.cancel()
        await self.manager.pump
        self.assertEqual(self.manager.status()['service_state'], 'FAULT')
        self.assertEqual(job['status'], 'FAILED')
        with self.assertRaises(BusyError):
            self.manager.finish()
        # This queued barrier waits for the existing native operation; it does
        # not cancel it, reset DMA, reload PL or supply any replacement output.
        await asyncio.get_running_loop().run_in_executor(self.manager.executor, lambda: None)
        self.assertEqual(self.hardware.downloads, 1)
        self.assertEqual(self.hardware.last_status & 0x3fff, 1)
        self.assertEqual(self.hardware.retained, [])  # Released only after its real wait/snapshot.
        self.assertTrue((self.manager.directory / job['run_id'] / 'failure.json').exists())
        with self.assertRaises(BusyError):
            self.manager.submit(request(nonce='secondnonce'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
