if {[version -short] ne "2017.4"} {error "VERSION"}
set root D:/PLD/retina_c7_single_image_repair
set out D:/PLD/tmp/single_repair_design_r2
if {![file exists $root/results/single_repair_reset_repair_r1/integration/receipt.json]} {error "Integration receipt missing"}
if {![file exists $root/results/single_repair_r1/rtl_receipt.json]} {error "Full RTL receipt missing"}
if {[file exists $out/physical_started]} {error "Physical attempt already started"}
set f [open $out/physical_started {WRONLY CREAT EXCL}];puts $f [clock seconds];close $f
set_param board.repoPaths [list D:/PLD/retina_c7_system/references/board/pynq-z2/pynq-z2]
open_project $out/single_repair.xpr
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "SYNTHESIS_FAILED"}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
open_run impl_1
report_timing_summary -report_unconstrained -warn_on_violation -file $out/timing_summary.rpt
report_utilization -file $out/utilization_routed.rpt
report_drc -file $out/drc.rpt
report_route_status -file $out/route_status.rpt
check_timing -verbose -file $out/check_timing.rpt
report_clocks -file $out/clocks.rpt
set c [get_clocks]
if {[llength $c]!=1 || abs([get_property PERIOD $c]-20.0)>0.000001} {error "CLOCK"}
set s [get_timing_paths -delay_type max -max_paths 1]
set h [get_timing_paths -delay_type min -max_paths 1]
set f [open $out/physical_summary.txt w]
puts $f "STATUS=[get_property STATUS [get_runs impl_1]]"
puts $f "WNS=[get_property SLACK $s] WHS=[get_property SLACK $h] CLOCK_NS=[get_property PERIOD $c]"
puts $f "BIT_NOT_GENERATED; complete route/pulse/DRC/constraints/endpoint audit next"
close $f
if {[get_property SLACK $s]<0 || [get_property SLACK $h]<0} {error "TIMING"}
if {[get_property STATUS [get_runs impl_1]] ne "route_design Complete!"} {error "ROUTE"}
close_project
exit
