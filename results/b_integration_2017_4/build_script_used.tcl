# B derives the pinned official Base BD and reuses the measured A4 branch.
# Original reference/prepared projects remain unchanged. See reuse audit.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2017.4" || [llength $argv] != 2} {error "Use Vivado 2017.4: new-output bd|full"}
set out [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
if {$stage ni {bd full} || [file exists $out]} {error "New build directory and bd|full required"}
file mkdir $out
file copy [info script] [file join $out build_script_used.tcl]
set source_bd [file join $root build official_v2.2.1 boards Pynq-Z2 base base base.srcs sources_1 bd system system.bd]
set bd_dir [file join $out b_integration.srcs sources_1 bd system]
file copy $source_bd [file join $out original_official_system.bd]
set_param board.repoPaths [list [file join $root references board pynq-z2 pynq-z2]]
create_project b_integration $out -part xc7z020clg400-1
file mkdir $bd_dir
file copy $source_bd [file join $bd_dir system.bd]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $root build official_v2.2.1 boards ip] [file join $root build a4_hls_02 solution1 impl ip]] [current_project]
update_ip_catalog
add_files -norecurse [file join $bd_dir system.bd]
open_bd_design [file join $bd_dir system.bd]
write_bd_tcl -force [file join $out original_official_bd.tcl]
set keep {ps7_0 video ps7_0_axi_periph rst_ps7_0_fclk0 rst_ps7_0_fclk1 btns_gpio switches_gpio leds_gpio rgbleds_gpio system_interrupts concat_interrupts}
set fp [open [file join $out pruning.txt] w]
foreach cell [get_bd_cells] {
    set name [get_property NAME $cell]
    if {$name ni $keep} {puts $fp "DELETE_CELL $name"; delete_bd_objs $cell}
}
set keep_interfaces {DDR FIXED_IO hdmi_in hdmi_in_ddc hdmi_out sws_2bits btns_4bits leds_4bits rgbleds_6bits}
foreach port [get_bd_intf_ports] {
    set name [get_property NAME $port]
    if {$name ni $keep_interfaces} {puts $fp "DELETE_INTERFACE $name"; delete_bd_objs $port}
}
foreach port [get_bd_ports] {
    set name [get_property NAME $port]
    set preserved [expr {$name in {hdmi_in_hpd hdmi_out_hpd}}]
    foreach intf $keep_interfaces {if {[string match ${intf}_* $name]} {set preserved 1}}
    if {!$preserved} {puts $fp "DELETE_PORT $name"; delete_bd_objs $port}
}
close $fp
# Remove only unused PS interfaces; board DDR/MIO preset stays as original.
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP1 {0} CONFIG.PCW_USE_S_AXI_GP0 {0} CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} CONFIG.PCW_I2C1_PERIPHERAL_ENABLE {0}] [get_bd_cells ps7_0]
set pin [get_bd_pins ps7_0/S_AXI_HP2_ACLK]
disconnect_bd_net [get_bd_nets -of_objects $pin] $pin
set_property CONFIG.PCW_S_AXI_HP2_FREQMHZ.VALUE_SRC DEFAULT [get_bd_cells ps7_0]
add_files -norecurse [file join $root rtl core retina_gaussian_guard.v]
file copy [file join $root rtl core retina_gaussian_guard.v] [file join $out gaussian_guard_used.v]
set_property include_dirs [list [file join $root rtl core]] [current_fileset]
update_compile_order -fileset sources_1
create_bd_cell -type module -reference retina_gaussian_guard point_stage
create_bd_cell -type ip -vlnv retinafpga.local:hls:retina_segmentation_hls:1.0 segmentation_filter
foreach {a b} {point_stage/hls_control segmentation_filter/control_V point_stage/hls_start segmentation_filter/ap_start segmentation_filter/ap_idle point_stage/hls_idle segmentation_filter/ap_done point_stage/hls_done segmentation_filter/ap_ready point_stage/hls_ready} {connect_bd_net [get_bd_pins $a] [get_bd_pins $b]}
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 point_control
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_DOUT_DEFAULT {0x00000000} CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells point_control]
connect_bd_net [get_bd_pins point_control/gpio_io_o] [get_bd_pins point_stage/cfg_control]
connect_bd_net [get_bd_pins point_stage/status_word] [get_bd_pins point_control/gpio2_io_i]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm {1} CONFIG.c_sg_length_width {23} CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_micro_dma {0} CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0} CONFIG.c_mm2s_burst_size {16} CONFIG.c_s2mm_burst_size {16}] [get_bd_cells axi_dma_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:1.1 loopback_fifo
set_property -dict [list CONFIG.TDATA_NUM_BYTES {4} CONFIG.FIFO_DEPTH {1024} CONFIG.HAS_TKEEP {1} CONFIG.HAS_TLAST {1} CONFIG.IS_ACLK_ASYNC {0}] [get_bd_cells loopback_fifo]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 memory_axi
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells memory_axi]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_100m
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_one
set_property CONFIG.CONST_VAL {1} [get_bd_cells const_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells const_zero]
# Preserve original IRQ bit positions, including removed four-bit IOP slot.
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero_iop_irq
set_property -dict [list CONFIG.CONST_WIDTH {4} CONFIG.CONST_VAL {0}] [get_bd_cells zero_iop_irq]
foreach n {1 2} {connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins concat_interrupts/In$n]}
connect_bd_net [get_bd_pins zero_iop_irq/dout] [get_bd_pins concat_interrupts/In4]
foreach {a b} {
    ps7_0_axi_periph/M03_AXI point_control/S_AXI
    ps7_0_axi_periph/M06_AXI axi_dma_0/S_AXI_LITE
    axi_dma_0/M_AXI_MM2S memory_axi/S00_AXI
    axi_dma_0/M_AXI_S2MM memory_axi/S01_AXI
    memory_axi/M00_AXI ps7_0/S_AXI_HP2
    axi_dma_0/M_AXIS_MM2S point_stage/S_AXIS
    point_stage/M_HLS segmentation_filter/source_V_V
    segmentation_filter/result_V_V point_stage/S_HLS
    point_stage/M_AXIS loopback_fifo/S_AXIS
    loopback_fifo/M_AXIS axi_dma_0/S_AXIS_S2MM
} {connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]}
foreach pin {ps7_0/S_AXI_HP2_ACLK point_control/s_axi_aclk point_stage/aclk segmentation_filter/ap_clk memory_axi/ACLK memory_axi/S00_ACLK memory_axi/S01_ACLK memory_axi/M00_ACLK axi_dma_0/s_axi_lite_aclk axi_dma_0/m_axi_mm2s_aclk axi_dma_0/m_axi_s2mm_aclk loopback_fifo/s_axis_aclk reset_100m/slowest_sync_clk} {connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins $pin]}
connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] [get_bd_pins reset_100m/ext_reset_in]
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset_100m/dcm_locked]
# Default auxiliary reset is active low; assert the actual IP parameter below.
# POLARITY on the pin is read-only and must not be written.
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset_100m/aux_reset_in]
connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins reset_100m/mb_debug_sys_rst]
foreach pin {memory_axi/ARESETN memory_axi/S00_ARESETN memory_axi/S01_ARESETN memory_axi/M00_ARESETN} {connect_bd_net [get_bd_pins reset_100m/interconnect_aresetn] [get_bd_pins $pin]}
foreach pin {axi_dma_0/axi_resetn loopback_fifo/s_axis_aresetn point_stage/aresetn point_control/s_axi_aresetn segmentation_filter/ap_rst_n} {connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [get_bd_pins $pin]}
create_bd_addr_seg -range 64K -offset 0x40400000 [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg] SEG_algorithm_dma_Reg
create_bd_addr_seg -range 64K -offset 0x43C80000 [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs point_control/S_AXI/Reg] SEG_algorithm_control_Reg
foreach space {axi_dma_0/Data_MM2S axi_dma_0/Data_S2MM} {create_bd_addr_seg -range 0x20000000 -offset 0 [get_bd_addr_spaces $space] [get_bd_addr_segs ps7_0/S_AXI_HP2/HP2_DDR_LOWOCM] SEG_ps7_0_HP2_DDR_LOWOCM}
# Deleting function groups leaves empty named nets in the copied BD.
# Remove only root nets with no remaining pins/ports (never video internal nets).
foreach net [get_bd_nets] {if {[llength [get_bd_pins -quiet -of_objects $net]] == 0 && [llength [get_bd_ports -quiet -of_objects $net]] == 0} {delete_bd_objs $net}}
foreach net [get_bd_intf_nets] {if {[llength [get_bd_intf_pins -quiet -of_objects $net]] == 0 && [llength [get_bd_intf_ports -quiet -of_objects $net]] == 0} {delete_bd_objs $net}}
validate_bd_design
foreach {cell prop expected} {reset_100m CONFIG.C_EXT_RESET_HIGH 0 reset_100m CONFIG.C_AUX_RESET_HIGH 0 axi_dma_0 CONFIG.c_m_axi_s2mm_data_width 32 ps7_0 CONFIG.PCW_M_AXI_GP0_FREQMHZ 100 ps7_0 CONFIG.PCW_S_AXI_HP2_FREQMHZ 100} {if {[get_property $prop [get_bd_cells $cell]] ne $expected} {error "Unexpected $cell $prop"}}
save_bd_design
write_bd_tcl -force [file join $out reconstructed_bd.tcl]
report_ip_status -file [file join $out ip_status.rpt]
set fp [open [file join $out configuration.txt] w]
foreach cell [lsort [get_bd_cells -hier -filter {TYPE == ip}]] {puts $fp "$cell [get_property VLNV $cell]"; foreach prop [lsort [list_property $cell]] {if {[string match CONFIG.* $prop]} {puts $fp "$prop=[get_property $prop $cell]"}}}
foreach seg [get_bd_addr_segs -hier] {puts $fp "$seg offset=[get_property OFFSET $seg] range=[get_property RANGE $seg]"}
close $fp
puts "B_BD_VALIDATED_HOST_ONLY"
set bd_file [get_files */system.bd]
generate_target all $bd_file
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
file copy [file join $root vivado constraints b_integration.xdc] [file join $out constraints_used.xdc]
add_files -fileset constrs_1 -norecurse [file join $out constraints_used.xdc]
# The pinned rgb2dvi XDC unconditionally claims PixelClk generates SerialClk.
# Original Base actually uses an external MMCM + divide-by-5 BUFR. Exclude
# only that inapplicable clock file in this project; retain its untouched bytes,
# all other IP constraints and the tool's real MMCM/BUFR auto-derived clocks.
if {[get_property CONFIG.kGenerateSerialClk [get_bd_cells video/hdmi_out/frontend/rgb2dvi_0]] ne "false"} {error "Expected official external serial clock"}
set serial_xdc [get_files -all */rgb2dvi_clocks.xdc]
if {[llength $serial_xdc] != 1} {error "Expected one scoped rgb2dvi clock file"}
set_property USED_IN_SYNTHESIS false $serial_xdc
set_property USED_IN_IMPLEMENTATION false $serial_xdc
set fp [open [file join $out external_serial_clock_constraints.txt] w]
puts $fp "EXCLUDED_ONLY_IN_THIS_PROJECT $serial_xdc"
puts $fp "RTL_UNCHANGED kGenerateSerialClk=false; MMCM/BUFR auto-derived clocks retained"
puts $fp "USED_IN_SYNTHESIS=[get_property USED_IN_SYNTHESIS $serial_xdc]"
puts $fp "USED_IN_IMPLEMENTATION=[get_property USED_IN_IMPLEMENTATION $serial_xdc]"
close $fp
update_compile_order -fileset sources_1
if {$stage eq "bd"} {exit 0}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "B synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "B implementation failed"}
open_run impl_1
report_timing_summary -warn_on_violation -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
report_clocks -file [file join $out clocks.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_bus_skew -file [file join $out bus_skew.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
set serial_clock [get_clocks -of_objects [get_pins system_i/video/hdmi_out/frontend/rgb2dvi_0/U0/SerialClk]]
set pixel_clock [get_clocks -of_objects [get_pins system_i/video/hdmi_out/frontend/rgb2dvi_0/U0/PixelClk]]
if {[llength $serial_clock] != 1 || [llength $pixel_clock] != 1 || abs([get_property PERIOD $serial_clock]-2.0)>0.00001 || abs([get_property PERIOD $pixel_clock]-10.0)>0.00001} {error "Unexpected actual MMCM/BUFR video clocks"}
if {[get_property MASTER_CLOCK $serial_clock] ne "clk_fpga_0"} {error "Serial clock must derive from actual MMCM reference"}
if {[llength [get_clocks -quiet */rgb2dvi_0/U0/SerialClk]] != 0} {error "Inapplicable vendor clock still active"}
foreach delay {max min} {set paths [get_timing_paths -delay_type $delay -max_paths 1]; if {[llength $paths] == 0 || [get_property SLACK $paths] < 0} {error "B timing failed ($delay); not released"}}
set hwh [glob -nocomplain [file join $bd_dir hw_handoff *.hwh]]
if {[llength $hwh] != 1} {error "Expected one B HWH: $hwh"}
file mkdir [file join $out deploy]
file copy [file join $out b_integration.runs impl_1 system_wrapper.bit] [file join $out deploy b_integration.bit]
file copy [lindex $hwh 0] [file join $out deploy b_integration.hwh]
puts "B_BITSTREAM_TIMING_CHECKED_BOARD_NOT_RUN"
exit 0
