"""Verify reference integrity, selected board pins, BD inventory and local links."""
from __future__ import annotations
import difflib
import hashlib
import json
import pathlib
import re
from datetime import datetime, timezone
from analyze_references import verify_sources

ROOT = pathlib.Path(__file__).resolve().parents[1]

def xdc_ports(path):
    ports = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        pins = re.search(r"PACKAGE_PIN\s+(\w+).*?IOSTANDARD\s+(\w+)", line)
        port = re.search(r"\[get_ports\s+(\{[^}]+\}|\w+)\]", line)
        if pins and port:
            name = port.group(1).strip(" {}").strip()
            ports[name] = {"pin": pins.group(1), "standard": pins.group(2)}
    return ports

def main():
    verified = verify_sources()
    filter_folder = ROOT / "references/xfopencv/2017.4_release"
    filter_manifest = json.loads((filter_folder / "SOURCE_MANIFEST.json").read_text())
    for item in filter_manifest["files"]:
        data = (filter_folder / item["path"]).read_bytes()
        assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    board_folder = ROOT / "references/board"
    board_manifest = json.loads((board_folder / "download_manifest.json").read_text(encoding="utf-8"))
    for item in board_manifest:
        if item["result"] == "downloaded":
            data = (board_folder / item["file"]).read_bytes()
            assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"], item["file"]
    expected = {}
    aliases = {}
    def add(base, master, pins, standard="LVCMOS33"):
        for i, pin in enumerate(pins):
            b, m = (base.format(i=i), master.format(i=i))
            expected[b] = {"pin": pin, "standard": standard}
            aliases[b] = m
    add("btns_4bits_tri_i[{i}]", "btn[{i}]", ["D19","D20","L20","L19"])
    add("sws_2bits_tri_i[{i}]", "sw[{i}]", ["M20","M19"])
    add("leds_4bits_tri_o[{i}]", "led[{i}]", ["R14","P14","N16","M14"])
    for i, (pin, master) in enumerate(zip(["L15","G17","N15","G14","L14","M15"], ["led4_b","led4_g","led4_r","led5_b","led5_g","led5_r"])):
        base = f"rgbleds_6bits_tri_o[{i}]"
        expected[base] = {"pin": pin, "standard": "LVCMOS33"}
        aliases[base] = master
    for direction, name, pp, nn, cp, cn in (
        ("out","tx",["K17","K19","J18"],["K18","J19","H18"],"L16","L17"),
        ("in","rx",["V20","T20","N20"],["W20","U20","P20"],"N18","P19")):
        add(f"hdmi_{direction}_data_p[{{i}}]", f"hdmi_{name}_d_p[{{i}}]", pp, "TMDS_33")
        add(f"hdmi_{direction}_data_n[{{i}}]", f"hdmi_{name}_d_n[{{i}}]", nn, "TMDS_33")
        for polarity, pin in (("p",cp),("n",cn)):
            base = f"hdmi_{direction}_clk_{polarity}"
            expected[base] = {"pin": pin, "standard": "TMDS_33"}
            aliases[base] = f"hdmi_{name}_clk_{polarity}"
    for base, master, pin in (("hdmi_out_hpd[0]","hdmi_tx_hpdn","R19"), ("hdmi_in_hpd[0]","hdmi_rx_hpd","T19"),
                              ("hdmi_in_ddc_scl_io","hdmi_rx_scl","U14"), ("hdmi_in_ddc_sda_io","hdmi_rx_sda","U15")):
        expected[base] = {"pin": pin, "standard": "LVCMOS33"}
        aliases[base] = master
    master = xdc_ports(board_folder / "pynq-z2_v1.0.xdc/PYNQ-Z2 v1.0.xdc")
    pin_results = []
    for tag in ("v2.2.1", "v3.0.1", "v3.1.2"):
        name = "top.xdc" if tag == "v2.2.1" else "base.xdc"
        source = ROOT / "references/PYNQ" / tag / "boards/Pynq-Z2/base/vivado/constraints" / name
        base = xdc_ports(source)
        for port, item in expected.items():
            assert base.get(port) == item, f"{tag}: mismatch for {port}: {base.get(port)} != {item}"
            assert master.get(aliases[port]) == item, f"Master XDC mismatch: {aliases[port]}"
        pin_results.append({"tag": tag, "selected_ports_checked": len(expected), "status": "PASS_STATIC_XDC_ONLY"})
    designs = json.loads((ROOT / "results/audit/base_inventory.json").read_text(encoding="utf-8"))
    measured = ROOT / "results/audit/official_v2.2.1/ip_inventory.tsv"
    actual_names = {line.split("\t")[0].lstrip("/") for line in measured.read_text().splitlines()[1:]}
    expected_names = {cell["instance"] for cell in designs[0]["ips"]}
    # Validation expands Interconnects into couplers/xbar. Only collapse
    # internal instances of known source Interconnect containers.
    interconnects = {cell["instance"] for cell in designs[0]["ips"]
                     if cell["vlnv"].split(":")[2] == "axi_interconnect"}
    collapsed = set()
    for name in actual_names:
        if name in expected_names:
            collapsed.add(name)
        else:
            parent = next((container for container in sorted(interconnects, key=len, reverse=True)
                           if name.startswith(container + "/")), None)
            assert parent is not None, f"Unexplained generated BD instance: {name}"
            collapsed.add(parent)
    assert collapsed == expected_names, f"BD/source mismatch after Interconnect expansion: {collapsed ^ expected_names}"
    packaging = ROOT / "results/audit/official_v2.2.1"
    differences = []
    for original in sorted(packaging.glob("*_run_ippack_original.tcl")):
        changed = original.with_name(original.name.replace("_original.tcl", "_audit.tcl"))
        a, b = original.read_text(), changed.read_text()
        a_normal = re.sub(r'^set Revision\s+"\d+"', 'set Revision "1"', a, flags=re.M)
        assert a_normal == b and a != b, f"Non-metadata change: {original.name}"
        differences.extend(difflib.unified_diff(a.splitlines(True), b.splitlines(True), fromfile=original.name, tofile=changed.name))
    assert len(list(packaging.glob("*_run_ippack_original.tcl"))) == 5
    (packaging / "packaging_revision.patch").write_text("".join(differences), encoding="utf-8")
    links = 0
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
        for match in re.finditer(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = match.group(1).strip("<>").split("#",1)[0]
            if not target or "://" in target:
                continue
            assert (path.parent / target).exists(), f"Broken link: {path.name} -> {target}"
            links += 1
    demos = json.loads((ROOT / "results/audit/demo_status.json").read_text())
    assert demos["board_availability"] in (
        "not_received", "received_not_tested", "received_boot_base_gpio_hdmi_vdma_verified")
    assert len(demos["tests"]) == 6
    if demos["board_availability"] == "not_received":
        assert all(not test["executed"] and test["status"].startswith("WAITING_HARDWARE") for test in demos["tests"])
    elif demos["board_availability"] == "received_not_tested":
        expected_status = {
            "board_boot": "NOT_EXECUTED", "jupyter_base_overlay": "NOT_EXECUTED",
            "official_hdmi_output": "NOT_EXECUTED_CONNECTIONS_UNKNOWN",
            "official_gpio_led": "NOT_EXECUTED",
            "official_video_framebuffer": "NOT_EXECUTED_CONNECTIONS_UNKNOWN",
            "independent_dma_loopback": "WAITING_A0_BUILD"
        }
        assert {test["id"]: test["status"] for test in demos["tests"]} == expected_status
        assert all(not test["executed"] for test in demos["tests"]), "Board arrival is not execution evidence"
    else:
        assert demos["pynq_version"] == "3.0.1"
        assert all(test["executed"] and test["status"].startswith("PASS_") for test in demos["tests"])
        for test in demos["tests"]:
            assert (ROOT / test["evidence"]).is_file(), test["id"]
        assert demos["a0_r2"]["status"] == "PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED"
        assert (ROOT / demos["a0_r2"]["raw_archive_manifest"]).is_file()
        assert (ROOT / demos["a0_r2"]["board_verification_report"]).is_file()
        # This validates evidence availability, not another run on hardware.
        if "a1" in demos:
            a1 = demos["a1"]
            assert a1["board_status"] in ("NOT_RUN", "PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED")
            if a1["board_status"] == "PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED":
                archive_path = ROOT / a1["raw_archive_manifest"]
                archive = json.loads(archive_path.read_text(encoding="utf-8"))
                assert archive["status"] == a1["board_status"] and archive["frames_verified"] == 17
                assert (ROOT / a1["board_verification_report"]).is_file()
                release = (ROOT / a1["manifest"]).read_bytes()
                assert hashlib.sha256(release).hexdigest() == archive["release_manifest_sha256"]
                for name, info in archive["files"].items():
                    data = (archive_path.parent / name).read_bytes()
                    assert len(data) == info["bytes"] and hashlib.sha256(data).hexdigest() == info["sha256"]
    report = {"captured_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS_AUDIT_INTEGRITY_ONLY",
              "pynq_sources": verified, "xfopencv_files_verified": len(filter_manifest["files"]),
              "manufacturer_downloads_verified": sum(item["result"] == "downloaded" for item in board_manifest),
              "xdc_cross_checks": pin_results, "source_vs_executed_v2_2_1_bd_source_instances": len(collapsed),
              "executed_bd_expanded_leaf_ip_count": len(actual_names),
              "metadata_only_packaging_changes_verified": 5, "local_document_links_checked": links,
              "scope": "Does not verify physical PCB, board demos, full overlay implementation or medical algorithms"}
    (ROOT / "results/audit/verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
