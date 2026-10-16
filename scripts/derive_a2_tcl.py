"""Keep proven A1 PS/DDR/DMA/FIFO/GPIO/reset; replace only computation path."""
from pathlib import Path
import difflib

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = (ROOT / "vivado/scripts/build_a1_point.tcl").read_text()
    new = original.replace("a1_point", "a2_gaussian").replace("A1", "A2")
    new = new.replace("# Pointwise diagnostic RTL only; no HDMI/full vessel analysis or programming.",
                      "# Reused vendor Gaussian + frame guard; no segmentation/HDMI/programming.")
    new = new.replace("# Derived reproducibly by scripts/derive_a1_tcl.py; A0 baseline is unchanged.",
                      "# Derived by scripts/derive_a2_tcl.py; A0/A1 baselines remain unchanged.")
    new = new.replace("file copy [info script] [file join $out build_script_used.tcl]",
                      "file copy [info script] [file join $out build_script_used.tcl]\nfile copy [file join $root rtl core retina_gaussian_guard.v] [file join $out gaussian_guard_used.v]")
    new = new.replace("add_files -norecurse [list [file join $root rtl core retina_point_axis.v] [file join $root rtl core contrast_lut.vh]]",
                      "set_property ip_repo_paths [list [file join $root build a2_hls_01 solution1 impl ip]] [current_project]\nupdate_ip_catalog\nadd_files -norecurse [file join $root rtl core retina_gaussian_guard.v]")
    new = new.replace("create_bd_cell -type module -reference retina_point_axis point_stage",
                      "create_bd_cell -type module -reference retina_gaussian_guard point_stage\ncreate_bd_cell -type ip -vlnv retinafpga.local:hls:retina_gaussian_hls:1.0 gaussian_filter\nforeach {a b} {point_stage/hls_control gaussian_filter/control_V point_stage/hls_start gaussian_filter/ap_start gaussian_filter/ap_idle point_stage/hls_idle gaussian_filter/ap_done point_stage/hls_done gaussian_filter/ap_ready point_stage/hls_ready} {connect_bd_net [get_bd_pins $a] [get_bd_pins $b]}")
    new = new.replace("    point_stage/M_AXIS loopback_fifo/S_AXIS", "    point_stage/M_HLS gaussian_filter/source_V_V\n    gaussian_filter/result_V_V point_stage/S_HLS\n    point_stage/M_AXIS loopback_fifo/S_AXIS")
    new = new.replace("    point_control/s_axi_aclk point_stage/aclk", "    point_control/s_axi_aclk point_stage/aclk gaussian_filter/ap_clk")
    new = new.replace("point_stage/aresetn point_control/s_axi_aresetn}", "point_stage/aresetn point_control/s_axi_aresetn gaussian_filter/ap_rst_n}")
    new = new.replace("point_control point_stage}", "point_control point_stage gaussian_filter}")
    new = new.replace("(host only; not board point-stage PASS)", "(host only; not board Gaussian PASS)")
    for marker in ("gaussian_filter/source_V_V", "gaussian_filter/result_V_V", "gaussian_filter/ap_rst_n", "point_stage/hls_start"):
        if marker not in new:
            raise ValueError("Derivation gate missing: " + marker)
    target = ROOT / "vivado/scripts/build_a2_gaussian.tcl"
    target.write_text(new, encoding="utf-8")
    (ROOT / "results/a2_gaussian_2017_4/a1_to_a2.diff").write_text("".join(difflib.unified_diff(
        original.splitlines(True), new.splitlines(True), fromfile="build_a1_point.tcl", tofile=target.name)), encoding="utf-8")
    print("A2_DERIVED_FROM_BOARD_VERIFIED_A1")


if __name__ == "__main__":
    main()
