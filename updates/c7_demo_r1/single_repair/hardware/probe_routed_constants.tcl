set out D:/PLD/tmp/single_repair_design_r1
open_checkpoint $out/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
set f [open $out/routed_constants_probe_r2.txt w]
foreach c {single_repair_i/repair_0/inst single_repair_i/memory_axi single_repair_i/control_axi} {
 puts $f "CELL=$c"
 foreach p [get_pins -of_objects [get_cells $c]] {
  set ns [get_nets -quiet -segments -of_objects $p]
  set types {};if {[llength $ns]} {set types [lsort -unique [get_property TYPE $ns]]}
  if {![llength $ns] || "GROUND" in $types || "POWER" in $types} {puts $f "$p dir=[get_property DIRECTION $p] types=$types nets=$ns"}
 }
}
close $f
write_verilog -mode funcsim $out/routed_audit_netlist.v
close_design
exit
