if {[version -short] ne "2017.4"} {error "VERSION"}
set out D:/PLD/tmp/three_repair_design_r1
set_param board.repoPaths [list D:/PLD/retina_c7_system/references/board/pynq-z2/pynq-z2]
if {![llength [get_board_parts tul.com.tw:pynq-z2:part0:1.0]]} {error "BOARD_DEFINITION_MISSING"}
if {![file exists D:/PLD/retina_c7_three_image_completion/results/three_repair_r1/physical_gates.json]} {error "NO_GATE_RECEIPT"}
if {[file exists $out/single_repair_release.bit]} {error "BIT_ALREADY_EXISTS"}
open_checkpoint $out/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
# No design edits, new optimizations, reroute or clock changes here.
write_bitstream $out/single_repair_release.bit
close_design
exit
