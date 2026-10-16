"""Gate and archive the corrected A3 host build; board execution remains pending."""
import argparse
import copy
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from a3_background_board_test import REVISION, NOTEBOOK, FIXED, background_expected, validate_a3_package
from a1_point_board_test import notebook_code_hash

ROOT = Path(__file__).resolve().parents[1]


def info(path):
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def check_hardware(build, result):
    log = text(result / "vivado_build_01.log")
    require("\nA3_BITSTREAM_GENERATED_TIMING_CHECKED" in log and "ERROR:" not in log, "Full build missing")
    critical = [s.strip() for s in log.splitlines() if s.startswith("CRITICAL WARNING:")]
    require(critical == ["CRITICAL WARNING: [BD 41-737] Cannot set the parameter POLARITY on /reset_100m/aux_reset_in. It is read-only."], "Unreviewed critical warning")
    timing = text(build / "timing_summary.rpt")
    for marker in ("All user specified timing constraints are met.", "There are 0 register/latch pins with no clock.",
                   "There are 0 pins that are not constrained for maximum delay.", "There are 0 combinational loops in the design."):
        require(marker in timing, "Missing timing check: " + marker)
    summary = re.search(r"WNS\(ns\).*\n\s*-+.*\n\s*([^\n]+)", timing)
    require(summary is not None, "Missing timing summary values")
    values = summary.group(1).split()
    require(len(values) == 12, "Unexpected timing columns")
    require(all(float(values[i]) >= 0 for i in (0, 4, 8)) and all(int(values[i]) == 0 for i in (2, 6, 10)), "Timing violations")
    drc = text(build / "drc.rpt")
    require(not re.search(r"\|\s*(?:Error|Critical Warning)\s*\|", drc, re.I), "DRC failure")
    warnings = re.findall(r"\|\s*([\w-]+)\s*\|\s*Warning\s*\|", drc)
    require(warnings == ["DPIP-1", "DPOP-1", "DPOP-2", "RTSTAT-10"], "New DRC warning needs review")
    for rule in ("DPIP-1", "DPOP-1", "DPOP-2"):
        require(drc.count(rule + "#1 Warning") == 1 and rule + "#2" not in drc, "Changed DSP warning scope")
    require(drc.count("DSP a3_background_i/background_filter/inst/join_words_U0/") == 3, "DSP advisories affect an unreviewed cell")
    for snapshot, source in (("build_script_used.tcl", "vivado/scripts/build_a3_background.tcl"),
                              ("gaussian_guard_used.v", "rtl/core/retina_gaussian_guard.v")):
        require(info(build / snapshot) == info(ROOT / source), "Changed hardware source: " + source)
    hwh = build / "deploy/a3_background.hwh"
    meta = json.loads(text(result / "hwh_host_check.json"))
    require(meta["hwh_sha256"] == info(hwh)["sha256"] and meta["auxiliary_reset_active_low_tied_high"], "Wrong reset metadata")
    tree = ET.parse(hwh)
    def module(name):
        value = tree.find(f".//MODULE[@INSTANCE='{name}']")
        require(value is not None, "Missing module: " + name)
        return value
    def connection(owner, name, instance, port):
        value = module(owner).find(f"./PORTS/PORT[@NAME='{name}']/CONNECTIONS/CONNECTION[@INSTANCE='{instance}'][@PORT='{port}']")
        require(value is not None, f"Wrong connection: {owner}/{name}")
    gpio = module("point_control")
    parameters = {p.get("NAME"): p.get("VALUE") for p in gpio.findall("./PARAMETERS/PARAMETER")}
    for key, value in {"C_IS_DUAL": 1, "C_GPIO_WIDTH": 32, "C_GPIO2_WIDTH": 32, "C_ALL_OUTPUTS": 1,
                       "C_ALL_INPUTS_2": 1, "C_INTERRUPT_PRESENT": 0}.items():
        require(int(parameters[key]) == value, "Wrong GPIO: " + key)
    require(meta["ip_dict"]["point_control"]["phys_addr"] == 0x41200000, "Wrong GPIO address")
    require(module("background_filter").get("VLNV") == "retinafpga.local:hls:retina_background_hls:1.0", "Wrong HLS IP")
    for owner, clock, reset in (("point_stage", "aclk", "aresetn"), ("background_filter", "ap_clk", "ap_rst_n")):
        connection(owner, clock, "ps7_0", "FCLK_CLK0")
        connection(owner, reset, "reset_100m", "peripheral_aresetn")
    connection("point_stage", "cfg_control", "point_control", "gpio_io_o")
    connection("point_stage", "status_word", "point_control", "gpio2_io_i")
    for signal in ("tdata", "tkeep", "tlast", "tvalid", "tready"):
        connection("point_stage", "s_axis_" + signal, "axi_dma_0", "m_axis_mm2s_" + signal)
        connection("point_stage", "m_axis_" + signal, "loopback_fifo", "s_axis_" + signal)
    for signal in ("tdata", "tvalid", "tready"):
        connection("point_stage", "m_hls_" + signal, "background_filter", "source_V_V_" + signal.upper())
        connection("point_stage", "s_hls_" + signal, "background_filter", "result_V_V_" + signal.upper())
    for a, b in (("hls_control", "control_V"), ("hls_start", "ap_start"), ("hls_idle", "ap_idle"),
                 ("hls_done", "ap_done"), ("hls_ready", "ap_ready")):
        connection("point_stage", a, "background_filter", b)
    for name in ("S_AXIS", "M_AXIS", "M_HLS", "S_HLS"):
        interface = module("point_stage").find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='{name}']")
        require(interface is not None, "Missing AXIS: " + name)
        p = {p.get("NAME"): p.get("VALUE") for p in interface.findall("PARAMETER")}
        for key, value in {"TDATA_NUM_BYTES": 4, "FREQ_HZ": 100000000,
                           "HAS_TLAST": int(name in ("S_AXIS", "M_AXIS")),
                           "HAS_TKEEP": int(name in ("S_AXIS", "M_AXIS"))}.items():
            require(int(p[key]) == value, "Wrong AXIS parameter: " + name + "/" + key)
    utilization = text(build / "utilization.rpt")
    counts = {}
    for name in ("Slice LUTs", "Slice Registers", "Block RAM Tile", "DSPs"):
        match = re.search(r"\|\s*" + name + r"\s*\|\s*(\d+(?:\.\d+)?)\s*\|", utilization)
        require(match is not None, "Missing utilization: " + name)
        value = float(match.group(1))
        counts[name] = int(value) if value.is_integer() else value
    return {"wns_ns": float(values[0]), "whs_ns": float(values[4]), "wpws_ns": float(values[8]),
            "clock_mhz": 100, "resources": counts, "reviewed_drc_warning": warnings,
            "scope": "Complete routed A3 host build, not board PASS or FPS"}


def check_hls(hls, result):
    csim = text(result / "hls_attempt_01.log")
    require("VENDOR_BACKGROUND_CSIM_PASS: 12 full frames, 1376256 exact words" in csim, "C simulation missing")
    require((hls / "solution1/syn/report/retina_background_hls_csynth.rpt").is_file(), "HLS synthesis report missing")
    packing = text(result / "ip_packaging_fixed_02.log")
    require("ERROR:" not in packing and "save_core" in packing, "Corrected IP export failed")
    before = text(result / "run_ippack.tcl")
    after = text(result / "run_ippack_a3meta.tcl")
    expected, count = re.subn(r'^set Revision\s+"\d+"', 'set Revision "1"', before, flags=re.M)
    require(count == 1 and expected == after, "IP patch changed more than date metadata")
    component = hls / "solution1/impl/ip/component.xml"
    tree = ET.parse(component)
    ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
    require([tree.findtext("s:" + k, namespaces=ns) for k in ("vendor", "library", "name", "version")] ==
            ["retinafpga.local", "hls", "retina_background_hls", "1.0"], "Unexpected packaged VLNV")
    syn = hls / "solution1/syn/verilog"
    sources = [p for p in sorted(syn.iterdir()) if p.suffix in (".v", ".dat")]
    require(len(sources) > 5 and any(p.suffix == ".dat" for p in sources), "Generated RTL/ROM missing")
    generated = {}
    for source in sources:
        packaged = hls / "solution1/impl/ip/hdl/verilog" / source.name
        require(packaged.is_file() and info(source) == info(packaged), "Simulation/IP source mismatch: " + source.name)
        generated[source.name] = info(source)
    # Check the actual preprocessor output against current project logic,
    # with only known HLS pixel-type macro expansion and whitespace removed.
    pp = hls / "solution1/.autopilot/db/retina_background_hls.pp.0.cpp"
    compiled = text(pp)
    current = text(ROOT / "hls/retina_background_hls.cpp")
    current = current[current.index("typedef hls::Mat"):]
    current = current.replace('#include "contrast_lut_values.h"', text(ROOT / "hls/contrast_lut_values.h"))
    current = current.replace("HLS_8UC1", "(((0) & ((1 << 11) - 1)) + (((1)-1) << 11))")
    current = current.replace("HLS_16UC1", "(((2) & ((1 << 11) - 1)) + (((1)-1) << 11))")
    def canonical(value):
        value = re.sub(r"/\*.*?\*/|//[^\n]*", "", value, flags=re.S)
        value = re.sub(r'^\s*#\s*\d+[^\n]*', "", value, flags=re.M)
        return re.sub(r"\s+", "", value)
    # Select the project GreenImage typedef after all vendor declarations.
    compiled_tail = compiled[compiled.rindex("typedef hls::Mat<512,512,(((0)"):]
    require(canonical(current) == canonical(compiled_tail), "HLS project logic differs from synthesized source")
    evidence = json.loads(text(result / "reuse_evidence.json"))
    for header in evidence["headers"]:
        require(info(Path(header["path"])) == {k: header[k] for k in ("bytes", "sha256")}, "Vendor library changed after audit")
    actual_headers = []
    for name in ("hls_video.h", "hls/hls_video_imgproc.h", "hls/hls_video_types.h", "hls/hls_video_mem.h"):
        header = Path("E:/vivado/Vivado/2017.4/common/technology/autopilot") / name
        require(header.name in compiled, "Header not found in actual preprocessor trace: " + name)
        actual_headers.append({"path": str(header), **info(header)})
    return {"component": info(component), "generated_verilog_and_rom": generated,
            "preprocessed_source": info(pp), "project_logic_matches_preprocessed_source": True,
            "compiled_vendor_headers": actual_headers, "reviewed_include_headers": evidence["headers"],
            "library_modified": False, "export_patch": "Revision metadata only; original and patch retained"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("hls", type=Path)
    parser.add_argument("axis_sim", type=Path)
    parser.add_argument("reset_sim", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--derivation", type=Path, required=True)
    args = parser.parse_args()
    require(not args.destination.exists(), "Refusing to overwrite an A3 release")
    require(not (args.results / "release_manifest.json").exists(), "Release already archived")
    derivation = json.loads(text(args.derivation))
    require(derivation["status"] == "PASS_A3_DERIVATION_REPRODUCTION", "Derivations not verified")
    for entry in derivation["checks"]:
        require(info(ROOT / entry["file"])["sha256"] == entry["sha256"], "Derived source changed after verification")
    hardware = check_hardware(args.build, args.results)
    hls_provenance = check_hls(args.hls, args.results)
    axis_log = args.axis_sim / "xsim.log"
    axis = text(axis_log)
    require("BACKGROUND_AXIS_SIM_PASS: cases=13 checked=1441792" in axis and "BACKGROUND_VALID_PASS: 11 frames" in axis
            and "BACKGROUND_BAD_INPUT_PASS:" in axis and "Fatal:" not in axis and "ERROR:" not in axis, "RTL tests failed")
    for dat in (args.hls / "solution1/syn/verilog").glob("*.dat"):
        require(info(dat) == info(args.axis_sim / dat.name), "Wrong simulation ROM initialization")
    reset_log = args.reset_sim / "reset_sim.sim/sim_1/behav/xsim/simulate.log"
    reset = text(reset_log)
    require("RESET_SIM_PASS: real vendor IP" in reset and "Fatal:" not in reset and "ERROR:" not in reset, "Reset test failed")
    regression = text(args.results / "host_runner_tests_release.log")
    test_count = re.search(r"Ran (\d+) tests", regression)
    require(test_count is not None and int(test_count.group(1)) >= 58 and "\nOK" in regression
            and "test_faults_retain_buffers_and_block_full_suite" in regression, "Runner fault tests missing")
    notebook = ROOT / "notebooks" / NOTEBOOK
    nb = json.loads(text(notebook))
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    require(len(code) == 6 and all(c["execution_count"] is None and not c["outputs"] for c in code), "Notebook is not a clean six-stage test")
    vectors = json.loads(text(args.axis_sim / "vector_manifest.json"))
    require(len(vectors) == 14, "Incomplete independent vectors")
    from prepare_a3_vectors import expected_words
    for record in vectors:
        side, number = record["side"], record["case"]
        words = np.loadtxt(args.axis_sim / f"case_{number:02d}_input.hex", dtype=np.uint32,
                           converters=lambda value: int(value, 16)).reshape(side, side)
        golden_hex = np.loadtxt(args.axis_sim / f"case_{number:02d}_expected.hex", dtype=np.uint32,
                                converters=lambda value: int(value, 16)).reshape(side, side)
        require(not record["labels_used"], "GT entered a test vector")
        require(hashlib.sha256(words.astype("<u4").tobytes()).hexdigest() == record["input_sha256"], "Changed simulation input")
        golden = expected_words(words, record["mode"])
        require(np.array_equal(golden, golden_hex), "Golden hex differs from independent M0 reference")
        require(np.array_equal(golden, background_expected(words, record["mode"])), "Board/M0 reference disagree")
        require(hashlib.sha256(golden.astype("<u4").tobytes()).hexdigest() == record["expected_sha256"], "Changed simulation golden")
        if record["pattern"] == "stare":
            image = np.load(args.axis_sim / f"stare_im0001_{side}.npy", allow_pickle=False)
            require(image.dtype == np.uint32 and np.array_equal(image, words), "Wrong RGB-only release input")
    a2 = json.loads(text(ROOT / "results/a2_gaussian_2017_4/release_manifest.json"))
    require(info(ROOT / "rtl/core/retina_gaussian_guard.v") == a2["source_files"]["rtl/core/retina_gaussian_guard.v"], "A2 frame guard changed")
    for name in ("a2_gaussian_board_test.py", "a1_point_board_test.py", "a0_dma_board_test.py"):
        require(info(ROOT / "scripts" / name) == a2["artifacts"][name], "Verified A2 helper changed: " + name)
    source_paths = ["hls/retina_background_hls.cpp", "hls/retina_background_hls.hpp", "hls/contrast_lut_values.h",
        "rtl/core/retina_gaussian_guard.v", "tests/retina_background_hls_tb.cpp", "tests/retina_background_axis_tb.sv",
        "vivado/scripts/build_a3_hls.tcl", "vivado/scripts/build_a3_background.tcl", "vivado/scripts/simulate_a3_reset.tcl",
        "scripts/derive_a3_tcl.py", "scripts/derive_a3_runner.py", "scripts/derive_a3_package.py",
        "scripts/run_background_simulation.ps1", "scripts/prepare_a3_vectors.py", "scripts/repack_a3_ip.py",
        "scripts/package_a3.py", "scripts/build_a3_notebook.py", "scripts/verify_a3_release.py", "scripts/verify_a3_derivations.py", "tests/test_a3_board_runner.py",
        "scripts/check_a0_hwh.py", "scripts/a0_reset_tb.sv"]
    sources = {"a3_background.bit": args.build / "deploy/a3_background.bit", "a3_background.hwh": args.build / "deploy/a3_background.hwh",
        NOTEBOOK: notebook, "a3_background_board_test.py": ROOT / "scripts/a3_background_board_test.py",
        "a2_gaussian_board_test.py": ROOT / "scripts/a2_gaussian_board_test.py",
        "a1_point_board_test.py": ROOT / "scripts/a1_point_board_test.py", "a0_dma_board_test.py": ROOT / "scripts/a0_dma_board_test.py",
        "使用说明.txt": ROOT / "docs/a3_background_validation_steps.md",
        **{f"stare_im0001_{s}.npy": args.axis_sim / f"stare_im0001_{s}.npy" for s in (256, 512)}}
    require(set(sources) == FIXED | {NOTEBOOK}, "Incomplete package definition")
    manifest = {"revision": REVISION, "host_status": "PASS_ROUTED_BUILD_CSIM_GENERATED_RTL_RESET_METADATA_AND_HOST_FAULT_TESTS",
        "board_status": "NOT_RUN", "vivado": "2017.4", "pynq_target": "3.0.1",
        "scope": "Raw G, exact Gaussian/LUT, 15x15 background and saturated response; no full segmentation, final HDMI or FPS PASS",
        "host_checks": hardware, "hls_provenance": hls_provenance, "rgb_only_test_vectors": vectors,
        "build_directory": str(args.build.resolve()), "rtl_simulation": {"cases": 13, "exact_outputs": 1441792},
        "hls_csim": {"frames": 12, "exact_outputs": 1376256}, "host_test_count": int(test_count.group(1)),
        "source_files": {p: info(ROOT / p) for p in source_paths},
        "derivation_verification": {"report": args.derivation.name, **info(args.derivation)},
        "artifacts": {name: info(source) for name, source in sources.items()},
        "notebook_validation": {"algorithm": "sha256-code-cells-v1", "sha256": notebook_code_hash(nb)},
        "dma_address": "0x40400000", "gpio_address": "0x41200000", "board_suite_frames": 45, "board_suite_words": 7274496,
        "base_a2_release_manifest_sha256": info(ROOT / "results/a2_gaussian_2017_4/release_manifest.json")["sha256"],
        "shared_frame_guard_and_helpers_unchanged_from_a2": True,
        "failed_attempts": "See failure_record.json: date metadata overflow, export working directory, simulator filename and host display stub; failed results not counted",
        "license_notice": "Official PYNQ APIs/drivers BSD-3-Clause; project wrapper scripts are project additions; AMD/Xilinx tool/IP terms and embedded OpenCV notice apply; installed proprietary headers not redistributed"}
    # Build and verify in a temporary directory before making the release visible.
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.destination.parent, prefix="a3_pack_") as temporary:
        staged = Path(temporary)
        for name, source in sources.items():
            shutil.copyfile(source, staged / name)
        payload = json.dumps(manifest, indent=2) + "\n"
        (staged / "a3_manifest.json").write_text(payload, encoding="utf-8")
        validate_a3_package(staged, manifest)
        saved = copy.deepcopy(nb)
        for cell in saved["cells"]:
            if cell["cell_type"] == "code":
                cell["execution_count"] = 1
                cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": "simulated save metadata, not board result\n"}]
        saved["metadata"]["save_probe"] = True
        (staged / NOTEBOOK).write_text(json.dumps(saved), encoding="utf-8")
        validate_a3_package(staged, manifest)
        shutil.copyfile(notebook, staged / NOTEBOOK)
        validate_a3_package(staged, manifest)
        args.destination.mkdir()
        for file in staged.iterdir():
            shutil.copyfile(file, args.destination / file.name)
    for name in ("timing_summary.rpt", "utilization.rpt", "drc.rpt", "clocks.rpt", "configuration.txt", "reconstructed_bd.tcl", "build_script_used.tcl", "gaussian_guard_used.v"):
        shutil.copyfile(args.build / name, args.results / name)
    for source, name in ((axis_log, "background_xsim.log"), (args.axis_sim / "vector_manifest.json", "vector_manifest.json"),
        (reset_log, "vendor_reset_simulate.log"), (args.reset_sim / "reset_tb.sv", "reset_tb_used.sv"),
        (args.hls / "solution1/syn/report/retina_background_hls_csynth.rpt", "hls_csynth.rpt"),
        (args.hls / "solution1/impl/ip/component.xml", "hls_component.xml")):
        shutil.copyfile(source, args.results / name)
    (args.results / "release_manifest.json").write_text(payload, encoding="utf-8")
    (args.results / "release_integrity.json").write_text(json.dumps({"status": "PASS_HOST_PACKAGE_AND_SAVED_NOTEBOOK_VALIDATION",
        "board_status": "NOT_RUN", "package_files": {p.name: info(p) for p in sorted(args.destination.iterdir())}}, indent=2) + "\n", encoding="utf-8")
    print("A3_RELEASE_READY_HOST_ONLY_BOARD_PENDING", args.destination)


if __name__ == "__main__":
    main()
