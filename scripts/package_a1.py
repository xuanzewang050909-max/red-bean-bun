"""Release only after host gates; never promote a host build to board PASS."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
from a1_point_board_test import REVISION, notebook_code_hash, validate_package

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results/a1_point_2017_4"


def info(path):
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("build_log", type=Path)
    parser.add_argument("reset_simulation", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--results", type=Path, required=True,
                        help="New result directory; original hardware evidence is read from r1")
    parser.add_argument("--regression-log", type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists() or args.results.exists():
        raise ValueError("Refusing to overwrite release")
    log = args.build_log.read_text(errors="replace")
    if "\nA1_BITSTREAM_GENERATED_TIMING_CHECKED" not in log or "ERROR:" in log:
        raise ValueError("Incomplete or failed build")
    expected_critical = "CRITICAL WARNING: [BD 41-737] Cannot set the parameter POLARITY on /reset_100m/aux_reset_in. It is read-only."
    critical = [line.strip() for line in log.splitlines() if line.startswith("CRITICAL WARNING:")]
    if critical != [expected_critical]:
        raise ValueError("Unreviewed critical warning: " + repr(critical))
    timing = (args.build / "timing_summary.rpt").read_text()
    for marker in ("All user specified timing constraints are met.",
                   "There are 0 register/latch pins with no clock.",
                   "There are 0 pins that are not constrained for maximum delay."):
        if marker not in timing:
            raise ValueError("Timing gate missing: " + marker)
    drc = (args.build / "drc.rpt").read_text()
    if re.search(r"\|\s*(?:Error|Critical Warning)\s*\|", drc, re.I):
        raise ValueError("DRC gate failed")
    if info(args.build / "build_script_used.tcl") != info(ROOT / "vivado/scripts/build_a1_point.tcl"):
        raise ValueError("Build source changed")
    hwh = args.build / "deploy/a1_point.hwh"
    metadata = json.loads((RESULT / "hwh_host_check.json").read_text())
    if metadata["hwh_sha256"] != info(hwh)["sha256"] or not metadata["auxiliary_reset_active_low_tied_high"]:
        raise ValueError("Wrong or unverified reset metadata")
    tree = ET.parse(hwh)
    def module(name):
        value = tree.find(f".//MODULE[@INSTANCE='{name}']")
        if value is None: raise ValueError("Missing module: " + name)
        return value
    gpio = module("point_control")
    parameters = {p.get("NAME"): p.get("VALUE") for p in gpio.findall("./PARAMETERS/PARAMETER")}
    expected = {"C_IS_DUAL": 1, "C_GPIO_WIDTH": 32, "C_GPIO2_WIDTH": 32,
                "C_ALL_OUTPUTS": 1, "C_ALL_INPUTS_2": 1, "C_INTERRUPT_PRESENT": 0}
    for key, value in expected.items():
        assert int(parameters[key]) == value
    gpio_desc = metadata["ip_dict"]["point_control"]
    assert gpio_desc["phys_addr"] == 0x41200000 and gpio_desc["addr_range"] == 0x10000
    point = module("point_stage")
    def connection(name, instance, port):
        node = point.find(f"./PORTS/PORT[@NAME='{name}']/CONNECTIONS/CONNECTION[@INSTANCE='{instance}'][@PORT='{port}']")
        if node is None: raise ValueError("Wrong point-stage connection: " + name)
    connection("aclk", "ps7_0", "FCLK_CLK0")
    connection("aresetn", "reset_100m", "peripheral_aresetn")
    connection("cfg_control", "point_control", "gpio_io_o")
    connection("status_word", "point_control", "gpio2_io_i")
    for signal in ("tdata", "tkeep", "tlast", "tvalid", "tready"):
        connection("s_axis_" + signal, "axi_dma_0", "m_axis_mm2s_" + signal)
        connection("m_axis_" + signal, "loopback_fifo", "s_axis_" + signal)
    for name in ("S_AXIS", "M_AXIS"):
        interface = point.find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='{name}']")
        parameters = {p.get("NAME"): p.get("VALUE") for p in interface.findall("PARAMETER")}
        for key, value in {"TDATA_NUM_BYTES": 4, "HAS_TLAST": 1, "HAS_TKEEP": 1, "FREQ_HZ": 100000000}.items():
            assert int(parameters[key]) == value
    reset_log = args.reset_simulation / "reset_sim.sim/sim_1/behav/xsim/simulate.log"
    reset_text = reset_log.read_text(errors="replace")
    if "RESET_SIM_PASS:" not in reset_text or "Fatal:" in reset_text:
        raise ValueError("Vendor reset simulation did not pass")
    xsim_log = (RESULT / "point_xsim.log").read_text(errors="replace")
    if "POINT_AXIS_SIM_PASS: checked=655365 accepted=655366" not in xsim_log or "Fatal:" in xsim_log:
        raise ValueError("Final point-stage simulation missing")
    tests = args.regression_log.read_text(encoding="utf-8-sig", errors="replace")
    count = re.search(r"Ran (\d+) tests", tests)
    if not count or int(count.group(1)) < 25 or "\nOK" not in tests or "test_saved_execution_metadata_and_output_pass_but_raw_hash_changes" not in tests:
        raise ValueError("Host fault tests missing")
    notebook = ROOT / "notebooks/a1_point_check.ipynb"
    nb = json.loads(notebook.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None and not cell["outputs"]
    args.destination.mkdir(parents=True)
    args.results.mkdir(parents=True)
    sources = {"a1_point.bit": args.build / "deploy/a1_point.bit", "a1_point.hwh": hwh,
               "a1_point_check.ipynb": notebook,
               "a1_point_board_test.py": ROOT / "scripts/a1_point_board_test.py",
               "a0_dma_board_test.py": ROOT / "scripts/a0_dma_board_test.py",
               "使用说明.txt": ROOT / "docs/a1_point_validation_steps.md"}
    for name, source in sources.items(): shutil.copyfile(source, args.destination / name)
    for name in ("timing_summary.rpt", "utilization.rpt", "drc.rpt", "clocks.rpt", "configuration.txt", "reconstructed_bd.tcl", "build_script_used.tcl"):
        shutil.copyfile(args.build / name, args.results / name)
    shutil.copyfile(args.build_log, args.results / "vivado_build.log")
    shutil.copyfile(reset_log, args.results / "reset_simulate.log")
    shutil.copyfile(args.reset_simulation / "reset_tb.sv", args.results / "reset_tb_used.sv")
    shutil.copyfile(args.regression_log, args.results / "host_regression_tests.log")
    manifest = {"revision": REVISION, "host_status": "PASS_HOST_BUILD_METADATA_RTL_AND_VENDOR_RESET_SIMULATION",
        "board_status": "NOT_RUN", "vivado": "2017.4", "pynq_target": "3.0.1",
        "scope": "Diagnostic point-stage only; no Gaussian, segmentation or HDMI",
        "build_directory": str(args.build.resolve()),
        "source_files": {str(path.relative_to(ROOT)): info(path) for path in [
            ROOT / "rtl/core/retina_point_axis.v", ROOT / "rtl/core/contrast_lut.vh",
            ROOT / "tests/retina_point_axis_tb.sv", ROOT / "vivado/scripts/build_a1_point.tcl",
            ROOT / "scripts/derive_a1_tcl.py", ROOT / "scripts/run_point_simulation.ps1",
            ROOT / "vivado/scripts/simulate_a1_reset.tcl", ROOT / "scripts/a0_reset_tb.sv",
            ROOT / "scripts/package_a1.py"]},
        "artifacts": {name: info(args.destination / name) for name in sources},
        "notebook_validation": {"algorithm": "sha256-code-cells-v1", "sha256": notebook_code_hash(nb)},
        "reviewed_warning": "Inherited read-only aux polarity setter warning; propagated C_AUX_RESET_HIGH=0, constant-one wiring and actual vendor reset simulation independently checked",
        "gpio_parameters": expected, "gpio_address": "0x41200000", "dma_address": "0x40400000"}
    payload = json.dumps(manifest, indent=2) + "\n"
    (args.destination / "a1_manifest.json").write_text(payload, encoding="utf-8")
    validate_package(args.destination, manifest)
    (args.results / "release_manifest.json").write_text(payload, encoding="utf-8")
    print("A1_RELEASE_PACKAGED_HOST_ONLY_BOARD_PENDING", args.destination)


if __name__ == "__main__":
    main()
