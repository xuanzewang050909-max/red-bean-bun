"""Q4 collector. Medical processing remains in the RQ51 PL adapter.

Batch requests use the same single-worker browser Manager and native driver.
No CPU algorithm or golden output arrays are shipped. Reference SHA values only validate actual DMA data.
"""
import asyncio
import json
import shutil
import time
import zipfile
from pathlib import Path

from pynq_q4.protocol import file_info, require, validate_package, write_json
from pynq_q4.launch import prepare, start, export_session, finish


def planned_requests(protocol):
    ids = sorted(protocol['split']['train'] + protocol['split']['heldout'])
    require(len(ids) == len(set(ids)) == 20, 'Expected original 20 distinct images')
    require(protocol['sizes'] == [256, 512] and protocol['algorithms'] == ['A', 'C2', 'C5'] and
            protocol['threshold'] == 28 and protocol['mode'] == 'final' and protocol['png_profile'] == 'fast',
            'Frozen quality configuration changed')
    return [dict(image_id=name, side=side, algorithm=algorithm, threshold=28,
                 mode='final', png_profile='fast', client_nonce='q4_%02d_%d_%s' % (i, side, algorithm))
            for i, name in enumerate(ids) for side in (256, 512) for algorithm in ('A', 'C2', 'C5')]


def validate_q4(root):
    root = Path(root).resolve()
    release = json.loads((root / 'q4_manifest.json').read_bytes())
    require(release['revision'] == 'q4_c5_experimental_r1' and release['board_status'] == 'NOT_RUN', 'Wrong Q4 release')
    browser = validate_package(root)
    expected = set(browser['artifacts']) | {'browser_manifest.json', 'q4_protocol.json', 'q4_board.py'}
    require(set(release['artifacts']) == expected, 'Q4 inventory changed')
    for name, info in release['artifacts'].items():
        require(file_info(root / name) == info, 'Q4 bytes changed: ' + name)
    protocol = json.loads((root / 'q4_protocol.json').read_bytes())
    plan = planned_requests(protocol)
    keys={f"{q['image_id']}_{q['side']}_{q['algorithm']}" for q in plan}
    require(set(protocol['expected_output_sha256'])==keys and all(len(v)==64 and set(v)<=set('0123456789abcdef') for v in protocol['expected_output_sha256'].values()), 'Incomplete fixed output hashes')
    require(set(browser['images']) == {q['image_id'] for q in plan}, 'Missing/extra quality images')
    require(all(set(sides) == {'256', '512'} and all(set(e['evaluation_only']) == {'AH', 'VK'} for e in sides.values())
                for sides in browser['images'].values()), 'Missing size or observer')
    require(browser['candidate'] == protocol['candidate']['id'], 'Fixed experimental candidate changed')
    return release, protocol


def prepare_q4(root, port=8090):
    root = Path(root).resolve()
    release, protocol = validate_q4(root)
    require(Path(__file__).resolve() == root / 'q4_board.py', 'Stale Q4 helper: use fresh kernel/package')
    require(shutil.disk_usage(root).free >= 1024 * 1024 * 1024, 'Need 1 GiB free SD space for evidence/export')
    context = prepare(root, port)
    context.update(q4_release=release, q4_protocol=protocol)
    print('Q4_PRECHECK_PASS: 20 images, two sizes, A/C2/C5 frozen; FPGA unchanged', flush=True)
    return context


async def collect_q4(context, timeout_seconds=60):
    manager = context['manager']
    require(manager is not None and not manager.jobs and not manager.exporting and
            not manager.error and manager.hardware.state == 'IDLE' and not manager.closed,
            'Q4 requires a fresh idle session; do not submit manual tasks before the batch')
    path = manager.directory / 'q4_collection.json'
    require(not path.exists(), 'Collect once; preserve any previous attempt')
    plan = planned_requests(context['q4_protocol'])
    journal = dict(protocol='Q4_FULL_DATASET_REAL_PL_R1', session_id=manager.session_id,
                   evidence_kind=manager.hardware.evidence_kind, status='COLLECTING',
                   protocol_file=file_info(context['root'] / 'q4_protocol.json'),
                   run_ids=[], started_ns=time.perf_counter_ns(), board_quality_pass=False,
                   note='Collection only. Independent full-word/quality verification after download; no browser FPS from batch.')
    write_json(path, journal)
    # The existing Manager exclusive snapshot gate blocks public submissions,
    # exports and finish. Temporarily release only for synchronous internal submit;
    # no await occurs in that window, so HTTP callbacks cannot interleave.
    manager.exporting = True
    try:
        for index, body in enumerate(plan, 1):
            manager.exporting = False
            try:
                job = manager.submit(body)
            finally:
                manager.exporting = True
            journal['run_ids'].append(job['run_id'])
            write_json(path, journal)  # preserve accepted ID before waiting
            deadline = time.monotonic() + timeout_seconds
            while manager.active is not None or manager.queue:
                if time.monotonic() >= deadline:
                    raise TimeoutError('No completed Q4 frame within 60 seconds; preserve live kernel/buffers')
                await asyncio.sleep(0.1)
            record = manager.get(job['run_id'])
            require(record['status'] == 'COMPLETED' and not manager.error and
                    record['request'] == manager.inputs.request(body), 'Q4 frame failed or request changed')
            require(len(manager.jobs) == index and manager.hardware.sequence == index, 'Unexpected extra native frame')
            expected_key = '%s_%s_%s' % (body['image_id'], body['side'], body['algorithm'])
            require(record['output']['sha256'] == context['q4_protocol']['expected_output_sha256'][expected_key],
                    'Actual PL words differ from fixed independent reference: ' + expected_key)
            journal['completed'] = index
            write_json(path, journal)
            print('Q4_FRAME_SAVED: %d/120 %s %d %s' % (index, body['image_id'], body['side'], body['algorithm']), flush=True)
        require(manager.hardware.state == 'IDLE' and not manager.hardware.retained, 'Not safely idle after collection')
        journal.update(status='PIXELS_MATCHED_QUALITY_REVIEW_PENDING', finished_ns=time.perf_counter_ns())
        write_json(path, journal)
        print('Q4_COLLECTION_COMPLETE: 120 real-request records saved; all 120 output SHA matched; visual/quality acceptance pending download audit', flush=True)
        return {'completed': 120, 'session_id': manager.session_id, 'quality_pass': False}
    except BaseException as exc:
        journal.update(status='FAILED_OR_INTERRUPTED', error=type(exc).__name__ + ': ' + str(exc),
                       hardware_state=manager.hardware.state, retained=len(manager.hardware.retained))
        write_json(path, journal)
        if manager.error is None:
            manager.error = {'type': type(exc).__name__, 'message': str(exc), 'recovery': 'Preserve kernel, pending work and all buffers; no retry/reload.'}
        raise
    finally:
        manager.exporting = False


async def export_q4(context, destination):
    manager = context['manager']
    path = manager.directory / 'q4_collection.json'
    journal = json.loads(path.read_bytes())
    require(journal['status'] == 'PIXELS_MATCHED_QUALITY_REVIEW_PENDING' and
            journal['completed'] == len(journal['run_ids']) == 120, 'Batch incomplete; preserve records')
    exported = Path(await export_session(context))
    destination = Path(destination)
    require(not destination.exists(), 'Export once to a new file')
    manager.exporting = True
    def copy_bundle():
        shutil.copyfile(exported, destination)
        with zipfile.ZipFile(destination, 'a', compression=zipfile.ZIP_DEFLATED) as z:
            z.write(path, 'q4_collection.json')
            for name in ('q4_manifest.json', 'q4_protocol.json'):
                z.write(context['root'] / name, name)
        return file_info(destination)
    try:
        info = await asyncio.get_running_loop().run_in_executor(manager.executor, copy_bundle)
    finally:
        manager.exporting = False
    print('Q4_RESULTS_READY:', destination, info, flush=True)
    return info
