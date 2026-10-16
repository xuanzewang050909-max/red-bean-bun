"""W4.1: sequential, fail-stop same-PS CPU / real C7 PL performance collector.

No CPU result is used as DMA input or sent to a browser. There is no HTTP server
in this experiment. Reserve the old service port before touching the FPGA.
"""
import asyncio
import json
import os
import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path
import numpy as np
from .common import (REVISION, REPEATS, WARMUP, SAMPLES, require, info, word_sha,
                     write_json, validate, group_order, summarize)


def environment():
    result = {'monotonic_clock': vars(time.get_clock_info('perf_counter'))}
    for name in ('/proc/meminfo', '/proc/loadavg', '/proc/self/status',
                 '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq',
                 '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
                 '/sys/class/thermal/thermal_zone0/temp'):
        path = Path(name)
        try:
            result[name] = path.read_text()
        except OSError:
            result[name] = None
    return result


def status(ctx):
    hw = ctx['base']['hardware']
    return dict(state=ctx['state'], hardware_state=hw.state, overlay_downloads=hw.downloads,
                pl_frames=hw.sequence, retained_buffers=len(hw.retained),
                completed_sizes=ctx['completed'], session=ctx['session'], error=ctx.get('error'))


def save_state(ctx):
    write_json(ctx['directory'] / 'state.json', status(ctx))


def fail(ctx, exc):
    ctx['state'] = 'FAULT'
    ctx['error'] = type(exc).__name__ + ': ' + str(exc)
    save_state(ctx)
    write_json(ctx['directory'] / 'failure.json', dict(status=status(ctx),
        last_hardware_attempt=ctx['base']['hardware'].last_attempt,
        note='No retry, reset, overlay reload, buffer release or worker cancellation. Preserve kernel and output.'))


async def bounded(ctx, function, *args):
    future = asyncio.get_running_loop().run_in_executor(ctx['base']['executor'], function, *args)
    ctx['inflight'] = future
    try:
        # Shield prevents a timeout/Notebook interrupt cancelling the owner job.
        value = await asyncio.wait_for(asyncio.shield(future), timeout=60)
        ctx['inflight'] = None
        return value
    except BaseException as exc:
        fail(ctx, exc)
        raise


def prepare(root):
    root = Path(root).resolve()
    manifest = validate(root)
    for name in ('system_bench', 'system_bench.board', 'system_bench.common'):
        require(Path(sys.modules[name].__file__).resolve().is_relative_to(root), 'Stale benchmark import; fresh folder/kernel required')
    require(sys.byteorder == 'little', 'Little-endian board expected')
    require(shutil.disk_usage(root).free >= 2*1024**3, 'Need 2 GiB free for raw evidence and export')
    require(not (root / 'w4_results').exists(), 'Preserve previous attempt; do not rerun prepare')
    # Resolve CPU dependency before Overlay even exists. Never install packages here.
    import cv2
    from . import cpu
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    require(cv2.getNumThreads() == 1 and not cv2.ocl.useOpenCL(), 'CPU comparator must not use OpenCL')
    for name in ('system_bench.cpu', 'bench_reference', 'bench_reference.q4d_features',
                 'bench_reference.q4d_forest', 'bench_reference.reference'):
        require(Path(sys.modules[name].__file__).resolve().is_relative_to(root), 'Stale CPU comparator import')
    sys.path.insert(0, str(root / 'c7_baseline'))
    from q4d_board import validate_q4d
    from pynq_q4d.launch import prepare as baseline_prepare
    _, protocol = validate_q4d(root / 'c7_baseline')
    base = baseline_prepare(root / 'c7_baseline', port=8090)
    ctx = dict(root=root, manifest=manifest, protocol=protocol, base=base, session=uuid.uuid4().hex,
               state='PRECHECK', completed=[], rows=[], groups=[], inflight=None, cpu=cpu.compute,
               model=json.loads((root / 'bench_reference/c7_d6_r1.json').read_bytes()), inputs={})
    ctx['directory'] = root / 'w4_results'
    try:
        ctx['directory'].mkdir(exist_ok=False)
        (ctx['directory'] / 'raw').mkdir()
        for side in (256, 512):
            entry = base['manifest']['images']['im0001'][str(side)]
            words = np.load(root / 'c7_baseline' / entry['input'], allow_pickle=False)
            require(words.dtype == np.uint32 and words.shape == (side, side) and
                    word_sha(words) == entry['input_word_sha256'], 'Frozen input differs')
            words.setflags(write=False)
            ctx['inputs'][side] = words
            np.save(ctx['directory'] / ('input_%d.npy' % side), words, allow_pickle=False)
        write_json(ctx['directory'] / 'identity.json', dict(revision=REVISION, session=ctx['session'],
            package_manifest=manifest, runtime=base['runtime'], opencv=cv2.__version__,
            opencv_threads=cv2.getNumThreads(), opencv_build=cv2.getBuildInformation(),
            before=environment(), mode='PROCESSING_ONLY_NO_HTTP_SERVER',
            evidence_kind='PYNQ_REAL_PL_PLUS_SEPARATE_PS_CPU_BENCHMARK'))
        save_state(ctx)
    except BaseException:
        for sock in base['sockets']:
            sock.close()
        base['executor'].shutdown(wait=False)
        raise
    print('W4_PRECHECK_PASS: trusted C7 unchanged; CPU dependency ready; FPGA untouched; 8090 reserved', flush=True)
    return ctx


async def load(ctx):
    require(ctx['state'] == 'PRECHECK', 'Load once after precheck; never retry')
    ctx['state'] = 'LOADING'
    save_state(ctx)
    await bounded(ctx, ctx['base']['hardware'].open)
    ctx['state'] = 'LOADED_IDLE'
    write_json(ctx['directory'] / 'loaded.json', dict(status=status(ctx), runtime=ctx['base']['hardware'].environment))
    save_state(ctx)
    print('W4_LOAD_PASS: trusted C7 loaded once; no image sent', flush=True)


def timed_call(ctx, kind, side):
    words = ctx['inputs'][side]
    start = time.perf_counter_ns()
    process_start = time.process_time_ns()
    if kind == 'CPU':
        output = ctx['cpu'](words, ctx['model'], 112)
        record = None
    else:
        request = dict(side=side, mode_code=3, threshold=112, algorithm='C7')
        output, record = ctx['base']['hardware'].run(words, request)
    process_end = time.process_time_ns()
    end = time.perf_counter_ns()
    return output, dict(call_start_ns=start, call_end_ns=end,
        process_start_ns=process_start, process_end_ns=process_end, hardware=record)


async def measure(ctx, side):
    require(ctx['state'] == 'LOADED_IDLE' and ctx['inflight'] is None, 'Not idle; preserve failure')
    require(side in (256, 512) and ctx['completed'] == ([] if side == 256 else [256]), 'Run each size once, 256 then 512')
    ctx['state'] = 'MEASURING'
    save_state(ctx)
    expected = ctx['protocol']['expected_output_sha256']['im0001_%d_C7' % side]
    try:
        with (ctx['directory'] / 'samples.jsonl').open('a', encoding='utf-8', buffering=1) as journal:
            for repeat in range(1, REPEATS+1):
                for kind in group_order(repeat):
                    group = dict(side=side, repeat=repeat, kind=kind, before=environment(),
                                 start_ns=time.perf_counter_ns())
                    write_json(ctx['directory'] / 'active_group.json', group)
                    for index in range(WARMUP+SAMPLES):
                        if index == WARMUP:
                            group['measured_start_ns'] = time.perf_counter_ns()
                        iteration_start = time.perf_counter_ns()
                        output, row = await bounded(ctx, timed_call, ctx, kind, side)
                        name = 'raw/%d_r%d_%s_%03d.npy' % (side, repeat, kind, index)
                        np.save(ctx['directory'] / name, output, allow_pickle=False)
                        digest = word_sha(output)
                        row.update(side=side, repeat=repeat, kind=kind, index=index, warmup=index<WARMUP,
                                   iteration_start_ns=iteration_start, output_sha256=digest, raw=name,
                                   input_sha256=word_sha(ctx['inputs'][side]))
                        # Persist offending output and metadata BEFORE checking it.
                        row['data_saved_ns'] = time.perf_counter_ns()
                        journal.write(json.dumps(row, allow_nan=False)+'\n')
                        journal.flush(); os.fsync(journal.fileno())
                        require(output.dtype == np.uint32 and output.shape == (side, side) and digest == expected,
                                '%s whole-word output differs: %s' % (kind, name))
                        if kind == 'PL':
                            require(row['hardware']['evidence_kind'] == 'PYNQ_PL_DMA' and
                                    row['hardware']['output_sha256'] == digest, 'Not real matching DMA output')
                        ctx['rows'].append(row)
                        if index == WARMUP+SAMPLES-1:
                            group['measured_end_ns'] = time.perf_counter_ns()
                        print('W4_FRAME_SAVED: %d rep%d %s %d/%d %s %.2f ms' %
                              (side, repeat, kind, index+1, WARMUP+SAMPLES,
                               'warmup' if index<WARMUP else 'measured',
                               (row['call_end_ns']-row['call_start_ns'])/1e6), flush=True)
                    group.update(end_ns=time.perf_counter_ns(), after=environment())
                    ctx['groups'].append(group)
                    write_json(ctx['directory'] / 'groups.json', ctx['groups'])
        require(ctx['base']['hardware'].state == 'IDLE' and not ctx['base']['hardware'].retained, 'PL not idle after suite')
        ctx['completed'].append(side)
        ctx['state'] = 'LOADED_IDLE'
        save_state(ctx)
        print('W4_%d_COMPLETE: 309 real PL + 309 separate PS CPU calls; outputs matched' % side, flush=True)
    except BaseException as exc:
        fail(ctx, exc)
        raise


def summary(ctx):
    require(ctx['state'] == 'LOADED_IDLE' and ctx['completed'] == [256, 512], 'Both sizes must finish first')
    report = summarize(ctx['rows'], ctx['groups'])
    write_json(ctx['directory'] / 'summary.json', report)
    ctx['summary_ready'] = True
    print('W4_SUMMARY_READY: 12 groups; 100 timed samples each, no warmup included', flush=True)
    for group in report['groups']:
        metric = group['metrics']['call']
        print('%d rep%d %s call median %.3f ms / p95 %.3f ms' %
              (group['side'],group['repeat'],group['kind'],metric['median_ns']/1e6,metric['p95_ns']/1e6))
    return report


def finish_export(ctx):
    require(ctx['state'] == 'LOADED_IDLE' and ctx.get('summary_ready') and ctx['inflight'] is None,
            'Finish only after both sizes and summary; never close a failed/in-flight kernel')
    hw = ctx['base']['hardware']
    require(hw.state == 'IDLE' and not hw.retained and hw.downloads == 1 and hw.sequence == 618, 'Unexpected hardware lifecycle')
    for sock in ctx['base']['sockets']:
        sock.close()
    ctx['base']['executor'].shutdown(wait=False)
    ctx['state'] = 'CLOSED_IDLE'
    save_state(ctx)
    write_json(ctx['directory'] / 'final_environment.json', environment())
    inventory = {p.relative_to(ctx['directory']).as_posix(): info(p) for p in ctx['directory'].rglob('*') if p.is_file()}
    write_json(ctx['directory'] / 'result_manifest.json', dict(files=inventory,
        status='COLLECTED_NOT_INDEPENDENTLY_VERIFIED', package_manifest_sha=info(ctx['root']/'w4_manifest.json')['sha256']))
    target = ctx['root'].parent / 'c7_w4_processing_results.zip'
    require(not target.exists(), 'Preserve earlier export')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in sorted(ctx['directory'].rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(ctx['directory']))
    print('W4_RESULTS_READY:', str(target), 'CLOSED_IDLE; download this ZIP and the executed Notebook', flush=True)
    return str(target)
