set out D:/PLD/tmp/single_repair_design_r1
open_checkpoint $out/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
set f [open $out/routed_endpoints.txt w]
set count 0
set boundary [get_pins -hier -filter {NAME =~ */repair_0/inst/*}]
foreach signal {ap_clk ap_rst_n s_axi_control_AWADDR s_axi_control_AWVALID s_axi_control_AWREADY s_axi_control_WDATA s_axi_control_WVALID s_axi_control_WREADY s_axi_control_BVALID s_axi_control_BREADY s_axi_control_ARVALID s_axi_control_ARREADY s_axi_control_RVALID s_axi_control_RREADY m_axi_ram_AWADDR m_axi_ram_AWVALID m_axi_ram_AWREADY m_axi_ram_WDATA m_axi_ram_WVALID m_axi_ram_WREADY m_axi_ram_BVALID m_axi_ram_BREADY m_axi_ram_ARADDR m_axi_ram_ARVALID m_axi_ram_ARREADY m_axi_ram_RDATA m_axi_ram_RVALID m_axi_ram_RREADY} {
 set pins {}
 foreach p $boundary {
  set leaf [lindex [split [get_property NAME $p] /] end]
  if {[lindex [split $leaf {[}] 0] eq $signal} {lappend pins $p}
 }
 if {![llength $pins]} {error "ROUTED_BOUNDARY_PIN_MISSING $signal"}
 foreach pin $pins {
  set nets [get_nets -of_objects $pin]
  if {![llength $nets]} {error "UNCONNECTED $pin"}
  set leaves [get_pins -leaf -of_objects $nets]
  puts $f "$pin dir=[get_property DIRECTION $pin] nets=$nets leaf_count=[llength $leaves]"
  incr count
 }
}
puts $f "CONNECTED_BOUNDARY_BITS=$count"
close $f
report_drc -file $out/final_drc.rpt
report_route_status -file $out/final_route_status.rpt
report_timing_summary -report_unconstrained -file $out/final_timing_summary.rpt
close_design
exit
