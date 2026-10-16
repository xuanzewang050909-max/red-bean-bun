# Host-only simulation of the corrected design's generated reset IP.
set root [file normalize [file join [file dirname [info script]] ..]]
if {$argc != 2} {error "Usage: simulate_a0_reset.tcl <build-directory> <new-simulation-directory>"}
set candidate [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Refusing to overwrite previous simulation"}
set_param board.repoPaths [list [file join $root references board pynq-z2 pynq-z2]]
create_project reset_sim $out -part xc7z020clg400-1
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
read_ip [file join $candidate a0_dma.srcs sources_1 bd a0_dma ip a0_dma_reset_100m_0 a0_dma_reset_100m_0.xci]
generate_target simulation [get_ips]
add_files -fileset sim_1 [file join $root scripts a0_reset_tb.sv]
set_property top a0_reset_tb [get_filesets sim_1]
set_property xsim.simulate.runtime 20us [get_filesets sim_1]
launch_simulation
close_sim
set f [open [file join $out reset_sim.sim sim_1 behav xsim simulate.log] r]
set result [read $f]
close $f
if {[string first "RESET_SIM_PASS:" $result] < 0 || [string first "Fatal:" $result] >= 0} {
    error "Reset simulation did not pass; inspect preserved simulate.log"
}
puts "RESET_SIMULATION_GATE_PASS"
exit 0
