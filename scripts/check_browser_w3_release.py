"""Validate final W3 bytes and browser host fixtures; never certify board FPS."""
import ast
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pynq_w3.protocol import file_info, require, validate_package, write_json
from verify_browser_w3_archive import check_run


def check(host_download):
    package = ROOT / 'build/deploy/browser_w3_c2_r1'
    upload = ROOT / 'build/deploy/browser_w3_upload_r1'
    manifest = validate_package(package)
    for folder, dest in (('pynq_w3', 'pynq_w3'), ('ui_w3', 'ui')):
        for path in (ROOT / folder).iterdir():
            if path.is_file() and path.suffix in ('.py', '.js', '.html', '.css'):
                require(file_info(path) == manifest['artifacts'][dest + '/' + path.name], 'Source/package mismatch')
                if path.suffix == '.py': ast.parse(path.read_bytes(), feature_version=(3, 10))
    with zipfile.ZipFile(upload / 'browser_w3_c2_r1.zip') as z:
        require(z.testzip() is None and len(z.namelist()) == 27, 'Bad W3 ZIP')
        require(set(z.namelist()) == set(manifest['artifacts']) | {'browser_manifest.json'}, 'ZIP inventory')
        for name in z.namelist(): require(z.read(name) == (package / name).read_bytes(), 'ZIP bytes differ')
    require((ROOT / 'notebooks/browser_w3_start.ipynb').read_bytes() == (upload / 'browser_w3_start.ipynb').read_bytes(), 'Notebook differs')
    nb = json.loads((upload / 'browser_w3_start.ipynb').read_bytes())
    code = [c for c in nb['cells'] if c['cell_type'] == 'code']
    require(len(code) == 6 and all(c['execution_count'] is None and not c['outputs'] for c in code), 'Release notebook executed')
    require(file_info(upload / 'browser_w3_c2_r1.zip')['sha256'] in ''.join(code[0]['source']), 'Startup hash stale')
    for cell in code: ast.parse(''.join(cell['source']), feature_version=(3, 10))
    tests = (ROOT / 'build/w3_host_tests_final.log').read_text(encoding='utf-8')
    require('Ran 31 tests' in tests and tests.rstrip().endswith('OK') and 'skipped' not in tests, 'Host tests incomplete')
    # Also validate the unchanged, immutable original release inventories.
    old = ROOT / 'build/deploy/browser_a4_w1_r1'
    old_manifest = json.loads((old / 'browser_manifest.json').read_bytes())
    original = {}
    for name, info in old_manifest['artifacts'].items():
        require(file_info(old / name) == info, 'W1 release changed')
        if name.startswith(('pynq_app/', 'ui/')):
            require(file_info(ROOT / name) == info, 'W1 source changed')
        original['W1/' + name] = info
    w2 = ROOT / 'build/deploy/w2_quality_2017_4_r1'
    for name, info in json.loads((w2 / 'w2_manifest.json').read_bytes())['artifacts'].items():
        require(file_info(w2 / name) == info, 'W2 release changed')
        original['W2/' + name] = info
    checked, observed = [], []
    with zipfile.ZipFile(host_download) as z:
        require(json.loads(z.read('capabilities.json'))['evidence_kind'] == 'HOST_TEST_DOUBLE_NOT_BOARD', 'Unlabelled host fixture')
        require(z.read('browser_manifest.json') == (package / 'browser_manifest.json').read_bytes(), 'QA used different final package')
        for rid in json.loads(z.read('session.json'))['run_ids']:
            r = json.loads(z.read(rid + '/record.json'))
            checked.append(check_run(z, r, package, manifest))
            observed.append(json.loads(z.read(rid + '/browser_timing.json')))
    require(len(checked) >= 21, 'Missing final UI runs')
    loops = [o for o in observed if o['loop_id'] is not None]
    require(len(loops) == 20 and [o['loop_index'] for o in loops] == list(range(1, 21)), 'UI loop incomplete')
    visible = True
    for index, obs in enumerate(loops, 1):
        visible = visible and obs['visibility'] == 'visible'
        expected = index * 1000 / (obs['render_done_ms'] - obs['loop_start_ms']) if index >= 2 and visible else None
        require(obs['browser_actual_fps'] == expected, 'UI FPS arithmetic mismatch')
    return dict(status='W3_HOST_RELEASE_VERIFIED_BOARD_NOT_RUN', tests_passed=31, tests_skipped=0,
        artifact_count=26, upload_files={p.name: file_info(p) for p in sorted(upload.iterdir()) if p.is_file()},
        reused_w2_bit=file_info(package/'w2_quality.bit'), reused_w2_hwh=file_info(package/'w2_quality.hwh'),
        original_files_preserved=original, host_ui_download=file_info(host_download), host_ui_tasks=len(checked),
        host_ui_full_words=sum(r['matched_words'] for r in checked), host_ui_png_values=sum(r['matched_png_values'] for r in checked),
        host_ui_continuous_observations=len(loops), host_ui_is_new_board_evidence=False,
        new_browser_fps=None, formal_quality=False, full_performance=False, stability=False)


if __name__ == '__main__':
    result = check(Path(sys.argv[1]))
    out = ROOT / 'results/browser_w3_2026-10-14'
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'release_validation.json', result)
    print(result['status'], result['tests_passed'], 'tests;', result['host_ui_tasks'], 'HOST UI tasks')
