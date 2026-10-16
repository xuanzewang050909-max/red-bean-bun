`timescale 1ns/1ps
// Simulates the real generated vendor reset IP, not a reimplementation.
module a0_reset_tb;
  reg clk = 0;
  always #5 clk = ~clk;
  reg external_reset_n;
  reg auxiliary_reset_n;
  wire interconnect_reset_n, peripheral_reset_n;
  a1_point_reset_100m_0 dut (
    .slowest_sync_clk(clk), .ext_reset_in(external_reset_n),
    .aux_reset_in(auxiliary_reset_n), .mb_debug_sys_rst(1'b0),
    .dcm_locked(1'b1), .mb_reset(), .bus_struct_reset(),
    .peripheral_reset(), .interconnect_aresetn(interconnect_reset_n),
    .peripheral_aresetn(peripheral_reset_n)
  );
  task cycles(input integer n);
    repeat(n) @(posedge clk);
    #1;
  endtask
  initial begin
    // Explicit post-time-zero transitions are required by the 2017.4
    // mixed-language bridge; declaration-only init left VHDL aux at U.
    #1;
    external_reset_n = 0;
    auxiliary_reset_n = 0;
    cycles(100);
    external_reset_n = 1;
    cycles(300);
    $display("CHECK: ext=%b aux=%b ic=%b per=%b GSR=%b", external_reset_n,
      auxiliary_reset_n, interconnect_reset_n, peripheral_reset_n, glbl.GSR);
    // Reproduce the first faulty package: constant 0 holds auxiliary reset.
    if (interconnect_reset_n !== 0 || peripheral_reset_n !== 0)
      $fatal(1, "Faulty auxiliary tie-low was not reproduced");
    $display("RESET_FAULT_REPRODUCED: aux=0 holds AXI/DMA reset");
    auxiliary_reset_n = 1;
    cycles(300);
    if (interconnect_reset_n !== 1 || peripheral_reset_n !== 1)
      $fatal(1, "Corrected tie-high did not release AXI/DMA reset");
    external_reset_n = 0;
    cycles(100);
    if (interconnect_reset_n !== 0 || peripheral_reset_n !== 0)
      $fatal(1, "PS reset assertion did not reset AXI/DMA");
    external_reset_n = 1;
    cycles(300);
    if (interconnect_reset_n !== 1 || peripheral_reset_n !== 1)
      $fatal(1, "PS reset release did not restore AXI/DMA");
    $display("RESET_SIM_PASS: real vendor IP, auxiliary polarity and PS reset verified");
    $finish;
  end
  initial begin
    #20000;
    $fatal(1, "Simulation timeout");
  end
endmodule
