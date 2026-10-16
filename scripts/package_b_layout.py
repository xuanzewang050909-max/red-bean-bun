"""Compose a separate renderer comparison; retain all released hardware/driver bytes."""
import argparse
import ast
import json
import re
import shutil
import tempfile
from pathlib import Path

from b_layout_board_test import REVISION, NOTEBOOK, GUIDE, INHERITED, ARTIFACTS, CONTRACT, validate_package
from b_integration_board_test import validate_b_package, notebook_code_hash
from check_b_hardware import info, require

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('scripts/b_layout_board_test.py', 'scripts/package_b_layout.py',
           'tests/test_b_layout.py', 'notebooks/b_layout_compare.ipynb', 'docs/b_layout_compare_steps.md')
OFFICIAL = ('references/PYNQ/v3.0.1/pynq/lib/video/dma.py',
            'references/PYNQ/v3.0.1/pynq/lib/video/hierarchies.py', 'references/PYNQ/v3.0.1/pynq/buffer.py')
HISTORY = ROOT / 'results/b_integration_2017_4_r2/release_manifest.json'
PROFILE_HISTORY = ROOT / 'results/b_profile_2017_4_r2/release_manifest.json'
PROFILE_VERIFICATION = ROOT / 'results/b_profile_2017_4_r2/board_execution_2026-10-12/timing_verification.json'


def stage_package(baseline, profiler, staged, regression):
    baseline, profiler, staged = Path(baseline), Path(profiler), Path(staged)
    require((baseline / 'b_manifest.json').read_bytes() == HISTORY.read_bytes(), 'Original B r2 manifest changed')
    original = json.loads(HISTORY.read_text(encoding='utf-8'))
    validate_b_package(baseline, original)
    for name, recorded in original['artifacts'].items():
        require(info(baseline / name) == recorded, 'Original B r2 file changed: ' + name)
    require((profiler / 'b_profile_manifest.json').read_bytes() == PROFILE_HISTORY.read_bytes(),
            'Proven profiler r2 manifest changed')
    profile = json.loads(PROFILE_HISTORY.read_text(encoding='utf-8'))
    helper = 'b_profile_board_test.py'
    require(info(profiler / helper) == profile['artifacts'][helper] and
            (ROOT / 'scripts' / helper).read_bytes() == (profiler / helper).read_bytes(),
            'Proven profiler helper changed')
    for name in INHERITED - {helper}:
        shutil.copyfile(baseline / name, staged / name)
    shutil.copyfile(profiler / helper, staged / helper)
    shutil.copyfile(ROOT / 'scripts/b_layout_board_test.py', staged / 'b_layout_board_test.py')
    shutil.copyfile(ROOT / 'notebooks' / NOTEBOOK, staged / NOTEBOOK)
    shutil.copyfile(ROOT / 'docs/b_layout_compare_steps.md', staged / GUIDE)
    for name in sorted(n for n in ARTIFACTS if n.endswith('.py')):
        ast.parse((staged / name).read_text(encoding='utf-8'), feature_version=(3, 10))
    notebook = json.loads((staged / NOTEBOOK).read_text(encoding='utf-8'))
    code = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
    require(len(code) == 7, 'Expected seven staged comparison code cells')
    for cell in code:
        ast.parse(''.join(cell['source']), feature_version=(3, 10))
        require(cell['execution_count'] is None and cell['outputs'] == [], 'Release notebook must remain unexecuted')
    snapshot = ROOT / 'references/PYNQ/v3.0.1'
    pinned = json.loads((snapshot / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    upstream = {entry['path']: {key: entry[key] for key in ('bytes', 'sha256')} for entry in pinned['files']}
    for name in OFFICIAL:
        relative = (ROOT / name).relative_to(snapshot).as_posix()
        require(info(ROOT / name) == upstream[relative], 'Pinned official source changed: ' + name)
    manifest = {'revision': REVISION, 'board_status': 'NOT_RUN', 'performance_improvement': 'NOT_MEASURED',
        'host_status': 'PASS_PIXEL_EQUIVALENCE_AND_HOST_CONTRACT_TESTS_ONLY',
        'contract': CONTRACT, 'artifacts': {name: info(staged / name) for name in sorted(ARTIFACTS)},
        'notebook_validation': {'algorithm': 'sha256-code-cells-v1', 'sha256': notebook_code_hash(notebook)},
        'inherited_notebook_validation': original['notebook_validation'],
        'baseline': {'manifest': str(HISTORY.relative_to(ROOT)).replace('\\', '/'), **info(HISTORY),
                     'all_13_original_r2_files_unchanged': True, 'hardware_rebuilt': False,
                     'profiler_manifest': {'path': str(PROFILE_HISTORY.relative_to(ROOT)).replace('\\', '/'), **info(PROFILE_HISTORY)},
                     'profiler_helper_unchanged': True,
                     'real_profile_verification': {'path': str(PROFILE_VERIFICATION.relative_to(ROOT)).replace('\\', '/'),
                                                   **info(PROFILE_VERIFICATION)}},
        'sources': {name: info(ROOT / name) for name in SOURCES},
        'official_driver_sources': {name: info(ROOT / name) for name in OFFICIAL},
        'official_pynq_commit': pinned['commit'], 'host_regression': regression,
        'changes': 'Static captions from original renderer cached once using runtime font; '
                   'ordinary NumPy canvas and scratch arrays reused. Native video buffers remain owned by original VDMA.',
        'limits': 'New paired comparison has not run on the board. Sequential original/cached groups on one fixed input; '
                  'same full-word/hash/native-display overhead. No SD input latency, pure PL cycles, '
                  'CPU algorithm baseline, calibrated scan rate or clinical quality acceptance.'}
    (staged / 'b_layout_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


def check_saved_notebooks(staged, manifest):
    staged = Path(staged)
    raw = {name: (staged / name).read_bytes() for name in (NOTEBOOK, 'b_integration_check.ipynb')}
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
    for name in ('baseline', 'profiler', 'destination', 'results'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    require(not args.destination.exists() and not (args.results / 'release_manifest.json').exists(), 'Preserve earlier release')
    log_path = args.results / 'host_tests.log'
    tests = log_path.read_text(encoding='utf-8-sig')
    count = re.search(r'Ran (\d+) tests', tests)
    require(count and int(count.group(1)) >= 23 and '\nOK' in tests and 'FAILED' not in tests,
            'Layout host regressions incomplete')
    tested = json.loads((args.results / 'host_test_sources.json').read_text(encoding='utf-8'))
    require(tested['log'] == info(log_path), 'Host test log changed')
    for name in SOURCES:
        require(tested['sources'][name] == info(ROOT / name), 'Source changed after tests: ' + name)
    regression = {'tests': int(count.group(1)), 'log': info(log_path),
                  'scope': 'Host pixel equality on varied inputs and downloaded actual array; synthetic driver lifecycle/faults. '
                           'Never new physical board execution or measured improvement.'}
    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory)
        manifest = stage_package(args.baseline, args.profiler, staged, regression)
        validation = {'original_notebooks': validate_package(staged, manifest),
                      'autosaved_notebooks': check_saved_notebooks(staged, manifest)}
        validate_package(staged, manifest)
        args.destination.mkdir(parents=True)
        for path in staged.iterdir():
            shutil.copyfile(path, args.destination / path.name)
    require(len(list(args.destination.iterdir())) == 18, 'Expected eighteen layout comparison files')
    require(all(info(args.destination / name) == info(args.baseline / name) for name in INHERITED - {'b_profile_board_test.py'}),
            'Inherited B r2 file changed')
    require(info(args.destination / 'b_profile_board_test.py') == info(args.profiler / 'b_profile_board_test.py'),
            'Inherited profiler helper changed')
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    (args.results / 'release_manifest.json').write_text(payload, encoding='utf-8', newline='\n')
    validation.update(status='PASS_HOST_LAYOUT_PACKAGE', board_status='NOT_RUN', performance_improvement='NOT_MEASURED',
                      files=18, code_cells=7, destination=str(args.destination.resolve()),
                      inherited_files_unchanged=sorted(INHERITED))
    (args.results / 'package_validation.json').write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('B_LAYOUT_READY_HOST_VERIFIED_BOARD_NOT_RUN', args.destination)


if __name__ == '__main__':
    main()
