"""Instrument original official PYNQ DMA calls; preserve all buffers on failure."""
import inspect
import json
import os
import platform
import shutil
import socket
import time
import uuid
import zipfile
from pathlib import Path
import numpy as np
from .common import PROTOCOL, REVISION, info, pattern, require, summarize, validate, word_sha, write_json
import a0_dma_board_test as original


def save(c):
    c['report']['retained_buffers'] = len(c['retained'])
    write_json(c['output']/'report.json', c['report'])


def phase(c, expected, running, done, action):
    require(c['report']['state'] == expected, 'Out of order or previous failure; preserve this kernel')
    c['report']['state'] = running
    save(c)
    try:
        result = action()
        c['report']['state'] = done
        save(c)
        print('W4C_'+done, flush=True)
        return result
    except BaseException as exc:
        c['report'].update(state='FAILED_OR_INTERRUPTED', failed_stage=running,
                           error=type(exc).__name__+': '+str(exc))
        save(c)
        raise


def prepare(root):
    root = Path(root).resolve()
    manifest = validate(root)
    require(shutil.disk_usage(root).free >= 2*1024**3, 'Need at least 2 GiB free for raw data and ZIP')
    # Refuse an existing production service; do not stop any other kernel.
    with socket.socket() as s:
        s.settimeout(2)
        require(s.connect_ex(('127.0.0.1', 8090)) == 111, 'Service 8090 active or unavailable status uncertain; stop')
    output = root/'w4c_results'
    output.mkdir(exist_ok=False)
    (output/'raw').mkdir()
    retained = []
    c = dict(root=root, output=output, retained=retained, report=dict(
        revision=REVISION, protocol=PROTOCOL, state='PRECHECK_STARTED', evidence_kind='PYNQ_PL_DMA',
        session_id=uuid.uuid4().hex, package=info(root/'w4c_manifest.json'), overlay_downloads=0,
        rows=[], error=None, retained_buffers=0,
        board_clock_unverified=True, runtime=dict(python=platform.python_version(), machine=platform.machine())))
    save(c)
    def action():
        c['original'] = original.prepare_test(root, retained)
        c['report']['runtime'].update(c['original']['report'])
        import pynq.lib.dma
        import pynq.buffer
        import pynq.overlay
        sources = {}
        for name, module in [('DMA', pynq.lib.dma), ('buffer', pynq.buffer), ('Overlay', pynq.overlay)]:
            p = Path(inspect.getsourcefile(module))
            sources[name] = dict(path=str(p), **info(p))
        c['report']['runtime_sources'] = sources
        c['report']['clock'] = dict(name='perf_counter', **time.get_clock_info('perf_counter').__dict__)
        require(c['report']['clock']['monotonic'], 'Timing clock not monotonic')
    phase(c, 'PRECHECK_STARTED', 'CHECKING', 'PRECHECK_PASS', action)
    return c


def load(c):
    def action():
        # Count attempted downloads before action; never retry a partially failed load.
        c['report']['overlay_downloads'] += 1
        save(c)
        original.load_test(c['original'])
        c['dma'] = c['original']['overlay'].axi_dma_0
        require(isinstance(c['dma'], c['original']['driver_class']), 'Official DMA binding failed')
        c['report']['driver'] = type(c['dma']).__module__+'.'+type(c['dma']).__name__
    phase(c, 'PRECHECK_PASS', 'LOADING', 'LOAD_PASS', action)


def transfer(c, words, side, repeat, index):
    require(c['original']['overlay'].is_loaded(), 'Overlay identity changed; stop')
    seq = len(c['report']['rows'])+1
    allocate = c['original']['allocate']
    tx = allocate(shape=(words,), dtype=np.uint32)
    c['retained'].append(tx)
    rx = allocate(shape=(words,), dtype=np.uint32)
    c['retained'].append(rx)
    nbytes = words*4
    a, b = int(tx.physical_address), int(rx.physical_address)
    for addr in (a, b):
        require(addr % 8 == 0 and 0x100000 <= addr and addr+nbytes <= 0x20000000, 'Invalid DMA DDR address')
    require(a+nbytes <= b or b+nbytes <= a, 'DMA buffers overlap')
    source = pattern(words, seq)
    tx[:] = source
    rx[:] = ~source
    rx.flush()
    dma = c['dma']
    t0 = time.perf_counter_ns()
    dma.recvchannel.transfer(rx)
    dma.sendchannel.transfer(tx)
    status = original.wait_both_idle(dma)
    t1 = time.perf_counter_ns()
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    t2 = time.perf_counter_ns()
    snapshot = np.array(rx, dtype=np.uint32, copy=True)
    t3 = time.perf_counter_ns()
    require(int(dma.sendchannel.transferred) == nbytes == int(dma.recvchannel.transferred), 'DMA byte count mismatch')
    name = 'raw/{:04d}.npy'.format(seq)
    np.save(c['output']/name, snapshot, allow_pickle=False)
    row = dict(sequence=seq, side=side, repeat=repeat, index=index, words=words, warmup=index<3,
        tx_address=a, rx_address=b, send_bytes=int(dma.sendchannel.transferred), recv_bytes=int(dma.recvchannel.transferred),
        dma_status=status, start_ns=t0, idle_observed_ns=t1, waits_done_ns=t2, snapshot_done_ns=t3,
        transaction_ns=t2-t0, submit_to_observed_idle_ns=t1-t0, wait_invalidate_ns=t2-t1, snapshot_ns=t3-t2,
        input_sha256=word_sha(source), output_sha256=word_sha(snapshot), raw=name, raw_file=info(c['output']/name),
        exact_match=bool(np.array_equal(source, snapshot)))
    c['report']['rows'].append(row)
    save(c)
    require(row['exact_match'], 'Loopback output mismatch; raw output preserved')
    # Only after idle, official invalidation, raw preservation and full comparison.
    rx.freebuffer()
    require(c['retained'].pop() is rx, 'RX ownership changed')
    tx.freebuffer()
    require(c['retained'].pop() is tx, 'TX ownership changed')
    save(c)
    print('W4C_FRAME_SAVED {}/619: side={} repeat={} index={}'.format(seq, side, repeat, index), flush=True)


def smoke(c):
    phase(c, 'LOAD_PASS', 'SMOKE_RUNNING', 'SMOKE_PASS', lambda: transfer(c, 17, 0, 0, 0))


def measure(c, side):
    require(side in (256, 512), 'Unsupported size')
    def action():
        for repeat in (1, 2, 3):
            for index in range(103):
                transfer(c, side*side, side, repeat, index)
    phase(c, 'SMOKE_PASS' if side == 256 else '256_COMPLETE', str(side)+'_RUNNING', str(side)+'_COMPLETE', action)


def finish_export(c):
    def close():
        require(not c['retained'], 'Buffers remain; stop without reset')
        require(len(c['report']['rows']) == 619 and c['report']['overlay_downloads'] == 1, 'Incomplete collection')
        c['report']['summary'] = summarize(c['report']['rows'])
        c['report']['close_status'] = original.wait_both_idle(c['dma'])
        c['dma'].sendchannel.stop()
        c['dma'].recvchannel.stop()
        c['report']['channels_stopped'] = True
    phase(c, '512_COMPLETE', 'CLOSING', 'CLOSED_IDLE', close)
    output = c['output']
    write_json(output/'bundle_manifest.json', dict(revision=REVISION,
        files={p.relative_to(output).as_posix():info(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    bundle = c['root'].parent/'c7_w4_dma_results.zip'
    require(not bundle.exists(), 'Results ZIP already exists; do not replace')
    temp = bundle.with_suffix('.zip.partial')
    require(not temp.exists(), 'Earlier interrupted export exists; preserve')
    files = [p for p in sorted(output.rglob('*')) if p.is_file()]
    with zipfile.ZipFile(temp, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for i, p in enumerate(files, 1):
            z.write(p, p.relative_to(output))
            if i % 25 == 0 or i == len(files):
                print('W4C_EXPORT_PROGRESS {}/{}'.format(i, len(files)), flush=True)
    temp.replace(bundle)
    print('W4C_RESULTS_READY:', bundle, flush=True)
    print(json.dumps(c['report']['summary'], ensure_ascii=False), flush=True)
    return str(bundle)
