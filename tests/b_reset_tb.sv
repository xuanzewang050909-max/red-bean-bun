`timescale 1ns/1ps
// Instantiate the actual three generated reset IPs, not behavioral substitutes.
module b_reset_tb;
  reg clk100=0, clk142=0, reset_n, aux_n;
  always #5 clk100=~clk100;
  // Official FCLK1 is IO PLL 1000 MHz / 7 = 142.857 MHz.
  always #3.5 clk142=~clk142;
  wire [2:0] ic_n, per_n;
  system_reset_100m_0 algorithm (
    .slowest_sync_clk(clk100), .ext_reset_in(reset_n), .aux_reset_in(aux_n),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1), .mb_reset(), .bus_struct_reset(),
    .peripheral_reset(), .interconnect_aresetn(ic_n[0]), .peripheral_aresetn(per_n[0]));
  system_rst_ps7_0_fclk0_0 control (
    .slowest_sync_clk(clk100), .ext_reset_in(reset_n), .aux_reset_in(1'b1),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1), .mb_reset(), .bus_struct_reset(),
    .peripheral_reset(), .interconnect_aresetn(ic_n[1]), .peripheral_aresetn(per_n[1]));
  system_rst_ps7_0_fclk1_0 video (
    .slowest_sync_clk(clk142), .ext_reset_in(reset_n), .aux_reset_in(1'b1),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1), .mb_reset(), .bus_struct_reset(),
    .peripheral_reset(), .interconnect_aresetn(ic_n[2]), .peripheral_aresetn(per_n[2]));
  initial begin
    #1; reset_n=0; aux_n=1;
    #2000;
    if (ic_n!==3'b000 || per_n!==3'b000) $fatal(1,"Startup reset failure");
    reset_n=1; #4000;
    if (ic_n!==3'b111 || per_n!==3'b111) $fatal(1,"100/142 MHz reset release failure");
    aux_n=0; #2000;
    if (ic_n!==3'b110 || per_n!==3'b110) $fatal(1,"Algorithm auxiliary reset/isolation failure");
    aux_n=1; #4000;
    if (ic_n!==3'b111 || per_n!==3'b111) $fatal(1,"Auxiliary recovery failure");
    reset_n=0; #2000;
    if (ic_n!==3'b000 || per_n!==3'b000) $fatal(1,"PS reset assertion failure");
    reset_n=1; #4000;
    if (ic_n!==3'b111 || per_n!==3'b111) $fatal(1,"PS reset recovery failure");
    $display("B_RESET_SIM_PASS: actual three vendor IPs; control/algorithm 100 MHz, video 142.857 MHz; isolation and PS reset");
    $finish;
  end
  initial begin #30000; $fatal(1,"Timeout"); end
endmodule
