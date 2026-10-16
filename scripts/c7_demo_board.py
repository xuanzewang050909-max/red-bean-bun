"""Demonstration orchestration only; reuses the byte-frozen W5b PL service."""
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from w5b_board import prepare_w5b, manual_cases
from pynq_w5b.launch import start
from pynq_w5b.protocol import require, file_info, write_json


def prepare_demo(root):
    # Read before loading FPGA. This identifies the boot, not a power-loss test.
    boot = dict(boot_id=str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip())),
                uptime_seconds=float(Path('/proc/uptime').read_text().split()[0]),
                scope='Boot identity recorded; physical restart confirmed by user/video only')
    ctx = prepare_w5b(root)
    ctx['demo_boot'] = boot
    print('DEMO_PRECHECK_PASS:', boot, flush=True)
    return ctx


def demo_summary(ctx):
    m = ctx['manager']; s = m.status(); jobs = list(m.jobs.values())
    require(s['accepted'] == s['completed'] == len(jobs) == 7, 'Need exactly seven manual tasks; preserve extra/missing records')
    require(s['service_state'] == 'READY' and s['hardware_state'] == 'IDLE' and s['overlay_downloads'] == 1 and
            s['pending'] == s['retained_buffer_count'] == 0 and s['active_run_id'] is None and s['error'] is None, 'Unsafe state; stop')
    for i, (job, case) in enumerate(zip(jobs, manual_cases())):
        require(all(job['request'][k] == v for k,v in case.items()), 'Wrong demonstration order: '+str(i+1))
        require(job['evidence']['hardware_latched_parameter_readback']['sequence'] == i+1, 'Wrong hardware sequence')
        obs = job.get('browser_timing')
        require(obs and obs['visibility'] == 'visible' and obs['loop_id'] is None, 'Wait for visible manual render evidence')
    require(jobs[1]['quality']['annotations'] == {} and jobs[1]['quality']['quality_reason'], 'No-GT display must remain unevaluated')
    pages = [j['browser_timing']['page_id'] for j in jobs]
    require(len(set(pages[:6])) == 1 and pages[-1] != pages[0], 'Reload once after sixth completed render')
    require(jobs[0]['output']['sha256'] == jobs[-1]['output']['sha256'], 'Reload changed C7 output')
    return dict(status='DEMO_COLLECTED_PENDING_DOWNLOAD_AUDIT', session_id=m.session_id,
                tasks=7, pages=pages, boot=ctx['demo_boot'])


async def close_demo(ctx):
    require(not ctx.get('demo_close_attempted'), 'Do not retry close; preserve session')
    ctx['demo_close_attempted'] = True
    summary = demo_summary(ctx)
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == summary['boot']['boot_id'], 'Boot changed')
    m = ctx['manager']
    write_json(m.directory/'demo_summary.json', summary)
    m.finish()
    ctx['server'].stop()
    await ctx['server'].close_all_connections()
    ctx['demo_closed'] = True
    print('DEMO_CLOSED_IDLE:', m.status(), flush=True)


async def export_demo(ctx):
    require(ctx.get('demo_closed') and not ctx.get('demo_export_attempted'), 'Close first; do not repeat export')
    ctx['demo_export_attempted'] = True
    m = ctx['manager']
    target = m.root.parent/'c7_demo_results.zip'
    require(not target.exists(), 'Preserve previous ZIP')
    require(shutil.disk_usage(m.root).free >= 256*1024**2, 'Need 256 MiB for export')
    # Reuse original exporter; no new image computation, reconfiguration or frame.
    original = await m.export()
    inventory = dict(original_session_export=file_info(original), summary=file_info(m.directory/'demo_summary.json'))
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        z.write(original, 'original_session_export.zip')
        z.write(m.directory/'demo_summary.json', 'demo_summary.json')
        z.writestr('demo_bundle_manifest.json', json.dumps(inventory))
    ctx['executor'].shutdown(wait=False)
    print('DEMO_RESULTS_READY:', str(target), flush=True)
    return str(target)
