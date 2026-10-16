"""Derive A3 release gates from the archived A2 gate, recording the exact diff."""
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = (ROOT / "scripts/package_a2.py").read_text(encoding="utf-8")
    new = original.replace("A2", "A3").replace("a2_gaussian", "a3_background").replace("_a2", "_a3")
    new = new.replace("a2_manifest.json", "a3_manifest.json").replace("a2_pack_", "a3_pack_")
    new = new.replace("gaussian_filter", "background_filter").replace("retina_gaussian_hls", "retina_background_hls")
    new = new.replace("retina_gaussian_axis_tb", "retina_background_axis_tb").replace("run_gaussian_simulation", "run_background_simulation")
    new = new.replace("gaussian_expected", "background_expected").replace("vivado_build_02.log", "vivado_build_01.log")
    new = new.replace("hls_attempt_03.log", "hls_attempt_01.log").replace("ip_packaging_fixed_03.log", "ip_packaging_fixed_02.log")
    new = new.replace("host_runner_tests_final.log", "host_runner_tests_release.log")
    new = new.replace("run_ippack_original.tcl", "run_ippack.tcl").replace("run_ippack_r2meta.tcl", "run_ippack_a3meta.tcl")
    new = new.replace("VENDOR_GAUSSIAN_CSIM_PASS: 8 full frames, 917504 exact words", "VENDOR_BACKGROUND_CSIM_PASS: 12 full frames, 1376256 exact words")
    new = new.replace("GAUSSIAN_AXIS_SIM_PASS: cases=11 checked=1114112", "BACKGROUND_AXIS_SIM_PASS: cases=13 checked=1441792")
    new = new.replace("GAUSSIAN_VALID_PASS: 9 frames", "BACKGROUND_VALID_PASS: 11 frames").replace("GAUSSIAN_BAD_INPUT_PASS:", "BACKGROUND_BAD_INPUT_PASS:")
    new = new.replace('>= 32', '>= 58').replace('"cases": 11, "exact_outputs": 1114112', '"cases": 13, "exact_outputs": 1441792')
    new = new.replace('"frames": 8, "exact_outputs": 917504', '"frames": 12, "exact_outputs": 1376256').replace('"board_suite_frames": 37', '"board_suite_frames": 45, "board_suite_words": 7274496')
    new = new.replace('"gaussian_xsim.log"', '"background_xsim.log"')
    new = new.replace('Diagnostic raw G/FOV, exact 3x3 Gaussian and LUT; no vessel segmentation, final HDMI or FPS PASS',
                      'Raw G, exact Gaussian/LUT, 15x15 background and saturated response; no full segmentation, final HDMI or FPS PASS')
    start = new.index('    vectors = json.loads(')
    end = new.index('    sources = {', start)
    new = new[:start] + '''    vectors = json.loads(text(args.axis_sim / "vector_manifest.json"))
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
''' + new[end:]
    new = new.replace('NOTEBOOK: notebook, "a3_background_board_test.py": ROOT / "scripts/a3_background_board_test.py",',
                      'NOTEBOOK: notebook, "a3_background_board_test.py": ROOT / "scripts/a3_background_board_test.py",\n        "a2_gaussian_board_test.py": ROOT / "scripts/a2_gaussian_board_test.py",')
    start = new.index('        "withdrawn_build":')
    end = new.index('        "license_notice":', start)
    new = new[:start] + '''        "base_a2_release_manifest_sha256": info(ROOT / "results/a2_gaussian_2017_4/release_manifest.json")["sha256"],
        "shared_frame_guard_and_helpers_unchanged_from_a2": True,
        "failed_attempts": "See failure_record.json: date metadata overflow, export working directory, simulator filename and host display stub; failed results not counted",
''' + new[end:]
    new = new.replace('    evidence = json.loads(text(result / "reuse_evidence.json"))\n',
        '    evidence = json.loads(text(result / "reuse_evidence.json"))\n'
        '    for header in evidence["headers"]:\n'
        '        require(info(Path(header["path"])) == {k: header[k] for k in ("bytes", "sha256")}, "Vendor library changed after audit")\n')
    new = new.replace(r'(\d+)\s*\|", utilization)', r'(\d+(?:\.\d+)?)\s*\|", utilization)')
    new = new.replace('        counts[name] = int(match.group(1))',
                      '        value = float(match.group(1))\n        counts[name] = int(value) if value.is_integer() else value')
    new = new.replace('    require(warnings == ["RTSTAT-10"], "New DRC warning needs review")',
        '    require(warnings == ["DPIP-1", "DPOP-1", "DPOP-2", "RTSTAT-10"], "New DRC warning needs review")\n'
        '    for rule in ("DPIP-1", "DPOP-1", "DPOP-2"):\n'
        '        require(drc.count(rule + "#1 Warning") == 1 and rule + "#2" not in drc, "Changed DSP warning scope")\n'
        '    require(drc.count("DSP a3_background_i/background_filter/inst/join_words_U0/") == 3, "DSP advisories affect an unreviewed cell")')
    new = new.replace('    parser.add_argument("--results", type=Path, required=True)',
                      '    parser.add_argument("--results", type=Path, required=True)\n    parser.add_argument("--derivation", type=Path, required=True)')
    new = new.replace('        "source_files": {p: info(ROOT / p) for p in source_paths},',
                      '        "source_files": {p: info(ROOT / p) for p in source_paths},\n        "derivation_verification": {"report": args.derivation.name, **info(args.derivation)},')
    new = new.replace('    hardware = check_hardware(args.build, args.results)',
        '    derivation = json.loads(text(args.derivation))\n'
        '    require(derivation["status"] == "PASS_A3_DERIVATION_REPRODUCTION", "Derivations not verified")\n'
        '    for entry in derivation["checks"]:\n'
        '        require(info(ROOT / entry["file"])["sha256"] == entry["sha256"], "Derived source changed after verification")\n'
        '    hardware = check_hardware(args.build, args.results)')
    target = ROOT / "scripts/package_a3.py"
    if target.exists():
        raise ValueError("Preserve earlier generated gate")
    target.write_text(new, encoding="utf-8", newline="\n")
    (ROOT / "results/a3_background_2017_4/a2_to_a3_package.diff").write_text("".join(difflib.unified_diff(
        original.splitlines(True), new.splitlines(True), fromfile="package_a2.py", tofile=target.name)),
        encoding="utf-8", newline="\n")
    print("A3_PACKAGE_GATE_DERIVED: A2 standard clock/reset/interface/source checks retained")


if __name__ == "__main__":
    main()
