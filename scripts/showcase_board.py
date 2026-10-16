"""Variable-length demonstration orchestration; all image computation stays in C7 PL."""
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from pynq_showcase.launch import prepare, start
from pynq_showcase.protocol import require, file_info, write_json, validate_package
from pynq_showcase.service import MAX_RUNS

EXAMPLES = ['im0077', 'im0081', 'im0162', 'im0240', 'im0001', 'im0044', 'im0004', 'im0324']


def validate_showcase(root):
    root = Path(root).resolve()
    m = json.loads((root/'showcase_manifest.json').read_bytes())
    require(m['revision'] == 'c7_showcase_r1' and m['examples'] == EXAMPLES, 'Wrong showcase package')
    for n, info in m['artifacts'].items():
        require(file_info(root/n) == info, 'Showcase file changed: '+n)
    validate_package(root)
    return m


def prepare_showcase(root):
    root = Path(root).resolve()
    validate_showcase(root)
    require(Path(__file__).resolve() == root/'showcase_board.py', 'Use fresh paired kernel/helper')
    require(not (root/'browser_results').exists(), 'Preserve old records; use a fresh folder')
    require(shutil.disk_usage(root).free >= 1024**3, 'Need 1 GiB free for records and export')
    boot = dict(boot_id=str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip())),
                uptime_seconds=float(Path('/proc/uptime').read_text().split()[0]))
    ctx = prepare(root, 8090)
    ctx['showcase_boot'] = boot
    print('SHOWCASE_PRECHECK_PASS:', boot, flush=True)
    return ctx


def summary_showcase(ctx):
    m = ctx['manager']; s = m.status(); jobs = list(m.jobs.values())
    require(1 <= len(jobs) <= MAX_RUNS and s['accepted'] == s['completed'] == len(jobs), 'Wait for all accepted tasks; need at least one')
    require(s['service_state'] == 'READY' and s['hardware_state'] == 'IDLE' and s['overlay_downloads'] == 1 and
            s['pending'] == s['retained_buffer_count'] == 0 and s['active_run_id'] is None and s['error'] is None, 'Unsafe state; preserve session')
    observed = []
    for i, job in enumerate(jobs):
        require(job['evidence']['hardware_latched_parameter_readback']['sequence'] == i+1, 'Wrong PL sequence')
        obs = job.get('browser_timing')
        # Missing/hidden observations remain explicitly incomplete; never invent a render.
        if obs and obs['visibility'] == 'visible' and obs['loop_id'] is None:
            observed.append(job['run_id'])
    return dict(status='SHOWCASE_COLLECTED_PENDING_DOWNLOAD_AUDIT', session_id=m.session_id,
                tasks=len(jobs), observed_run_ids=observed, unobserved_run_ids=[j['run_id'] for j in jobs if j['run_id'] not in observed],
                images=sorted({j['request']['image_id'] for j in jobs}), boot=ctx['showcase_boot'], video='DEFERRED_BY_USER')


async def close_showcase(ctx):
    summary = summary_showcase(ctx)  # A busy check does not close or alter the service.
    require(not ctx.get('showcase_close_attempted'), 'Do not retry a failed close')
    ctx['showcase_close_attempted'] = True
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == summary['boot']['boot_id'], 'Boot changed')
    m = ctx['manager']
    write_json(m.directory/'showcase_summary.json', summary)
    m.finish(); ctx['server'].stop()
    await ctx['server'].close_all_connections()
    ctx['showcase_closed'] = True
    print('SHOWCASE_CLOSED_IDLE:', m.status(), flush=True)


async def export_showcase(ctx):
    require(ctx.get('showcase_closed') and not ctx.get('showcase_export_attempted'), 'Close first; export once')
    ctx['showcase_export_attempted'] = True
    m = ctx['manager']; target = m.root.parent/'c7_showcase_results.zip'
    require(not target.exists(), 'Preserve previous ZIP')
    require(shutil.disk_usage(m.root).free >= 256*1024**2, 'Need 256 MiB free for export')
    original = await m.export()
    summary = m.directory/'showcase_summary.json'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        z.write(original, 'original_session_export.zip'); z.write(summary, 'showcase_summary.json')
        z.writestr('showcase_bundle_manifest.json', json.dumps(dict(original_session_export=file_info(original), summary=file_info(summary))))
    ctx['executor'].shutdown(wait=False)
    print('SHOWCASE_RESULTS_READY:', target, flush=True)
    return str(target)
