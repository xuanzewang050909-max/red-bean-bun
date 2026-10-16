"""W5a lifecycle; no algorithm computations or automatic hardware recovery."""
import asyncio
import json
import os
import shutil
from pathlib import Path
from pynq_w5a.launch import prepare, start
from pynq_w5a.protocol import file_info, require, validate_package


def validate_w5a(root):
    root = Path(root).resolve()
    m = json.loads((root/'w5a_manifest.json').read_bytes())
    require(m['revision'] == 'c7_w5a_stability_r1', 'Wrong W5a revision')
    for name, info in m['artifacts'].items():
        require(file_info(root/name) == info, 'W5a file changed: '+name)
    validate_package(root)
    return m


def prepare_w5a(root):
    root = Path(root).resolve()
    validate_w5a(root)
    require(Path(__file__).resolve() == root/'w5a_board.py', 'Stale helper; fresh folder/kernel required')
    require(not (root/'browser_results').exists(), 'Keep prior session; use fresh folder')
    require(shutil.disk_usage(root).free >= 1536*1024**2, 'Need 1.5 GiB free for W5a unique data/export/reserve')
    # Confirm same-filesystem hardlinks BEFORE any PL access. Leave failures for diagnosis.
    probe = root/'w5a_storage_probe'
    probe.mkdir(exist_ok=False)
    a,b = probe/'source',probe/'linked'
    a.write_bytes(b'W5a storage probe; no FPGA access')
    os.link(a,b)
    require(a.stat().st_ino == b.stat().st_ino and a.read_bytes() == b.read_bytes(), 'Hardlink support required')
    b.unlink();a.unlink();probe.rmdir()
    ctx = prepare(root,8090)
    print('W5A_PRECHECK_PASS: hashes, free space and hardlinks checked; FPGA unchanged',flush=True)
    return ctx


def ready_w5a(ctx):
    s = ctx['manager'].status()
    require(s['completed'] == s['accepted'] == 0 and s['hardware_state'] == 'IDLE' and not s['error'], 'Not a fresh idle session')
    print('W5A_BROWSER_READY: open 8090, keep foreground; start 1000 paced tasks once',flush=True)
    return s


def summarize_w5a(ctx):
    result = ctx['manager'].endurance_summary()
    print('W5A_COLLECTION_COMPLETE:',result,flush=True)
    return result


async def close_w5a(ctx):
    ctx['manager'].endurance_summary()
    ctx['manager'].finish()
    ctx['server'].stop()
    await ctx['server'].close_all_connections()
    ctx['w5a_closed'] = True
    print('W5A_CLOSED_IDLE: no active/pending/retained operation',flush=True)


async def export_w5a(ctx):
    require(ctx.get('w5a_closed') and not ctx.get('w5a_export_attempted'), 'Close safely first; export once')
    ctx['w5a_export_attempted'] = True
    path = await ctx['manager'].export()
    ctx['executor'].shutdown(wait=False)
    print('W5A_RESULTS_READY:',str(path),flush=True)
    return str(path)
