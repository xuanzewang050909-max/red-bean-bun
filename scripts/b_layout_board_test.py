"""Pixel-equivalent PS canvas reuse with unchanged official B hardware/drivers.

The renderer owns only ordinary NumPy scratch/canvas arrays. Native video
frames are still allocated and owned exclusively by the official VDMA driver.
"""
import hashlib
import json
import sys
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import b_integration_board_test as b
import b_profile_board_test as p

REVISION = 'b_layout_r1_cached_titles_and_numpy_canvas'
NOTEBOOK = 'b_layout_compare.ipynb'
GUIDE = '排版对比说明.txt'
INHERITED = b.FIXED | {b.NOTEBOOK, 'b_manifest.json', 'b_profile_board_test.py'}
FIXED = (INHERITED - {b.NOTEBOOK}) | {'b_layout_board_test.py', GUIDE}
ARTIFACTS = FIXED | {b.NOTEBOOK, NOTEBOOK}
GROUPS = ('original', 'cached')
CONTRACT = {'side': 512, 'mode': 3, 'pattern': 'stare', 'groups': list(GROUPS),
            'timed_frames_per_group': 30, 'warmup_frames_per_group': 3,
            'stages': list(p.STAGES), 'clock': 'perf_counter_ns', 'overlay_downloads': 1,
            'algorithm_frames': 68, 'comparison': 'full_packed_word_check_in_both_groups',
            'native_video': 'unchanged_official_pynq_3.0.1', 'pixel_gate': 'whole_720p_bgr_canvas_equality',
            'group_order': 'original_then_cached', 'cpu_cache': 'ordinary_numpy_arrays_only'}
OUTPUTS = ('b_layout_result.json', 'a4_output_stare_512_mode3.npy', 'b_color_pattern.png',
           'b_layout_reference.png', 'b_layout_cached.png', 'b_layout_original_final.png', 'b_layout_cached_final.png')


class CachedCanvas:
    """Cache static captions once and reuse ordinary CPU image/scratch storage.

    render returns borrowed storage, consumed/copied before the next render.
    No native PynqBuffer is cached, mutated after submission, or freed here.
    """
    def __init__(self):
        started = time.perf_counter_ns()
        self.template = b.medical_canvas(np.zeros((512, 512), dtype=np.uint32), 0)
        self.template[24:48] = 16  # Clear the original initial progress marker.
        self.template.setflags(write=False)
        self.image = self.template.copy()
        self.green = np.empty((512, 512), dtype=np.uint8)
        self.mask = np.empty((512, 512), dtype=np.uint8)
        self.shifted = np.empty((512, 512), dtype=np.uint32)
        self.valid = np.empty((512, 512), dtype=bool)
        self.selected = np.empty((512, 512), dtype=bool)
        self.left = self.image[128:640, 64:576]
        self.right = self.image[128:640, 704:1216]
        self.initialization_ns = time.perf_counter_ns() - started

    def render(self, output, index=0):
        b.require(output.shape == (512, 512) and output.dtype == np.uint32, 'Expected real 512 packed algorithm output')
        np.bitwise_and(output, np.uint32(255), out=self.green, casting='unsafe')
        np.right_shift(output, np.uint32(16), out=self.shifted)
        np.bitwise_and(self.shifted, np.uint32(255), out=self.mask, casting='unsafe')
        np.equal(self.mask, 0, out=self.valid)
        np.equal(self.mask, 255, out=self.selected)
        np.logical_or(self.valid, self.selected, out=self.valid)
        b.require(bool(np.all(self.valid)), 'Mask must remain binary')
        self.left[:] = self.green[:, :, None]
        self.right[:] = self.left
        self.right[self.selected] = [0, 255, 0]
        self.image[24:48] = self.template[24:48]
        x = 16 + (int(index) % 100) * 12
        self.image[24:48, x:x + 48] = 255
        return self.image


def validate_package(directory, manifest):
    directory = Path(directory)
    b.require(manifest.get('revision') == REVISION and manifest.get('contract') == CONTRACT and
              manifest.get('board_status') == 'NOT_RUN', 'Wrong layout release/contract')
    b.require(set(manifest.get('artifacts', {})) == ARTIFACTS, 'Incomplete layout package')
    for name in sorted(FIXED):
        b.require(b.sha256_file(directory / name) == manifest['artifacts'][name]['sha256'], 'Layout package mismatch: ' + name)
    code_hash = b.notebook_code_hash(json.loads((directory / NOTEBOOK).read_text(encoding='utf-8')))
    b.require(manifest.get('notebook_validation') == {'algorithm': 'sha256-code-cells-v1', 'sha256': code_hash},
              'Layout notebook code mismatch')
    original = json.loads((directory / 'b_manifest.json').read_text(encoding='utf-8'))
    return {'fixed_artifacts': 'PASS_EXACT_SHA256_EXCLUDING_NOTEBOOK_JSON',
            'notebook_code_sha256': code_hash, 'current_notebook_sha256': b.sha256_file(directory / NOTEBOOK),
            'baseline': b.validate_b_package(directory, original)}


def prepare_layout(directory, retained):
    directory = Path(directory).resolve()
    for name in OUTPUTS + ('b_layout_bundle.zip', 'b_integration_result.json'):
        b.require(not (directory / name).exists(), 'Use new folder; preserve result: ' + name)
    manifest = json.loads((directory / 'b_layout_manifest.json').read_text(encoding='utf-8'))
    validation = validate_package(directory, manifest)
    for name in sorted(n for n in FIXED if n.endswith('.py')):
        module = sys.modules[Path(name).stem]
        b.require(b.sha256_file(module.__file__) == manifest['artifacts'][name]['sha256'], 'Imported module mismatch: ' + name)
    clock = time.get_clock_info('perf_counter')
    b.require(clock.monotonic and clock.resolution <= 1e-6, 'Need high-resolution monotonic perf_counter')
    context = b.prepare_b(directory, retained)
    original_save = context['save']
    context['report'].update(layout_manifest=manifest, layout_package_validation=validation,
        layout={'contract': CONTRACT, 'groups': [], 'clock': {'name': 'perf_counter_ns',
                'monotonic': clock.monotonic, 'resolution_seconds': clock.resolution, 'implementation': clock.implementation},
                'scope': 'Paired original/cached PS layout with full verification, hash and native display costs. '
                         'One fixed input; no SD latency, pure PL cycles or calibrated scan Hz.'})

    def save():
        original_save()
        path = directory / 'b_layout_result.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(context['report'], indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    context['save'] = save
    def check_cpu_canvas():
        context['cached_canvas'] = CachedCanvas()
        canvas = context['cached_canvas']
        context['report']['layout']['cache_initialization_ns'] = canvas.initialization_ns
        context['report']['layout']['ordinary_cpu_cache_bytes'] = sum(
            value.nbytes for value in vars(canvas).values() if isinstance(value, np.ndarray) and value.flags.owndata)
        context['report']['layout']['numpy_version'] = np.__version__
        import PIL
        context['report']['layout']['pillow_version'] = PIL.__version__
        # Preload-only geometry probes contain no GT or FPGA interaction.
        y, x = np.indices((512, 512), dtype=np.uint32)
        words = ((x + y) & 255) | ((((x % 13) == 0).astype(np.uint32) * 255) << 16)
        probes = []
        for marker in (0, 99, 100, -1):
            reference = b.medical_canvas(words, marker)
            actual = canvas.render(words, marker)
            b.require(np.array_equal(actual, reference), 'Cached canvas geometry pixels differ')
            probes.append({'marker': marker, 'sha256_bgr': hashlib.sha256(actual.tobytes()).hexdigest()})
        context['report']['layout']['geometry_checks'] = probes
        context['report']['status'] = 'B_PRECHECK_FPGA_UNCHANGED'
        save()

    b.phase(context, 'B_LAYOUT_PREPARING_CPU_CANVAS_FPGA_UNCHANGED', check_cpu_canvas)
    print('B_LAYOUT_PRECHECK_PASS: package/metadata and full canvas geometry checked; FPGA unchanged', flush=True)
    return context


def load_layout(context):
    b.load_b(context)
    print('B_LAYOUT_LOAD_PASS: original B loaded once', flush=True)


def start_layout(context):
    b.require(context['report']['status'] == 'B_LOADED_NO_TRANSFER', 'Load once before short frame/HDMI')
    b.smoke_b(context)
    b.start_hdmi_b(context)
    print('B_LAYOUT_HDMI_READY: original color pattern; next check uses real FPGA pixels', flush=True)


def check_actual_pixels(context):
    b.require(context['report']['status'] == 'B_COLOR_SUBMITTED', 'Start original HDMI before pixel gate')

    def action():
        b.assert_loaded(context)
        b.transfer_a4(context, 512, 3, 'stare')
        path = context['directory'] / 'a4_output_stare_512_mode3.npy'
        output = np.load(path, allow_pickle=False)
        b.require(np.array_equal(output, b.segmentation_expected(b.make_pattern(512, 'stare', 0, context['directory']), 3)),
                  'Actual FPGA source changed')
        checks = []
        from PIL import Image
        for marker in (0, 99, 100):
            reference = b.medical_canvas(output, marker)
            cached = context['cached_canvas'].render(output, marker)
            b.require(np.array_equal(reference, cached), 'Actual FPGA full canvas pixels differ')
            checks.append({'marker': marker, 'sha256_bgr': hashlib.sha256(cached.tobytes()).hexdigest(),
                           'matched_pixels': 921600, 'matched_bytes': 2764800})
            if marker == 0:
                Image.fromarray(reference[:, :, ::-1]).save(context['directory'] / 'b_layout_reference.png')
                Image.fromarray(cached[:, :, ::-1]).save(context['directory'] / 'b_layout_cached.png')
                b.submit(context, cached, 'CACHED_LAYOUT_PIXEL_GATE')
        context['report']['layout']['actual_pixel_checks'] = checks
        context['report']['status'] = 'B_LAYOUT_ACTUAL_PIXELS_PASS'
        context['save']()
        print('B_LAYOUT_PIXELS_PASS: original and cached entire 720p canvases identical on actual FPGA output', flush=True)

    b.phase(context, 'B_LAYOUT_CHECKING_ACTUAL_PIXELS', action)


def measure_group(context, expected, tx, rx, name, renderer):
    # Same completed native DMA calls/stages as the proved profiler. Only renderer
    # and two-group frame ledger differ; no per-frame reference image is computed.
    group_index = GROUPS.index(name)
    group = {'name': name, 'samples': []}
    context['report']['layout']['groups'].append(group)
    context['save']()
    loop_start = None
    for index in range(33):
        boundaries = [time.perf_counter_ns()]
        if index == 3:
            loop_start = boundaries[0]
        context['dma'].recvchannel.transfer(rx)
        context['dma'].sendchannel.transfer(tx)
        dma_status = b.wait_both_idle(context['dma'])
        context['dma'].sendchannel.wait()
        context['dma'].recvchannel.wait()
        boundaries.append(time.perf_counter_ns())
        b.require(np.array_equal(rx, expected), 'Layout benchmark FPGA word mismatch')
        boundaries.append(time.perf_counter_ns())
        send_bytes = int(context['dma'].sendchannel.transferred)
        recv_bytes = int(context['dma'].recvchannel.transferred)
        b.require(send_bytes == recv_bytes == 1048576, 'Layout benchmark DMA byte count mismatch')
        count = 3 + group_index * 33 + index
        frame_status = int(context['gpio'].channel2.read())
        b.require(frame_status == (count | count << 14), 'Layout benchmark frame counter/error mismatch')
        boundaries.append(time.perf_counter_ns())
        image = renderer(np.asarray(rx).reshape(512, 512), index - 3)
        boundaries.append(time.perf_counter_ns())
        frame = context['hdmi_out'].newframe()
        context['display_retained'].append(frame)
        b.require(frame.shape == (720, 1280, 3) and frame.dtype == np.uint8 and frame.strides == (3840, 3, 1), 'Wrong native video frame')
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
        output_hash = hashlib.sha256(np.asarray(rx).tobytes()).hexdigest()
        boundaries.append(time.perf_counter_ns())
        row = {'index': index, 'warmup': index < 3, 'frame_count': count, 'frame_status': frame_status,
               'words': 262144, 'send_bytes': send_bytes, 'recv_bytes': recv_bytes,
               'dma_status': dma_status, 'vdma_status': vdma_status, 'display_buffer': description,
               'output_sha256': output_hash, 'status': 'PASS_EXACT_SEGMENTATION_WORDS'}
        group['samples'].append(row)
        if index >= 3 and (index - 2) % 5 == 0:
            print('B_LAYOUT_PROGRESS: {} {}/30'.format(name, index - 2), flush=True)
        boundaries.append(time.perf_counter_ns())
        row.update(boundaries_ns=boundaries, durations_ns=p.stage_durations(boundaries), sample_ns=boundaries[-1] - boundaries[0])
    loop_end = time.perf_counter_ns()
    group['summary'] = p.summarize(group['samples'], loop_start, loop_end)
    group['summary']['loop_includes'] = ('DMA/cache/wait, full word compare, counters/status, ' + name +
        ' PS layout, native allocation/copy/flush/IRQ submission, video status, output hash, record/progress')
    path = context['directory'] / ('b_layout_' + name + '_final.png')
    from PIL import Image
    Image.fromarray(image[:, :, ::-1]).save(path)
    group['final_display'] = {'name': path.name, 'sha256': b.sha256_file(path),
                              'sha256_bgr': hashlib.sha256(image.tobytes()).hexdigest(), 'marker_index': 29}
    context['save']()
    print('B_LAYOUT_GROUP_COMPLETE: {} layout={:.3f} ms, checked_loop={:.3f} FPS'.format(
        name, group['summary']['stages']['ps_layout']['mean_ms'], group['summary']['loop_fps']), flush=True)


def compare_layout(context):
    b.require(context['report']['status'] == 'B_LAYOUT_ACTUAL_PIXELS_PASS', 'Actual pixel gate must pass before timing')

    def action():
        b.assert_loaded(context)
        b.video_status(context)
        layout = context['report']['layout']
        b.require(not layout['groups'] and len(context['report']['transfers']) == 2, 'Run paired comparison once')
        source = b.make_pattern(512, 'stare', 0, context['directory'])
        expected = b.segmentation_expected(source, 3).reshape(-1)
        context['gpio'].channel1.write(3, 0xffffffff)
        tx = context['allocate'](shape=(262144,), dtype=np.uint32)
        context['retained'].append(tx)
        rx = context['allocate'](shape=(262144,), dtype=np.uint32)
        context['retained'].append(rx)
        for buffer in (tx, rx):
            b.require(buffer.dtype == np.uint32 and buffer.shape == (262144,) and buffer.strides == (4,) and
                      buffer.physical_address % 8 == 0 and 0x100000 <= buffer.physical_address <= 0x20000000 - 1048576,
                      'Invalid algorithm allocation')
        b.require(abs(tx.physical_address - rx.physical_address) >= 1048576, 'Algorithm buffers overlap')
        tx[:] = source.reshape(-1)
        rx[:] = np.bitwise_not(expected)
        rx.flush()
        layout.update(input_sha256=hashlib.sha256(source.tobytes()).hexdigest(),
                      expected_sha256=hashlib.sha256(expected.tobytes()).hexdigest(),
                      algorithm_buffers={'tx': p.buffer_info(tx), 'rx': p.buffer_info(rx)},
                      native_video_cacheable_frames=bool(context['video'].axi_vdma.writechannel.cacheable_frames))
        for name, renderer in (('original', b.medical_canvas), ('cached', context['cached_canvas'].render)):
            measure_group(context, expected, tx, rx, name, renderer)
        b.assert_loaded(context)
        groups = layout['groups']
        b.require([group['name'] for group in groups] == list(GROUPS) and
                  all(len(group['samples']) == 33 for group in groups) and
                  groups[0]['final_display']['sha256_bgr'] == groups[1]['final_display']['sha256_bgr'],
                  'Paired final display mismatch/incomplete samples')
        before, after = [group['summary'] for group in groups]
        b.require(before['stages']['ps_layout']['mean_ms'] > 0 and after['stages']['ps_layout']['mean_ms'] > 0,
                  'Layout clock did not advance')
        layout['comparison'] = {'original_layout_mean_ms': before['stages']['ps_layout']['mean_ms'],
            'cached_layout_mean_ms': after['stages']['ps_layout']['mean_ms'],
            'layout_ratio_original_over_cached': before['stages']['ps_layout']['mean_ms'] / after['stages']['ps_layout']['mean_ms'],
            'original_checked_loop_fps': before['loop_fps'], 'cached_checked_loop_fps': after['loop_fps'],
            'loop_ratio_cached_over_original': after['loop_fps'] / before['loop_fps'],
            'scope': 'Actual paired measured workload; same word compare/hash/native video overhead. '
                     'No file input/PL-only/clinical or calibrated scan-rate PASS.'}
        rx.freebuffer()
        b.require(context['retained'].pop() is rx, 'Receive ownership ledger changed')
        tx.freebuffer()
        b.require(context['retained'].pop() is tx, 'Send ownership ledger changed')
        layout['total_algorithm_frames'] = 68
        context['report']['status'] = 'B_LAYOUT_MEASURED'
        context['save']()
        print('B_LAYOUT_COMPARE_COMPLETE: paired real measurements saved; performance acceptance pending independent review', flush=True)

    b.phase(context, 'B_LAYOUT_COMPARING', action)


def finish_layout(context):
    b.require(context['report']['status'] == 'B_LAYOUT_MEASURED', 'Complete paired timing before close/package')
    bundle = context['directory'] / 'b_layout_bundle.zip'
    b.require(not bundle.exists(), 'Preserve earlier layout bundle')

    def action():
        b.assert_loaded(context)
        context['report']['display']['final_vdma_status'] = b.video_status(context)
        context['hdmi_out'].close()
        context['report']['display']['closed'] = True
        context['report']['status'] = 'B_LAYOUT_RECORDS_READY_VISUAL_PENDING'
        context['save']()
        with ZipFile(bundle, 'w', ZIP_DEFLATED) as archive:
            for name in OUTPUTS:
                archive.write(context['directory'] / name, arcname=name)
        print('B_LAYOUT_RESULTS_READY: download b_layout_bundle.zip and executed b_layout_compare.ipynb', flush=True)

    b.phase(context, 'B_LAYOUT_CLOSING_AND_PACKAGING', action)
