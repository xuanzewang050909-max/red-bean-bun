"""Verify and archive Q2 host HLS/RTL evidence; never claim board results."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_pair(commit, names):
    result = {}
    for name in names:
        historic = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
        current = (ROOT / name).read_bytes()
        require(historic == current, 'Source changed since build: ' + name)
        result[name] = hashlib.sha256(historic).hexdigest()
    return result


def verify_vectors(directory):
    manifest = json.loads((directory / 'vector_manifest.json').read_text(encoding='utf-8'))
    members = manifest.get('hex_file_sha256', manifest.get('hex_sha256'))
    for name, digest in members.items():
        require(sha(directory / name) == digest, 'Vector changed: ' + name)
    require(not manifest['heldout_decoded'] and not manifest['annotation_arrays_loaded'], 'Wrong algorithm vector scope')
    return manifest


def main():
    support = ROOT / 'results/q2_support_2017_4'
    pipeline = ROOT / 'results/q2_pipeline_2017_4'
    require(not (support / 'verification.json').exists() and not (pipeline / 'verification.json').exists(), 'Preserve earlier audit')
    reuse = json.loads((support / 'reuse_evidence.json').read_text(encoding='utf-8'))
    for name, digest in reuse['preserved_files_before'].items():
        require(sha(ROOT / name) == digest, 'Original A4/W1/candidate changed: ' + name)
    for header in reuse['headers']:
        require(sha(Path(header['path'])) == header['sha256'], 'Installed header changed')

    initial = ROOT / 'build/q2_support_axis_sim_01'
    focused = ROOT / 'build/q2_support_reset_focus_02'
    full = ROOT / 'build/q2_quality_axis_sim_01'
    support_vectors = verify_vectors(initial)
    focused_vectors = verify_vectors(focused)
    require(support_vectors['hex_file_sha256'] == focused_vectors['hex_file_sha256'], 'Focused run altered vectors')
    full_vectors = verify_vectors(full)
    initial_log = (initial / 'xsim.log').read_text(encoding='utf-8')
    focused_log = (focused / 'xsim.log').read_text(encoding='utf-8')
    full_log = (full / 'xsim.log').read_text(encoding='utf-8')
    matched_support = re.findall(r'C2_SUPPORT_RTL_FRAME_PASS: frame=(\d+) side=(\d+) words=(\d+)', initial_log)
    require(len(matched_support) == 47 and [int(r[0]) for r in matched_support] == list(range(1, 48)), 'Incomplete initial module coverage')
    require(sum(int(r[2]) for r in matched_support) == support_vectors['completed_frame_words'] == 3955712, 'Support word count changed')
    require('Fatal: C2 mismatch vector=48 pixel=0 actual=80ef011d expected=028b0100' in initial_log,
            'Initial reset failure missing; do not rewrite it as PASS')
    require('C2_RESET_ABORTED_SENDER_STATE: valid=1 word=80ef1da7' in focused_log, 'Missing reset-cause trace')
    require('C2_SUPPORT_RESET_FOCUS_PASS: full_frames=3 full_words=328704 total_checked=328704' in focused_log and
            not re.search(r'Fatal:|Error:', focused_log), 'Focused reset recovery not verified')
    require('Q2_QUALITY_AXIS_SIM_PASS:' in full_log and not re.search(r'Fatal:|Error:', full_log), 'Full pipeline RTL has not passed')
    matched_full = re.findall(r'Q2_QUALITY_AXIS_FRAME_PASS: case=(\d+) words=(\d+) status=([0-9a-f]+)', full_log)
    require(len(matched_full) == full_vectors['complete_frames'] == 17 and
            sum(int(r[1]) for r in matched_full) == full_vectors['full_words'] == 2490368, 'Full pipeline count differs')
    require('Q2_QUALITY_BAD_INPUT_PASS:' in full_log and 'Q2_QUALITY_VALID_PASS:' in full_log, 'Guard coverage missing')
    expected = {r['case']: r for r in full_vectors['cases']}
    for index, (ordinal, words, _status) in enumerate(matched_full):
        actual_case = index + 1 if index < 16 else 18
        require(int(ordinal) == index + 1 and int(words) == expected[actual_case]['words'], 'Frame order mismatch')
    csim_support = (support / 'host_synthesis_01/csim.log').read_text(encoding='utf-8')
    csim_full = (pipeline / 'host_synthesis_01/csim.log').read_text(encoding='utf-8')
    require('C2_SUPPORT_CSIM_PASS: 27 frames; 678912 exact words' in csim_support, 'Module Csim incomplete')
    require('Q2_QUALITY_PIPELINE_CSIM_PASS: 24 full frames, 2949120 exact words' in csim_full, 'Full Csim incomplete')
    module_source = source_pair('0642480', ['hls/retina_c2_support_hls.cpp', 'hls/retina_c2_support_hls.hpp'])
    full_source = source_pair('7a8770d', ['hls/retina_quality_hls.cpp', 'hls/retina_quality_hls.hpp', 'tests/retina_quality_hls_tb.cpp'])
    for build, result in [('q2_support_hls_01', support), ('q2_quality_hls_01', pipeline)]:
        metadata = json.loads((result / 'host_synthesis_01/synthesis_metadata.json').read_text(encoding='utf-8'))
        for name, digest in metadata['generated_rtl_and_rom_sha256'].items():
            require(sha(ROOT / 'build' / build / 'solution1/syn/verilog' / name) == digest, 'Actual generated RTL changed')
    common = {'client_date': '2026-10-14', 'tool': 'Vivado HLS / xsim 2017.4',
              'candidate_id': 'C2_l9_d12345_m1_p28', 'installed_headers_unchanged': True,
              'original_A4_W1_and_selected_candidate_unchanged': True,
              'board_status': 'NOT_RUN', 'new_board_quality': None, 'core_time_ms': None,
              'complete_overlay_utilization': None, 'post_route_timing': None}
    module_record = {**common, 'status': 'MODULE_PIXEL_COVERAGE_AND_FOCUSED_RESET_VERIFIED_NOT_SINGLE_RUN_48_PASS',
                     'source_commit': '0642480', 'source_sha256': module_source,
                     'csim_full_frames': 27, 'csim_exact_words': 678912,
                     'initial_stress_run_overall_status': 'FAILED_TESTBENCH_RESET_SOURCE_REPLAY_PRESERVED',
                     'initial_full_frames_matched_before_failure': 47, 'initial_exact_words_before_failure': 3955712,
                     'training_intermediate_pixels': 3276800,
                     'focused_reset_full_frames': 3, 'focused_reset_exact_words': 328704,
                     'focused_testbench_commit': '1ef4ccf', 'hardware_compute_mutated_to_fix_failure': False,
                     'combined_corrected_48_frame_run_claimed': False,
                     'inputs_scope': '27 synthetic + 20 existing training E/A intermediates; no GT decoded'}
    pipeline_record = {**common, 'status': 'FULL_PIPELINE_HOST_CSIM_AND_ACTUAL_RTL_VERIFIED_NOT_BOARD_ACCEPTANCE',
                       'source_commit': '7a8770d', 'source_sha256': full_source,
                       'csim_full_frames': 24, 'csim_exact_words': 2949120,
                       'rtl_full_frames': 17, 'rtl_exact_full_frame_words': 2490368,
                       'rtl_testbench_commit': 'a8fe7db', 'rtl_guard': 'Unchanged original retina_gaussian_guard',
                       'A_T28_compatibility_full_cases_in_Csim': 16,
                       'runtime_thresholds_verified_in_HLS_RTL': [1, 27, 28, 29, 255],
                       'algorithms_verified_in_HLS_RTL': ['A', 'C2'], 'stages_verified': [0, 1, 2, 3],
                       'side_choices_verified': [256, 512], 'frame_middle_configuration_changes_verified': True,
                       'finite_FIFO_random_backpressure_and_active_reset_verified': True,
                       'inputs_scope': 'Synthetic and original training im0001 RGB/FOV; no GT decoded',
                       'W2_new_observer_or_paired_firmware_verified_by_this_record': False}
    for result, record, files in [(support, module_record, [(initial / 'vector_manifest.json', 'rtl_vectors_01.json'),
                                  (initial / 'xsim.log', 'rtl_initial_failure.log'),
                                  (focused / 'xsim.log', 'rtl_reset_focus_02.log')]),
                                 (pipeline, pipeline_record, [(full / 'vector_manifest.json', 'rtl_vectors_01.json'),
                                  (full / 'xsim.log', 'rtl_sim_01.log')])]:
        for path, name in files:
            require(not (result / name).exists(), 'Preserve earlier log')
            shutil.copyfile(path, result / name)
        record['archived_original_log_manifest_sha256'] = {name: sha(result / name) for _, name in files}
        (result / 'verification.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Q2_HOST_PROBES_ARCHIVED: full pipeline 17 RTL frames / 2490368 words; no board PASS')


if __name__ == '__main__':
    main()
