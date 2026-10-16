"""Formal browser performance lifecycle; actual image processing remains PL."""
import json
import shutil
import sys
import zipfile
from pathlib import Path
from pynq_w4b.protocol import require, file_info, write_json
from pynq_w4b.launch import prepare, start


def validate_w4b(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'w4b_manifest.json').read_bytes())
    require(manifest['revision']=='c7_w4_browser_r1' and manifest['board_status']=='BOARD_NOT_RUN', 'Wrong W4b package')
    require(manifest['protocol']==dict(image_id='im0001',side=512,algorithm='C7',threshold=112,
        mode='final',png_profile='fast',repeats=3,warmup=3,samples=100,total=309), 'Formal protocol changed')
    for name, expected in manifest['artifacts'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name and ':' not in name, 'Unsafe path')
        require(file_info(root/name)==expected, 'W4b bytes changed: '+name)
    from pynq_w4b.protocol import validate_package
    browser=validate_package(root)
    require(set(manifest['artifacts'])==set(browser['artifacts'])|{'browser_manifest.json','w4b_board.py'}, 'Wrong complete inventory')
    return manifest


def prepare_w4b(root):
    root=Path(root).resolve(); manifest=validate_w4b(root)
    require(Path(__file__).resolve()==root/'w4b_board.py', 'Stale helper; use fresh kernel/folder')
    require(not (root/'browser_results').exists(), 'Keep earlier attempt; use fresh folder')
    require(shutil.disk_usage(root).free>=3*1024**3, 'Need 3 GiB free SD space for complete raw evidence/export')
    ctx=prepare(root,8090);ctx['w4b_manifest']=manifest
    print('W4B_PRECHECK_PASS: immutable C7 hardware; 3 x (3 + 100); FPGA unchanged',flush=True)
    return ctx


def ready_w4b(ctx):
    m=ctx['manager'];require(m is not None and not m.jobs and not m.error and m.hardware.state=='IDLE','Fresh idle service required')
    print('W4B_BROWSER_READY: open http://192.168.2.99:8090/ , Ctrl+F5, click the formal 3-round button once. Keep foreground until 309/309.',flush=True)
    return m.status()


def summarize_w4b(ctx):
    report=ctx['manager'].formal_summary()
    print('W4B_SUMMARY_READY: 3 groups, 100 visible timed samples per group; 9 warmup frames excluded',flush=True)
    for g in report['groups']:
        print('round%d: median %.3f ms, p95 %.3f ms, %.6f FPS'%(g['repeat'],g['median_ms'],g['p95_ms'],g['actual_fps']))
    ctx['w4b_summary']=report
    return report


async def close_w4b(ctx):
    require('w4b_summary' in ctx and not ctx.get('w4b_closed'), 'Summarize once before closing')
    ctx['manager'].formal_summary()
    ctx['manager'].finish()  # Reject all native active/pending/FAULT/retained cases.
    ctx['server'].stop();await ctx['server'].close_all_connections()
    ctx['w4b_closed']=True
    print('W4B_CLOSED_IDLE: server closed; native buffers released; records preserved for export',flush=True)


async def export_w4b(ctx):
    require(ctx.get('w4b_closed') and not ctx.get('w4b_export_attempted'), 'Close safely first; export once')
    ctx['w4b_export_attempted']=True
    m=ctx['manager'];require(m.closed and not m.error and m.hardware.state=='IDLE' and not m.hardware.retained, 'Cannot export successful suite from fault')
    source=await m.export()
    target=ctx['root'].parent/'c7_w4_browser_results.zip'
    require(not target.exists(),'Preserve previous export')
    shutil.copyfile(source,target)
    with zipfile.ZipFile(target,'a',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(m.directory/'w4b_summary.json','w4b_summary.json')
        z.write(ctx['root']/'w4b_manifest.json','w4b_manifest.json')
    ctx['executor'].shutdown(wait=False)
    print('W4B_RESULTS_READY:',str(target),flush=True)
    return str(target)
