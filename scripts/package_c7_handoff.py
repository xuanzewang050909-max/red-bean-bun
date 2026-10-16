"""Read-only historical evidence collection, never rebuild or replace a release."""
import argparse,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=Path('D:/PLD/retina_fpga')

def info(p):return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def build(out, demo_audit=None):
    if out.exists():raise ValueError('Preserve existing handoff')
    status='INITIAL_C7_HANDOFF_DEMO_BOARD_NOT_RUN'
    if demo_audit:
        evidence=json.loads(demo_audit.read_bytes())
        if evidence['status']!='C7_DEMO_BOARD_RECORDS_VERIFIED_VIDEO_REVIEW_SEPARATE':
            raise ValueError('Expected independently verified real demonstration')
        originals=ROOT/'build/board_results/c7_demo_2026-10-16'
        for key,name in [('archive','c7_demo_results.zip'),('notebook','c7_delivery_demo.ipynb')]:
            if info(originals/name)!=evidence[key]:raise ValueError('Downloaded demo changed')
        status='C7_SOFTWARE_DEMO_VERIFIED_REBOOT_AND_VIDEO_PENDING'
    report=json.loads((ROOT/'results/q4d_detector_2017_4_r1/verification.json').read_bytes())['actual_hardware']
    gen=ORIGINAL/'build/q4d_detector_hls_03/solution1/syn/verilog'
    for name,expected in report['generated_rtl_rom'].items():
        if info(gen/name)!=expected:raise ValueError('Generated RTL changed: '+name)
    deploy=ORIGINAL/'build/q4d_detector_full_02/deploy'
    package=ROOT/'build/deploy/c7_w5b_interaction_r1/package'
    for name in ('q4d_detector.bit','q4d_detector.hwh'):
        if info(deploy/name)!=info(package/name):raise ValueError('Hardware pair changed')
    for name in ('retina_detector_hls.cpp','retina_detector_hls.hpp','retina_detector_c5.cpp','retina_c7_model.hpp'):
        if (ROOT/'hls'/name).read_bytes()!=(ORIGINAL/'hls'/name).read_bytes():raise ValueError('Original C7 source differs')
    out.mkdir(parents=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','archive','--format=zip','--output='+str((out/'source_snapshot.zip').resolve()),'HEAD'],cwd=ROOT,check=True)
    shutil.copytree(ORIGINAL/'build/q4d_detector_hls_export_02/solution1/impl/ip',out/'generated_ip')
    shutil.copytree(gen,out/'generated_rtl')
    shutil.copytree(deploy,out/'hardware')
    (out/'reports').mkdir();(out/'documents').mkdir()
    full=ORIGINAL/'build/q4d_detector_full_02'
    for name in ('timing_summary.rpt','utilization.rpt','drc.rpt','clocks.rpt','ip_status.rpt','build_script_used.tcl','reconstructed_bd.tcl','configuration.txt','quality_guard_used.v'):
        shutil.copy2(full/name,out/'reports'/name)
    for p in (ROOT/'docs').glob('c7_*.md'):shutil.copy2(p,out/'documents'/p.name)
    shutil.copytree(ROOT/'build/deploy/c7_delivery_demo_r1/upload',out/'board_upload')
    if demo_audit:
        shutil.copytree(demo_audit.parent,out/'demo_evidence')
        shutil.copytree(originals,out/'demo_downloads')
        shutil.copy2(ROOT/'docs/c7_submission_index.md',out/'README.md')
    manifest=dict(status=status,source_commit=commit,
        generated_rtl_files_verified=len(report['generated_rtl_rom']),
        scope='Source snapshot and frozen generated IP/RTL; not a newly rebuilt bitstream or validated relocated XPR',
        historical_build=str(full),
        files={p.relative_to(out).as_posix():info(p) for p in sorted(out.rglob('*')) if p.is_file()})
    for name,expected in manifest['files'].items():
        if info(out/name)!=expected:raise ValueError('Copy mismatch '+name)
    with zipfile.ZipFile(out/'source_snapshot.zip') as z:
        if z.testzip() is not None:raise ValueError('Source archive corrupt')
    (out/'handoff_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return dict(status=manifest['status'],source_commit=commit,files=len(manifest['files']),generated_rtl_files_verified=manifest['generated_rtl_files_verified'],manifest=info(out/'handoff_manifest.json'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--demo-audit',type=Path)
    a=p.parse_args();print(json.dumps(build(a.destination,a.demo_audit),indent=2))
