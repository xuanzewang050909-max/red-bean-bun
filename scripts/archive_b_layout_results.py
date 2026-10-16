"""Independently verify paired B layout downloads, without executing board code."""
import argparse
import base64
import copy
import io
import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import numpy as np
from PIL import Image

from archive_a4_board_results import require, digest, word_digest, regenerate_input, independent_expected, write_json
from archive_b_board_results import flatten_text, close_number, video_status, decode_png
from archive_b_profile_results import dma_status, address, buffer_description, DRIVERS, STAGES
from a1_point_board_test import notebook_code_hash
from b_layout_board_test import validate_package

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'results/b_layout_2017_4_r1/release_manifest.json'
BASELINE = ROOT / 'results/b_integration_2017_4_r2/release_manifest.json'
NAMES = {'b_layout_result.json', 'a4_output_stare_512_mode3.npy', 'b_color_pattern.png',
         'b_layout_reference.png', 'b_layout_cached.png', 'b_layout_original_final.png', 'b_layout_cached_final.png'}
GROUPS = ('original', 'cached')


def read_bundle(path):
    require(path.stat().st_size <= 4_000_000, 'ZIP exceeds size limit')
    with ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == 7 and {entry.filename for entry in entries} == NAMES,
                'Missing, duplicate or unexpected ZIP member')
        require(sum(entry.file_size for entry in entries) <= 4_000_000, 'Uncompressed ZIP exceeds limit')
        for entry in entries:
            require(not entry.is_dir() and not entry.flag_bits & 1 and
                    stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFLNK and
                    entry.compress_type in (ZIP_STORED, ZIP_DEFLATED), 'Unsupported ZIP member')
            require(0 < entry.file_size <= (1_100_000 if entry.filename.endswith('.npy') else 500_000),
                    'Unexpected ZIP member size')
        return {entry.filename: archive.read(entry) for entry in entries}


def verify_notebook(notebook, manifest, released_notebook):
    cells = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
    trailing, normalized = 0, notebook
    # The final Shift+Enter may add one unused blank code cell; only that tail
    # is excluded from this read-only code check. The original download stays intact.
    if len(cells) == 8:
        tail = cells[-1]
        require(notebook['cells'][-1] is tail and tail['execution_count'] is None and tail['outputs'] == [] and
                flatten_text(tail['source']).strip() == '', 'Unexpected executable notebook tail')
        trailing = 1
        normalized = copy.deepcopy(notebook)
        normalized['cells'].pop()
    cells = cells[:7]
    require(len(cells) == 7 and [cell['execution_count'] for cell in cells] == list(range(1, 8)),
            'Notebook execution order differs')
    require(all(output.get('output_type') != 'error' for cell in cells for output in cell['outputs']), 'Notebook error output')
    require(notebook_code_hash(released_notebook) == manifest['notebook_validation']['sha256'], 'Released notebook code changed')
    reference = [cell for cell in released_notebook['cells'] if cell['cell_type'] == 'code']
    require(len(reference) == 7, 'Released notebook cell inventory differs')
    pre_normalization_hash = notebook_code_hash(normalized)
    normalized = copy.deepcopy(normalized)
    normalized_cells = [cell for cell in normalized['cells'] if cell['cell_type'] == 'code']
    extra_lines = []
    for index, (actual, original) in enumerate(zip(cells, reference)):
        source = flatten_text(actual['source']).replace('\r\n', '\n')
        expected = flatten_text(original['source']).replace('\r\n', '\n')
        if source != expected:
            # This download adds one blank trailing line in code cell 3, after
            # the board's original precheck. Permit exactly one additional LF
            # on an already newline-terminated cell, never executable edits.
            require(expected.endswith('\n') and source == expected + '\n', 'Notebook code changed')
            normalized_cells[index]['source'] = original['source']
            extra_lines.append({'code_cell': index + 1, 'extra_trailing_empty_lines': 1})
    require(notebook_code_hash(normalized) == manifest['notebook_validation']['sha256'], 'Notebook code changed')
    streams = [''.join(flatten_text(output.get('text', '')) for output in cell['outputs']
                       if output.get('output_type') == 'stream') for cell in cells]
    all_text = ''.join(streams)
    markers = {1: 'B_LAYOUT_PRECHECK_PASS:', 2: 'B_LAYOUT_LOAD_PASS:', 3: 'B_LAYOUT_HDMI_READY:',
               4: 'B_LAYOUT_PIXELS_PASS:', 5: 'B_LAYOUT_COMPARE_COMPLETE:', 6: 'B_LAYOUT_RESULTS_READY:'}
    for index, marker in markers.items():
        require(streams[index].count(marker) == all_text.count(marker) == 1, 'Notebook stage marker differs')
    require('SEGMENTATION_FRAME_PASS: 1/61 256 mode 3 vessel_stripes' in streams[3] and
            'SEGMENTATION_FRAME_PASS: 2/61 512 mode 3 stare' in streams[4], 'Notebook prefix confirmation differs')
    progress = [line for line in streams[5].splitlines() if line.startswith('B_LAYOUT_PROGRESS:')]
    require(progress == [f'B_LAYOUT_PROGRESS: {name} {index}/30'
                         for name in GROUPS for index in (5, 10, 15, 20, 25, 30)], 'Notebook paired progress differs')
    return cells, streams, {'executed_code_cells': 7, 'inert_trailing_cells': trailing,
                           'canonical_executed_code_sha256': notebook_code_hash(normalized),
                           'executed_source_sha256_before_empty_line_normalization': pre_normalization_hash,
                           'ignored_single_trailing_empty_lines': extra_lines,
                           'raw_notebook_code_sha256': notebook_code_hash(notebook),
                           'source_policy': 'Exact released source, except explicitly recorded single trailing LF; '
                                            'read-only download check only. Runtime/release hash contract unchanged.'}


def verify_timing_group(group, stream):
    name, samples = group['name'], group['samples']
    require(len(samples) == 33, 'Incomplete paired timing sample ledger')
    previous = None
    for index, sample in enumerate(samples):
        require(type(sample['index']) is int and sample['index'] == index and
                type(sample['warmup']) is bool and sample['warmup'] == (index < 3), 'Warmup/sample order differs')
        boundaries = sample['boundaries_ns']
        require(len(boundaries) == 11 and all(type(value) is int and value >= 0 for value in boundaries),
                'Invalid raw stage timestamps')
        differences = [boundaries[i + 1] - boundaries[i] for i in range(10)]
        require(all(value >= 0 for value in differences) and differences[0] > 0, 'Timing clock reversed/not advancing')
        require(previous is None or boundaries[0] >= previous, 'Overlapping frame timestamps')
        previous = boundaries[-1]
        require(sample['durations_ns'] == dict(zip(STAGES, differences)) and
                all(type(value) is int for value in sample['durations_ns'].values()) and
                type(sample['sample_ns']) is int and sample['sample_ns'] == sum(differences), 'Raw stage sum differs')
    summary, timed = group['summary'], samples[3:]
    require(type(summary['count']) is int and summary['count'] == 30 and set(summary['stages']) == set(STAGES),
            'Paired summary contract differs')
    start, end = summary['loop_start_ns'], summary['loop_end_ns']
    require(type(start) is int and type(end) is int and start == timed[0]['boundaries_ns'][0] and
            end >= previous > start, 'Complete loop timestamps differ')
    total_ns = sum(sample['sample_ns'] for sample in timed)
    loop_ns = end - start
    require(loop_ns >= total_ns and summary['loop_ns'] == loop_ns and summary['sample_sum_ns'] == total_ns and
            summary['loop_unattributed_ns'] == loop_ns - total_ns, 'Loop/sample reconciliation differs')
    durations = np.asarray([sample['sample_ns'] for sample in timed], dtype=np.float64)
    metrics = {'count': 30, 'sum_seconds': total_ns / 1e9, 'mean_ms': float(durations.mean() / 1e6),
               'median_ms': float(np.median(durations) / 1e6), 'p95_ms': float(np.percentile(durations, 95) / 1e6),
               'frames_per_sum_transaction_seconds': 30 * 1e9 / total_ns,
               'loop_seconds': loop_ns / 1e9, 'loop_fps': 30 * 1e9 / loop_ns}
    for key, value in metrics.items():
        close_number(summary[key], value, name + '/' + key)
    stages = {}
    for stage_name in STAGES:
        values = [sample['durations_ns'][stage_name] for sample in timed]
        metric = {'sum_ns': sum(values), 'mean_ms': sum(values) / 30e6,
                  'median_ms': float(np.median(values) / 1e6), 'p95_ms': float(np.percentile(values, 95) / 1e6),
                  'share_of_sample_time_percent': 100 * sum(values) / total_ns}
        for key, value in metric.items():
            close_number(summary['stages'][stage_name][key], value, name + '/' + stage_name + '/' + key)
        stages[stage_name] = metric
    require(sum(stage['sum_ns'] for stage in stages.values()) == total_ns, 'Attributed timing total differs')
    require(stream.count('B_LAYOUT_GROUP_COMPLETE: {} layout={:.3f} ms, checked_loop={:.3f} FPS'.format(
        name, stages['ps_layout']['mean_ms'], metrics['loop_fps'])) == 1, 'Notebook group summary differs')
    lines = stream.splitlines()
    heading = '{}: checked loop {:.6f} FPS'.format(name, metrics['loop_fps'])
    require(lines.count(heading) == 1, 'Notebook full precision loop FPS differs')
    block = lines[lines.index(heading) + 1:lines.index(heading) + 11]
    require(block == ['  {}: {:.6f} ms, {:.3f}%'.format(stage_name, stages[stage_name]['mean_ms'],
                        stages[stage_name]['share_of_sample_time_percent']) for stage_name in STAGES],
            'Notebook paired stage metrics differ')
    return {**metrics, 'name': name, 'stages': stages, 'warmup_frames': 3, 'loop_start_ns': start,
            'loop_end_ns': end, 'loop_ns': loop_ns, 'sample_sum_ns': total_ns,
            'loop_unattributed_ns': loop_ns - total_ns}


def with_marker(pixels, marker):
    image = pixels.copy()
    image[24:48] = 16
    x = 16 + int(marker) % 100 * 12
    image[24:48, x:x + 48] = 255
    return image


def panes(pixels, words):
    image = pixels.copy()
    green, mask = (words & 255).astype(np.uint8), ((words >> 16) & 255).astype(np.uint8)
    grey = np.repeat(green[:, :, None], 3, axis=2)
    marked = grey.copy()
    marked[mask != 0] = [0, 255, 0]
    image[128:640, 64:576] = grey
    image[128:640, 704:1216] = marked
    return image


def verify_display(cells, report, members, output):
    display, layout = report['display'], report['layout']
    require(display['closed'] is True and display['visual_status'] == 'PENDING_USER_OBSERVATION', 'Original pending/closed record changed')
    require(display['configured_mode'] == {'width': 1280, 'height': 720, 'bpp': 24, 'requested_hz': 60, 'format': 'BGR24'},
            'Video mode differs')
    require([item['label'] for item in display['submissions']] == ['BLUE_GREEN_RED_WITH_POSITION_LINES', 'CACHED_LAYOUT_PIXEL_GATE'],
            'Display submission ledger differs')
    for status in [item['vdma_status'] for item in display['submissions']] + [display['final_vdma_status']]:
        video_status(status)
    colors = decode_png(members['b_color_pattern.png'])
    expected = np.empty_like(colors)
    expected[:, :426], expected[:, 426:853], expected[:, 853:] = [0, 0, 255], [0, 255, 0], [255, 0, 0]
    expected[:4] = expected[-4:] = expected[:, :4] = expected[:, -4:] = 255
    expected[358:362] = 255
    expected[:, 638:642] = 255
    require(np.array_equal(colors, expected), 'Color pattern pixels differ')
    require(display['color_reference'] == {'name': 'b_color_pattern.png', 'sha256': digest(members['b_color_pattern.png'])} and
            display['submissions'][0]['sha256_bgr'] == digest(colors[:, :, ::-1].tobytes()), 'Color provenance differs')
    reference = decode_png(members['b_layout_reference.png'])
    cached = decode_png(members['b_layout_cached.png'])
    require(np.array_equal(reference, cached), 'Original/cached pixel-gate entire canvas differs')
    expected = with_marker(panes(np.full_like(reference, 16), output), 0)
    comparison = np.ones((720, 1280), dtype=bool)
    comparison[76:110, 60:690] = False
    comparison[76:110, 700:1270] = False
    comparison[660:700, 60:1270] = False
    require(np.array_equal(reference[comparison], expected[comparison]), 'Actual array panels/background/marker differ')
    actual_checks = layout['actual_pixel_checks']
    require([check['marker'] for check in actual_checks] == [0, 99, 100], 'Actual marker gate differs')
    for check in actual_checks:
        canvas = with_marker(reference, check['marker'])
        require(check == {'marker': check['marker'], 'sha256_bgr': digest(canvas[:, :, ::-1].tobytes()),
                          'matched_pixels': 921600, 'matched_bytes': 2764800}, 'Actual full canvas hash/gate differs')
    require(display['submissions'][1]['sha256_bgr'] == actual_checks[0]['sha256_bgr'], 'Pixel-gate submission provenance differs')
    y, x = np.indices((512, 512), dtype=np.uint32)
    probe = ((x + y) & 255) | ((((x % 13) == 0).astype(np.uint32) * 255) << 16)
    geometry = layout['geometry_checks']
    require([check['marker'] for check in geometry] == [0, 99, 100, -1], 'Geometry probes differ')
    for check in geometry:
        canvas = with_marker(panes(reference, probe), check['marker'])
        require(check == {'marker': check['marker'], 'sha256_bgr': digest(canvas[:, :, ::-1].tobytes())},
                'Geometry full-canvas hash differs')
    final_images = []
    expected = with_marker(reference, 29)
    for group in layout['groups']:
        name = 'b_layout_' + group['name'] + '_final.png'
        image = decode_png(members[name])
        require(np.array_equal(image, expected), 'Final entire canvas differs from actual pixel gate')
        require(group['final_display'] == {'name': name, 'sha256': digest(members[name]),
                'sha256_bgr': digest(image[:, :, ::-1].tobytes()), 'marker_index': 29}, 'Final display provenance differs')
        final_images.append(image)
    require(np.array_equal(final_images[0], final_images[1]), 'Original/cached final entire canvas differs')
    embedded = [output['data']['image/png'] for output in cells[6]['outputs']
                if output.get('output_type') == 'display_data' and 'image/png' in output.get('data', {})]
    require(len(embedded) == 1, 'Final notebook image missing/not unique')
    png = base64.b64decode(''.join(flatten_text(embedded[0]).split()), validate=True)
    require(np.array_equal(decode_png(png), final_images[1]), 'Notebook final image differs from cached PNG')
    return {'status': 'PASS_FULL_CANVAS_PAIRS_GEOMETRY_ACTUAL_GATE_FINAL_AND_NOTEBOOK',
            'pixel_gate_mismatched_pixels': 0, 'final_pair_mismatched_pixels': 0,
            'pixels_per_canvas': 921600, 'actual_markers': [0, 99, 100], 'geometry_markers': [0, 99, 100, -1],
            'pixel_gate_png_bytes_identical': members['b_layout_reference.png'] == members['b_layout_cached.png'],
            'final_png_bytes_identical': members['b_layout_original_final.png'] == members['b_layout_cached_final.png'],
            'png_sha256': {name: digest(data) for name, data in members.items() if name.endswith('.png')},
            'limit': 'Caption rectangles excluded only from host independent-font reconstruction; original/cached '
                     'pairs and final versus actual gate compared over every pixel including captions. Photos reviewed separately.'}


def verify_records(notebook, report, manifest, package, members):
    baseline = json.loads(BASELINE.read_bytes())
    require(report['layout_manifest'] == manifest and report['manifest'] == baseline, 'Release manifest differs')
    require(report['status'] == 'B_LAYOUT_RECORDS_READY_VISUAL_PENDING' and not any(
        name in report for name in ('error', 'failed_stage', 'retained_buffers', 'retained_display_frames')), 'Incomplete/failed layout run')
    require((report['pynq'], report['python'], report['kernel']) == ('3.0.1', '3.10.4', '5.15.19-xilinx-v2022.1'), 'Board runtime differs')
    require(report['drivers'] == DRIVERS, 'Official driver binding differs')
    require(type(report['overlay_downloads']) is int and report['overlay_downloads'] == 1, 'Single overlay download differs')
    released_bytes = (package / 'b_layout_compare.ipynb').read_bytes()
    require(digest(released_bytes) == manifest['artifacts']['b_layout_compare.ipynb']['sha256'], 'Local released notebook bytes changed')
    cells, streams, notebook_checks = verify_notebook(notebook, manifest, json.loads(released_bytes))
    validation = report['layout_package_validation']
    require(validation['fixed_artifacts'] == 'PASS_EXACT_SHA256_EXCLUDING_NOTEBOOK_JSON' and
            validation['notebook_code_sha256'] == manifest['notebook_validation']['sha256'] and
            validation['baseline'] == report['package_validation'] and re.fullmatch('[0-9a-f]{64}', validation['current_notebook_sha256']),
            'Layout package validation differs')
    old = validation['baseline']
    require(old['fixed_artifacts'] == 'PASS_EXACT_SHA256' and old['notebook_code'] == 'PASS_CANONICAL_CODE_SHA256' and
            old['notebook_code_sha256'] == baseline['notebook_validation']['sha256'] and
            old['original_notebook_sha256'] == baseline['artifacts']['b_integration_check.ipynb']['sha256'] and
            re.fullmatch('[0-9a-f]{64}', old['current_notebook_sha256']), 'Inherited notebook code validation differs')
    layout = report['layout']
    require(layout['contract'] == manifest['contract'] and layout['total_algorithm_frames'] == 68 and
            layout['ordinary_cpu_cache_bytes'] == 7626752 and type(layout['cache_initialization_ns']) is int and
            layout['cache_initialization_ns'] > 0, 'Layout workload/cache contract differs')
    require((layout['numpy_version'], layout['pillow_version']) == ('1.21.5', '9.0.1'), 'Recorded board array/font runtime differs')
    clock = layout['clock']
    require(clock['name'] == 'perf_counter_ns' and clock['monotonic'] is True and
            clock['implementation'] == 'clock_gettime(CLOCK_MONOTONIC)' and type(clock['resolution_seconds']) in (int, float) and
            0 < clock['resolution_seconds'] <= 1e-6, 'Unexpected monotonic timing clock')
    require(len(report['transfers']) == 2, 'Unexpected prefix/full-suite ledger')
    frames = []
    expected = None
    for index, (record, case) in enumerate(zip(report['transfers'], ((256, 'vessel_stripes'), (512, 'stare')))):
        side, pattern = case
        require((record['side'], record['mode'], record['pattern'], record['words'], record['send_bytes'], record['recv_bytes']) ==
                (side, 3, pattern, side * side, side * side * 4, side * side * 4) and
                record['status'] == 'PASS_EXACT_SEGMENTATION_WORDS' and record['frame_status'] == (index + 1) | (index + 1) << 14,
                'Prefix frame/bytes/counter differs')
        dma_status(record['dma_status'])
        for value in (record['tx_address'], record['rx_address']):
            address(value, side * side * 4)
        require(abs(record['tx_address'] - record['rx_address']) >= side * side * 4, 'Prefix DDR overlap')
        source = regenerate_input(side, pattern, 0, package)
        expected = independent_expected(source, 3)
        require(record['input_sha256'] == word_digest(source) and
                record['expected_sha256'] == record['output_sha256'] == word_digest(expected), 'Independent prefix input/golden hash differs')
        frames.append({'frame': index + 1, 'side': side, 'words': side * side, 'output_sha256': record['output_sha256']})
    require(layout['input_sha256'] == word_digest(source) and layout['expected_sha256'] == word_digest(expected), 'Independent STARE input/golden differs')
    buffers = layout['algorithm_buffers']
    require(set(buffers) == {'tx', 'rx'} and layout['native_video_cacheable_frames'] is True, 'Algorithm/video buffer properties differ')
    for description in buffers.values():
        buffer_description(description, [262144], [4], 'uint32', 1048576)
    tx, rx = buffers['tx']['physical_address'], buffers['rx']['physical_address']
    require(abs(tx - rx) >= 1048576, 'Algorithm DDR overlap')
    groups = layout['groups']
    require([group['name'] for group in groups] == list(GROUPS), 'Paired group order differs')
    timing = []
    for group_index, group in enumerate(groups):
        require(len(group['samples']) == 33, 'Incomplete paired sample ledger')
        for index, sample in enumerate(group['samples']):
            count = 3 + group_index * 33 + index
            require(type(sample['frame_count']) is int and sample['frame_count'] == count and
                    sample['frame_status'] == count | count << 14 and sample['status'] == 'PASS_EXACT_SEGMENTATION_WORDS' and
                    (sample['words'], sample['send_bytes'], sample['recv_bytes']) == (262144, 1048576, 1048576), 'Pair frame/bytes/counter differs')
            require(sample['output_sha256'] == word_digest(expected), 'Independent pair output hash differs')
            dma_status(sample['dma_status'])
            video_status(sample['vdma_status'])
            description = sample['display_buffer']
            buffer_description(description, [720, 1280, 3], [3840, 3, 1], 'uint8', 2764800)
            location = description['physical_address']
            require(all(location + 2764800 <= algorithm or algorithm + 1048576 <= location for algorithm in (tx, rx)),
                    'Video/algorithm DDR overlap')
            frames.append({'frame': count, 'side': 512, 'words': 262144, 'group': group['name'], 'output_sha256': sample['output_sha256']})
        timing.append(verify_timing_group(group, streams[5]))
    require(groups[1]['samples'][0]['boundaries_ns'][0] >= timing[0]['loop_end_ns'], 'Timing groups overlap')
    before, after = timing
    comparison = {'original_layout_mean_ms': before['stages']['ps_layout']['mean_ms'],
                  'cached_layout_mean_ms': after['stages']['ps_layout']['mean_ms'],
                  'layout_ratio_original_over_cached': before['stages']['ps_layout']['mean_ms'] / after['stages']['ps_layout']['mean_ms'],
                  'original_checked_loop_fps': before['loop_fps'], 'cached_checked_loop_fps': after['loop_fps'],
                  'loop_ratio_cached_over_original': after['loop_fps'] / before['loop_fps']}
    for key, value in comparison.items():
        close_number(layout['comparison'][key], value, key)
    comparison['layout_time_reduction_percent'] = 100 * (1 - after['stages']['ps_layout']['mean_ms'] / before['stages']['ps_layout']['mean_ms'])
    output_bytes = members['a4_output_stare_512_mode3.npy']
    require(report['transfers'][1]['saved_output'] == {'name': 'a4_output_stare_512_mode3.npy', 'sha256': digest(output_bytes)}, 'Saved raw output hash differs')
    output = np.load(io.BytesIO(output_bytes), allow_pickle=False)
    require(output.dtype == np.dtype('<u4') and output.shape == (512, 512), 'Saved raw output format differs')
    require(np.array_equal(output, expected), 'Actual raw FPGA output differs from independent M0')
    require(np.all(((output >> 16) & 255)[(source >> 24) == 0] == 0), 'Final mask outside FOV')
    return {'frames': frames, 'notebook': notebook_checks,
            'timing': {'status': 'PASS_INDEPENDENT_RAW_TIMESTAMPS_STAGES_LOOPS_RATIOS_AND_NOTEBOOK', 'groups': timing,
                       'comparison': comparison, 'cache_initialization_ns': layout['cache_initialization_ns'],
                       'limit': 'Sequential original/cached groups, fixed input with full verification/hash/native display. '
                                'No SD latency, pure PL, CPU algorithm baseline or calibrated scan Hz.'},
            'display': verify_display(cells, report, members, output),
            'raw_array': {'name': 'a4_output_stare_512_mode3.npy', 'words': 262144, 'mismatched_words': 0,
                          'file_sha256': digest(output_bytes), 'word_sha256': word_digest(output),
                          'mask_values': [int(value) for value in np.unique((output >> 16) & 255)]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('notebook', type=Path)
    parser.add_argument('bundle', type=Path)
    for name in ('package', 'destination', 'raw-destination', 'color-photo', 'medical-photo'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.destination.exists() and not args.raw_destination.exists(), 'Preserve earlier archive')
    manifest_data = (args.package / 'b_layout_manifest.json').read_bytes()
    require(manifest_data == RELEASE.read_bytes(), 'Local layout release differs')
    manifest = json.loads(manifest_data)
    validate_package(args.package, manifest)
    require(args.notebook.stat().st_size <= 1_000_000, 'Notebook exceeds size limit')
    notebook_data, bundle_data = args.notebook.read_bytes(), args.bundle.read_bytes()
    members = read_bundle(args.bundle)
    report = json.loads(members['b_layout_result.json'])
    checks = verify_records(json.loads(notebook_data), report, manifest, args.package, members)
    require(args.notebook.read_bytes() == notebook_data and args.bundle.read_bytes() == bundle_data, 'Downloads changed during verification')
    photos = {'monitor_color_photo.jpg': args.color_photo.read_bytes(), 'monitor_medical_photo.jpg': args.medical_photo.read_bytes()}
    for data in photos.values():
        with Image.open(io.BytesIO(data)) as image:
            require(image.format == 'JPEG' and min(image.size) >= 700, 'Invalid supplied photo')
            image.verify()
    args.destination.mkdir(parents=True)
    args.raw_destination.mkdir(parents=True)
    raw = {'b_layout_compare_executed.ipynb': notebook_data, 'b_layout_bundle.zip': bundle_data, **members, **photos}
    files = {}
    for name, data in raw.items():
        path = args.raw_destination / name
        path.write_bytes(data)
        require(path.read_bytes() == data, 'Raw byte preservation failed')
        files[name] = {'path': str(path.resolve()), 'bytes': len(data), 'sha256': digest(data)}
    (args.destination / 'b_layout_result.json').write_bytes(members['b_layout_result.json'])
    for name, value in checks.items():
        write_json(args.destination / (name + '_verification.json'), value)
    csv = ['group,index,warmup,frame_count,start_ns,end_ns,sample_ns,' + ','.join(name + '_ns' for name in STAGES)]
    for group in report['layout']['groups']:
        for sample in group['samples']:
            csv.append(','.join(str(value) for value in [group['name'], sample['index'], int(sample['warmup']), sample['frame_count'],
                sample['boundaries_ns'][0], sample['boundaries_ns'][-1], sample['sample_ns'], *[sample['durations_ns'][name] for name in STAGES]]))
    (args.destination / 'timing_samples.csv').write_text('\n'.join(csv) + '\n', encoding='utf-8', newline='\n')
    write_json(args.destination / 'archive_manifest.json', {
        'status': 'PASS_B_LAYOUT_BOARD_PIXELS_REAL_ARRAY_AND_PAIRED_RAW_TIMESTAMPS',
        'client_received_date': '2026-10-12', 'verified_host_utc': datetime.now(timezone.utc).isoformat(),
        'board_clock_utc_unverified': report['board_clock_utc_unverified'], 'revision': manifest['revision'],
        'release_manifest_sha256': digest(manifest_data), 'overlay_downloads': 1,
        'frame_records_verified': 68, 'input_words_verified': 17629184, 'raw_output_words_verified': 262144,
        'warmup_frames_per_group': 3, 'timed_frames_per_group': 30, 'files': files,
        'scope': 'Two prefix records plus 66 verified output hash records, one actual saved FPGA array, full PNG pairs and '
                 'all stage/loop/ratio formulas independently recomputed. Fixed ordered comparison only; no PL-only/SD/CPU/scan-Hz/clinical PASS. '
                 'Raw JSON visual PENDING and original 2022 clock retained; supplied photos assessed separately.'})
    print('B_LAYOUT_ARCHIVED: 68 frames, 262144 actual output words, two 30-sample groups, all pixels/stage/loop/ratio formulas checked')


if __name__ == '__main__':
    main()
