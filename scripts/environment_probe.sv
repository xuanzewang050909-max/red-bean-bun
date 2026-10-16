// Toolchain smoke test only. This is not a RetinaFPGA algorithm or overlay.
`timescale 1ns/1ps
module environment_probe(input wire clk, input wire [7:0] din,
                         output reg [7:0] dout);
    always @(posedge clk) dout <= din ^ 8'h5a;
endmodule
