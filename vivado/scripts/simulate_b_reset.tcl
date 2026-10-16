# Real generated vendor reset modules: algorithm/official control/official video.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {$argc != 2} {error "Use candidate-build new-simulation-directory"}
set candidate [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "New simulation directory required"}
set_param board.repoPaths [list [file join $root references board pynq-z2 pynq-z2]]
create_project b_reset_sim $out -part xc7z020clg400-1
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
foreach name {reset_100m rst_ps7_0_fclk0 rst_ps7_0_fclk1} {
    read_ip [file join $candidate b_integration.srcs sources_1 bd system ip system_${name}_0 system_${name}_0.xci]
}
generate_target simulation [get_ips]
file copy [file join $root tests b_reset_tb.sv] [file join $out reset_tb_used.sv]
add_files -fileset sim_1 [file join $out reset_tb_used.sv]
set_property top b_reset_tb [get_filesets sim_1]
set_property xsim.simulate.runtime 30us [get_filesets sim_1]
launch_simulation
close_sim
set f [open [file join $out b_reset_sim.sim sim_1 behav xsim simulate.log] r]
set result [read $f]; close $f
if {[string first "B_RESET_SIM_PASS:" $result] < 0 || [string first "Fatal:" $result] >= 0 || [string first "ERROR:" $result] >= 0} {error "B generated vendor reset test failed"}
puts "B_VENDOR_RESET_GATE_PASS"
exit 0
