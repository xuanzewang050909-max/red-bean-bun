if {[version -short] ne "2017.4"} {error "Vivado version"}
set src [file dirname [file normalize [info script]]]
set out D:/PLD/tmp/single_repair_design_r2
if {[file exists $out]} {error "Do not overwrite build"}
set_param board.repoPaths [list D:/PLD/retina_c7_system/references/board/pynq-z2/pynq-z2]
create_project single_repair $out -part xc7z020clg400-1
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list D:/PLD/tmp/single_repair_ip_r1] [current_project]
update_ip_catalog
create_bd_design single_repair
source $src/ps7_verified_50m.tcl
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR
create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO
connect_bd_intf_net [get_bd_intf_ports DDR] [get_bd_intf_pins ps7_0/DDR]
connect_bd_intf_net [get_bd_intf_ports FIXED_IO] [get_bd_intf_pins ps7_0/FIXED_IO]
create_bd_cell -type ip -vlnv xilinx.com:hls:valley_repair:1.0 repair_0
foreach name {control_axi memory_axi} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 $name
 set_property -dict [list CONFIG.NUM_MI 1 CONFIG.NUM_SI 1] [get_bd_cells $name]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_50m
set_property -dict [list CONFIG.C_EXT_RESET_HIGH 0 CONFIG.C_AUX_RESET_HIGH 0] [get_bd_cells reset_50m]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
set_property CONFIG.CONST_VAL 1 [get_bd_cells one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero
set_property CONFIG.CONST_VAL 0 [get_bd_cells zero]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset_50m/dcm_locked] [get_bd_pins reset_50m/aux_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset_50m/mb_debug_sys_rst]
connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] [get_bd_pins reset_50m/ext_reset_in]
connect_bd_intf_net [get_bd_intf_pins ps7_0/M_AXI_GP0] [get_bd_intf_pins control_axi/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins control_axi/M00_AXI] [get_bd_intf_pins repair_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins repair_0/m_axi_ram] [get_bd_intf_pins memory_axi/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins memory_axi/M00_AXI] [get_bd_intf_pins ps7_0/S_AXI_HP0]
set clocks {repair_0/ap_clk ps7_0/M_AXI_GP0_ACLK ps7_0/S_AXI_HP0_ACLK reset_50m/slowest_sync_clk control_axi/ACLK control_axi/S00_ACLK control_axi/M00_ACLK memory_axi/ACLK memory_axi/S00_ACLK memory_axi/M00_ACLK}
foreach p $clocks {connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins $p]}
foreach p {control_axi/ARESETN memory_axi/ARESETN} {connect_bd_net [get_bd_pins reset_50m/interconnect_aresetn] [get_bd_pins $p]}
foreach p {repair_0/ap_rst_n control_axi/S00_ARESETN control_axi/M00_ARESETN memory_axi/S00_ARESETN memory_axi/M00_ARESETN} {connect_bd_net [get_bd_pins reset_50m/peripheral_aresetn] [get_bd_pins $p]}
create_bd_addr_seg -range 0x10000 -offset 0x43C00000 [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs repair_0/s_axi_control/Reg] REPAIR_CONTROL
create_bd_addr_seg -range 0x20000000 -offset 0 [get_bd_addr_spaces repair_0/Data_m_axi_ram] [get_bd_addr_segs ps7_0/S_AXI_HP0/HP0_DDR_LOWOCM] REPAIR_DDR
validate_bd_design
if {abs([get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps7_0]]-50.0)>0.00001} {error "CLOCK"}
set f [open $out/connections.txt w]
foreach p $clocks {puts $f "$p [get_bd_nets -of_objects [get_bd_pins $p]]"}
foreach p {ps7_0/M_AXI_GP0 control_axi/S00_AXI control_axi/M00_AXI repair_0/s_axi_control repair_0/m_axi_ram memory_axi/S00_AXI memory_axi/M00_AXI ps7_0/S_AXI_HP0} {puts $f "$p [get_bd_intf_nets -of_objects [get_bd_intf_pins $p]]"}
close $f
save_bd_design
set bd [get_files */single_repair.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top single_repair_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl -force $out/reconstructed_bd.tcl
export_simulation -of_objects $bd -simulator xsim -directory $out/sim_export -force
puts "SINGLE_REPAIR_BD_GENERATED_50MHZ"
close_project
exit
