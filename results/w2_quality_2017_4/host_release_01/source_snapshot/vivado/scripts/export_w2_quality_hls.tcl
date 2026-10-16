# Export a separately preserved copy of the actual Q2 HLS build, not new synthesis.
set task_args $argv
if {[lindex $task_args 0] eq "-f"} {set task_args [lrange $task_args 2 end]}
if {[lindex $task_args 0] eq "-tclargs"} {set task_args [lrange $task_args 1 end]}
if {[llength $task_args] != 1} {error "Expected preserved HLS project copy"}
set copied_project [file normalize [lindex $task_args 0]]
if {![file exists [file join $copied_project solution1 syn verilog retina_quality_hls.v]]} {
    error "Missing actual generated RTL in HLS project copy"
}
if {[file exists [file join $copied_project solution1 impl ip]]} {error "Do not overwrite previous export"}
cd [file dirname $copied_project]
open_project [file tail $copied_project]
open_solution solution1
export_design -format ip_catalog -rtl verilog -vendor retinafpga.local -library hls -version 1.0
exit
