`timescale 1ns/1ps
// Verilog-2001 module reference for Vivado 2017.4; diagnostic stage only.
module retina_point_axis (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn" *)
    input wire aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,
    input wire [31:0] cfg_control,
    output reg [31:0] frames_received,
    output reg [31:0] frames_sent,
    output reg [2:0] sticky_errors, // bit0 TLAST; bit1 TKEEP; bit2 reserved mode
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *)
    input wire [3:0] s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input wire s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input wire s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output wire s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output reg [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output reg [3:0] m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output reg m_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output reg m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input wire m_axis_tready,
    output wire [31:0] status_word
);
    `include "contrast_lut.vh"
    reg [31:0] active_control;
    reg [31:0] beat_index;
    reg frame_open;
    wire [31:0] frame_control = frame_open ? active_control : cfg_control;
    wire [31:0] final_index = frame_control[2] ? 32'd65535 : 32'd262143;
    wire [7:0] green = s_axis_tdata[15:8];
    assign s_axis_tready = aresetn && (!m_axis_tvalid || m_axis_tready);
    // AXI GPIO channel 2 exposes sticky errors and modulo-16384 frame counters.
    assign status_word = {1'b0, sticky_errors, frames_sent[13:0], frames_received[13:0]};

    always @(posedge aclk) begin
        if (!aresetn) begin
            m_axis_tdata <= 0;
            m_axis_tkeep <= 0;
            m_axis_tlast <= 0;
            m_axis_tvalid <= 0;
            active_control <= 0;
            beat_index <= 0;
            frame_open <= 0;
            frames_received <= 0;
            frames_sent <= 0;
            sticky_errors <= 0;
        end else begin
            if (m_axis_tvalid && m_axis_tready && m_axis_tlast)
                frames_sent <= frames_sent + 1'b1;
            if (s_axis_tready) begin
                m_axis_tvalid <= s_axis_tvalid;
                if (s_axis_tvalid) begin
                    case (frame_control[1:0])
                        2'd1: m_axis_tdata <= {16'd0, green, green};
                        2'd2: m_axis_tdata <= {16'd0, contrast_lut(green), green};
                        default: m_axis_tdata <= s_axis_tdata;
                    endcase
                    m_axis_tkeep <= s_axis_tkeep;
                    m_axis_tlast <= s_axis_tlast;
                    if (!frame_open) active_control <= cfg_control;
                    if (s_axis_tlast != (beat_index == final_index)) sticky_errors[0] <= 1'b1;
                    if (s_axis_tkeep != 4'b1111) sticky_errors[1] <= 1'b1;
                    if (frame_control[1:0] == 2'd3) sticky_errors[2] <= 1'b1;
                    if (s_axis_tlast) begin
                        frames_received <= frames_received + 1'b1;
                        beat_index <= 0;
                        frame_open <= 0;
                    end else begin
                        // Saturation keeps arbitrarily long malformed packets in error state.
                        if (beat_index != 32'hffffffff) beat_index <= beat_index + 1'b1;
                        frame_open <= 1;
                    end
                end
            end
        end
    end
endmodule
