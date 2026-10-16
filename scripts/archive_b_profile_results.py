"""Verify real B profiling downloads without executing their code or editing bytes."""
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
from a1_point_board_test import notebook_code_hash
from b_profile_board_test import validate_profile_package

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'results/b_profile_2017_4_r2/release_manifest.json'
BASELINE = ROOT / 'results/b_integration_2017_4_r2/release_manifest.json'
STAGES = ('dma_transfer', 'word_compare', 'algorithm_status', 'ps_layout', 'frame_allocate',
          'frame_copy', 'display_submit', 'video_status', 'output_hash', 'record_and_progress')
NAMES = {'b_profile_result.json', 'b_profile_output_512.npy', 'b_profile_display.png', 'b_color_pattern.png'}
DRIVERS = {'dma': 'pynq.lib.dma.DMA', 'gpio': 'pynq.lib.axigpio.AxiGPIO',
           'video': 'pynq.lib.video.hierarchies.HDMIWrapper', 'hdmi_out': 'pynq.lib.video.hierarchies.VideoOut',
           'vdma': 'pynq.lib.video.dma.AxiVDMA'}


def read_bundle(path):
    require(path.stat().st_size <= 3_000_000, 'ZIP exceeds size limit')
    with ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == 4 and {entry.filename for entry in entries} == NAMES,
                'Missing, duplicate or unexpected ZIP member')
        require(sum(entry.file_size for entry in entries) <= 2_000_000, 'Uncompressed ZIP exceeds limit')
        for entry in entries:
            require(not entry.is_dir() and not entry.flag_bits & 1 and
                    stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFLNK and
                    entry.compress_type in (ZIP_DEFLATED, ZIP_STORED), 'Unsupported ZIP member')
            limit = 1_100_000 if entry.filename.endswith('.npy') else 500_000
            require(0 < entry.file_size <= limit, 'Unexpected ZIP member size')
        return {entry.filename: archive.read(entry) for entry in entries}


def verify_notebook(notebook, manifest):
    cells = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
    trailing = 0
    # Shift+Enter on the final Jupyter cell can add one unused empty cell.
    # Only this inert tail is excluded from this read-only downloaded-code check.
    if len(cells) == 7:
        tail = cells[-1]
        require(notebook['cells'][-1] is tail and tail['execution_count'] is None and tail['outputs'] == [] and
                flatten_text(tail['source']).strip() == '', 'Unexpected executable notebook tail')
        trailing = 1
        normalized = copy.deepcopy(notebook)
        normalized['cells'].pop()
    else:
        normalized = notebook
    require(notebook_code_hash(normalized) == manifest['notebook_validation']['sha256'], 'Notebook code changed')
    cells = cells[:6]
    require(len(cells) == 6 and [cell['execution_count'] for cell in cells] == list(range(1, 7)),
            'Notebook execution order differs')
    require(all(output.get('output_type') != 'error' for cell in cells for output in cell['outputs']), 'Notebook error output')
    streams = [''.join(flatten_text(output.get('text', '')) for output in cell['outputs']
                       if output.get('output_type') == 'stream') for cell in cells]
    text = ''.join(streams)
    for index, marker in {1: 'B_PROFILE_PRECHECK_PASS:', 2: 'B_PROFILE_LOAD_PASS:',
                          3: 'B_PROFILE_HDMI_READY:', 4: 'B_PROFILE_COMPLETE:', 5: 'B_PROFILE_RESULTS_READY:'}.items():
        require(streams[index].count(marker) == text.count(marker) == 1, 'Notebook stage marker differs')
    require('SEGMENTATION_FRAME_PASS: 1/61 256 mode 3 vessel_stripes' in streams[3], 'Missing smoke confirmation')
    progress = [line for line in streams[4].splitlines() if line.startswith('B_PROFILE_PROGRESS:')]
    require(progress == [f'B_PROFILE_PROGRESS: {index}/30' for index in (5, 10, 15, 20, 25, 30)],
            'Notebook progress differs')
    return cells, streams, {'executed_code_cells': 6, 'inert_trailing_cells': trailing,
                           'canonical_executed_code_sha256': notebook_code_hash(normalized),
                           'raw_notebook_code_sha256': notebook_code_hash(notebook)}


def dma_status(status):
    require(set(status) == {'mm2s', 's2mm'} and all(type(value) is int and value & 2 and
            not value & 0x771 for value in status.values()), 'DMA halted/busy/error')


def address(value, size):
    require(type(value) is int and value % 8 == 0 and 0x100000 <= value <= 0x20000000 - size,
            'Invalid DDR address/alignment')


def buffer_description(description, shape, strides, dtype, size):
    require(description['shape'] == shape and description['strides'] == strides and
            description['dtype'] == dtype and description['nbytes'] == size, 'Buffer description differs')
    require(description['cacheable'] is True and description['coherent'] is False, 'Unexpected recorded buffer cache properties')
    address(description['physical_address'], size)


def verify_timing(profile, stream):
    samples = profile['samples']
    require(len(samples) == 33, 'Incomplete profiling sample ledger')
    clock = profile['clock']
    require(clock['name'] == 'perf_counter_ns' and clock['monotonic'] is True and
            clock['implementation'] == 'clock_gettime(CLOCK_MONOTONIC)' and
            type(clock['resolution_seconds']) in (int, float) and 0 < clock['resolution_seconds'] <= 1e-6,
            'Unexpected monotonic timing clock')
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
                type(sample['sample_ns']) is int and sample['sample_ns'] == sum(differences), 'Raw stage sum differs')
    timed = samples[3:]
    summary = profile['summary']
    require(summary['count'] == 30 and set(summary['stages']) == set(STAGES), 'Timing summary contract differs')
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
    for name, value in metrics.items():
        close_number(summary[name], value, name)
    stages = {}
    for name in STAGES:
        values = [sample['durations_ns'][name] for sample in timed]
        metric = {'sum_ns': sum(values), 'mean_ms': sum(values) / 30e6,
                  'median_ms': float(np.median(values) / 1e6), 'p95_ms': float(np.percentile(values, 95) / 1e6),
                  'share_of_sample_time_percent': 100 * sum(values) / total_ns}
        for key, value in metric.items():
            close_number(summary['stages'][name][key], value, name + '/' + key)
        require(stream.count('B_PROFILE_STAGE: {} mean={:.3f} ms, share={:.2f}%'.format(
            name, metric['mean_ms'], metric['share_of_sample_time_percent'])) == 1, 'Notebook stage metric differs')
        stages[name] = metric
    require(sum(stage['sum_ns'] for stage in stages.values()) == total_ns, 'Total attributed time differs')
    require(stream.count('B_PROFILE_COMPLETE: 30 timed + 3 warmup; checked loop {:.3f} FPS; no optimization claim'.format(
        metrics['loop_fps'])) == 1, 'Notebook loop FPS differs')
    return {**metrics, 'stages': stages, 'warmup_frames': 3, 'loop_start_ns': start, 'loop_end_ns': end,
            'loop_ns': loop_ns, 'sample_sum_ns': total_ns, 'loop_unattributed_ns': loop_ns - total_ns,
            'status': 'PASS_INDEPENDENT_RAW_BOUNDARIES_STAGE_TOTALS_LOOP_AND_NOTEBOOK_METRICS',
            'limit': 'Repeated fixed input with verification/layout/native submission/hash; no SD input latency, PL-only cycles or calibrated display scan Hz.'}


def verify_display(cells, report, members, output):
    display, profile = report['display'], report['profile']
    require(display['closed'] is True and display['visual_status'] == 'PENDING_USER_OBSERVATION',
            'Original display pending/closed record changed')
    require(display['configured_mode'] == {'width': 1280, 'height': 720, 'bpp': 24, 'requested_hz': 60, 'format': 'BGR24'},
            'Video mode differs')
    require(len(display['submissions']) == 1 and display['submissions'][0]['label'] == 'BLUE_GREEN_RED_WITH_POSITION_LINES',
            'Color submission ledger differs')
    for status in (display['submissions'][0]['vdma_status'], display['final_vdma_status']):
        video_status(status)
    colors = decode_png(members['b_color_pattern.png'])
    expected = np.empty_like(colors)
    expected[:, :426] = [0, 0, 255]
    expected[:, 426:853] = [0, 255, 0]
    expected[:, 853:] = [255, 0, 0]
    expected[:4] = expected[-4:] = expected[:, :4] = expected[:, -4:] = 255
    expected[358:362] = 255
    expected[:, 638:642] = 255
    require(np.array_equal(colors, expected), 'Color pattern pixels differ')
    require(display['color_reference'] == {'name': 'b_color_pattern.png', 'sha256': digest(members['b_color_pattern.png'])} and
            display['submissions'][0]['sha256_bgr'] == digest(colors[:, :, ::-1].tobytes()), 'Color reference hash differs')
    medical = decode_png(members['b_profile_display.png'])
    green, mask = (output & 255).astype(np.uint8), ((output >> 16) & 255).astype(np.uint8)
    grey = np.repeat(green[:, :, None], 3, axis=2)
    marked = grey.copy()
    marked[mask != 0] = [0, 255, 0]
    expected = np.full_like(medical, 16)
    expected[128:640, 64:576] = grey
    expected[128:640, 704:1216] = marked
    expected[24:48, 364:412] = 255  # Final timed index 29, same original marker calculation.
    comparison = np.ones((720, 1280), dtype=bool)
    comparison[76:110, 60:690] = False
    comparison[76:110, 700:1270] = False
    comparison[660:700, 60:1270] = False
    require(np.array_equal(medical[comparison], expected[comparison]), 'Medical image panels/marker differ from actual array')
    require(profile['final_display'] == {'name': 'b_profile_display.png', 'sha256': digest(members['b_profile_display.png']),
            'sha256_bgr': digest(medical[:, :, ::-1].tobytes()), 'marker_index': 29}, 'Final display provenance differs')
    embedded = [output['data']['image/png'] for output in cells[5]['outputs']
                if output.get('output_type') == 'display_data' and 'image/png' in output.get('data', {})]
    require(len(embedded) == 1, 'Final notebook image missing/not unique')
    png = base64.b64decode(''.join(flatten_text(embedded[0]).split()), validate=True)
    require(np.array_equal(decode_png(png), medical), 'Notebook final image differs from saved PNG')
    return {'status': 'PASS_COLOR_AND_REAL_OUTPUT_PANES_MARKER_BGR_HASH_AND_NOTEBOOK_IMAGE',
            'medical_png_sha256': digest(members['b_profile_display.png']), 'color_png_sha256': digest(members['b_color_pattern.png']),
            'limit': 'Independent caption rectangles excluded only for platform font differences; full notebook and PNG match. Photographs reviewed separately.'}


def verify_records(notebook, report, manifest, package, members):
    baseline = json.loads(BASELINE.read_bytes())
    require(report['profile_manifest'] == manifest and report['manifest'] == baseline, 'Release manifest differs')
    require(report['status'] == 'B_PROFILE_RECORDS_READY_VISUAL_PENDING' and not any(
        name in report for name in ('error', 'failed_stage', 'retained_buffers', 'retained_display_frames')), 'Incomplete/failed profile')
    require((report['pynq'], report['python'], report['kernel']) == ('3.0.1', '3.10.4', '5.15.19-xilinx-v2022.1'), 'Board runtime differs')
    require(report['drivers'] == DRIVERS, 'Official driver binding differs')
    require(type(report['overlay_downloads']) is int and report['overlay_downloads'] == 1, 'Single overlay download differs')
    cells, streams, notebook_checks = verify_notebook(notebook, manifest)
    validation = report['profile_package_validation']
    require(validation['fixed_artifacts'] == 'PASS_EXACT_SHA256_EXCLUDING_NOTEBOOK_JSON' and
            validation['mutable_notebook_json'] == ['b_integration_check.ipynb', 'b_performance_profile.ipynb'] and
            validation['notebook_code_sha256'] == manifest['notebook_validation']['sha256'] and
            validation['baseline'] == report['package_validation'], 'Profile package validation differs')
    old_validation = validation['baseline']
    require(old_validation['fixed_artifacts'] == 'PASS_EXACT_SHA256' and old_validation['notebook_code'] == 'PASS_CANONICAL_CODE_SHA256' and
            old_validation['notebook_code_sha256'] == baseline['notebook_validation']['sha256'] and
            old_validation['original_notebook_sha256'] == baseline['artifacts']['b_integration_check.ipynb']['sha256'] and
            all(re.fullmatch('[0-9a-f]{64}', value) for value in (old_validation['current_notebook_sha256'], validation['current_notebook_sha256'])),
            'Inherited notebook code validation differs')
    profile = report['profile']
    require(profile['contract'] == manifest['contract'] and profile['total_algorithm_frames'] == 34,
            'Profile workload contract differs')
    require(len(report['transfers']) == 1, 'Unexpected smoke/full-suite ledger')
    smoke = report['transfers'][0]
    require((smoke['side'], smoke['mode'], smoke['pattern'], smoke['words'], smoke['send_bytes'], smoke['recv_bytes']) ==
            (256, 3, 'vessel_stripes', 65536, 262144, 262144) and smoke['status'] == 'PASS_EXACT_SEGMENTATION_WORDS' and
            smoke['frame_status'] == 16385, 'Smoke record differs')
    dma_status(smoke['dma_status'])
    for value in (smoke['tx_address'], smoke['rx_address']):
        address(value, 262144)
    require(abs(smoke['tx_address'] - smoke['rx_address']) >= 262144, 'Smoke DDR overlap')
    smoke_input = regenerate_input(256, 'vessel_stripes', 0, package)
    smoke_expected = independent_expected(smoke_input, 3)
    require(smoke['input_sha256'] == word_digest(smoke_input) and
            smoke['expected_sha256'] == smoke['output_sha256'] == word_digest(smoke_expected), 'Independent smoke hash differs')
    source = regenerate_input(512, 'stare', 0, package)
    expected = independent_expected(source, 3)
    require(profile['input_sha256'] == word_digest(source) and profile['expected_sha256'] == word_digest(expected), 'Independent STARE input/golden differs')
    buffers = profile['algorithm_buffers']
    require(set(buffers) == {'tx', 'rx'} and profile['native_video_cacheable_frames'] is True, 'Algorithm/video allocation properties differ')
    for description in buffers.values():
        buffer_description(description, [262144], [4], 'uint32', 1048576)
    tx, rx = buffers['tx']['physical_address'], buffers['rx']['physical_address']
    require(abs(tx - rx) >= 1048576, 'Algorithm DDR overlap')
    frames = [{'frame': 1, 'side': 256, 'words': 65536, 'output_sha256': word_digest(smoke_expected)}]
    require(len(profile['samples']) == 33, 'Incomplete profiling sample ledger')
    for index, sample in enumerate(profile['samples']):
        require((sample['words'], sample['send_bytes'], sample['recv_bytes']) == (262144, 1048576, 1048576) and
                sample['status'] == 'PASS_EXACT_SEGMENTATION_WORDS', 'Profile compare/byte count differs')
        count = index + 2
        require(sample['frame_status'] == count | count << 14, 'Profile frame counter/error differs')
        require(sample['output_sha256'] == word_digest(expected), 'Independent profile output hash differs')
        dma_status(sample['dma_status'])
        video_status(sample['vdma_status'])
        description = sample['display_buffer']
        buffer_description(description, [720, 1280, 3], [3840, 3, 1], 'uint8', 2764800)
        location = description['physical_address']
        require(all(location + 2764800 <= algorithm or algorithm + 1048576 <= location for algorithm in (tx, rx)),
                'Video/algorithm DDR overlap')
        frames.append({'frame': count, 'side': 512, 'words': 262144, 'output_sha256': sample['output_sha256']})
    output_bytes = members['b_profile_output_512.npy']
    require(profile['final_output'] == {'name': 'b_profile_output_512.npy', 'sha256': digest(output_bytes), 'word_sha256': word_digest(expected)},
            'Saved raw output hash differs')
    output = np.load(io.BytesIO(output_bytes), allow_pickle=False)
    require(output.dtype == np.dtype('<u4') and output.shape == (512, 512), 'Saved raw output format differs')
    require(np.array_equal(output, expected), 'Actual raw FPGA output differs from independent M0')
    require(np.all(((output >> 16) & 255)[(source >> 24) == 0] == 0), 'Final mask outside FOV')
    return {'frames': frames, 'notebook': notebook_checks,
            'timing': verify_timing(profile, streams[4]), 'display': verify_display(cells, report, members, output),
            'raw_array': {'name': 'b_profile_output_512.npy', 'words': 262144, 'mismatched_words': 0,
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
    manifest_data = (args.package / 'b_profile_manifest.json').read_bytes()
    require(manifest_data == RELEASE.read_bytes(), 'Local profiling release differs')
    manifest = json.loads(manifest_data)
    validate_profile_package(args.package, manifest)
    require(args.notebook.stat().st_size <= 1_000_000, 'Notebook exceeds size limit')
    notebook_data, bundle_data = args.notebook.read_bytes(), args.bundle.read_bytes()
    members = read_bundle(args.bundle)
    report = json.loads(members['b_profile_result.json'])
    checks = verify_records(json.loads(notebook_data), report, manifest, args.package, members)
    require(args.notebook.read_bytes() == notebook_data and args.bundle.read_bytes() == bundle_data, 'Downloads changed during verification')
    photos = {'monitor_color_photo.jpg': args.color_photo.read_bytes(), 'monitor_medical_photo.jpg': args.medical_photo.read_bytes()}
    for data in photos.values():
        with Image.open(io.BytesIO(data)) as image:
            require(image.format == 'JPEG' and min(image.size) >= 700, 'Invalid supplied photo')
            image.verify()
    args.destination.mkdir(parents=True)
    args.raw_destination.mkdir(parents=True)
    raw = {'b_performance_profile_executed.ipynb': notebook_data, 'b_profile_bundle.zip': bundle_data, **members, **photos}
    files = {}
    for name, data in raw.items():
        path = args.raw_destination / name
        path.write_bytes(data)
        require(path.read_bytes() == data, 'Raw byte preservation failed')
        files[name] = {'path': str(path.resolve()), 'bytes': len(data), 'sha256': digest(data)}
    (args.destination / 'b_profile_result.json').write_bytes(members['b_profile_result.json'])
    for name, value in checks.items():
        write_json(args.destination / (name + '_verification.json'), value)
    csv = ['index,warmup,start_ns,end_ns,sample_ns,' + ','.join(name + '_ns' for name in STAGES)]
    for sample in report['profile']['samples']:
        csv.append(','.join(str(value) for value in [sample['index'], int(sample['warmup']), sample['boundaries_ns'][0],
            sample['boundaries_ns'][-1], sample['sample_ns'], *[sample['durations_ns'][name] for name in STAGES]]))
    (args.destination / 'timing_samples.csv').write_text('\n'.join(csv) + '\n', encoding='utf-8', newline='\n')
    write_json(args.destination / 'archive_manifest.json', {
        'status': 'PASS_B_PROFILE_BOARD_RECORDS_REAL_ARRAY_DISPLAY_AND_RAW_TIMESTAMPS',
        'client_received_date': '2026-10-12', 'verified_host_utc': datetime.now(timezone.utc).isoformat(),
        'board_clock_utc_unverified': report['board_clock_utc_unverified'], 'revision': manifest['revision'],
        'release_manifest_sha256': digest(manifest_data), 'overlay_downloads': 1,
        'frame_records_verified': 34, 'input_words_verified': 8716288, 'raw_output_words_verified': 262144,
        'warmup_frames': 3, 'timed_frames': 30, 'files': files,
        'scope': 'Independent input/output hashes, final real array and pixels; all raw stage/loop timestamp formulas recomputed. '
                 'Only final array downloaded. No new optimization, PL-only/SD/scan-Hz/clinical PASS. '
                 'Raw JSON visual PENDING and original 2022 clock retained; supplied photos assessed separately.'})
    print('B_PROFILE_ARCHIVED: 34 frame records, 262144 actual output words, 30 timed samples, all stage and loop clocks reconciled')


if __name__ == '__main__':
    main()
