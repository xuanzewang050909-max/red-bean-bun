`timescale 1ns/1ps
module environment_probe_tb;
    reg clk = 0;
    reg [7:0] din = 0;
    wire [7:0] dout;
    environment_probe dut(.clk(clk), .din(din), .dout(dout));
    always #5 clk = ~clk;
    integer i;
    initial begin
        for (i=0; i<256; i=i+1) begin
            @(negedge clk) din = i;
            @(posedge clk); #1;
            if (dout !== (din ^ 8'h5a)) $fatal(1,"ENVIRONMENT_SIM_FAIL");
        end
        $display("ENVIRONMENT_SIM_PASS: 256 vectors");
        $finish;
    end
endmodule
