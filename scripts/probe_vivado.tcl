# Read tool/IP/board availability, then synthesize a tiny OOC tool probe.
# Does not program hardware, modify installed tools, or build an overlay.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root results audit vivado_probe]
file mkdir $out
set f [open [file join $out capabilities.txt] w]
puts $f "Vivado: [version -short]"
puts $f "Part: [get_parts -quiet xc7z020clg400-1]"
puts $f "Installed PYNQ boards (before project-local repository): [get_board_parts -quiet *pynq*]"
set_param board.repoPaths [list [file join $root references board pynq-z2]]
puts $f "PYNQ boards (after project-local repository): [get_board_parts -quiet *pynq*]"
create_project -in_memory -part xc7z020clg400-1
foreach pattern {processing_system7 axi_dma axi_vdma axi_gpio axi_interconnect proc_sys_reset v_tc v_axi4s_vid_out} {
    puts $f "IP $pattern: [get_ipdefs -all -quiet *:${pattern}:*]"
}
close $f
read_verilog [file join $root scripts environment_probe.sv]
synth_design -top environment_probe -part xc7z020clg400-1 -mode out_of_context
create_clock -name probe_clk -period 10.000 [get_ports clk]
report_utilization -file [file join $out smoke_utilization.rpt]
opt_design
place_design
route_design
report_timing_summary -file [file join $out smoke_timing.rpt]
write_checkpoint -force [file join $out smoke_ooc.dcp]
puts "ENVIRONMENT_SYNTH_IMPLEMENT_PASS (OOC probe only, no bitstream)"
exit
