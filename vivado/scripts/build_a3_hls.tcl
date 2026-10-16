# Derive the proven A2 HLS flow; use installed Gaussian and BoxFilter unchanged.
set root [file normalize [file join [file dirname [info script]] ../..]]
set task_args $argv
if {[lindex $task_args 0] eq "-f"} {set task_args [lrange $task_args 2 end]}
if {[lindex $task_args 0] eq "-tclargs"} {set task_args [lrange $task_args 1 end]}
if {[llength $task_args] != 2} {error "Expected NEW output directory and csim|synth: $task_args"}
set out [file normalize [lindex $task_args 0]]
set stage [lindex $task_args 1]
if {$stage ni {csim synth}} {error "Invalid stage"}
if {[file exists $out]} {error "Refusing to overwrite HLS evidence"}
file mkdir [file dirname $out]
cd [file dirname $out]
open_project [file tail $out]
set_top retina_background_hls
add_files [file join $root hls retina_background_hls.cpp] -cflags "-I[file join $root hls]"
add_files -tb [file join $root tests retina_background_hls_tb.cpp] -cflags "-I[file join $root hls]"
open_solution solution1
set_part xc7z020clg400-1
create_clock -period 10 -name default
config_rtl -reset all -reset_level low
csim_design -clean
if {$stage eq "synth"} {
    csynth_design
    export_design -format ip_catalog -rtl verilog -vendor retinafpga.local -library hls -version 1.0
}
exit
