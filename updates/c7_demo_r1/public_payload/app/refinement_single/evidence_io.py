"""Disk evidence only; no hardware imports, allocation, inference or retry.

The original transport event writer already flushes and fsyncs each JSONL line.
These helpers use it without changing its schema. fsync/reopen are OS evidence,
not a guarantee against a storage device that ignores flushes or loses power.
"""
from pathlib import Path
import datetime
import hashlib
import os
import time
import numpy as np
import transport


def boot_context():
    # Called once by the ARM operator, before loading any overlay.
    return dict(pid=os.getpid(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                monotonic_seconds=time.monotonic(),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                uptime_text=Path('/proc/uptime').read_text().strip(),
                clock_note='Board wall clock may be stale; use boot_id and monotonic time.')


def trace_call(ctx, label, action, details):
    """Exactly one action; preserve a durable intent if it hangs or throws.

    No retry or extra register read. Nested metadata cannot overwrite event fields.
    A missing return record identifies the last attempted call, not its root cause.
    """
    # Critical records never print; stdout/Jupyter backpressure must not precede action.
    transport.event(ctx, 'ACCESS_INTENT', dict(label=label, details=details), console=False)
    started = time.perf_counter()
    try:
        result = action()
    except BaseException as exc:
        transport.event(ctx, 'ACCESS_FAILED', dict(label=label, details=details,
                        seconds=time.perf_counter()-started,
                        exception_type=type(exc).__name__, exception_message=str(exc)), console=False)
        raise
    transport.event(ctx, 'ACCESS_RETURNED', dict(label=label, details=details,
                    seconds=time.perf_counter()-started), console=False)
    return result



def sync_directory(path):
    if os.name != 'posix':
        return 'NOT_SUPPORTED_ON_THIS_HOST'
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return 'FSYNC_RETURNED'


def reload_arrays(path, arrays, expected):
    with np.load(path, allow_pickle=False) as loaded:
        transport.require(set(loaded.files) == {'h', 'z', 'r'}, 'SR_DISK_FIELDS')
        for name, original in arrays.items():
            value = loaded[name]
            transport.require(value.dtype == original.dtype and value.shape == original.shape,
                              'SR_DISK_LAYOUT:' + name)
            transport.require(np.array_equal(value, original), 'SR_DISK_VALUES:' + name)
            transport.require(transport.raw_sha(value) == expected[name], 'SR_DISK_SHA:' + name)


def persist_sr(ctx, frame, arrays, expected):
    """Save ordinary CPU copies after the original device-to-CPU invalidation.

    No device buffer access here. Temporary and final files are never overwritten.
    On error leave the temporary file for diagnosis and propagate the exception.
    """
    transport.require(set(arrays) == set(expected) == {'h', 'z', 'r'}, 'SR_FIELDS')
    for name, value in arrays.items():
        transport.require(type(value) is np.ndarray and value.dtype == np.int16,
                          'SR_HOST_INT16:' + name)
    actual = {name: transport.raw_sha(value) for name, value in arrays.items()}
    transport.require(actual == expected, 'S_R_NUMERIC_MISMATCH; BRIDGE_NOT_STARTED')
    final = Path(frame) / 'sr_before_bridge.npz'
    temp = Path(frame) / 'sr_before_bridge.npz.partial'
    transport.require(not final.exists() and not temp.exists(), 'SR_DISK_ALREADY_EXISTS')
    transport.event(ctx, 'SR_PERSIST_INTENT', dict(frame=Path(frame).name, array_sha=actual))
    started = time.perf_counter()
    with temp.open('xb') as f:
        np.savez_compressed(f, **arrays)
        f.flush()
        os.fsync(f.fileno())
    reload_arrays(temp, arrays, expected)
    # Hard-link publication is atomic and refuses to replace an existing final.
    # The board's Linux ext4 supports it; failure is a stop, never a fallback.
    os.link(temp, final)
    dir_sync = sync_directory(frame)
    temp.unlink()
    sync_directory(frame)
    reload_arrays(final, arrays, expected)
    receipt = dict(frame=Path(frame).name, array_sha=actual,
                   arrays={k: dict(dtype=str(v.dtype), shape=list(v.shape), bytes=int(v.nbytes))
                           for k, v in arrays.items()},
                   file_sha256=transport.sha(final), file_bytes=final.stat().st_size,
                   file_fsync='RETURNED', directory_fsync=dir_sync,
                   temporary_and_final_reload='EXACT', seconds=time.perf_counter()-started,
                   scope='Actual current PL values; no cached substitution; no power-loss guarantee')
    transport.write(Path(frame) / 'sr_persistence_receipt.json', receipt)
    transport.write(Path(frame) / 'sr_before_bridge_sha.json', actual)
    sync_directory(frame)
    transport.event(ctx, 'SR_DISK_RELOADED_VERIFIED', receipt)
    return actual


def persist_c7(ctx, frame, array, side, expected_sha):
    """Future runs only: ordinary CPU uint32 copy, never read a device buffer here.

    Reuses the S/R exclusive temporary -> fsync -> reload -> hard-link ->
    directory sync -> reload sequence. OS returns are not a power-loss guarantee.
    """
    transport.require(type(array) is np.ndarray and array.dtype == np.dtype('uint32')
                      and side in (256, 512) and array.shape == (side, side), 'C7_HOST_LAYOUT')
    transport.require(transport.raw_sha(array) == expected_sha, 'C7_HOST_SHA')
    frame = Path(frame)
    final = frame / 'c7_output.npy'
    temp = frame / 'c7_output.npy.partial'
    transport.require(not final.exists() and not temp.exists(), 'C7_DISK_ALREADY_EXISTS')

    def reload(path):
        got = np.load(path, allow_pickle=False)
        transport.require(got.dtype == array.dtype and got.shape == array.shape, 'C7_DISK_LAYOUT')
        transport.require(np.array_equal(got, array) and transport.raw_sha(got) == expected_sha, 'C7_DISK_VALUES')

    transport.event(ctx, 'C7_PERSIST_INTENT', dict(frame=frame.name, raw_sha=expected_sha), console=False)
    started = time.perf_counter()
    with temp.open('xb') as f:
        np.save(f, array, allow_pickle=False)
        f.flush()
        os.fsync(f.fileno())
    reload(temp)
    os.link(temp, final)
    directory_status = sync_directory(frame)
    temp.unlink()
    sync_directory(frame)
    reload(final)
    receipt = dict(frame=frame.name, dtype=str(array.dtype), shape=list(array.shape),
        raw_bytes=int(array.nbytes), raw_sha256=expected_sha,
        file_bytes=final.stat().st_size, file_sha256=transport.sha(final),
        file_fsync='RETURNED', directory_fsync=directory_status,
        temporary_and_final_reload='EXACT', seconds=time.perf_counter()-started,
        scope='Ordinary host copy of current capture; no cached substitution; no power-loss guarantee')
    transport.write(frame / 'c7_persistence_receipt.json', receipt)
    sync_directory(frame)
    transport.event(ctx, 'C7_DISK_RELOADED_VERIFIED', receipt, console=False)
    return receipt
