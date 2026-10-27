open_checkpoint D:/PLD/tmp/single_repair_design_r1/single_repair.runs/impl_1/single_repair_wrapper_routed.dcp
write_verilog -mode funcsim -cell [get_cells single_repair_i/reset_50m] -rename_top routed_reset D:/PLD/retina_c7_single_image_repair/results/single_repair_reset_repair_r1/old_routed_reset.v
close_design
exit
