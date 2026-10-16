# A4 standard-IP DMA loopback for PYNQ-Z2, Vivado 2017.4.
# Board preset: immutable TUL board files in references/board.
# Reused Gaussian/BoxFilter and unchanged A2 guard; threshold/closing/cleanup/FOV complete algorithm A.
# Derived by scripts/derive_a4_sources.py; A0/A1/A2 baselines remain unchanged.
# Usage: vivado -mode batch -source this.tcl -tclargs <new-output-dir> bd|full
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2017.4"} {error "This baseline is verified only with Vivado 2017.4"}
if {[llength $argv] != 2} {error "Expected new output directory and bd|full"}
set out [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
if {$stage ni {bd full}} {error "Invalid stage"}
if {[file exists $out]} {error "Refusing to overwrite existing build directory: $out"}
file mkdir $out
file copy [info script] [file join $out build_script_used.tcl]
file copy [file join $root rtl core retina_gaussian_guard.v] [file join $out gaussian_guard_used.v]
set_param board.repoPaths [list [file join $root references board pynq-z2 pynq-z2]]
create_project a4_segmentation $out -part xc7z020clg400-1
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $root build a4_hls_01 solution1 impl ip]] [current_project]
update_ip_catalog
add_files -norecurse [file join $root rtl core retina_gaussian_guard.v]
set_property include_dirs [list [file join $root rtl core]] [current_fileset]
update_compile_order -fileset sources_1
create_bd_design a4_segmentation
create_bd_cell -type module -reference retina_gaussian_guard point_stage
create_bd_cell -type ip -vlnv retinafpga.local:hls:retina_segmentation_hls:1.0 segmentation_filter
foreach {a b} {point_stage/hls_control segmentation_filter/control_V point_stage/hls_start segmentation_filter/ap_start segmentation_filter/ap_idle point_stage/hls_idle segmentation_filter/ap_done point_stage/hls_done segmentation_filter/ap_ready point_stage/hls_ready} {connect_bd_net [get_bd_pins $a] [get_bd_pins $b]}
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 point_control
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_DOUT_DEFAULT {0x00000000} \
    CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells point_control]
connect_bd_net [get_bd_pins point_control/gpio_io_o] [get_bd_pins point_stage/cfg_control]
connect_bd_net [get_bd_pins point_stage/status_word] [get_bd_pins point_control/gpio2_io_i]
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
    [get_bd_cells ps7_0]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} CONFIG.PCW_FPGA3_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_RST0_PORT {1}] [get_bd_cells ps7_0]
# The board preset predates propagate-only frequency fields and sets their
# VALUE_SRC to USER (10 MHz). Release those two derived fields for propagation.
foreach prop {PCW_M_AXI_GP0_FREQMHZ PCW_S_AXI_HP0_FREQMHZ} {
    set_property CONFIG.${prop}.VALUE_SRC DEFAULT [get_bd_cells ps7_0]
}

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_s2mm {1} CONFIG.c_sg_length_width {23} \
    CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axis_mm2s_tdata_width {32} \
    CONFIG.c_micro_dma {0} \
    CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_mm2s_burst_size {16} CONFIG.c_s2mm_burst_size {16}] [get_bd_cells axi_dma_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:1.1 loopback_fifo
set_property -dict [list CONFIG.TDATA_NUM_BYTES {4} CONFIG.FIFO_DEPTH {1024} \
    CONFIG.HAS_TKEEP {1} CONFIG.HAS_TLAST {1} CONFIG.IS_ACLK_ASYNC {0}] [get_bd_cells loopback_fifo]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 control_axi
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells control_axi]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory_axi
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells memory_axi]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_100m
# Reset polarity and S2MM widths are derived by this tool's BD propagation.
# FCLK_RESET0_N propagates ACTIVE_LOW; FIFO propagates 32-bit S2MM stream/memory.
# The interconnect's standard width converter adapts S2MM 32 -> HP0 64.
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_one
set_property CONFIG.CONST_VAL {1} [get_bd_cells const_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells const_zero]

foreach {a b} {
    ps7_0/M_AXI_GP0 control_axi/S00_AXI
    control_axi/M00_AXI axi_dma_0/S_AXI_LITE
    control_axi/M01_AXI point_control/S_AXI
    axi_dma_0/M_AXI_MM2S memory_axi/S00_AXI
    axi_dma_0/M_AXI_S2MM memory_axi/S01_AXI
    memory_axi/M00_AXI ps7_0/S_AXI_HP0
    axi_dma_0/M_AXIS_MM2S point_stage/S_AXIS
    point_stage/M_HLS segmentation_filter/source_V_V
    segmentation_filter/result_V_V point_stage/S_HLS
    point_stage/M_AXIS loopback_fifo/S_AXIS
    loopback_fifo/M_AXIS axi_dma_0/S_AXIS_S2MM
} {connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]}
set clk [get_bd_pins ps7_0/FCLK_CLK0]
foreach pin {
    ps7_0/M_AXI_GP0_ACLK ps7_0/S_AXI_HP0_ACLK
    control_axi/ACLK control_axi/S00_ACLK control_axi/M00_ACLK control_axi/M01_ACLK
    point_control/s_axi_aclk point_stage/aclk segmentation_filter/ap_clk
    memory_axi/ACLK memory_axi/S00_ACLK memory_axi/S01_ACLK memory_axi/M00_ACLK
    axi_dma_0/s_axi_lite_aclk axi_dma_0/m_axi_mm2s_aclk axi_dma_0/m_axi_s2mm_aclk
    loopback_fifo/s_axis_aclk reset_100m/slowest_sync_clk
} {connect_bd_net $clk [get_bd_pins $pin]}
connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] [get_bd_pins reset_100m/ext_reset_in]
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset_100m/dcm_locked]
# The reset IP's aux_reset_in defaults to ACTIVE_LOW in this BD/tool.
# Explicitly declare its polarity, then tie HIGH to keep it deasserted.
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_pins reset_100m/aux_reset_in]
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset_100m/aux_reset_in]
connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins reset_100m/mb_debug_sys_rst]
foreach pin {
    control_axi/ARESETN control_axi/S00_ARESETN control_axi/M00_ARESETN control_axi/M01_ARESETN
    memory_axi/ARESETN memory_axi/S00_ARESETN memory_axi/S01_ARESETN memory_axi/M00_ARESETN
} {connect_bd_net [get_bd_pins reset_100m/interconnect_aresetn] [get_bd_pins $pin]}
foreach pin {axi_dma_0/axi_resetn loopback_fifo/s_axis_aresetn point_stage/aresetn point_control/s_axi_aresetn segmentation_filter/ap_rst_n} {
    connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [get_bd_pins $pin]
}
# A4 uses bounded polling. IRQ outputs intentionally unconnected, not software-enabled.
assign_bd_address
set dma_seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data] -filter {NAME =~ *axi_dma_0*}]
if {[llength $dma_seg] != 1} {error "Expected exactly one DMA control address segment"}
set_property offset 0x40400000 $dma_seg
set_property range 64K $dma_seg
set gpio_seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data] -filter {NAME =~ *point_control*}]
if {[llength $gpio_seg] != 1} {error "Expected one GPIO control segment"}
set_property offset 0x41200000 $gpio_seg
set_property range 64K $gpio_seg
validate_bd_design
foreach {pin prop expected} {
    reset_100m CONFIG.C_EXT_RESET_HIGH 0
    reset_100m CONFIG.C_AUX_RESET_HIGH 0
    axi_dma_0 CONFIG.c_s_axis_s2mm_tdata_width 32
    axi_dma_0 CONFIG.c_m_axi_s2mm_data_width 32
    axi_dma_0 CONFIG.c_m_axis_mm2s_tdata_width 32
    axi_dma_0 CONFIG.c_m_axi_mm2s_data_width 64
    ps7_0 CONFIG.PCW_M_AXI_GP0_FREQMHZ 100
    ps7_0 CONFIG.PCW_S_AXI_HP0_FREQMHZ 100
} {
    if {[get_property $prop [get_bd_cells $pin]] ne $expected} {error "Unexpected derived parameter $pin $prop"}
}
save_bd_design
write_bd_tcl -force [file join $out reconstructed_bd.tcl]
report_ip_status -file [file join $out ip_status.rpt]
set fp [open [file join $out configuration.txt] w]
puts $fp "Vivado [version -short]; part [get_property PART [current_project]]; board [get_property BOARD_PART [current_project]]"
foreach cell {ps7_0 axi_dma_0 loopback_fifo reset_100m point_control point_stage segmentation_filter} {
    puts $fp "\n$cell [get_property VLNV [get_bd_cells $cell]]"
    foreach prop [lsort [list_property [get_bd_cells $cell]]] {
        if {[string match CONFIG.* $prop]} {puts $fp "$prop=[get_property $prop [get_bd_cells $cell]]"}
    }
}
foreach seg [get_bd_addr_segs -hier] {puts $fp "$seg offset=[get_property OFFSET $seg] range=[get_property RANGE $seg]"}
close $fp
puts "A4_BD_VALIDATED (host only, board test pending)"
if {$stage eq "bd"} {exit 0}
set bd_file [get_files */a4_segmentation.bd]
generate_target all $bd_file
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top a4_segmentation_wrapper [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed; inspect run log"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed; inspect run log"}
open_run impl_1
report_timing_summary -warn_on_violation -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
report_clocks -file [file join $out clocks.rpt]
set setup_paths [get_timing_paths -delay_type max -max_paths 1]
set hold_paths [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_paths] == 0 || [llength $hold_paths] == 0} {error "Missing timing paths"}
if {[get_property SLACK $setup_paths] < 0 || [get_property SLACK $hold_paths] < 0} {error "Timing violation; artifact not released"}
set hwh [glob -nocomplain [file join $out a4_segmentation.srcs sources_1 bd a4_segmentation hw_handoff *.hwh]]
if {[llength $hwh] != 1} {error "Expected one generated HWH: $hwh"}
file mkdir [file join $out deploy]
file copy [file join $out a4_segmentation.runs impl_1 a4_segmentation_wrapper.bit] [file join $out deploy a4_segmentation.bit]
file copy [lindex $hwh 0] [file join $out deploy a4_segmentation.hwh]
puts "A4_BITSTREAM_GENERATED_TIMING_CHECKED (host only; not board segmentation PASS)"
exit 0
