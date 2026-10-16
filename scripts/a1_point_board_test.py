"""Point-stage board validation; official PYNQ DMA/GPIO, no vessel segmentation."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from a0_dma_board_test import guarded_phase, sha256_file, wait_both_idle


REVISION = "a1_point_r2_notebook_precheck_fix"
FIXED_ARTIFACTS = {"a1_point.bit", "a1_point.hwh", "a1_point_board_test.py",
                   "a0_dma_board_test.py", "使用说明.txt"}
NOTEBOOK_NAME = "a1_point_check.ipynb"


def notebook_code_hash(notebook):
    """Execution outputs/metadata change on save; executable cell sources must match."""
    if notebook.get("nbformat") != 4 or not isinstance(notebook.get("cells"), list):
        raise ValueError("Unsupported notebook structure")
    sources = []
    for cell in notebook["cells"]:
        if cell.get("cell_type") == "code":
            source = cell.get("source")
            if isinstance(source, list) and all(isinstance(line, str) for line in source):
                source = "".join(source)
            if not isinstance(source, str):
                raise ValueError("Malformed notebook code source")
            sources.append(source.replace("\r\n", "\n"))
    if not sources:
        raise ValueError("Notebook has no code cells")
    payload = json.dumps(sources, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_package(directory, manifest):
    directory = Path(directory)
    if manifest.get("revision") != REVISION:
        raise ValueError("Wrong release; upload both corrected runner and manifest")
    if set(manifest.get("artifacts", {})) != FIXED_ARTIFACTS | {NOTEBOOK_NAME}:
        raise ValueError("Incomplete or unexpected artifact manifest")
    for name in sorted(FIXED_ARTIFACTS):
        if sha256_file(directory / name) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Package mismatch: " + name)
    contract = manifest.get("notebook_validation", {})
    if contract.get("algorithm") != "sha256-code-cells-v1":
        raise ValueError("Missing notebook code validation contract")
    notebook = json.loads((directory / NOTEBOOK_NAME).read_text(encoding="utf-8"))
    code_hash = notebook_code_hash(notebook)
    if code_hash != contract.get("sha256"):
        raise ValueError("Notebook code mismatch: " + NOTEBOOK_NAME)
    return {"fixed_artifacts": "PASS_EXACT_SHA256", "notebook_code": "PASS_CANONICAL_CODE_SHA256",
            "notebook_code_sha256": code_hash,
            "current_notebook_sha256": sha256_file(directory / NOTEBOOK_NAME),
            "original_notebook_sha256": manifest["artifacts"][NOTEBOOK_NAME]["sha256"],
            "policy": "Execution counts, outputs, notebook metadata and Markdown are excluded; all executable code must match"}


def point_expected(words, mode):
    if mode == 0:
        return words.copy()
    green = (words >> 8) & np.uint32(255)
    enhanced = green if mode == 1 else np.minimum(255, (green * 255 + 96) // 192)
    return (green | (enhanced << 8)).astype(np.uint32)


def prepare_a1(directory, retained_buffers):
    import pynq
    from pynq import Overlay, allocate
    from pynq.lib import DMA, AxiGPIO
    if pynq.__version__ != "3.0.1":
        raise RuntimeError("Use the measured PYNQ 3.0.1 runtime")
    if retained_buffers:
        raise RuntimeError("Earlier in-flight buffers remain; stop")
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "a1_manifest.json").read_text())
    package_validation = validate_package(directory, manifest)
    overlay = Overlay(str(directory / "a1_point.bit"), download=False)
    dma = overlay.ip_dict["axi_dma_0"]
    gpio = overlay.ip_dict["point_control"]
    if dma["type"] != "xilinx.com:ip:axi_dma:7.1" or dma["phys_addr"] != 0x40400000:
        raise ValueError("Unexpected DMA mapping")
    expected = {"c_include_sg": 0, "c_micro_dma": 0, "c_sg_length_width": 23,
                "c_m_axis_mm2s_tdata_width": 32, "c_s_axis_s2mm_tdata_width": 32,
                "c_m_axi_mm2s_data_width": 64, "c_m_axi_s2mm_data_width": 32}
    if any(int(dma["parameters"][key]) != value for key, value in expected.items()):
        raise ValueError("Unexpected DMA parameters")
    if gpio["type"] != "xilinx.com:ip:axi_gpio:2.0" or gpio["phys_addr"] != 0x41200000:
        raise ValueError("Unexpected GPIO mapping")
    for key, value in {"C_IS_DUAL": 1, "C_GPIO_WIDTH": 32, "C_GPIO2_WIDTH": 32,
                       "C_ALL_OUTPUTS": 1, "C_ALL_INPUTS_2": 1, "C_INTERRUPT_PRESENT": 0}.items():
        if int(gpio["parameters"][key]) != value:
            raise ValueError("Unexpected GPIO parameter: " + key)
    report = {"status": "PRECHECK_PASS_FPGA_UNCHANGED", "manifest": manifest,
              "package_validation": package_validation,
              "board_clock_utc_unverified": datetime.now(timezone.utc).isoformat(),
              "pynq": pynq.__version__, "python": platform.python_version(),
              "kernel": platform.release(), "transfers": [],
              "scope": "Point-stage bypass/green/LUT only; no Gaussian, segmentation, HDMI or FPS PASS"}
    output = directory / "a1_point_result.json"
    if output.exists():
        raise RuntimeError("Use a new folder; preserve earlier board result")
    def save():
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(output)
    save()
    print("A1_PRECHECK_PASS: file hashes and metadata; FPGA unchanged", flush=True)
    return {"overlay": overlay, "report": report, "save": save, "retained": retained_buffers,
            "allocate": allocate, "dma_class": DMA, "gpio_class": AxiGPIO}


def load_a1(context):
    if context["report"]["status"] != "PRECHECK_PASS_FPGA_UNCHANGED":
        raise RuntimeError("Precheck must finish before loading")
    def action():
        context["overlay"].download()
        context["dma"] = context["overlay"].axi_dma_0
        context["gpio"] = context["overlay"].point_control
        if not isinstance(context["dma"], context["dma_class"]) or not isinstance(context["gpio"], context["gpio_class"]):
            raise RuntimeError("Official DMA/GPIO drivers did not bind")
        context["gpio"].channel1.setdirection("out")
        context["gpio"].channel2.setdirection("in")
        if context["gpio"].channel2.read() != 0:
            raise RuntimeError("Frame state not reset after programming")
        context["report"]["status"] = "A1_LOADED_NO_TRANSFER"
        context["save"]()
        print("A1_LOAD_PASS: official drivers and reset state checked", flush=True)
    guarded_phase(context, "A1_PROGRAMMING_OVERLAY", action)


def transfer_a1(context, side, mode, pattern):
    if side not in (256, 512) or mode not in (0, 1, 2):
        raise ValueError("Only complete 256/512 frames and valid modes supported")
    count = side * side
    if pattern == "black":
        source = np.full(count, 0x01000000, np.uint32)
    elif pattern == "white":
        source = np.full(count, 0x01FFFFFF, np.uint32)
    elif pattern == "ramp":
        index = np.arange(count, dtype=np.uint32)
        source = ((index & 1) << 24) | (((index * 11) & 255) << 16) | ((index & 255) << 8) | ((index * 7) & 255)
    elif pattern == "random":
        rng = np.random.default_rng(20261011 + len(context["report"]["transfers"]))
        source = rng.integers(0, 1 << 24, count, dtype=np.uint32) | (rng.integers(0, 2, count, dtype=np.uint32) << 24)
    else:
        raise ValueError("Unknown pattern")
    expected = point_expected(source, mode)
    gpio, dma = context["gpio"], context["dma"]
    gpio.channel1.write(mode | (4 if side == 256 else 0), 0xFFFFFFFF)
    tx = context["allocate"](shape=(count,), dtype=np.uint32)
    context["retained"].append(tx)
    rx = context["allocate"](shape=(count,), dtype=np.uint32)
    context["retained"].append(rx)
    nbytes = count * 4
    for buffer in (tx, rx):
        if buffer.physical_address % 8 or not (0x00100000 <= buffer.physical_address <= 0x20000000 - nbytes):
            raise RuntimeError("Buffer outside aligned HP0 DDR window")
    if max(tx.physical_address, rx.physical_address) < min(tx.physical_address, rx.physical_address) + nbytes:
        raise RuntimeError("DMA buffers overlap")
    tx[:] = source
    rx[:] = np.bitwise_not(expected)
    rx.flush()
    # Persist the exact case before any DMA/MMIO access that might block.
    context["report"]["active_case"] = {"side": side, "mode": mode, "pattern": pattern}
    context["save"]()
    dma.recvchannel.transfer(rx)
    dma.sendchannel.transfer(tx)
    statuses = wait_both_idle(dma)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    if dma.sendchannel.transferred != nbytes or dma.recvchannel.transferred != nbytes:
        raise AssertionError("DMA byte count mismatch")
    mismatch = np.flatnonzero(rx != expected)
    if mismatch.size:
        raise AssertionError("Point-stage mismatch at word " + str(int(mismatch[0])))
    frame_status = int(gpio.channel2.read())
    expected_frames = (len(context["report"]["transfers"]) + 1) & 0x3FFF
    if frame_status >> 28 or (frame_status & 0x3FFF) != expected_frames or ((frame_status >> 14) & 0x3FFF) != expected_frames:
        raise AssertionError("RTL frame counters/error flags do not match completed DMA")
    context["report"]["transfers"].append({"side": side, "mode": mode, "pattern": pattern,
        "words": count, "send_bytes": int(dma.sendchannel.transferred), "recv_bytes": int(dma.recvchannel.transferred),
        "tx_address": int(tx.physical_address), "rx_address": int(rx.physical_address),
        "dma_status": statuses, "frame_status": frame_status, "status": "PASS_EXACT_POINT_STAGE_WORDS",
        "input_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
        "expected_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
        "output_sha256": hashlib.sha256(np.asarray(rx).tobytes()).hexdigest()})
    context["report"].pop("active_case")
    context["save"]()
    rx.freebuffer(); tx.freebuffer()
    context["retained"].clear()
    print("POINT_FRAME_PASS:", side, "mode", mode, pattern, flush=True)


def smoke_a1(context):
    if context["report"]["status"] != "A1_LOADED_NO_TRANSFER":
        raise RuntimeError("Load once before the smoke test")
    def action():
        transfer_a1(context, 256, 1, "ramp")
        context["report"]["status"] = "A1_SMOKE_PASS_FULL_SUITE_PENDING"
        context["save"]()
        print("A1_SMOKE_PASS: full 256x256 green frame matched", flush=True)
    guarded_phase(context, "A1_SMOKE_RUNNING", action)


def full_a1(context):
    if context["report"]["status"] != "A1_SMOKE_PASS_FULL_SUITE_PENDING":
        raise RuntimeError("Smoke must pass first")
    def action():
        cases = [(side, mode, pattern) for side in (256, 512) for mode in (0, 1, 2)
                 for pattern in ("ramp", "random")]
        cases += [(side, 2, pattern) for side in (256, 512) for pattern in ("black", "white")]
        for case in cases:
            transfer_a1(context, *case)
        context["report"]["status"] = "A1_PASS_17_POINT_FRAMES_NOT_FULL_MEDICAL_ALGORITHM"
        context["save"]()
        print("A1 POINT PASS: 17 complete frames matched; no segmentation/HDMI PASS", flush=True)
    guarded_phase(context, "A1_FULL_SUITE_RUNNING", action)
    return context["report"]
