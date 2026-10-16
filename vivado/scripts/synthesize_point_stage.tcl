# Out-of-context synthesis/placement only; no PS, DMA, bitstream or board programming.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2017.4"} {error "Tested with Vivado 2017.4 only"}
if {[llength $argv] != 1} {error "Expected a NEW output directory"}
set out [file normalize [lindex $argv 0]]
if {[file exists $out]} {error "Refusing to overwrite previous result"}
file mkdir $out
create_project -in_memory -part xc7z020clg400-1
set_property include_dirs [list [file join $root rtl core]] [current_fileset]
read_verilog [file join $root rtl core retina_point_axis.v]
synth_design -top retina_point_axis -part xc7z020clg400-1 -mode out_of_context
create_clock -name aclk -period 10 [get_ports aclk]
# Model same-clock adjacent registers; combinational IO paths get a real timing budget.
set_input_delay -clock aclk 2 [get_ports {aresetn cfg_control[*] s_axis_tdata[*] s_axis_tkeep[*] s_axis_tlast s_axis_tvalid m_axis_tready}]
set_output_delay -clock aclk 2 [get_ports {frames_received[*] frames_sent[*] sticky_errors[*] s_axis_tready m_axis_tdata[*] m_axis_tkeep[*] m_axis_tlast m_axis_tvalid}]
opt_design
place_design
route_design
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
write_checkpoint [file join $out point_stage_routed.dcp]
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$wns < 0 || $whs < 0} {error "Point stage timing failed"}
puts "POINT_OOC_TIMING_PASS: WNS=$wns WHS=$whs; no full overlay/board PASS"
exit 0
