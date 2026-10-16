"""Host release integrity/provenance checks, not a new board measurement."""
import ast
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from pynq_app.protocol import file_info, require, validate_package, write_json
from verify_browser_w1_archive import check_run


def main():
    destination = ROOT / 'results/browser_w1_2026-10-13'
    package = ROOT / 'build/deploy/browser_a4_w1_r1'
    manifest = validate_package(package)
    before = json.loads((ROOT / 'results/browser_transition_2026-10-13/before_change.json').read_bytes())
    immutable = {name: file_info(ROOT / name) for name in before['immutable_files']}
    require(immutable == before['immutable_files'], 'A previous protected source/release/evidence file changed')
    sources = {}
    prohibited = ('software', 'cv2', 'a1_point_board_test', 'a2_gaussian_board_test', 'a3_background_board_test', 'a4_segmentation_board_test', 'prepare_a4_vectors')
    for path in sorted((ROOT / 'pynq_app').glob('*.py')):
        tree = ast.parse(path.read_bytes(), feature_version=(3, 10))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(name.name for name in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        require(not any(name == prefix or name.startswith(prefix + '.') for name in imports for prefix in prohibited), 'Production CPU medical/reference import')
        require(not any('video' in name or 'vdma' in name for name in imports), 'New application has a video dependency')
        sources[path.relative_to(ROOT).as_posix()] = {'file': file_info(path), 'imports': imports}
        require(file_info(path) == file_info(package / 'pynq_app' / path.name), 'Package differs from current application source')
    for path in sorted((ROOT / 'ui').iterdir()):
        if path.is_file():
            require(file_info(path) == file_info(package / 'ui' / path.name), 'Package UI differs from source')
    archive_path = package.parent / 'browser_a4_w1_r1.zip'
    with zipfile.ZipFile(archive_path) as archive:
        require(set(archive.namelist()) == set(manifest['artifacts']) | {'browser_manifest.json'}, 'ZIP inventory differs')
        for name in archive.namelist():
            require(archive.read(name) == (package / name).read_bytes(), 'ZIP bytes differ')
    notebook_path = package.parent / 'browser_start.ipynb'
    notebook = json.loads(notebook_path.read_bytes())
    require(notebook_path.read_bytes() == (ROOT / 'notebooks/browser_start.ipynb').read_bytes(), 'Upload notebook differs')
    code = [''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code']
    require(len(code) == 6 and file_info(archive_path)['sha256'] in code[0], 'Startup hash/steps mismatch')
    for source in code:
        ast.parse(source, feature_version=(3, 10))
    tests = (destination / 'host_tests_ownership_final.log').read_text(encoding='utf-8')
    require('Ran 23 tests' in tests and tests.rstrip().endswith('OK') and 'skipped' not in tests, 'Current host tests not passed')
    qa = json.loads((destination / 'browser_qa.json').read_bytes())
    host_path = Path(qa['download_path'])
    host = []
    with zipfile.ZipFile(host_path) as archive:
        require(json.loads(archive.read('capabilities.json'))['evidence_kind'] == 'HOST_TEST_DOUBLE_NOT_BOARD', 'Host fixture mislabeled as real board')
        qa_manifest = json.loads(archive.read('browser_manifest.json'))
        # Last production edit strengthened exception/cancellation recording;
        # UI/input/A4 bytes used for the browser screenshot are unchanged.
        stable = [name for name in manifest['artifacts'] if name.startswith(('ui/', 'inputs/', 'evaluation_only/')) or name in manifest['baseline_original_files']]
        require(all(manifest['artifacts'][name] == qa_manifest['artifacts'][name] for name in stable), 'Browser QA UI/data/A4 changed after capture')
        session = json.loads(archive.read('session.json'))
        for run_id in session['run_ids']:
            record = json.loads(archive.read(run_id + '/record.json'))
            host.append(check_run(archive, record, package, manifest))
        require(len(host) == 24, 'Browser QA did not complete expected 24 fixture runs')
        browser = [json.loads(archive.read(item['run_id'] + '/browser_timing.json')) for item in host]
        loops = [item for item in browser if item['loop_id'] is not None]
        require(len(loops) == 20 and [item['loop_index'] for item in loops] == list(range(1, 21)), 'UI continuous loop observations missing')
        for index, item in enumerate(loops, 1):
            require(item['request_to_render_ms'] == item['render_done_ms'] - item['request_start_ms'], 'Host client interval mismatch')
            fps = index * 1000 / (item['render_done_ms'] - item['loop_start_ms']) if index >= 2 else None
            require(item['browser_actual_fps'] == fps, 'Host client FPS formula mismatch')
    report = {'status': 'HOST_RELEASE_INTEGRITY_PASS_NOT_BOARD', 'tests': {'passed': 23, 'skipped': 0},
              'new_board_status': 'NOT_RUN', 'new_board_measurements': None,
              'protected_original_file_count': len(immutable), 'protected_original_files': immutable,
              'original_a4_12_files_byte_identical': True, 'production_sources': sources,
              'package_manifest': file_info(package / 'browser_manifest.json'), 'zip': file_info(archive_path),
              'notebook': file_info(notebook_path), 'artifact_count': len(manifest['artifacts']),
              'host_browser_fixture_runs': len(host), 'host_browser_fullword_comparisons': sum(item['matched_words'] for item in host),
              'host_browser_observations': 24, 'host_continuous_observations': 20,
              'host_download': {'file': file_info(host_path), 'evidence_kind': 'HOST_TEST_DOUBLE_NOT_BOARD'},
              'host_quality_and_fps_are_board_measurements': False, 'client_pixel_hash_claimed': False,
              'runtime_changes_after_ui_capture': 'Service error/journal/interrupted-await fencing and explicit LF JSON publication; exercised by final 23 host tests. UI/input/A4 bytes identical.',
              'formal_quality_cpu_core_dma_bandwidth_power_stability_acceptance': 'PENDING'}
    write_json(destination / 'release_validation.json', report)
    (destination / 'browser_manifest.json').write_bytes((package / 'browser_manifest.json').read_bytes())
    print('HOST_RELEASE_INTEGRITY_PASS_NOT_BOARD: 23 tests, 24 UI fixture runs, ' + str(report['host_browser_fullword_comparisons']) + ' compared words; ' + str(len(immutable)) + ' originals preserved')


if __name__ == '__main__':
    main()
