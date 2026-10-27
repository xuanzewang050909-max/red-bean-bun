# Read-only old routed DCP inspection. Reports go to the new repair directory.
open_checkpoint D:/PLD/tmp/single_repair_design_r1/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
set f [open D:/PLD/retina_c7_single_image_repair/results/single_repair_reset_repair_r1/old_routed_reset.tsv {WRONLY CREAT EXCL}]
puts $f "pin\ttypes\tdrivers\tloads"
foreach name {aux_reset_in ext_reset_in dcm_locked mb_debug_sys_rst peripheral_aresetn interconnect_aresetn} {
 foreach p [get_pins -quiet single_repair_i/reset_50m/$name*] {
  set ns [get_nets -quiet -segments -of_objects $p]
  if {![llength $ns]} {puts $f "$p\tOPTIMIZED_NO_NET\t\t";continue}
  set types [lsort -unique [get_property TYPE $ns]]
  set drivers [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == OUT}]
  set loads [get_pins -quiet -leaf -of_objects $ns -filter {DIRECTION == IN}]
  puts $f "$p\t$types\t$drivers\t$loads"
 }
}
close $f
puts "OLD_ROUTED_RESET_INSPECTION_COMPLETE_NO_DESIGN_EDITS"
close_design
exit
