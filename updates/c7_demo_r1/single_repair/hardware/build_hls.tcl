set root [file normalize [file dirname [info script]]]
set out D:/PLD/tmp/single_repair_hls_r1
if {[file exists $out]} {error "Do not overwrite HLS evidence"}
cd [file dirname $out]
open_project [file tail $out]
set_top valley_repair
add_files $root/repair.cpp
open_solution solution
set_part xc7z020clg400-1
create_clock -period 20 -name default
set_clock_uncertainty 2.5
csynth_design
exit
