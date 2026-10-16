"""Compose a separate CPU-copy comparison from the immutable 18-file layout release."""
import argparse
import ast
import json
import re
import shutil
import tempfile
from pathlib import Path

from b_snapshot_board_test import REVISION, NOTEBOOK, GUIDE, CONTRACT, INHERITED, ARTIFACTS, validate_package
from b_layout_board_test import validate_package as validate_layout
from b_integration_board_test import notebook_code_hash
from check_b_hardware import info, require

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'results/b_layout_2017_4_r1/release_manifest.json'
BOARD_TIMING = ROOT / 'results/b_layout_2017_4_r1/board_execution_2026-10-12/timing_verification.json'
SOURCES = ('scripts/b_snapshot_board_test.py', 'scripts/package_b_snapshot.py',
           'tests/test_b_snapshot.py', 'notebooks/b_snapshot_compare.ipynb', 'docs/b_snapshot_compare_steps.md')
OFFICIAL = ('references/PYNQ/v3.0.1/pynq/lib/dma.py', 'references/PYNQ/v3.0.1/pynq/lib/video/dma.py',
            'references/PYNQ/v3.0.1/pynq/lib/video/hierarchies.py', 'references/PYNQ/v3.0.1/pynq/buffer.py')


def stage_package(baseline, staged, regression):
    baseline, staged = Path(baseline), Path(staged)
    require((baseline / 'b_layout_manifest.json').read_bytes() == HISTORY.read_bytes(), 'Immutable layout manifest changed')
    original = json.loads(HISTORY.read_text(encoding='utf-8'))
    validate_layout(baseline, original)
    for name, recorded in original['artifacts'].items():
        require(info(baseline / name) == recorded, 'Original layout artifact changed: ' + name)
    for name in INHERITED:
        shutil.copyfile(baseline / name, staged / name)
    shutil.copyfile(ROOT / 'scripts/b_snapshot_board_test.py', staged / 'b_snapshot_board_test.py')
    shutil.copyfile(ROOT / 'notebooks' / NOTEBOOK, staged / NOTEBOOK)
    shutil.copyfile(ROOT / 'docs/b_snapshot_compare_steps.md', staged / GUIDE)
    for name in sorted(n for n in ARTIFACTS if n.endswith('.py')):
        ast.parse((staged / name).read_text(encoding='utf-8'), feature_version=(3, 10))
    notebook = json.loads((staged / NOTEBOOK).read_text(encoding='utf-8'))
    code = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
    require(len(code) == 7, 'Expected seven snapshot code cells')
    for cell in code:
        ast.parse(''.join(cell['source']), feature_version=(3, 10))
        require(cell['execution_count'] is None and cell['outputs'] == [], 'Release notebook must remain unexecuted')
    snapshot = ROOT / 'references/PYNQ/v3.0.1'
    pinned = json.loads((snapshot / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    upstream = {entry['path']: {key: entry[key] for key in ('bytes', 'sha256')} for entry in pinned['files']}
    for name in OFFICIAL:
        require(info(ROOT / name) == upstream[(ROOT / name).relative_to(snapshot).as_posix()], 'Official driver source changed: ' + name)
    manifest = {'revision': REVISION, 'board_status': 'NOT_RUN', 'performance_improvement': 'NOT_MEASURED',
        'host_status': 'PASS_CPU_COPY_PIXEL_EQUIVALENCE_AND_HOST_CONTRACT_TESTS_ONLY',
        'contract': CONTRACT, 'artifacts': {name: info(staged / name) for name in sorted(ARTIFACTS)},
        'notebook_validation': {'algorithm': 'sha256-code-cells-v1', 'sha256': notebook_code_hash(notebook)},
        'baseline': {'manifest': str(HISTORY.relative_to(ROOT)).replace('\\', '/'), **info(HISTORY),
                     'all_18_files_unchanged': True, 'hardware_rebuilt': False,
                     'previous_real_board_timing': {'path': str(BOARD_TIMING.relative_to(ROOT)).replace('\\', '/'), **info(BOARD_TIMING)},
                     'previous_fps_policy': 'Previous layout measurement is context only; new direct/snapshot groups must actually run'},
        'sources': {name: info(ROOT / name) for name in SOURCES},
        'official_driver_sources': {name: info(ROOT / name) for name in OFFICIAL}, 'official_pynq_commit': pinned['commit'],
        'host_regression': regression,
        'changes': 'One np.copyto into a reused 1 MiB ordinary CPU array after original receive wait; '
                   'read-only between captures. Same cached renderer, all word/byte/counter/hash/native-video checks retained.',
        'native_policy': 'Original receive wait invalidates through original driver. No allocation/cache/mmap/VDMA override; '
                         'cacheable property is not treated as proof of kernel mapping.',
        'limits': 'Snapshot strategy and 11-stage timing have not run on the board. CPU copy cost is inside the measured loop. '
                  'No SD/PL-only/CPU-algorithm/scan-Hz/clinical or complete performance acceptance.'}
    (staged / 'b_snapshot_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


def check_saved_notebooks(staged, manifest):
    staged = Path(staged)
    names = (NOTEBOOK, 'b_layout_compare.ipynb', 'b_integration_check.ipynb')
    raw = {name: (staged / name).read_bytes() for name in names}
    try:
        for name, payload in raw.items():
            notebook = json.loads(payload)
            notebook['metadata']['host_autosave_probe'] = 'HOST ONLY'
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    cell['execution_count'] = 1
                    cell['outputs'] = [{'output_type': 'stream', 'name': 'stdout', 'text': 'HOST SAVE PROBE ONLY\n'}]
                else:
                    cell['source'] = ['Host-only Markdown save change\n']
            (staged / name).write_text(json.dumps(notebook), encoding='utf-8', newline='\n')
        return validate_package(staged, manifest)
    finally:
        for name, payload in raw.items():
            (staged / name).write_bytes(payload)


def main():
    parser = argparse.ArgumentParser()
    for name in ('baseline', 'destination', 'results'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    require(not args.destination.exists() and not (args.results / 'release_manifest.json').exists(), 'Preserve earlier release')
    log_path = args.results / 'host_tests.log'
    tests = log_path.read_text(encoding='utf-8-sig')
    count = re.search(r'Ran (\d+) tests', tests)
    require(count and int(count.group(1)) >= 24 and '\nOK' in tests and 'FAILED' not in tests and 'skipped' not in tests,
            'Snapshot host regressions incomplete')
    tested = json.loads((args.results / 'host_test_sources.json').read_text(encoding='utf-8'))
    require(tested['log'] == info(log_path), 'Host test log changed')
    for name in SOURCES:
        require(tested['sources'][name] == info(ROOT / name), 'Source changed after tests: ' + name)
    regression = {'tests': int(count.group(1)), 'log': info(log_path),
                  'scope': 'Host CPU ownership/byte/pixel checks, actual downloaded array, synthetic driver lifecycle and timing. '
                           'No physical execution or measured improvement of the snapshot strategy.'}
    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary)
        manifest = stage_package(args.baseline, staged, regression)
        validation = {'original_notebooks': validate_package(staged, manifest),
                      'autosaved_notebooks': check_saved_notebooks(staged, manifest)}
        validate_package(staged, manifest)
        args.destination.mkdir(parents=True)
        for path in staged.iterdir():
            shutil.copyfile(path, args.destination / path.name)
    require(len(list(args.destination.iterdir())) == 22, 'Expected twenty-two snapshot files')
    require(all(info(args.destination / name) == info(args.baseline / name) for name in INHERITED), 'Inherited layout file changed')
    (args.results / 'release_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    validation.update(status='PASS_HOST_SNAPSHOT_PACKAGE', board_status='NOT_RUN', performance_improvement='NOT_MEASURED',
                      files=22, code_cells=7, inherited_files_unchanged=sorted(INHERITED), destination=str(args.destination.resolve()))
    (args.results / 'package_validation.json').write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('B_SNAPSHOT_READY_HOST_VERIFIED_BOARD_NOT_RUN', args.destination)


if __name__ == '__main__':
    main()
