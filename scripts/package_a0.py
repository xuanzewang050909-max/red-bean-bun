"""Package a successful host build without marking the board test as passed."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file_info(path):
    return {"bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=ROOT / "results/a0_dma_2017_4")
    args = parser.parse_args()
    build = args.build.resolve()
    destination = args.destination.resolve()
    result = args.results.resolve()
    result.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("Refusing to overwrite an existing deployment directory")
    log_text = args.log.read_text(encoding="utf-8", errors="replace")
    if "\nA0_BITSTREAM_GENERATED_TIMING_CHECKED (host only; not board DMA PASS)" not in log_text:
        raise RuntimeError("Missing completed build marker")
    if "ERROR:" in log_text:
        raise RuntimeError("Build log contains errors")
    timing = (build / "timing_summary.rpt").read_text(encoding="utf-8")
    if "All user specified timing constraints are met." not in timing:
        raise RuntimeError("Timing report did not pass")
    if "There are 0 register/latch pins with no clock." not in timing:
        raise RuntimeError("Unclocked registers")
    if "There are 0 pins that are not constrained for maximum delay." not in timing:
        raise RuntimeError("Unconstrained internal endpoints")
    summary = re.search(
        r"WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)"
        r"\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)"
        r"\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)", timing, re.S)
    if not summary:
        raise RuntimeError("Cannot read timing summary")
    values = summary.groups()
    timing_summary = {"wns_ns": float(values[0]), "tns_ns": float(values[1]),
                      "setup_failing_endpoints": int(values[2]),
                      "whs_ns": float(values[4]), "ths_ns": float(values[5]),
                      "hold_failing_endpoints": int(values[6]),
                      "wpws_ns": float(values[8]), "tpws_ns": float(values[9]),
                      "pulse_width_failing_endpoints": int(values[10])}
    if any(timing_summary[key] != 0 for key in (
        "setup_failing_endpoints", "hold_failing_endpoints", "pulse_width_failing_endpoints")):
        raise RuntimeError("Timing failures")
    drc = (build / "drc.rpt").read_text(encoding="utf-8")
    if re.search(r"\|\s*(?:Error|Critical Warning)\s*\|", drc, re.I):
        raise RuntimeError("DRC contains errors or critical warnings")
    if file_info(build / "build_script_used.tcl") != file_info(ROOT / "vivado/scripts/build_minimal_dma.tcl"):
        raise RuntimeError("Build script differs from current source")
    metadata = json.loads((result / "hwh_host_check.json").read_text(encoding="utf-8"))
    if metadata.get("auxiliary_reset_active_low_tied_high") is not True:
        raise RuntimeError("Correct auxiliary reset wiring has not been checked")
    if metadata["hwh_sha256"] != file_info(build / "deploy/a0_dma.hwh")["sha256"]:
        raise RuntimeError("Metadata check does not match build HWH")
    reset_check = json.loads((result / "reset_simulation_check.json").read_text(encoding="utf-8"))
    if reset_check["status"] != "PASS_HOST_VENDOR_RESET_SIMULATION":
        raise RuntimeError("Vendor reset simulation has not passed")
    if reset_check["xci_sha256"] != file_info(build / "a0_dma.srcs/sources_1/bd/a0_dma/ip/a0_dma_reset_100m_0/a0_dma_reset_100m_0.xci")["sha256"]:
        raise RuntimeError("Reset simulation belongs to a different IP configuration")
    if reset_check["testbench_sha256"] != file_info(ROOT / "scripts/a0_reset_tb.sv")["sha256"]:
        raise RuntimeError("Reset testbench differs from tested source")
    if reset_check["simulation_tcl_sha256"] != file_info(ROOT / "scripts/simulate_a0_reset.tcl")["sha256"]:
        raise RuntimeError("Reset simulation script differs from tested source")
    if reset_check["simulate_log_sha256"] != file_info(result / "reset_simulate.log")["sha256"]:
        raise RuntimeError("Reset simulation log changed")
    sim_text = (result / "reset_simulate.log").read_text(encoding="utf-8", errors="replace")
    if "RESET_SIM_PASS:" not in sim_text or "Fatal:" in sim_text:
        raise RuntimeError("Reset simulation did not finish successfully")
    # Verify notebook has exactly the current script and no execution outputs.
    notebook = ROOT / "notebooks/a0_dma_loopback.ipynb"
    data = json.loads(notebook.read_text(encoding="utf-8"))
    codes = [c for c in data["cells"] if c["cell_type"] == "code"]
    assert "".join(codes[0]["source"]) == (ROOT / "scripts/a0_dma_board_test.py").read_text(encoding="utf-8")
    for c in codes:
        assert c["execution_count"] is None and not c["outputs"]
        compile("".join(c["source"]), "notebook", "exec")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_paths = ["vivado/scripts/build_minimal_dma.tcl", "scripts/a0_dma_board_test.py",
                    "scripts/build_a0_notebook.py", "scripts/check_a0_hwh.py",
                    "scripts/package_a0.py", "scripts/a0_reset_tb.sv",
                    "scripts/simulate_a0_reset.tcl", "tests/test_a0_board_runner.py",
                    "notebooks/a0_dma_loopback.ipynb"]
    # Compare committed files using git's newline-filtered index, so CRLF host
    # working copies are allowed but unpublished source modifications are not.
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--", *source_paths], cwd=ROOT)
    if dirty:
        raise RuntimeError("Source changes must be committed before packaging")
    manifest = {"created_host_utc": datetime.now(timezone.utc).isoformat(),
                "status": "HOST_BUILD_COMPLETE_BOARD_TEST_PENDING", "source_commit": commit,
                "tool": "Vivado 2017.4", "part": "xc7z020clg400-1",
                "board_part": "tul.com.tw:pynq-z2:part0:1.0", "pcb_revision": None,
                "target_runtime": "PYNQ 3.0.1", "build_directory": str(build.relative_to(ROOT)),
                "revision": "r2_auxiliary_reset_fix",
                "sources": {name: file_info(ROOT / name) for name in source_paths},
                "board_reference": {name: file_info(ROOT / "references/board/pynq-z2/pynq-z2/A.0" / name)
                                    for name in ("board.xml", "preset.xml", "part0_pins.xml")},
                "hwh_parser_reference": "PYNQ v3.0.1 / 93ddd21ab623883590a8c8b07f0b157b2855da4b",
                "artifacts": {name: file_info(build / "deploy" / name)
                              for name in ("a0_dma.bit", "a0_dma.hwh")},
                "notebook": file_info(notebook), "timing": timing_summary,
                "reset_simulation": reset_check,
                "test_plan": "70 exact DMA/FIFO loopbacks; short packets, 256/512 frames, increment/random",
                "scope": "Host implementation + metadata + vendor reset simulation; board DMA, medical algorithm and final HDMI overlay unverified"}
    destination.mkdir(parents=True)
    for name in ("a0_dma.bit", "a0_dma.hwh"):
        shutil.copy2(build / "deploy" / name, destination / name)
    shutil.copy2(notebook, destination / notebook.name)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (destination / "a0_manifest.json").write_text(payload, encoding="utf-8")
    (result / "a0_manifest.json").write_text(payload, encoding="utf-8")
    for name in ("configuration.txt", "reconstructed_bd.tcl", "timing_summary.rpt", "utilization.rpt",
                 "drc.rpt", "clocks.rpt", "ip_status.rpt", "build_script_used.tcl"):
        shutil.copy2(build / name, result / name)
    shutil.copy2(args.log, result / "vivado_build.log")
    for stage in ("synth_1", "impl_1"):
        shutil.copy2(build / "a0_dma.runs" / stage / "runme.log", result / (stage + ".log"))
    print("PACKAGED_HOST_BUILD_BOARD_PENDING:", destination)
    print(json.dumps(timing_summary))


if __name__ == "__main__":
    main()
