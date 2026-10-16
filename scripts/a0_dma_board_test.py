"""A0 board test: reuse PYNQ 3.0.1 DMA/allocate, no custom DMA driver.

Imported by the generated notebook. Retains in-flight buffers on failure;
Polling deadlines apply only while MMIO returns; they cannot recover a hung AXI bus.
"""
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wait_both_idle(dma, timeout=5.0):
    deadline = time.monotonic() + timeout
    while True:
        status = {"mm2s": int(dma.mmio.read(0x04)),
                  "s2mm": int(dma.mmio.read(0x34))}
        if any(value & 0x70 for value in status.values()):
            raise RuntimeError("DMA error: " + json.dumps(status))
        if all(value & 0x02 for value in status.values()):
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError("DMA timeout: " + json.dumps(status))
        time.sleep(0.001)


def run_suite(dma, allocate, report, retained_buffers, save_report, cases=None):
    """70 transfers, full compare, including two 1 MiB frame sequences.

    Caller retains the list until reprogramming/reset ends any failed DMA.
    Tests verify MM2S/S2MM + FIFO + DDR/cache path, not an algorithm or HDMI.
    """
    rng = np.random.default_rng(20261011)
    if cases is None:
        cases = [(n, pattern) for n in (1, 3, 17, 1023, 1024)
                 for pattern in ("increment", "random")]
        cases += [(side * side, pattern) for side in (256, 512)
                  for pattern in ("increment", "random") for _ in range(15)]
    report["expected_transfers"] = len(cases)
    report["status"] = "RUNNING"
    save_report()
    for index, (words, pattern) in enumerate(cases):
        tx = allocate(shape=(words,), dtype=np.uint32)
        retained_buffers.append(tx)
        rx = allocate(shape=(words,), dtype=np.uint32)
        retained_buffers.append(rx)
        # Retain buffers if allocation/transfer fails. Never use a context
        # manager which could free a buffer while hardware still accesses it.
        nbytes = words * 4
        for buf in (tx, rx):
            if (buf.physical_address % 8 or buf.physical_address < 0x00100000
                    or buf.physical_address + nbytes > 0x20000000):
                raise RuntimeError("Buffer outside A0 aligned HP0 DDR window")
        if pattern == "random":
            expected = rng.integers(0, 1 << 32, size=words, dtype=np.uint32)
        else:
            expected = np.arange(words, dtype=np.uint32) ^ np.uint32(index * 0x01010101)
        tx[:] = expected
        rx[:] = np.bitwise_not(expected)
        # Ensure poison data reaches DDR before S2MM and cannot overwrite it
        # through a later dirty cache line. Official send.transfer flushes tx.
        rx.flush()
        started = time.monotonic()
        dma.recvchannel.transfer(rx)
        dma.sendchannel.transfer(tx)
        statuses = wait_both_idle(dma)
        # Both engines are idle here; the official wait does not spin.
        dma.sendchannel.wait()
        dma.recvchannel.wait()  # official buffer invalidate
        for channel in (dma.sendchannel, dma.recvchannel):
            if int(channel.transferred) != nbytes:
                raise AssertionError("Transferred byte count does not match requested size")
        different = np.flatnonzero(rx != expected)
        if different.size:
            first = int(different[0])
            raise AssertionError("Mismatch at word {}: {} != {}".format(
                first, int(rx[first]), int(expected[first])))
        report["transfers"].append({
            "index": index, "words": words, "bytes": nbytes, "pattern": pattern,
            "status": "PASS_EXACT_WORD_COMPARE", "dma_status": statuses,
            "send_bytes": int(dma.sendchannel.transferred),
            "recv_bytes": int(dma.recvchannel.transferred),
            "send_physical_address": int(tx.physical_address),
            "recv_physical_address": int(rx.physical_address),
            "elapsed_seconds": time.monotonic() - started,
            "input_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
            "output_sha256": hashlib.sha256(np.asarray(rx).tobytes()).hexdigest(),
        })
        save_report()
        # Hardware is idle and these buffers have passed the compare.
        rx.freebuffer()
        tx.freebuffer()
        # ndarray equality is elementwise; list.remove would compare arrays.
        assert retained_buffers.pop() is rx
        assert retained_buffers.pop() is tx
        print("PASS {}/{}: {} words, {}".format(index + 1, len(cases), words, pattern))
    report["status"] = "PASS_ALL_EXACT_WORD_COMPARE"
    save_report()


def prepare_test(directory=".", retained_buffers=None):
    """Check paired files and metadata without programming the FPGA."""
    import pynq
    from pynq import Overlay, allocate
    from pynq.lib.dma import DMA

    if platform.system() != "Linux" or platform.machine() not in ("armv7l", "armv7"):
        raise RuntimeError("Run this notebook on the PYNQ-Z2 board, not Windows")
    if pynq.__version__ != "3.0.1":
        raise RuntimeError("This test is prepared for the measured PYNQ 3.0.1 runtime")
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "a0_manifest.json").read_text(encoding="utf-8"))
    for name in ("a0_dma.bit", "a0_dma.hwh"):
        if sha256_file(directory / name) != manifest["artifacts"][name]["sha256"]:
            raise RuntimeError("Artifact hash mismatch: " + name)
    if retained_buffers is None:
        raise ValueError("Caller must keep a retained_buffers list alive on failure")
    if retained_buffers:
        raise RuntimeError("Earlier failed buffers remain; reset/reprogram before a new run")
    report = {"status": "PRECHECK_STARTED_FPGA_UNCHANGED", "transfers": [],
              "board_clock_utc_unverified": datetime.now(timezone.utc).isoformat(),
              "pynq": pynq.__version__, "python": platform.python_version(),
              "kernel": platform.release(), "manifest": manifest,
              "scope": "A0 DMA/FIFO exact loopback only; no medical algorithm or HDMI"}
    output = directory / "a0_dma_result.json"

    def save_report():
        tmp = output.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        tmp.replace(output)

    save_report()
    print("PRECHECK: reading metadata; FPGA unchanged", flush=True)
    overlay = Overlay(str(directory / "a0_dma.bit"), download=False)
    description = overlay.ip_dict["axi_dma_0"]
    params = description["parameters"]
    expected = {"c_include_sg": 0, "c_micro_dma": 0, "c_include_mm2s": 1,
                "c_include_s2mm": 1, "c_sg_length_width": 23,
                "c_m_axi_mm2s_data_width": 64, "c_m_axi_s2mm_data_width": 32,
                "c_m_axis_mm2s_tdata_width": 32, "c_s_axis_s2mm_tdata_width": 32}
    for key, value in expected.items():
        if int(params[key]) != value:
            raise RuntimeError("Unexpected DMA parameter: " + key)
    if int(description["phys_addr"]) != 0x40400000:
        raise RuntimeError("Unexpected DMA control address")
    if manifest.get("revision") != "r2_auxiliary_reset_fix":
        raise RuntimeError("Old A0 package withdrawn; use paired r2 files")
    report["status"] = "PRECHECK_PASS_FPGA_UNCHANGED"
    report["dma_description"] = {"type": description["type"],
                                 "phys_addr": int(description["phys_addr"]),
                                 "parameters_checked": expected}
    save_report()
    print("PRECHECK_PASS: hashes, runtime and DMA metadata checked; FPGA unchanged", flush=True)
    return {"overlay": overlay, "report": report, "save": save_report,
            "retained": retained_buffers, "allocate": allocate, "driver_class": DMA}


def guarded_phase(context, stage, action):
    report = context["report"]
    if report["status"] == "FAILED_OR_INTERRUPTED":
        raise RuntimeError("Previous phase failed; stop and preserve records")
    report["status"] = stage
    context["save"]()
    print(stage, flush=True)
    try:
        action()
    except BaseException as exc:
        report["failed_stage"] = report["status"]
        report["status"] = "FAILED_OR_INTERRUPTED"
        report["error"] = type(exc).__name__ + ": " + str(exc)
        report["retained_buffers"] = len(context["retained"])
        report["recovery"] = "Stop and preserve records; do not free in-flight buffers."
        context["save"]()
        raise


def load_test(context):
    if context["report"]["status"] != "PRECHECK_PASS_FPGA_UNCHANGED":
        raise RuntimeError("Run precheck once before loading")
    def action():
        context["overlay"].download()
        context["report"]["status"] = "OVERLAY_LOADED_NO_DMA_TRANSFER"
        context["save"]()
        print("LOAD_PASS: overlay loaded; no DMA transfer yet", flush=True)
    guarded_phase(context, "PROGRAMMING_OVERLAY", action)


def smoke_test(context):
    if context["report"]["status"] != "OVERLAY_LOADED_NO_DMA_TRANSFER":
        raise RuntimeError("Complete loading before the short test")
    def action():
        dma = context["overlay"].axi_dma_0
        if not isinstance(dma, context["driver_class"]):
            raise RuntimeError("PYNQ did not bind its official DMA driver")
        context["dma"] = dma
        context["report"]["dma_description"]["driver"] = type(dma).__module__ + "." + type(dma).__name__
        context["report"]["status"] = "SMOKE_TRANSFERRING_17_WORDS"
        context["report"]["smoke"] = {"transfers": []}
        context["save"]()
        print("DRIVER_READY: starting one 17-word loopback", flush=True)
        run_suite(dma, context["allocate"], context["report"]["smoke"],
                  context["retained"], context["save"], cases=[(17, "increment")])
        context["report"]["status"] = "SMOKE_PASS_17_WORDS_FULL_SUITE_PENDING"
        context["save"]()
        print("SMOKE_PASS: all 17 words and both byte counts matched", flush=True)
    guarded_phase(context, "OPENING_OFFICIAL_DMA_DRIVER", action)


def full_test(context):
    if context["report"]["status"] != "SMOKE_PASS_17_WORDS_FULL_SUITE_PENDING":
        raise RuntimeError("Short loopback must pass before the full suite")
    def action():
        run_suite(context["dma"], context["allocate"], context["report"],
                  context["retained"], context["save"])
        print("A0 DMA PASS: all 70 transfers matched. Saved a0_dma_result.json", flush=True)
    guarded_phase(context, "FULL_SUITE_RUNNING", action)
    return context["report"]
