`timescale 1ns/1ps
// Derived from board-verified retina_gaussian_guard; unchanged stream framing.
// W2 ABI v1 adds valid frame configuration and completed-frame clock snapshots.
// No AXI slave is reimplemented: observe_select/data connect to standard AXI GPIO.
module retina_quality_guard #(parameter COUNTER_WIDTH=32) (
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
    input wire [31:0] observe_select,
    output reg [31:0] observe_data,
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
    reg cfg_rejected;
    // Stage[1:0], side256[2], C2[3], reserved[7:4]=0, T[15:8]=1..255,
    // user frame tag[31:16]. Parameters are latched on the first input handshake.
    wire cfg_valid=(cfg_control[15:8]!=0) && (cfg_control[7:4]==0);
    reg [31:0] issued_id, completed_id, completed_control;
    reg completed_valid, completed_overflow;
    reg measuring, core_seen, core_input_complete, live_overflow;
    reg [18:0] core_words, completed_input_words, completed_output_words;
    reg [COUNTER_WIDTH-1:0] elapsed, core_elapsed, input_gaps, output_stalls;
    reg [31:0] completed_core, completed_drain, completed_gaps, completed_stalls;
    localparam [COUNTER_WIDTH-1:0] COUNTER_MAX={COUNTER_WIDTH{1'b1}};
    wire [COUNTER_WIDTH-1:0] next_elapsed=(elapsed==COUNTER_MAX) ? elapsed : elapsed+1'b1;
    wire [COUNTER_WIDTH-1:0] next_gaps=(input_gaps==COUNTER_MAX) ? input_gaps : input_gaps+1'b1;
    wire [COUNTER_WIDTH-1:0] next_stalls=(output_stalls==COUNTER_MAX) ? output_stalls : output_stalls+1'b1;
    wire gap_event=measuring && !core_input_complete && !m_hls_tvalid;
    wire stall_event=measuring && s_hls_tvalid && !s_hls_tready;
    wire counter_overflow=measuring && ((elapsed==COUNTER_MAX) ||
                            (gap_event && input_gaps==COUNTER_MAX) ||
                            (stall_event && output_stalls==COUNTER_MAX));

    // All completed pages are updated together at the final output handshake.
    // Read completed_id before and after a multi-register read to detect a new frame.
    always @* begin
        case(observe_select)
            0: observe_data=32'h52513231; // RQ21 identity, ABI version 1
            1: observe_data={24'd0,4'd0,completed_overflow,cfg_rejected,completed_valid,busy};
            2: observe_data=hls_control;
            3: observe_data=completed_control;
            4: observe_data=completed_id;
            5: observe_data=completed_core;
            6: observe_data=completed_drain;
            7: observe_data=completed_gaps;
            8: observe_data=completed_stalls;
            9: observe_data={13'd0,completed_input_words};
            10: observe_data={13'd0,completed_output_words};
            11: observe_data=issued_id;
            12: observe_data=COUNTER_WIDTH;
            default: observe_data=32'hffffffff;
        endcase
    end

    always @(posedge aclk) begin
        if(!aresetn) begin
            issued_id<=0; completed_id<=0; completed_control<=0;
            completed_valid<=0; completed_overflow<=0;
            measuring<=0; core_seen<=0; core_input_complete<=0; live_overflow<=0;
            core_words<=0; completed_input_words<=0; completed_output_words<=0;
            elapsed<=0; core_elapsed<=0; input_gaps<=0; output_stalls<=0;
            completed_core<=0; completed_drain<=0; completed_gaps<=0; completed_stalls<=0;
        end else begin
            if(!busy && s_axis_tvalid && s_axis_tready) begin
                issued_id<=issued_id+1'b1;
                measuring<=0; core_seen<=0; core_input_complete<=0; live_overflow<=0;
                core_words<=0; elapsed<=0; core_elapsed<=0; input_gaps<=0; output_stalls<=0;
            end
            // Core boundary is the HLS input handshake, not the earlier DMA/guard input.
            if(m_hls_tvalid && m_hls_tready) begin
                if(!measuring) begin measuring<=1; elapsed<=0; end
                core_words<=core_words+1'b1;
                if(core_words=={1'b0,final_output}) core_input_complete<=1;
            end
            if(measuring) begin
                elapsed<=next_elapsed;
                if(gap_event) input_gaps<=next_gaps;
                if(stall_event) output_stalls<=next_stalls;
                if(counter_overflow) live_overflow<=1;
                if(!core_seen && s_hls_tvalid && output_index==final_output) begin
                    core_elapsed<=next_elapsed;
                    core_seen<=1;
                end
            end
            if(m_axis_tvalid && m_axis_tready && m_axis_tlast) begin
                measuring<=0;
                completed_valid<=1;
                completed_id<=issued_id;
                completed_control<=hls_control;
                completed_core<=core_seen ? core_elapsed : next_elapsed;
                completed_drain<=next_elapsed;
                completed_gaps<=gap_event ? next_gaps : input_gaps;
                completed_stalls<=stall_event ? next_stalls : output_stalls;
                completed_input_words<=core_words+((m_hls_tvalid && m_hls_tready)?1'b1:1'b0);
                completed_output_words<={1'b0,final_output}+1'b1;
                completed_overflow<=live_overflow || counter_overflow;
            end
        end
    end
    wire [31:0] frame_control=busy ? hls_control : cfg_control;
    wire [17:0] final_input=frame_control[2] ? 18'd65535 : 18'd262143;
    wire [17:0] final_output=hls_control[2] ? 18'd65535 : 18'd262143;
    assign status_word={cfg_rejected,errors,sent,received};
    assign s_axis_tready=aresetn && (busy ? !input_complete : (hls_idle && cfg_valid)) && (!m_hls_tvalid || m_hls_tready);
    assign m_axis_tdata=s_hls_tdata;
    assign m_axis_tkeep=4'b1111;
    assign m_axis_tlast=(output_index==final_output);
    assign m_axis_tvalid=aresetn && busy && !output_complete && s_hls_tvalid;
    assign s_hls_tready=aresetn && busy && !output_complete && m_axis_tready;

    always @(posedge aclk) begin
        if(!aresetn) begin
            busy<=0; input_complete<=0; output_complete<=0; done_seen<=0; running_seen<=0;
            hls_start<=0; hls_control<=0; m_hls_tvalid<=0; m_hls_tdata<=0;
            input_index<=0; output_index<=0; received<=0; sent<=0; errors<=0; cfg_rejected<=0;
        end else begin
            if(!busy && s_axis_tvalid && !cfg_valid) cfg_rejected<=1;
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
