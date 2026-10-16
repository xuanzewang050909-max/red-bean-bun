"""Read completed DMA output once into ordinary CPU storage, retaining all checks.

No official allocation/cache/wait/VDMA code is changed. The CPU copy is measured,
and each group still checks every output word, bytes, counters and output hash.
"""
import hashlib
import json
import sys
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import b_layout_board_test as l

b, p = l.b, l.p
REVISION = 'b_snapshot_r1_one_cpu_copy_after_official_receive_wait'
NOTEBOOK = 'b_snapshot_compare.ipynb'
GUIDE = '输出暂存对比说明.txt'
INHERITED = l.ARTIFACTS | {'b_layout_manifest.json'}
FIXED = (INHERITED - {b.NOTEBOOK, l.NOTEBOOK}) | {'b_snapshot_board_test.py', GUIDE}
ARTIFACTS = FIXED | {b.NOTEBOOK, l.NOTEBOOK, NOTEBOOK}
GROUPS = ('direct', 'snapshot')
STAGES = ('dma_transfer', 'cpu_snapshot', *p.STAGES[1:])
COUNT, WARMUP = 30, 3
CONTRACT = {'side': 512, 'mode': 3, 'pattern': 'stare', 'groups': list(GROUPS),
            'timed_frames_per_group': COUNT, 'warmup_frames_per_group': WARMUP,
            'stages': list(STAGES), 'clock': 'perf_counter_ns', 'overlay_downloads': 1,
            'algorithm_frames': 68, 'renderer': l.REVISION, 'group_order': 'direct_then_snapshot',
            'snapshot': 'one_np_copyto_after_official_recv_wait_into_readonly_between_captures_cpu_array',
            'comparison': 'full_packed_words_bytes_counters_hash_and_native_video_in_both_groups'}
OUTPUTS = ('b_snapshot_result.json', 'b_snapshot_dma_512.npy', 'b_snapshot_cpu_512.npy',
           'b_snapshot_direct_final_512.npy', 'b_snapshot_snapshot_final_512.npy', 'b_color_pattern.png',
           'b_snapshot_reference.png', 'b_snapshot_cpu.png', 'b_snapshot_direct_final.png', 'b_snapshot_snapshot_final.png')


class CpuSnapshot:
    """Reusable ordinary CPU array; caller must complete native DMA waits first.

    Returned data is borrowed until the next capture and is read-only between
    captures. It is never a PynqBuffer or a native video/algorithm buffer cache.
    """
    def __init__(self):
        self.words = np.empty((262144,), dtype=np.uint32)
        self.words.setflags(write=False)
        self.captures = 0

    def capture(self, received):
        b.require(received.dtype == np.uint32 and received.shape == (262144,) and received.strides == (4,),
                  'Expected completed contiguous 512 DMA words')
        b.require(type(self.words) is np.ndarray and self.words.dtype == np.uint32 and self.words.shape == (262144,) and
                  self.words.strides == (4,) and self.words.flags.owndata and self.words.flags.c_contiguous and
                  not self.words.flags.writeable and not np.shares_memory(received, self.words), 'Invalid ordinary CPU snapshot ownership')
        self.words.setflags(write=True)
        try:
            np.copyto(self.words, np.asarray(received), casting='no')
        finally:
            self.words.setflags(write=False)
        self.captures += 1
        return self.words

    def description(self):
        return {'shape': list(self.words.shape), 'strides': list(self.words.strides), 'dtype': str(self.words.dtype),
                'nbytes': int(self.words.nbytes), 'owndata': bool(self.words.flags.owndata),
                'readonly_between_captures': not self.words.flags.writeable,
                'has_physical_address': hasattr(self.words, 'physical_address')}


def validate_package(directory, manifest):
    directory = Path(directory)
    b.require(manifest.get('revision') == REVISION and manifest.get('contract') == CONTRACT and
              manifest.get('board_status') == 'NOT_RUN', 'Wrong snapshot release/contract')
    b.require(set(manifest.get('artifacts', {})) == ARTIFACTS, 'Incomplete snapshot package')
    for name in sorted(FIXED):
        b.require(b.sha256_file(directory / name) == manifest['artifacts'][name]['sha256'], 'Snapshot package mismatch: ' + name)
    code_hash = b.notebook_code_hash(json.loads((directory / NOTEBOOK).read_text(encoding='utf-8')))
    b.require(manifest.get('notebook_validation') == {'algorithm': 'sha256-code-cells-v1', 'sha256': code_hash},
              'Snapshot notebook code mismatch')
    baseline = json.loads((directory / 'b_layout_manifest.json').read_text(encoding='utf-8'))
    return {'fixed_artifacts': 'PASS_EXACT_SHA256_EXCLUDING_THREE_NOTEBOOK_JSONS',
            'notebook_code_sha256': code_hash, 'current_notebook_sha256': b.sha256_file(directory / NOTEBOOK),
            'baseline': l.validate_package(directory, baseline)}


def prepare_snapshot(directory, retained):
    directory = Path(directory).resolve()
    for name in OUTPUTS + ('b_snapshot_bundle.zip',):
        b.require(not (directory / name).exists(), 'Use new folder; preserve result: ' + name)
    manifest = json.loads((directory / 'b_snapshot_manifest.json').read_text(encoding='utf-8'))
    validation = validate_package(directory, manifest)
    for name in sorted(n for n in FIXED if n.endswith('.py')):
        b.require(b.sha256_file(sys.modules[Path(name).stem].__file__) == manifest['artifacts'][name]['sha256'],
                  'Imported module mismatch: ' + name)
    context = l.prepare_layout(directory, retained)  # Proven metadata/font geometry gate; FPGA unchanged.
    original_save = context['save']
    context['report'].update(snapshot_manifest=manifest, snapshot_package_validation=validation,
        snapshot_compare={'contract': CONTRACT, 'groups': [], 'clock': context['report']['layout']['clock'],
            'scope': 'Same cached renderer, direct DMA reads versus one ordinary CPU copy; full word/hash/native display costs retained. '
                     'No kernel mapping inference, SD/PL-only/CPU-algorithm/scan-Hz/clinical acceptance.'})

    def save():
        original_save()
        path = directory / 'b_snapshot_result.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(context['report'], indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    context['save'] = save

    def action():
        context['cpu_snapshot'] = CpuSnapshot()
        context['report']['snapshot_compare']['cpu_storage'] = context['cpu_snapshot'].description()
        context['report']['status'] = 'B_PRECHECK_FPGA_UNCHANGED'
        save()

    b.phase(context, 'B_SNAPSHOT_PREPARING_ORDINARY_CPU_ARRAY_FPGA_UNCHANGED', action)
    print('B_SNAPSHOT_PRECHECK_PASS: immutable sources, geometry and ordinary CPU storage; FPGA unchanged', flush=True)
    return context


def load_snapshot(context):
    b.load_b(context)
    print('B_SNAPSHOT_LOAD_PASS: original B loaded once', flush=True)


def start_snapshot(context):
    b.require(context['report']['status'] == 'B_LOADED_NO_TRANSFER', 'Load once before short frame/HDMI')
    b.smoke_b(context)
    b.start_hdmi_b(context)
    print('B_SNAPSHOT_HDMI_READY: original color pattern submitted', flush=True)


def allocate_pair(context, source, expected):
    context['gpio'].channel1.write(3, 0xffffffff)
    tx = context['allocate'](shape=(262144,), dtype=np.uint32)
    context['retained'].append(tx)
    rx = context['allocate'](shape=(262144,), dtype=np.uint32)
    context['retained'].append(rx)
    for buffer in (tx, rx):
        b.require(buffer.dtype == np.uint32 and buffer.shape == (262144,) and buffer.strides == (4,) and
                  buffer.physical_address % 8 == 0 and 0x100000 <= buffer.physical_address <= 0x20000000 - 1048576,
                  'Invalid original algorithm allocation')
    b.require(abs(tx.physical_address - rx.physical_address) >= 1048576, 'Algorithm buffers overlap')
    tx[:] = source.reshape(-1)
    rx[:] = np.bitwise_not(expected.reshape(-1))
    rx.flush()
    return tx, rx


def release_pair(context, tx, rx):
    rx.freebuffer()
    b.require(context['retained'].pop() is rx, 'Receive ownership ledger changed')
    tx.freebuffer()
    b.require(context['retained'].pop() is tx, 'Send ownership ledger changed')


def check_snapshot(context):
    b.require(context['report']['status'] == 'B_COLOR_SUBMITTED', 'Start HDMI before snapshot gate')

    def action():
        b.assert_loaded(context)
        source = b.make_pattern(512, 'stare', 0, context['directory'])
        expected = b.segmentation_expected(source, 3).reshape(-1)
        tx, rx = allocate_pair(context, source, expected)
        context['dma'].recvchannel.transfer(rx)
        context['dma'].sendchannel.transfer(tx)
        dma_status = b.wait_both_idle(context['dma'])
        context['dma'].sendchannel.wait()
        context['dma'].recvchannel.wait()  # Original driver invalidates receive memory before CPU access.
        snapshot = context['cpu_snapshot'].capture(rx)
        b.require(np.array_equal(rx, snapshot) and np.array_equal(snapshot, expected), 'Actual DMA/CPU snapshot words differ')
        send_bytes, recv_bytes = int(context['dma'].sendchannel.transferred), int(context['dma'].recvchannel.transferred)
        frame_status = int(context['gpio'].channel2.read())
        b.require(send_bytes == recv_bytes == 1048576 and frame_status == (2 | 2 << 14), 'Snapshot gate bytes/counter differ')
        direct_hash = hashlib.sha256(np.asarray(rx).tobytes()).hexdigest()
        cpu_hash = hashlib.sha256(snapshot.tobytes()).hexdigest()
        b.require(direct_hash == cpu_hash, 'Snapshot gate hashes differ')
        files = {}
        for name, data in (('b_snapshot_dma_512.npy', np.asarray(rx)), ('b_snapshot_cpu_512.npy', snapshot)):
            path = context['directory'] / name
            np.save(path, data.reshape(512, 512), allow_pickle=False)
            files[name] = {'sha256': b.sha256_file(path), 'word_sha256': cpu_hash}
        from PIL import Image
        checks = []
        for marker in (0, 29, 99, 100):
            direct = context['cached_canvas'].render(np.asarray(rx).reshape(512, 512), marker).copy()
            copied = context['cached_canvas'].render(snapshot.reshape(512, 512), marker)
            b.require(np.array_equal(direct, copied), 'DMA/CPU snapshot entire canvas differs')
            checks.append({'marker': marker, 'sha256_bgr': hashlib.sha256(copied.tobytes()).hexdigest(),
                           'matched_pixels': 921600, 'matched_bytes': 2764800})
            if marker == 0:
                Image.fromarray(direct[:, :, ::-1]).save(context['directory'] / 'b_snapshot_reference.png')
                Image.fromarray(copied[:, :, ::-1]).save(context['directory'] / 'b_snapshot_cpu.png')
                b.submit(context, copied, 'DMA_CPU_SNAPSHOT_PIXEL_GATE')
        snapshot_report = context['report']['snapshot_compare']
        snapshot_report['actual_gate'] = {'input_sha256': hashlib.sha256(source.tobytes()).hexdigest(),
            'output_sha256': cpu_hash, 'raw_files': files, 'matched_words': 262144, 'mismatched_words': 0,
            'pixel_checks': checks, 'cpu_storage': context['cpu_snapshot'].description(), 'captures': context['cpu_snapshot'].captures}
        context['report']['transfers'].append({'side': 512, 'mode': 3, 'pattern': 'stare', 'words': 262144,
            'send_bytes': send_bytes, 'recv_bytes': recv_bytes, 'tx_address': int(tx.physical_address),
            'rx_address': int(rx.physical_address), 'dma_status': dma_status, 'frame_status': frame_status,
            'input_sha256': snapshot_report['actual_gate']['input_sha256'], 'expected_sha256': cpu_hash,
            'output_sha256': cpu_hash, 'status': 'PASS_EXACT_SEGMENTATION_WORDS'})
        release_pair(context, tx, rx)
        context['report']['status'] = 'B_SNAPSHOT_ACTUAL_GATE_PASS'
        context['save']()
        print('B_SNAPSHOT_PIXELS_PASS: actual 262144 DMA/CPU words and four entire canvases identical', flush=True)

    b.phase(context, 'B_SNAPSHOT_CHECKING_ACTUAL_DMA_CPU_COPY', action)


def stage_durations(boundaries):
    b.require(len(boundaries) == len(STAGES) + 1 and all(type(value) is int and value >= 0 for value in boundaries),
              'Invalid snapshot stage timestamps')
    differences = [end - start for start, end in zip(boundaries, boundaries[1:])]
    b.require(all(value >= 0 for value in differences) and differences[0] > 0 and boundaries[-1] > boundaries[0],
              'Snapshot clock reversed or DMA clock did not advance')
    return dict(zip(STAGES, differences))


def summarize(samples, loop_start, loop_end):
    b.require(len(samples) == WARMUP + COUNT, 'Incomplete snapshot sample ledger')
    previous_end = None
    for index, row in enumerate(samples):
        b.require(row['index'] == index and row['warmup'] == (index < WARMUP), 'Invalid warmup/sample order')
        durations = stage_durations(row['boundaries_ns'])
        b.require(row['durations_ns'] == durations and row['sample_ns'] == sum(durations.values()), 'Stage sum does not reconcile')
        b.require(previous_end is None or row['boundaries_ns'][0] >= previous_end, 'Overlapping frame timestamps')
        previous_end = row['boundaries_ns'][-1]
    timed = samples[WARMUP:]
    b.require(type(loop_start) is int and type(loop_end) is int and loop_start == timed[0]['boundaries_ns'][0] and
              loop_end >= previous_end, 'Invalid complete-loop timestamps')
    total_ns = sum(row['sample_ns'] for row in timed)
    loop_ns = loop_end - loop_start
    b.require(loop_ns >= total_ns > 0, 'Loop/sample durations do not reconcile')
    stages = {}
    for name in STAGES:
        values = np.asarray([row['durations_ns'][name] for row in timed], dtype=np.float64)
        summed = sum(row['durations_ns'][name] for row in timed)
        stages[name] = {'sum_ns': summed, 'mean_ms': float(values.mean() / 1e6), 'median_ms': float(np.median(values) / 1e6),
                        'p95_ms': float(np.percentile(values, 95) / 1e6), 'share_of_sample_time_percent': 100 * summed / total_ns}
    b.require(sum(stage['sum_ns'] for stage in stages.values()) == total_ns, 'Attributed total mismatch')
    result = b.timing_summary([row['sample_ns'] for row in timed])
    result.update(stages=stages, loop_start_ns=loop_start, loop_end_ns=loop_end, loop_ns=loop_ns,
                  loop_seconds=loop_ns / 1e9, loop_fps=COUNT * 1e9 / loop_ns, sample_sum_ns=total_ns,
                  loop_unattributed_ns=loop_ns - total_ns,
                  loop_includes='DMA/cache/wait, selected source/CPU copy, full words/counters, same cached layout, '
                                'native allocation/copy/flush/IRQ submission, video status, output hash, record/progress',
                  loop_excludes='Input/reference/initial allocations, prefix gate, warmup, final PNG/NPY/JSON/ZIP writes and close')
    return result


def measure_group(context, expected, tx, rx, name):
    group_index = GROUPS.index(name)
    group = {'name': name, 'samples': []}
    report = context['report']['snapshot_compare']
    report['groups'].append(group)
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
        context['dma'].recvchannel.wait()
        boundaries.append(time.perf_counter_ns())
        data = context['cpu_snapshot'].capture(rx) if name == 'snapshot' else np.asarray(rx)
        boundaries.append(time.perf_counter_ns())
        b.require(np.array_equal(data, expected), 'Snapshot benchmark FPGA words differ')
        boundaries.append(time.perf_counter_ns())
        send_bytes, recv_bytes = int(context['dma'].sendchannel.transferred), int(context['dma'].recvchannel.transferred)
        count = 3 + group_index * 33 + index
        frame_status = int(context['gpio'].channel2.read())
        b.require(send_bytes == recv_bytes == 1048576 and frame_status == (count | count << 14), 'Snapshot benchmark bytes/counter differ')
        boundaries.append(time.perf_counter_ns())
        image = context['cached_canvas'].render(data.reshape(512, 512), index - WARMUP)
        boundaries.append(time.perf_counter_ns())
        frame = context['hdmi_out'].newframe()
        context['display_retained'].append(frame)
        b.require(frame.shape == (720, 1280, 3) and frame.dtype == np.uint8 and frame.strides == (3840, 3, 1), 'Wrong native display frame')
        b.require(frame.physical_address % 8 == 0 and 0x100000 <= frame.physical_address <= 0x20000000 - frame.nbytes,
                  'Invalid native video DDR frame')
        description = p.buffer_info(frame)
        boundaries.append(time.perf_counter_ns())
        frame[:] = image
        boundaries.append(time.perf_counter_ns())
        context['hdmi_out'].writeframe(frame)
        b.require(context['display_retained'].pop() is frame, 'Display ownership ledger changed')
        boundaries.append(time.perf_counter_ns())
        vdma_status = b.video_status(context)
        boundaries.append(time.perf_counter_ns())
        output_hash = hashlib.sha256(data.tobytes()).hexdigest()
        b.require(output_hash == report['expected_sha256'], 'Snapshot benchmark output hash differs')
        boundaries.append(time.perf_counter_ns())
        row = {'index': index, 'warmup': index < WARMUP, 'frame_count': count, 'frame_status': frame_status,
               'words': 262144, 'send_bytes': send_bytes, 'recv_bytes': recv_bytes, 'dma_status': dma_status,
               'vdma_status': vdma_status, 'display_buffer': description, 'output_sha256': output_hash,
               'cpu_copy_performed': name == 'snapshot', 'status': 'PASS_EXACT_SEGMENTATION_WORDS'}
        group['samples'].append(row)
        if index >= WARMUP and (index - WARMUP + 1) % 5 == 0:
            print('B_SNAPSHOT_PROGRESS: {} {}/30'.format(name, index - WARMUP + 1), flush=True)
        boundaries.append(time.perf_counter_ns())
        row.update(boundaries_ns=boundaries, durations_ns=stage_durations(boundaries), sample_ns=boundaries[-1] - boundaries[0])
    loop_end = time.perf_counter_ns()
    group['summary'] = summarize(group['samples'], loop_start, loop_end)
    raw_path = context['directory'] / ('b_snapshot_' + name + '_final_512.npy')
    np.save(raw_path, data.reshape(512, 512), allow_pickle=False)
    from PIL import Image
    image_path = context['directory'] / ('b_snapshot_' + name + '_final.png')
    Image.fromarray(image[:, :, ::-1]).save(image_path)
    group.update(final_output={'name': raw_path.name, 'sha256': b.sha256_file(raw_path), 'word_sha256': output_hash},
                 final_display={'name': image_path.name, 'sha256': b.sha256_file(image_path),
                                'sha256_bgr': hashlib.sha256(image.tobytes()).hexdigest(), 'marker_index': COUNT - 1})
    context['save']()
    print('B_SNAPSHOT_GROUP_COMPLETE: {} copy={:.3f} ms, layout={:.3f} ms, checked_loop={:.3f} FPS'.format(
        name, group['summary']['stages']['cpu_snapshot']['mean_ms'], group['summary']['stages']['ps_layout']['mean_ms'],
        group['summary']['loop_fps']), flush=True)


def compare_snapshot(context):
    b.require(context['report']['status'] == 'B_SNAPSHOT_ACTUAL_GATE_PASS', 'Pass actual DMA/CPU pixel gate before timing')

    def action():
        b.assert_loaded(context)
        b.video_status(context)
        report = context['report']['snapshot_compare']
        b.require(not report['groups'] and len(context['report']['transfers']) == 2 and context['cpu_snapshot'].captures == 1,
                  'Run snapshot comparison once')
        source = b.make_pattern(512, 'stare', 0, context['directory'])
        expected = b.segmentation_expected(source, 3).reshape(-1)
        tx, rx = allocate_pair(context, source, expected)
        report.update(input_sha256=hashlib.sha256(source.tobytes()).hexdigest(),
                      expected_sha256=hashlib.sha256(expected.tobytes()).hexdigest(),
                      algorithm_buffers={'tx': p.buffer_info(tx), 'rx': p.buffer_info(rx)},
                      native_video_cacheable_frames=bool(context['video'].axi_vdma.writechannel.cacheable_frames))
        for name in GROUPS:
            measure_group(context, expected, tx, rx, name)
        b.assert_loaded(context)
        before, after = report['groups']
        b.require([group['name'] for group in report['groups']] == list(GROUPS) and
                  all(len(group['samples']) == 33 for group in report['groups']) and
                  int(context['gpio'].channel2.read()) == (68 | 68 << 14) and
                  before['final_output']['word_sha256'] == after['final_output']['word_sha256'] == report['expected_sha256'] and
                  before['final_display']['sha256_bgr'] == after['final_display']['sha256_bgr'] and
                  context['cpu_snapshot'].captures == 34, 'Paired output/display/copy count differs')
        report['comparison'] = {'direct_checked_loop_fps': before['summary']['loop_fps'],
            'snapshot_checked_loop_fps': after['summary']['loop_fps'],
            'loop_ratio_snapshot_over_direct': after['summary']['loop_fps'] / before['summary']['loop_fps'],
            'direct_layout_mean_ms': before['summary']['stages']['ps_layout']['mean_ms'],
            'snapshot_layout_mean_ms': after['summary']['stages']['ps_layout']['mean_ms'],
            'snapshot_copy_mean_ms': after['summary']['stages']['cpu_snapshot']['mean_ms'],
            'scope': 'Measured full verification workload including CPU copy; no new performance acceptance without independent review.'}
        release_pair(context, tx, rx)
        report.update(total_algorithm_frames=68, total_cpu_captures=context['cpu_snapshot'].captures,
                      cpu_storage_after=context['cpu_snapshot'].description())
        context['report']['status'] = 'B_SNAPSHOT_MEASURED'
        context['save']()
        print('B_SNAPSHOT_COMPARE_COMPLETE: direct and ordinary CPU copy groups recorded; independent verification pending', flush=True)

    b.phase(context, 'B_SNAPSHOT_COMPARING', action)


def finish_snapshot(context):
    b.require(context['report']['status'] == 'B_SNAPSHOT_MEASURED', 'Complete both groups before closing/packaging')
    bundle = context['directory'] / 'b_snapshot_bundle.zip'
    b.require(not bundle.exists(), 'Preserve earlier snapshot bundle')

    def action():
        b.assert_loaded(context)
        context['report']['display']['final_vdma_status'] = b.video_status(context)
        context['hdmi_out'].close()
        context['report']['display']['closed'] = True
        context['report']['status'] = 'B_SNAPSHOT_RECORDS_READY_VISUAL_PENDING'
        context['save']()
        with ZipFile(bundle, 'w', ZIP_DEFLATED) as archive:
            for name in OUTPUTS:
                archive.write(context['directory'] / name, arcname=name)
        print('B_SNAPSHOT_RESULTS_READY: download b_snapshot_bundle.zip and executed b_snapshot_compare.ipynb', flush=True)

    b.phase(context, 'B_SNAPSHOT_CLOSING_AND_PACKAGING', action)
