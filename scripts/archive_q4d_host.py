"""Save independently checked C7 host evidence; never mark physical board or quality PASS."""
import argparse
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

from check_q4d_hardware import check as check_hardware
from check_q4d_sharded_rtl import check as check_rtl, info, require
from evaluate_q4_refinement import protected
from pynq_q4d.protocol import validate_package
from q4d_board import validate_q4d

ROOT = Path(__file__).resolve().parents[1]


def main(out):
    require(not out.exists(), 'Preserve earlier evidence')
    hardware = check_hardware(ROOT / 'build/q4d_detector_full_02')
    rtl = check_rtl(ROOT / 'build/q4d_sharded_rtl_02')
    baseline = json.loads((ROOT / 'results/q4_profile_audit_2026-10-14/provenance.json').read_bytes())['protected_before']
    require(protected() == baseline and len(baseline) == 179, 'Old release changed')
    from pynq_q4.protocol import validate_package as validate_old
    validate_old(ROOT / 'build/deploy/q4_c5_experimental_r1')
    package = ROOT / 'build/deploy/q4d_c7_experimental_r1'
    host = ROOT / 'build/q4d_host_candidate_01/package'
    manifest, protocol = validate_q4d(package)
    validate_package(package)
    # Full host behavior checks used the same real bit/HWH and application/data
    # bytes while slow actual RTL checks finished. The host candidate was never
    # published and was marked HOST_TEST_DOUBLE in all simulated observations.
    for name in manifest['artifacts']:
        require(info(package / name) == info(host / name), 'Final release differs from host-tested bytes: ' + name)
    initial = (ROOT / 'build/q4d_host_suite_01.log').read_text(encoding='utf-8-sig')
    recheck = (ROOT / 'build/q4d_host_recheck_02.log').read_text(encoding='utf-8-sig')
    require('Ran 49 tests' in initial and 'FAILED (errors=3)' in initial, 'Unexpected initial host results')
    failed = set(re.findall(r'^ERROR: (test_\w+) \(([^)]+)\)', initial, re.M))
    rerun = set(re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\.', recheck, re.M))
    require(len(failed) == 3 and failed == rerun and re.search(r'Ran 3 tests.*\n\s*\nOK\s*$', recheck, re.S), 'Unresolved host failures')
    require(len(re.findall(r'(?:\.\.\. |^)ok$', initial, re.M)) == 46, 'Unexpected passed host count')
    final_recheck = (ROOT / 'build/q4d_final_package_recheck_01.log').read_text(encoding='utf-8-sig')
    require(len(re.findall(r'\.\.\. ok$', final_recheck, re.M)) == 3 and
            re.search(r'Ran 3 tests.*\n\s*\nOK\s*$', final_recheck, re.S),
            'Final published ZIP and startup extraction checks missing')
    csim = ROOT / 'build/q4d_detector_hls_03/solution1/csim/report/retina_detector_hls_csim.log'
    require('C7_CSIM_PASS frames=18 words=2555904 features=9720' in csim.read_text(), 'Full Csim gate missing')
    for p in (ROOT / 'pynq_q4d').glob('*.py'):
        ast.parse(p.read_bytes(), feature_version=(3, 10))
    ast.parse((ROOT / 'scripts/q4d_board.py').read_bytes(), feature_version=(3, 10))
    out.mkdir(parents=True)
    paths = [
        csim, ROOT/'build/q4d_detector_hls_03/solution1/syn/report/retina_detector_hls_csynth.rpt',
        ROOT/'build/q4d_detector_hls_03/solution1/syn/report/c7_filter_csynth.rpt',
        ROOT/'build/q4d_detector_full_02/timing_summary.rpt', ROOT/'build/q4d_detector_full_02/utilization.rpt',
        ROOT/'build/q4d_detector_full_02/drc.rpt', ROOT/'build/q4d_detector_hardware_check_01.json',
        ROOT/'build/q4d_guard_sim_01/session.log', ROOT/'build/q4d_detector_reset_session_01.log',
        ROOT/'build/q4d_host_suite_01.log', ROOT/'build/q4d_host_recheck_02.log',
        ROOT/'build/q4d_shard_compile_01/compile.log', ROOT/'build/q4d_shard_compile_01/elaborate.log',
        ROOT/'build/q4d_shard_compile_01/source_identity.json', ROOT/'build/q4d_shard_compile_01/sources.prj',
        ROOT/'build/q4d_detector_axis_sim_03/vector_manifest.json',
        ROOT/'build/q4d_board_references_01/frozen_evaluation.json',
        ROOT/'build/q4d_frozen_visual_02/review.md', ROOT/'build/q4d_host_ui_preview_01.jpg',
        ROOT/'build/q4d_host_ui_state_01.json',
        ROOT/'build/q4d_original_region_review_01/audit.json',
        ROOT/'build/q4d_original_region_review_01/same_roi_c5_real_c7_reference.png',
        ROOT/'build/q4d_original_region_review_01/same_full_fov_centerline.png',
        ROOT/'build/q4d_bounded_host_rejection_03.log',
        ROOT/'build/q4d_rtl_gate_pending_02.log', ROOT/'build/q4d_rtl_gate_pending_03.log',
        ROOT/'build/q4d_final_package_recheck_01.log', ROOT/'build/q4d_release_package_01.log',
        ROOT/'build/q4d_sharded_rtl_verified_01.json', ROOT/'build/q4d_sharded_rtl_verified_01.log',
    ]
    paths += [ROOT/f'build/q4d_sharded_rtl_02/group_{i:02d}/xsim.log' for i in range(1,9)]
    saved = {}
    for path in paths:
        target = out / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        saved[path.relative_to(ROOT).as_posix()] = info(path)
    upload = ROOT/'build/deploy/q4d_c7_upload_r1'
    source_paths = list((ROOT/'pynq_q4d').glob('*.py')) + list((ROOT/'ui_q4d').glob('*'))
    source_paths += list((ROOT/'hls').glob('*detector*')) + [ROOT/'hls/retina_c7_model.hpp', ROOT/'software/models/c7_d6_r1.json']
    source_paths += list((ROOT/'scripts').glob('*q4d*.py')) + list((ROOT/'tests').glob('*q4d*'))
    source_paths += [ROOT/'rtl/core/retina_detector_guard.v', ROOT/'tests/retina_detector_hls_tb.cpp']
    report = dict(status='HOST_RELEASE_VERIFIED_BOARD_NOT_RUN', board_status='NOT_RUN', quality_accepted=False,
        source_commit_before_archive=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        host_distinct_tests=49, initial_failures_preserved=3, corrected_rechecks=3,
        host_only_batch=dict(frames=160, words=26214400, png_images=800, png_channel_values=235929600),
        actual_hardware=hardware, actual_rtl=rtl, csim=dict(frames=18,words=2555904,scalar_features=9720),
        uploads={p.name:info(p) for p in upload.iterdir()}, old_files_unchanged=baseline,
        saved_evidence=saved, model=info(ROOT/'software/models/c7_d6_r1.json'),
        current_sources={p.relative_to(ROOT).as_posix():info(p) for p in source_paths if p.is_file()},
        fixed_protocol=info(ROOT/'docs/q4d_board_protocol_r1.json'),
        limitations=['C7 optional, not final quality acceptance', '512 training OOF bright-vessel recall protection failed',
                    'im0324 and im0004 reused-heldout regressions retained; no post-holdout retuning',
                    'Actual board time/FPS and algorithm outputs require the new physical-board experiment'])
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','host_distinct_tests','uploads','limitations')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    main(parser.parse_args().output)
