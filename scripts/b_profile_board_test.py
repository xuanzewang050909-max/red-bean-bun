"""Attribute the proven B path using official drivers and original PS layout.

This adds measurement only. It does not optimize the algorithm, layout, cache,
polling, or video driver. A writeframe interval includes native flush/IRQ wait.
"""
import hashlib
import json
import sys
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import b_integration_board_test as b

REVISION = 'b_profile_r2_inherited_notebook_code_check'
NOTEBOOK = 'b_performance_profile.ipynb'
GUIDE = '分段计时说明.txt'
INHERITED = b.FIXED | {b.NOTEBOOK, 'b_manifest.json'}
FIXED = (INHERITED - {b.NOTEBOOK}) | {'b_profile_board_test.py', GUIDE}
ARTIFACTS = FIXED | {b.NOTEBOOK, NOTEBOOK}
COUNT, WARMUP, SIDE = 30, 3, 512
STAGES = ('dma_transfer', 'word_compare', 'algorithm_status', 'ps_layout',
          'frame_allocate', 'frame_copy', 'display_submit', 'video_status',
          'output_hash', 'record_and_progress')
CONTRACT = {'side': SIDE, 'mode': 3, 'pattern': 'stare', 'timed_frames': COUNT,
            'warmup_frames': WARMUP, 'stages': list(STAGES),
            'clock': 'perf_counter_ns', 'layout': 'unchanged_b_r2_medical_canvas',
            'driver': 'unchanged_official_pynq_3.0.1', 'overlay_downloads': 1}
OUTPUTS = ('b_profile_result.json', 'b_profile_output_512.npy',
           'b_profile_display.png', 'b_color_pattern.png')


def validate_profile_package(directory, manifest):
    directory = Path(directory)
    b.require(manifest.get('revision') == REVISION and manifest.get('contract') == CONTRACT,
              'Wrong profiling release or measurement contract')
    b.require(manifest.get('board_status') == 'NOT_RUN', 'Use original profiling release manifest')
    b.require(set(manifest.get('artifacts', {})) == ARTIFACTS, 'Incomplete profiling package')
    for name in sorted(FIXED):
        b.require(b.sha256_file(directory / name) == manifest['artifacts'][name]['sha256'],
                  'Profiling package mismatch: ' + name)
    code_hash = b.notebook_code_hash(json.loads((directory / NOTEBOOK).read_text(encoding='utf-8')))
    b.require(manifest.get('notebook_validation') == {
        'algorithm': 'sha256-code-cells-v1', 'sha256': code_hash}, 'Profiling notebook code mismatch')
    original = json.loads((directory / 'b_manifest.json').read_text(encoding='utf-8'))
    baseline = b.validate_b_package(directory, original)
    # The inherited notebook uses the already-proven B code-cell contract.
    # Both notebook JSONs may change on save; neither can change executable code.
    return {'fixed_artifacts': 'PASS_EXACT_SHA256_EXCLUDING_NOTEBOOK_JSON', 'notebook_code_sha256': code_hash,
            'mutable_notebook_json': [b.NOTEBOOK, NOTEBOOK],
            'current_notebook_sha256': b.sha256_file(directory / NOTEBOOK), 'baseline': baseline}


def prepare_profile(directory, retained):
    directory = Path(directory).resolve()
    for name in OUTPUTS + ('b_profile_bundle.zip', 'b_integration_result.json'):
        b.require(not (directory / name).exists(), 'Use a new profiling folder; preserve earlier result: ' + name)
    manifest = json.loads((directory / 'b_profile_manifest.json').read_text(encoding='utf-8'))
    validation = validate_profile_package(directory, manifest)
    # Also reject a stale imported script from a different release/kernel.
    for name in sorted(n for n in FIXED if n.endswith('.py')):
        module = sys.modules[Path(name).stem]
        b.require(b.sha256_file(module.__file__) == manifest['artifacts'][name]['sha256'],
                  'Imported module mismatch; use the new notebook kernel: ' + name)
    clock = time.get_clock_info('perf_counter')
    b.require(clock.monotonic and clock.resolution <= 1e-6, 'Need a monotonic high-resolution perf_counter')
    context = b.prepare_b(directory, retained)  # Existing metadata gate, no download/allocation.
    original_save = context['save']
    context['report'].update(profile_manifest=manifest, profile_package_validation=validation,
        profile={'contract': CONTRACT, 'samples': [], 'clock': {
            'name': 'perf_counter_ns', 'monotonic': clock.monotonic,
            'resolution_seconds': clock.resolution, 'implementation': clock.implementation},
            'scope': 'Repeated fixed STARE input; full packed-word verification and original PS layout. '
                     'No SD input latency, pure PL cycles, calibrated scan rate, optimization, or clinical quality claim.'})

    def save():
        original_save()
        path = directory / 'b_profile_result.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(context['report'], indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    context['save'] = save
    save()
    print('B_PROFILE_PRECHECK_PASS: fixed r2 hardware/drivers/inputs; FPGA unchanged', flush=True)
    return context


def load_profile(context):
    b.load_b(context)
    print('B_PROFILE_LOAD_PASS: original B loaded once; no profiling transfer yet', flush=True)


def start_profile(context):
    b.require(context['report']['status'] == 'B_LOADED_NO_TRANSFER', 'Load once before HDMI preparation')
    b.smoke_b(context)
    b.start_hdmi_b(context)
    print('B_PROFILE_HDMI_READY: original color pattern submitted; next cell measures 512 frames', flush=True)


def buffer_info(buffer):
    # Public PynqBuffer properties; observe, never change caching policy.
    return {'physical_address': int(buffer.physical_address), 'nbytes': int(buffer.nbytes),
            'shape': list(buffer.shape), 'strides': list(buffer.strides), 'dtype': str(buffer.dtype),
            'cacheable': bool(buffer.cacheable) if hasattr(buffer, 'cacheable') else None,
            'coherent': bool(buffer.coherent) if hasattr(buffer, 'coherent') else None}


def stage_durations(boundaries):
    b.require(len(boundaries) == len(STAGES) + 1 and
              all(type(value) is int and value >= 0 for value in boundaries), 'Invalid stage timestamps')
    differences = [end - start for start, end in zip(boundaries, boundaries[1:])]
    b.require(all(value >= 0 for value in differences) and differences[0] > 0 and
              boundaries[-1] > boundaries[0], 'Stage clock went backwards or DMA clock did not advance')
    return dict(zip(STAGES, differences))


def summarize(samples, loop_start, loop_end):
    b.require(len(samples) == WARMUP + COUNT, 'Incomplete profiling sample ledger')
    previous_end = None
    for index, row in enumerate(samples):
        b.require(row['index'] == index and row['warmup'] == (index < WARMUP), 'Invalid warmup/sample order')
        durations = stage_durations(row['boundaries_ns'])
        b.require(row['durations_ns'] == durations, 'Stage durations disagree with raw timestamps')
        b.require(row['sample_ns'] == sum(durations.values()), 'Stage sum does not reconcile')
        if previous_end is not None:
            b.require(row['boundaries_ns'][0] >= previous_end, 'Overlapping frame timestamps')
        previous_end = row['boundaries_ns'][-1]
    timed = samples[WARMUP:]
    b.require(type(loop_start) is int and type(loop_end) is int and
              loop_start == timed[0]['boundaries_ns'][0] and loop_end >= previous_end,
              'Invalid complete-loop timestamps')
    total_ns = sum(row['sample_ns'] for row in timed)
    loop_ns = loop_end - loop_start
    b.require(loop_ns >= total_ns > 0, 'Loop/sample durations do not reconcile')
    stages = {}
    for name in STAGES:
        values = np.asarray([row['durations_ns'][name] for row in timed], dtype=np.float64)
        summed = sum(row['durations_ns'][name] for row in timed)
        stages[name] = {'sum_ns': summed, 'mean_ms': float(values.mean() / 1e6),
                        'median_ms': float(np.median(values) / 1e6),
                        'p95_ms': float(np.percentile(values, 95) / 1e6),
                        'share_of_sample_time_percent': 100 * summed / total_ns}
    b.require(sum(stage['sum_ns'] for stage in stages.values()) == total_ns, 'Total attribution mismatch')
    result = b.timing_summary([row['sample_ns'] for row in timed])
    result.update(stages=stages, loop_start_ns=loop_start, loop_end_ns=loop_end,
        loop_ns=loop_ns, loop_seconds=loop_ns / 1e9, loop_fps=COUNT * 1e9 / loop_ns,
        sample_sum_ns=total_ns, loop_unattributed_ns=loop_ns - total_ns,
        loop_unattributed_scope='Timing-ledger assignment and inter-frame bookkeeping outside measured stages',
        loop_includes='DMA/cache/wait, full word compare, counters/status, original layout, native allocation, '
                      'copy, original writeframe, output hash, record building, timing overhead, progress printing',
        loop_excludes='Input loading, golden generation, initial algorithm allocation/fill/flush, warmup, '
                      'final PNG/NPY/JSON/ZIP writes, final display close')
    return result


def profile_frames(context):
    b.require(context['report']['status'] == 'B_COLOR_SUBMITTED', 'Complete HDMI preparation once before profiling')

    def action():
        b.assert_loaded(context)
        b.video_status(context)
        profile = context['report']['profile']
        b.require(not profile['samples'] and len(context['report']['transfers']) == 1,
                  'Run this measurement once; do not repeat the old B suite')
        source = b.make_pattern(SIDE, 'stare', 0, context['directory'])
        expected = b.segmentation_expected(source, 3).reshape(-1)
        words, nbytes = SIDE * SIDE, SIDE * SIDE * 4
        context['gpio'].channel1.write(3, 0xffffffff)
        tx = context['allocate'](shape=(words,), dtype=np.uint32)
        context['retained'].append(tx)
        rx = context['allocate'](shape=(words,), dtype=np.uint32)
        context['retained'].append(rx)
        for buffer in (tx, rx):
            b.require(buffer.dtype == np.uint32 and buffer.shape == (words,) and buffer.strides == (4,) and
                      buffer.physical_address % 8 == 0 and
                      0x100000 <= buffer.physical_address <= 0x20000000 - nbytes,
                      'Invalid official algorithm allocation')
        b.require(abs(tx.physical_address - rx.physical_address) >= nbytes, 'Algorithm buffers overlap')
        profile['algorithm_buffers'] = {'tx': buffer_info(tx), 'rx': buffer_info(rx)}
        setting = getattr(context['video'].axi_vdma.writechannel, 'cacheable_frames', None)
        profile['native_video_cacheable_frames'] = bool(setting) if setting is not None else None
        profile['input_sha256'] = hashlib.sha256(source.tobytes()).hexdigest()
        profile['expected_sha256'] = hashlib.sha256(expected.tobytes()).hexdigest()
        tx[:] = source.reshape(-1)
        rx[:] = np.bitwise_not(expected)
        rx.flush()
        context['save']()
        loop_start = None
        for index in range(WARMUP + COUNT):
            boundaries = [time.perf_counter_ns()]
            if index == WARMUP:
                loop_start = boundaries[0]
            context['dma'].recvchannel.transfer(rx)
            context['dma'].sendchannel.transfer(tx)
            dma_status = b.wait_both_idle(context['dma'])
            context['dma'].sendchannel.wait()
            context['dma'].recvchannel.wait()  # Original driver invalidates receive memory.
            boundaries.append(time.perf_counter_ns())
            b.require(np.array_equal(rx, expected), 'Profile FPGA word mismatch')
            boundaries.append(time.perf_counter_ns())
            send_bytes = int(context['dma'].sendchannel.transferred)
            recv_bytes = int(context['dma'].recvchannel.transferred)
            b.require(send_bytes == recv_bytes == nbytes, 'Profile DMA byte count mismatch')
            frame_status = int(context['gpio'].channel2.read())
            expected_count = index + 2  # One existing 256 smoke frame, then this 512 sequence.
            b.require(frame_status == (expected_count | expected_count << 14), 'Profile frame counter/error mismatch')
            boundaries.append(time.perf_counter_ns())
            image = b.medical_canvas(np.asarray(rx).reshape(SIDE, SIDE), index - WARMUP)
            boundaries.append(time.perf_counter_ns())
            frame = context['hdmi_out'].newframe()
            context['display_retained'].append(frame)
            b.require(frame.shape == image.shape and frame.dtype == image.dtype and frame.strides == (3840, 3, 1),
                      'Wrong native display frame layout')
            b.require(frame.physical_address % 8 == 0 and
                      0x100000 <= frame.physical_address <= 0x20000000 - frame.nbytes, 'Invalid video DDR frame')
            display_buffer = buffer_info(frame)
            boundaries.append(time.perf_counter_ns())
            frame[:] = image
            boundaries.append(time.perf_counter_ns())
            context['hdmi_out'].writeframe(frame)  # Native flush and IRQ wait stay together.
            b.require(context['display_retained'].pop() is frame, 'Display ownership ledger changed')
            boundaries.append(time.perf_counter_ns())
            vdma_status = b.video_status(context)
            boundaries.append(time.perf_counter_ns())
            output_hash = hashlib.sha256(np.asarray(rx).tobytes()).hexdigest()
            boundaries.append(time.perf_counter_ns())
            row = {'index': index, 'warmup': index < WARMUP, 'words': words,
                   'send_bytes': send_bytes, 'recv_bytes': recv_bytes, 'frame_status': frame_status,
                   'dma_status': dma_status, 'vdma_status': vdma_status, 'display_buffer': display_buffer,
                   'output_sha256': output_hash, 'status': 'PASS_EXACT_SEGMENTATION_WORDS'}
            profile['samples'].append(row)
            if index >= WARMUP and (index - WARMUP + 1) % 5 == 0:
                print('B_PROFILE_PROGRESS: {}/{}'.format(index - WARMUP + 1, COUNT), flush=True)
            boundaries.append(time.perf_counter_ns())
            row.update(boundaries_ns=boundaries, durations_ns=stage_durations(boundaries),
                       sample_ns=boundaries[-1] - boundaries[0])
        loop_end = time.perf_counter_ns()  # Includes final timing-ledger bookkeeping.
        profile['summary'] = summarize(profile['samples'], loop_start, loop_end)
        b.assert_loaded(context)
        b.require(frame_status == (34 | 34 << 14), 'Wrong total diagnostic frame count')
        directory = context['directory']
        output_path = directory / 'b_profile_output_512.npy'
        np.save(output_path, np.asarray(rx).reshape(SIDE, SIDE), allow_pickle=False)
        from PIL import Image
        display_path = directory / 'b_profile_display.png'
        Image.fromarray(image[:, :, ::-1]).save(display_path)
        profile['final_output'] = {'name': output_path.name, 'sha256': b.sha256_file(output_path),
                                  'word_sha256': output_hash}
        profile['final_display'] = {'name': display_path.name, 'sha256': b.sha256_file(display_path),
                                   'sha256_bgr': hashlib.sha256(image.tobytes()).hexdigest(), 'marker_index': COUNT - 1}
        profile['total_algorithm_frames'] = 34
        # Only release algorithm buffers after completion and successful checks.
        rx.freebuffer()
        b.require(context['retained'].pop() is rx, 'Receive ownership ledger changed')
        tx.freebuffer()
        b.require(context['retained'].pop() is tx, 'Send ownership ledger changed')
        context['report']['status'] = 'B_PROFILE_TIMING_COMPLETE'
        context['save']()
        for name in STAGES:
            metric = profile['summary']['stages'][name]
            print('B_PROFILE_STAGE: {} mean={:.3f} ms, share={:.2f}%'.format(
                name, metric['mean_ms'], metric['share_of_sample_time_percent']), flush=True)
        print('B_PROFILE_COMPLETE: 30 timed + 3 warmup; checked loop {:.3f} FPS; no optimization claim'.format(
            profile['summary']['loop_fps']), flush=True)

    b.phase(context, 'B_PROFILE_RUNNING', action)


def finish_profile(context):
    b.require(context['report']['status'] == 'B_PROFILE_TIMING_COMPLETE', 'Complete profiling before close/package')
    directory = context['directory']
    bundle = directory / 'b_profile_bundle.zip'
    b.require(not bundle.exists(), 'Preserve earlier profiling bundle')

    def action():
        b.assert_loaded(context)
        context['report']['display']['final_vdma_status'] = b.video_status(context)
        context['hdmi_out'].close()
        context['report']['display']['closed'] = True
        context['report']['status'] = 'B_PROFILE_RECORDS_READY_VISUAL_PENDING'
        context['save']()
        with ZipFile(bundle, 'w', ZIP_DEFLATED) as archive:
            for name in OUTPUTS:
                archive.write(directory / name, arcname=name)
        print('B_PROFILE_RESULTS_READY: download b_profile_bundle.zip and executed profiling notebook', flush=True)

    b.phase(context, 'B_PROFILE_CLOSING_AND_PACKAGING', action)
