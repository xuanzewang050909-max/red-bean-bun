"""Preserve W2 host sources, raw failures and final implementation evidence."""
import argparse
import difflib
import json
import shutil
import subprocess
from pathlib import Path
from check_b_hardware import info,require
from package_w2_quality import gates

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);p.add_argument('release',type=Path)
    a=p.parse_args();hardware=gates();require(not a.destination.exists(),'Preserve existing archive')
    manifest=json.loads((a.release/'w2_manifest.json').read_text(encoding='utf-8'))
    require(manifest['board_status']=='NOT_RUN','Do not change historical release board status')
    for name,expected in manifest['artifacts'].items():require(info(a.release/name)==expected,'Release mismatch '+name)
    a.destination.mkdir(parents=True)
    files=['w2_guard_unit_01_session.log','w2_quality_axis_sim_01_session.log','w2_quality_axis_sim_02_session.log',
           'w2_quality_axis_sim_03_session.log','w2_quality_full_01_session.log','w2_quality_reset_01_session.log',
           'w2_quality_hls_export_01_session.log','w2_quality_hls_export_02_session.log','w2_quality_ip_repack_02_session.log',
           'w2_quality_bd_01_session.log','w2_quality_bd_02_session.log','w2_board_vectors_01_session.log',
           'w2_board_host_01.log','w2_board_host_02.log','w2_board_host_03.log','w2_package_host_01.log','w2_package_host_02.log',
           'w2_observer_host_01.log','w2_archive_host_01.log','w2_archive_host_02.log','w2_hardware_check_01.log','w2_hardware_check_02.log','w2_hardware_check_03.log']
    artifacts={}
    for name in files:
        source=ROOT/'build'/name;require(source.is_file(),'Missing original log '+name)
        shutil.copy2(source,a.destination/name);artifacts[name]=info(source)
    for name in ('timing_summary.rpt','utilization.rpt','drc.rpt','clocks.rpt','configuration.txt','build_script_used.tcl','quality_guard_used.v','reconstructed_bd.tcl'):
        source=ROOT/'build/w2_quality_full_01'/name;shutil.copy2(source,a.destination/name);artifacts[name]=info(source)
    for name in ('retina_w2_quality_axis_tb.sv','vector_manifest.json','xsim.log'):
        source=ROOT/'build/w2_quality_axis_sim_03'/name;target='actual_axis_'+name;shutil.copy2(source,a.destination/target);artifacts[target]=info(source)
    shutil.copy2(a.release/'w2_manifest.json',a.destination/'release_manifest.json')
    shutil.copy2(ROOT/'build/w2_board_vectors_01/w2_vectors.json',a.destination/'board_vector_manifest.json')
    source_files=['rtl/core/retina_quality_guard.v','hls/retina_quality_hls.cpp','hls/retina_quality_hls.hpp',
                  'pynq_app/quality_observer.py','scripts/w2_quality_board_test.py','scripts/package_w2_quality.py',
                  'scripts/prepare_w2_board_vectors.py','scripts/check_w2_hardware.py','scripts/verify_w2_board_results.py',
                  'scripts/archive_w2_host.py','scripts/run_w2_quality_simulation.ps1','scripts/run_w2_guard_simulation.ps1',
                  'tests/retina_w2_quality_axis_tb.sv','tests/retina_quality_guard_tb.sv',
                  'tests/test_w2_quality_observer.py','tests/test_w2_board_runner.py','tests/test_w2_package_validation.py','tests/test_w2_archive.py',
                  'vivado/scripts/build_w2_quality.tcl','vivado/scripts/export_w2_quality_hls.tcl','vivado/scripts/simulate_w2_reset.tcl',
                  'notebooks/w2_quality_check.ipynb']
    # Preserve exact working bytes as well as Git provenance (Windows line endings).
    for name in source_files:
        target=a.destination/'source_snapshot'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    for before,after,target in [('rtl/core/retina_gaussian_guard.v','rtl/core/retina_quality_guard.v','a4_guard_to_w2.diff'),
                                 ('vivado/scripts/build_a4_segmentation.tcl','vivado/scripts/build_w2_quality.tcl','a4_build_to_w2.diff')]:
        diff=''.join(difflib.unified_diff((ROOT/before).read_text().splitlines(True),(ROOT/after).read_text().splitlines(True),fromfile=before,tofile=after))
        (a.destination/target).write_text(diff,encoding='utf-8')
    report=dict(status='W2_HOST_RELEASE_READY_BOARD_NOT_RUN',board_status='NOT_RUN',client_date='2026-10-14',
                source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                source_files={name:info(ROOT/name) for name in source_files},raw_evidence=artifacts,
                hardware=hardware,host_distinct_tests=28,actual_generated_rtl_frames=17,actual_generated_rtl_words=2490368,
                guard_surrogate_only_frames=6,guard_surrogate_only_words=589824,
                original_a4_reference_cases=61,planned_board_frames=80,planned_board_words=13303808,
                failed_or_incomplete_attempts={
                    'axis_01':'Vector generator empty-directory check rejected source files copied too early; no RTL simulated.',
                    'axis_02':'Manually stopped after 9 complete frames to correct interrupted sender quiescence; not a full PASS. Original guard/core unchanged.',
                    'hls_export_01':'HLS project command rejected colon-containing absolute project name; fixed by cd and basename.',
                    'hls_export_02':'2017 IP packer date revision exceeded signed int; reused existing metadata-only Revision=1 repack; generated RTL/ROM byte hashes unchanged.',
                    'bd_01':'Rejected missing component.xml before successful metadata-only repack.',
                    'hardware_check_02':'Extended source gate initially looked for ROM in shared RTL directory; generated Vivado keeps ROM at the instance HDL directory. Both actual locations are now compared byte-for-byte.',
                    'board_host_01':'Host preview-failure test lacked temporary IPython mock in final negative check; corrected fixture and chosen output index, no output fallback.'},
                notes=['DRC DSP pipeline warnings belong to reused response_carrier; routed timing passes.',
                       'RTSTAT-10 and write-first advisories belong to unchanged standard DMA/interconnect/FIFO; original parameters exact; not suppressed.',
                       'Original TUL DDR preset negative skew advisories retained; reset polarity warning checked with actual generated vendor reset simulation.',
                       'Core elapsed includes input starvation/output backpressure. No pure DMA or browser timing inferred.',
                       'Golden arrays only compare outputs. Preview consumes verified, saved actual DMA arrays. No new board quality or FPS claimed.'])
    (a.destination/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'],len(artifacts),'raw evidence files')


if __name__=='__main__':main()
