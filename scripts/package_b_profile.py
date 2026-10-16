"""Compose a new profiling folder; leave every proven B r2 file unchanged."""
import argparse
import ast
import json
import re
import shutil
import tempfile
from pathlib import Path

from b_profile_board_test import REVISION, NOTEBOOK, GUIDE, INHERITED, ARTIFACTS, CONTRACT, validate_profile_package
from b_integration_board_test import validate_b_package, notebook_code_hash
from check_b_hardware import info, require

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('scripts/b_profile_board_test.py', 'scripts/package_b_profile.py',
           'tests/test_b_profile.py', 'notebooks/b_performance_profile.ipynb',
           'docs/b_performance_profile_steps.md', 'docs/b_profile_precheck_recovery_steps.md')
OFFICIAL = ('references/PYNQ/v3.0.1/pynq/lib/video/dma.py',
            'references/PYNQ/v3.0.1/pynq/lib/video/hierarchies.py',
            'references/PYNQ/v3.0.1/pynq/buffer.py')
HISTORY = ROOT / 'results/b_integration_2017_4_r2/release_manifest.json'
BASELINE_TIMING = ROOT / 'results/b_integration_2017_4_r2/board_execution_2026-10-12/timing_verification.json'
PROFILE_HISTORY = ROOT / 'results/b_profile_2017_4_r1/release_manifest.json'


def stage_package(baseline, staged, regression):
    baseline, staged = Path(baseline), Path(staged)
    require((baseline / 'b_manifest.json').read_bytes() == HISTORY.read_bytes(), 'Original r2 manifest changed')
    original = json.loads((baseline / 'b_manifest.json').read_text(encoding='utf-8'))
    validate_b_package(baseline, original)
    for name, recorded in original['artifacts'].items():
        require(info(baseline / name) == recorded, 'Original r2 file changed: ' + name)
    for name in INHERITED:
        shutil.copyfile(baseline / name, staged / name)
    shutil.copyfile(ROOT / 'scripts/b_profile_board_test.py', staged / 'b_profile_board_test.py')
    shutil.copyfile(ROOT / 'notebooks' / NOTEBOOK, staged / NOTEBOOK)
    shutil.copyfile(ROOT / 'docs/b_performance_profile_steps.md', staged / GUIDE)
    # Parse using the board's Python language version, without running notebook code.
    ast.parse((staged / 'b_profile_board_test.py').read_text(encoding='utf-8'), feature_version=(3, 10))
    notebook = json.loads((staged / NOTEBOOK).read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            ast.parse(''.join(cell['source']), feature_version=(3, 10))
            require(cell['execution_count'] is None and cell['outputs'] == [], 'Release notebook must remain unexecuted')
    snapshot = ROOT / 'references/PYNQ/v3.0.1'
    pinned = json.loads((snapshot / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    upstream = {entry['path']: {key: entry[key] for key in ('bytes', 'sha256')} for entry in pinned['files']}
    for name in OFFICIAL:
        relative = (ROOT / name).relative_to(snapshot).as_posix()
        require(info(ROOT / name) == upstream[relative], 'Pinned official source changed: ' + name)
    manifest = {'revision': REVISION, 'board_status': 'NOT_RUN',
        'host_status': 'PASS_COMPOSITION_AND_HOST_CONTRACT_TESTS_ONLY',
        'contract': CONTRACT, 'artifacts': {name: info(staged / name) for name in sorted(ARTIFACTS)},
        'notebook_validation': {'algorithm': 'sha256-code-cells-v1', 'sha256': notebook_code_hash(notebook)},
        'inherited_notebook_validation': original['notebook_validation'],
        'software_fix': {'superseded_release': str(PROFILE_HISTORY.relative_to(ROOT)).replace('\\', '/'),
                         'superseded_manifest': info(PROFILE_HISTORY),
                         'reason': 'R1 incorrectly locked inherited notebook full JSON before canonical B validation',
                         'measurement_contract_unchanged': CONTRACT == json.loads(PROFILE_HISTORY.read_text(encoding='utf-8'))['contract'],
                         'runtime_notebook_policy': 'Canonical code-cell SHA256 for both notebooks; output/metadata/Markdown save changes accepted'},
        'baseline': {'manifest': str(HISTORY.relative_to(ROOT)).replace('\\', '/'), **info(HISTORY),
                     'all_13_original_r2_files_unchanged': True, 'hardware_rebuilt': False,
                     'board_timing_evidence': {'path': str(BASELINE_TIMING.relative_to(ROOT)).replace('\\', '/'),
                                               **info(BASELINE_TIMING)}},
        'sources': {name: info(ROOT / name) for name in SOURCES},
        'official_driver_sources': {name: info(ROOT / name) for name in OFFICIAL},
        'official_pynq_commit': pinned['commit'],
        'host_regression': regression,
        'limits': 'Stage profiling has not run on the board. No performance improvement, PL-cycle, '
                  'display-scan-rate or medical-quality PASS. Original B r2 evidence stays separate.'}
    (staged / 'b_profile_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


def check_saved_notebook(staged, manifest):
    staged = Path(staged)
    raw = {name: (staged / name).read_bytes() for name in (NOTEBOOK, 'b_integration_check.ipynb')}
    try:
        for name, payload in raw.items():
            notebook = json.loads(payload)
            notebook['metadata']['host_autosave_probe'] = 'HOST ONLY'
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    cell['execution_count'] = 1
                    cell['outputs'] = [{'output_type': 'stream', 'name': 'stdout',
                                        'text': 'HOST AUTOSAVE CONTRACT CHECK ONLY\n'}]
            (staged / name).write_text(json.dumps(notebook), encoding='utf-8', newline='\n')
        return validate_profile_package(staged, manifest)
    finally:
        for name, payload in raw.items():
            (staged / name).write_bytes(payload)


def stage_fix(baseline, destination, manifest):
    """Create the three-file correction only after proving the minimal delta."""
    baseline, destination = Path(baseline), Path(destination)
    old_manifest_path = baseline / 'b_profile_manifest.json'
    require(old_manifest_path.read_bytes() == PROFILE_HISTORY.read_bytes(), 'Original profiling r1 manifest changed')
    old = json.loads(old_manifest_path.read_text(encoding='utf-8'))
    for name, recorded in old['artifacts'].items():
        require(info(baseline / name) == recorded, 'Original profiling r1 artifact changed: ' + name)
    changed = {'b_profile_board_test.py', GUIDE}
    require(set(old['artifacts']) == set(manifest['artifacts']), 'Fix changed release inventory')
    for name in set(old['artifacts']) - changed:
        require(old['artifacts'][name] == manifest['artifacts'][name], 'Fix changed another artifact: ' + name)
    require(old['contract'] == manifest['contract'], 'Fix changed timing workload')
    before = (baseline / 'b_profile_board_test.py').read_text(encoding='utf-8')
    expected = before.replace("REVISION = 'b_profile_r1_stage_timestamps'", "REVISION = 'b_profile_r2_inherited_notebook_code_check'")
    expected = expected.replace("FIXED = INHERITED | {'b_profile_board_test.py', GUIDE}",
        "FIXED = (INHERITED - {b.NOTEBOOK}) | {'b_profile_board_test.py', GUIDE}\nARTIFACTS = FIXED | {b.NOTEBOOK, NOTEBOOK}")
    expected = expected.replace("set(manifest.get('artifacts', {})) == FIXED | {NOTEBOOK}",
                                "set(manifest.get('artifacts', {})) == ARTIFACTS")
    expected = expected.replace("    return {'fixed_artifacts': 'PASS_EXACT_SHA256', 'notebook_code_sha256': code_hash,",
        "    # The inherited notebook uses the already-proven B code-cell contract.\n"
        "    # Both notebook JSONs may change on save; neither can change executable code.\n"
        "    return {'fixed_artifacts': 'PASS_EXACT_SHA256_EXCLUDING_NOTEBOOK_JSON', 'notebook_code_sha256': code_hash,\n"
        "            'mutable_notebook_json': [b.NOTEBOOK, NOTEBOOK],")
    require(expected == (ROOT / 'scripts/b_profile_board_test.py').read_text(encoding='utf-8'),
            'Profiler fix changed more than revision and notebook validation')
    require(not destination.exists(), 'Preserve earlier patch package')
    destination.mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/b_profile_board_test.py', destination / 'b_profile_board_test.py')
    shutil.copyfile(ROOT / 'docs/b_performance_profile_steps.md', destination / GUIDE)
    (destination / 'b_profile_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return {'files': {path.name: info(path) for path in destination.iterdir()},
            'unchanged_artifacts': sorted(set(old['artifacts']) - changed),
            'measurement_code_and_contract_unchanged': True}


def main():
    parser = argparse.ArgumentParser()
    for name in ('baseline', 'destination', 'results'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--patch-baseline', type=Path, required=True)
    parser.add_argument('--patch-destination', type=Path, required=True)
    args = parser.parse_args()
    require(not args.destination.exists() and not (args.results / 'release_manifest.json').exists(),
            'Preserve earlier release')
    log_path = args.results / 'host_tests.log'
    tests = log_path.read_text(encoding='utf-8-sig')
    count = re.search(r'Ran (\d+) tests', tests)
    require(count and int(count.group(1)) >= 22 and '\nOK' in tests and 'FAILED' not in tests,
            'Profiling host regressions incomplete')
    tested = json.loads((args.results / 'host_test_sources.json').read_text(encoding='utf-8'))
    require(tested['log'] == info(log_path), 'Host test log changed')
    for name in SOURCES:
        require(tested['sources'][name] == info(ROOT / name), 'Source changed after tests: ' + name)
    regression = {'tests': int(count.group(1)), 'log': info(log_path),
                  'scope': 'Host fakes for timing attribution and ownership/error handling; never physical board evidence'}
    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory)
        manifest = stage_package(args.baseline, staged, regression)
        validation = {'original_notebook': validate_profile_package(staged, manifest),
                      'autosaved_notebook': check_saved_notebook(staged, manifest)}
        validate_profile_package(staged, manifest)
        args.destination.mkdir(parents=True)
        for path in staged.iterdir():
            shutil.copyfile(path, args.destination / path.name)
    require(len(list(args.destination.iterdir())) == 17, 'Expected 17 profiling files')
    require(all(info(args.destination / name) == info(args.baseline / name) for name in INHERITED),
            'Inherited B r2 file changed')
    validation['minimal_fix'] = stage_fix(args.patch_baseline, args.patch_destination, manifest)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    (args.results / 'release_manifest.json').write_text(payload, encoding='utf-8', newline='\n')
    validation.update(status='PASS_HOST_PROFILING_PACKAGE', board_status='NOT_RUN', files=17,
                      destination=str(args.destination.resolve()), inherited_files_unchanged=sorted(INHERITED))
    (args.results / 'package_validation.json').write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('B_PROFILE_R2_READY_HOST_VERIFIED_BOARD_NOT_RUN', args.destination, args.patch_destination)


if __name__ == '__main__':
    main()
