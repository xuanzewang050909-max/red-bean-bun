`timescale 1ns/1ps
// A1 frame/register semantics adapted for the vendor ap_ctrl_hs frame engine.
// HLS consumes/produces exactly N words; frame TLAST is checked/regenerated here.
module retina_gaussian_guard (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK",
       X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXIS:M_HLS:S_HLS:M_AXIS, ASSOCIATED_RESET aresetn" *)
    input wire aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
    input wire aresetn,
    input wire [31:0] cfg_control,
    output reg [31:0] hls_control,
    output reg hls_start,
    input wire hls_idle,
    input wire hls_done,
    input wire hls_ready,
    output wire [31:0] status_word,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TDATA" *) input wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *) input wire [3:0] s_axis_tkeep,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TLAST" *) input wire s_axis_tlast,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TVALID" *) input wire s_axis_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS TREADY" *) output wire s_axis_tready,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_HLS TDATA" *) output reg [31:0] m_hls_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_HLS TVALID" *) output reg m_hls_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_HLS TREADY" *) input wire m_hls_tready,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_HLS TDATA" *) input wire [31:0] s_hls_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_HLS TVALID" *) input wire s_hls_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_HLS TREADY" *) output wire s_hls_tready,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TDATA" *) output wire [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *) output wire [3:0] m_axis_tkeep,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TLAST" *) output wire m_axis_tlast,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TVALID" *) output wire m_axis_tvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 M_AXIS TREADY" *) input wire m_axis_tready
);
    reg busy, input_complete, output_complete, done_seen, running_seen;
    reg [17:0] input_index, output_index;
    reg [13:0] received, sent;
    reg [2:0] errors;
    wire [31:0] frame_control=busy ? hls_control : cfg_control;
    wire [17:0] final_input=frame_control[2] ? 18'd65535 : 18'd262143;
    wire [17:0] final_output=hls_control[2] ? 18'd65535 : 18'd262143;
    assign status_word={1'b0,errors,sent,received};
    assign s_axis_tready=aresetn && (busy ? !input_complete : hls_idle) && (!m_hls_tvalid || m_hls_tready);
    assign m_axis_tdata=s_hls_tdata;
    assign m_axis_tkeep=4'b1111;
    assign m_axis_tlast=(output_index==final_output);
    assign m_axis_tvalid=aresetn && busy && !output_complete && s_hls_tvalid;
    assign s_hls_tready=aresetn && busy && !output_complete && m_axis_tready;

    always @(posedge aclk) begin
        if(!aresetn) begin
            busy<=0; input_complete<=0; output_complete<=0; done_seen<=0; running_seen<=0;
            hls_start<=0; hls_control<=0; m_hls_tvalid<=0; m_hls_tdata<=0;
            input_index<=0; output_index<=0; received<=0; sent<=0; errors<=0;
        end else begin
            // The DATAFLOW engine must see START until all input tasks accept it.
            // A one-clock pulse can start parameter setup but strand the reader.
            if(hls_start && hls_ready) hls_start<=0;
            if(busy && !hls_idle) running_seen<=1;
            if(busy && running_seen && hls_done) done_seen<=1;
            if(busy && output_complete && (done_seen || (running_seen && hls_done))) begin
                busy<=0; input_complete<=0; output_complete<=0; done_seen<=0; running_seen<=0;
            end
            if(m_hls_tvalid && m_hls_tready) m_hls_tvalid<=0;
            if(s_axis_tvalid && s_axis_tready) begin
                m_hls_tdata<=s_axis_tdata; m_hls_tvalid<=1;
                if(!busy) begin
                    hls_control<=cfg_control; busy<=1; hls_start<=1;
                    done_seen<=0; running_seen<=0;
                end
                if(s_axis_tlast != (input_index==final_input)) errors[0]<=1;
                if(s_axis_tkeep != 4'b1111) errors[1]<=1;
                if(input_index==final_input) begin
                    input_index<=0; input_complete<=1; received<=received+1'b1;
                end else input_index<=input_index+1'b1;
            end
            if(m_axis_tvalid && m_axis_tready) begin
                if(m_axis_tlast) begin
                    output_index<=0; output_complete<=1; sent<=sent+1'b1;
                end else output_index<=output_index+1'b1;
            end
            if(s_hls_tvalid && (!busy || output_complete)) errors[2]<=1;
        end
    end
endmodule
