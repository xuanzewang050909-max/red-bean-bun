set out D:/PLD/tmp/single_repair_design_r2
open_checkpoint $out/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
set core [get_cells single_repair_i/repair_0/inst]
if {[llength $core]!=1} {error "EXACT_CORE_MISSING"}
set f [open $out/routed_boundary_audit_r2.tsv w]
puts $f "pin\tdirection\ttype\tdrivers\tloads\tsegments"
set count 0
set signals {}
foreach p [get_pins -of_objects $core] {
 set leaf [lindex [split [get_property NAME $p] /] end]
 set signal [lindex [split $leaf {[}] 0]
 if {![string match s_axi_control_* $signal] && ![string match m_axi_ram_* $signal] && $signal ni {ap_clk ap_rst_n}} {continue}
 dict incr signals $signal
 set ns [get_nets -segments -of_objects $p]
 if {![llength $ns]} {
  set reason ""
  if {[regexp {^m_axi_ram_(AR|AW)ADDR\[[01]\]$} $leaf]} {set reason WORD_ALIGNED_LOW2_OPTIMIZED}
  if {[regexp {^m_axi_ram_(AR|AW)LEN\[[4-7]\]$} $leaf]} {set reason MAX_BURST16_HIGH_LEN_OPTIMIZED}
  if {[regexp {^m_axi_ram_(AR|AW)(BURST|CACHE|LOCK|PROT|QOS|REGION|SIZE|USER|ID)\[[0-3]\]$} $leaf]} {set reason FIXED_REQUEST_SIDEBAND_OPTIMIZED}
  if {[regexp {^m_axi_ram_(BID|BRESP|BUSER|RID|RUSER|WID|WUSER)\[[01]\]$} $leaf]} {set reason HLS_UNUSED_ID_USER_OR_WRITE_STATUS}
  if {$leaf eq "m_axi_ram_WLAST"} {set reason CONVERTER_REGENERATES_LAST_FROM_LENGTH}
  if {[regexp {^s_axi_control_(BRESP|RRESP)\[[01]\]$} $leaf]} {set reason AXIL_RESPONSE_OKAY_CONSTANT}
  if {$reason eq ""} {error "UNEXPLAINED_UNCONNECTED_CORE_BOUNDARY $p"}
  puts $f "$p\t[get_property DIRECTION $p]\t$reason\t0\t0\t0"
  incr count
  continue
 }
 set drivers [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == OUT}]
 set loads [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == IN}]
 set types [lsort -unique [get_property TYPE $ns]]
 if {[string match *VALID $signal] || [string match *READY $signal] || $signal in {ap_clk ap_rst_n}} {
  if {![llength $drivers] || ![llength $loads] || "GROUND" in $types || "POWER" in $types} {error "CRITICAL_SIGNAL_NOT_CONNECTED $p types=$types"}
 }
 puts $f "$p\t[get_property DIRECTION $p]\t$types\t[llength $drivers]\t[llength $loads]\t[llength $ns]"
 incr count
}
foreach s {ap_clk ap_rst_n s_axi_control_AWADDR s_axi_control_AWVALID s_axi_control_AWREADY s_axi_control_WDATA s_axi_control_WVALID s_axi_control_WREADY s_axi_control_BVALID s_axi_control_BREADY s_axi_control_ARVALID s_axi_control_ARREADY s_axi_control_RVALID s_axi_control_RREADY m_axi_ram_AWADDR m_axi_ram_AWVALID m_axi_ram_AWREADY m_axi_ram_WDATA m_axi_ram_WVALID m_axi_ram_WREADY m_axi_ram_BVALID m_axi_ram_BREADY m_axi_ram_ARADDR m_axi_ram_ARVALID m_axi_ram_ARREADY m_axi_ram_RDATA m_axi_ram_RVALID m_axi_ram_RREADY} {
 if {![dict exists $signals $s]} {error "BOUNDARY_SIGNAL_MISSING $s"}
}
puts $f "BOUNDARY_BITS=$count"
puts $f "SIGNAL_WIDTHS=$signals"
# Check physical PS HP0 endpoints independently, including length/LAST after the
# stock protocol/width converter; request address low bits must be constant zero.
foreach p [get_pins -of_objects [get_cells single_repair_i/ps7_0/inst]] {
 set leaf [lindex [split [get_property NAME $p] /] end]
 if {![regexp {^S_AXI_HP0_(AWADDR|AWLEN|AWVALID|AWREADY|WDATA|WSTRB|WLAST|WVALID|WREADY|BVALID|BREADY|ARADDR|ARLEN|ARVALID|ARREADY|RDATA|RLAST|RVALID|RREADY)(\[[0-9]+\])?$} $leaf]} {continue}
 set ns [get_nets -quiet -segments -of_objects $p]
 if {![llength $ns]} {error "PS_HP0_ENDPOINT_UNCONNECTED $p"}
 set types [lsort -unique [get_property TYPE $ns]]
 set drivers [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == OUT}]
 set loads [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == IN}]
 if {![llength $drivers] || ![llength $loads]} {error "PS_HP0_ENDPOINT_NO_DRIVER_LOAD $p"}
 if {[regexp {(VALID|READY|LAST)$} $leaf] && ("GROUND" in $types || "POWER" in $types)} {error "PS_HP0_CRITICAL_CONSTANT $p"}
 if {[regexp {(AR|AW)ADDR\[[01]\]$} $leaf] && $types ne "GROUND"} {error "PS_HP0_ALIGNMENT $p"}
 puts $f "$p\t[get_property DIRECTION $p]\t$types\t[llength $drivers]\t[llength $loads]\t[llength $ns]"
}
# Verify actual routed peripheral-reset source, not just a nonconstant core pin.
set rp [get_pins single_repair_i/repair_0/inst/ap_rst_n]
set rnets [get_nets -segments -of_objects $rp]
set rd [get_pins -leaf -of_objects $rnets -filter {DIRECTION == OUT}]
if {![string match *reset_50m* $rd]} {error "CORE_RESET_SOURCE_MISMATCH $rd"}
puts $f "ACTUAL_CORE_RESET_DRIVERS=$rd"
foreach rname {aux_reset_in ext_reset_in dcm_locked mb_debug_sys_rst peripheral_aresetn interconnect_aresetn} {
 set ps [get_pins -quiet single_repair_i/reset_50m/$rname*]
 foreach p $ps {
  set ns [get_nets -quiet -segments -of_objects $p]
  if {![llength $ns]} {puts $f "RESET_PIN $p OPTIMIZED_NO_NET; checked by routed-cell functional simulation";continue}
  puts $f "RESET_PIN $p TYPES=[lsort -unique [get_property TYPE $ns]] NETS=$ns"
 }
}
close $f
report_drc -file $out/final_drc.rpt
report_route_status -file $out/final_route_status.rpt
report_timing_summary -report_unconstrained -file $out/final_timing_summary.rpt
report_exceptions -file $out/timing_exceptions.rpt
write_xdc $out/routed_constraints.xdc
write_verilog -mode funcsim -cell [get_cells single_repair_i/reset_50m] -rename_top routed_reset $out/routed_reset.v
write_verilog -mode funcsim $out/routed_functional.v
puts "ROUTED_BOUNDARY_AUDIT_PASS bits=$count"
close_design
exit
