"""Derive A1 from the proven A0 script; preserve A0 and record a reviewable diff."""
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = (ROOT / "vivado/scripts/build_minimal_dma.tcl").read_text()
    text = original.replace("a0_dma", "a1_point").replace("A0", "A1")
    def replace_once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError("Baseline changed; review before derivation: " + old)
        text = text.replace(old, new)
    replace_once("# No HDMI/algorithm RTL; no hardware programming. Output goes to a new build dir.",
                 "# Pointwise diagnostic RTL only; no HDMI/full vessel analysis or programming.\n# Derived reproducibly by scripts/derive_a1_tcl.py; A0 baseline is unchanged.")
    replace_once("create_bd_design a1_point", """add_files -norecurse [list [file join $root rtl core retina_point_axis.v] [file join $root rtl core contrast_lut.vh]]
set_property include_dirs [list [file join $root rtl core]] [current_fileset]
update_compile_order -fileset sources_1
create_bd_design a1_point
create_bd_cell -type module -reference retina_point_axis point_stage
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 point_control
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_DOUT_DEFAULT {0x00000000} \\
    CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells point_control]
connect_bd_net [get_bd_pins point_control/gpio_io_o] [get_bd_pins point_stage/cfg_control]
connect_bd_net [get_bd_pins point_stage/status_word] [get_bd_pins point_control/gpio2_io_i]""")
    replace_once("CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}", "CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}")
    replace_once("control_axi/M00_AXI axi_dma_0/S_AXI_LITE", "control_axi/M00_AXI axi_dma_0/S_AXI_LITE\n    control_axi/M01_AXI point_control/S_AXI")
    replace_once("axi_dma_0/M_AXIS_MM2S loopback_fifo/S_AXIS", "axi_dma_0/M_AXIS_MM2S point_stage/S_AXIS\n    point_stage/M_AXIS loopback_fifo/S_AXIS")
    replace_once("control_axi/ACLK control_axi/S00_ACLK control_axi/M00_ACLK", "control_axi/ACLK control_axi/S00_ACLK control_axi/M00_ACLK control_axi/M01_ACLK\n    point_control/s_axi_aclk point_stage/aclk")
    replace_once("control_axi/ARESETN control_axi/S00_ARESETN control_axi/M00_ARESETN", "control_axi/ARESETN control_axi/S00_ARESETN control_axi/M00_ARESETN control_axi/M01_ARESETN")
    replace_once("foreach pin {axi_dma_0/axi_resetn loopback_fifo/s_axis_aresetn}", "foreach pin {axi_dma_0/axi_resetn loopback_fifo/s_axis_aresetn point_stage/aresetn point_control/s_axi_aresetn}")
    replace_once("set_property range 64K $dma_seg", """set_property range 64K $dma_seg
set gpio_seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data] -filter {NAME =~ *point_control*}]
if {[llength $gpio_seg] != 1} {error "Expected one GPIO control segment"}
set_property offset 0x41200000 $gpio_seg
set_property range 64K $gpio_seg""")
    replace_once("foreach cell {ps7_0 axi_dma_0 loopback_fifo reset_100m}", "foreach cell {ps7_0 axi_dma_0 loopback_fifo reset_100m point_control point_stage}")
    text = text.replace("not board DMA PASS", "not board point-stage PASS")
    destination = ROOT / "vivado/scripts/build_a1_point.tcl"
    destination.write_text(text, encoding="utf-8")
    diff = "".join(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                    fromfile="proven_A0_r2/build_minimal_dma.tcl", tofile="A1/build_a1_point.tcl"))
    evidence = ROOT / "results/a1_point_2017_4"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "a0_to_a1.diff").write_text(diff, encoding="utf-8")
    print("A1_DERIVED_WITH_REVIEW_DIFF")


if __name__ == "__main__":
    main()
