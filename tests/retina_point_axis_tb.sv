`timescale 1ns/1ps
module retina_point_axis_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=0;
    reg [31:0] cfg=0;
    reg [31:0] sd=0;
    reg [3:0] sk=15;
    reg sl=0, sv=0, mr=0;
    wire sr, mv, ml;
    wire [31:0] md, received, sent;
    wire [3:0] mk;
    wire [2:0] errors;
    wire [31:0] status;
    retina_point_axis dut(clk,rst,cfg,received,sent,errors,sd,sk,sl,sv,sr,md,mk,ml,mv,mr,status);
    reg [31:0] queue_data[0:15];
    reg [3:0] queue_keep[0:15];
    reg queue_last[0:15];
    integer put=0, get=0, checked=0, incoming=0;
    integer mode_model=0, index_model=0;
    integer received_model=0, sent_model=0;
    reg [2:0] errors_model=0;
    reg [31:0] config_model=0;
    reg model_open=0, was_stalled=0;
    reg [31:0] held_data;
    reg [3:0] held_keep;
    reg held_last;
    reg random_ready=1;
    reg [31:0] lfsr=32'h19427aab;
    integer gray, value, last_index;
    integer cycles=0, first_fast_cycle=0, fast_accepted=0;
    reg fast_active=0;

    // Independent software-like integer formula, not the generated lookup table.
    function automatic [31:0] expected_word(input [31:0] word_in, input integer mode);
        integer g,lut;
        begin
            g=(word_in >> 8) & 255;
            lut=(255*g+96)/192;
            if (lut>255) lut=255;
            case(mode)
                1: expected_word=g | (g<<8);
                2: expected_word=g | (lut<<8);
                default: expected_word=word_in;
            endcase
        end
    endfunction

    always @(negedge clk) begin
        lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        if (random_ready) mr=lfsr[0] | lfsr[1];
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if (!rst) begin
            put=0; get=0; model_open=0; index_model=0; errors_model=0;
            received_model=0; sent_model=0; was_stalled=0;
        end else begin
            if (was_stalled && (!mv || md!==held_data || mk!==held_keep || ml!==held_last))
                $fatal(1,"Output changed during backpressure");
            was_stalled=mv && !mr;
            held_data=md; held_keep=mk; held_last=ml;
            if (mv && mr) begin
                if (get==put) $fatal(1,"Unexpected output");
                if (md!==queue_data[get%16] || mk!==queue_keep[get%16] || ml!==queue_last[get%16])
                    $fatal(1,"Output mismatch at checked word %0d",checked);
                if (ml) sent_model=sent_model+1;
                get=get+1; checked=checked+1;
            end
            if (sv && sr) begin
                if (fast_active) begin
                    if (fast_accepted==0) first_fast_cycle=cycles;
                    else if (cycles-first_fast_cycle!=fast_accepted)
                        $fatal(1,"Throughput dropped below one beat per clock");
                    fast_accepted=fast_accepted+1;
                end
                if (!model_open) config_model=cfg;
                mode_model=config_model & 3;
                queue_data[put%16]=expected_word(sd,mode_model);
                queue_keep[put%16]=sk; queue_last[put%16]=sl;
                put=put+1; incoming=incoming+1;
                if (put-get>15) $fatal(1,"Scoreboard overflow");
                last_index=config_model[2] ? 65535 : 262143;
                if (sl != (index_model==last_index)) errors_model[0]=1;
                if (sk!=15) errors_model[1]=1;
                if (mode_model==3) errors_model[2]=1;
                if (sl) begin
                    received_model=received_model+1; index_model=0; model_open=0;
                end else begin index_model=index_model+1; model_open=1; end
            end
            #1;
            if (received!==received_model || sent!==sent_model || errors!==errors_model)
                $fatal(1,"Frame counters or sticky errors mismatch");
            if(status!=={1'b0,errors_model,sent_model[13:0],received_model[13:0]})
                $fatal(1,"GPIO status packing mismatch");
        end
    end

    task automatic reset_now;
        begin
            @(negedge clk); rst=0; sv=0;
            repeat(3) @(negedge clk);
            rst=1;
        end
    endtask

    task automatic continuous_frame(input integer omit_last);
        integer i;
        begin
            random_ready=0;
            @(negedge clk); cfg=6; mr=1; fast_active=1; fast_accepted=0;
            for(i=0;i<65536;i=i+1) begin
                @(negedge clk); sv=1; sd=(i&255)<<8; sk=15;
                sl=(i==65535) && !omit_last;
                @(posedge clk);
                while (!sr) @(posedge clk);
            end
            @(negedge clk); sv=0; fast_active=0;
            drain();
            if(fast_accepted!=65536) $fatal(1,"Continuous frame lost words");
        end
    endtask
    task automatic send_word(input [31:0] data_in, input last_in, input [3:0] keep_in);
        begin
            @(negedge clk); sd=data_in; sl=last_in; sk=keep_in; sv=1;
            @(posedge clk);
            while (!sr) @(posedge clk);
            @(negedge clk); sv=0;
        end
    endtask
    task automatic drain;
        begin
            @(negedge clk); sv=0;
            while (get!=put) @(negedge clk);
            repeat(2) @(negedge clk);
        end
    endtask
    task automatic frame(input integer words, input [31:0] control, input integer pattern);
        integer i;
        reg [31:0] data_word;
        begin
            @(negedge clk); cfg=control;
            for(i=0;i<words;i=i+1) begin
                // Check all 256 green values repeatedly, plus independent other bytes.
                case(pattern)
                    0: data_word=32'h01000000;
                    1: data_word=32'h01ffffff;
                    default: data_word=((i&1)<<24)|(((i*11)&255)<<16)|((i&255)<<8)|((i*7)&255);
                endcase
                send_word(data_word,i==words-1,15);
                // Change both dimension and mode mid-frame: current frame must hold.
                if(i==127) cfg=control ^ 32'd7;
            end
        end
    endtask

    initial begin
        reset_now();
        frame(65536,32'd6,2); // LUT at 256, all gray values, random backpressure
        frame(65536,32'd5,0); // green, consecutive frame, all black
        frame(262144,32'd2,1); // LUT at 512, all white/saturation
        frame(65536,32'd4,2); // 32-bit bypass
        drain();
        if(errors!==0 || sent!==4) $fatal(1,"Valid frames flagged as erroneous");
        $display("POINT_VALID_FRAMES_PASS: all LUT levels, 256/512, frame configuration latch");
        frame(3,32'd7,2); // reserved mode and early TLAST
        send_word(32'h01902aff,0,4'b0011); // partial keep and missing TLAST
        drain();
        if(errors!==7) $fatal(1,"Malformed packet diagnostics missing");
        $display("POINT_BAD_PACKET_PASS: TLAST/TKEEP/reserved mode are flagged and preserved");

        // Reset with an occupied output register under a hard stall; discard in-flight data.
        random_ready=0; @(negedge clk); mr=0;
        send_word(32'h01556677,0,15);
        repeat(8) @(negedge clk);
        if(!mv || sr) $fatal(1,"Elastic stage did not hold under stall");
        reset_now();
        if(mv || received || sent || errors) $fatal(1,"Reset failed to clear state");
        random_ready=1;
        frame(65536,32'd6,2); drain();
        if(errors || sent!==1) $fatal(1,"Post-reset frame failed");
        continuous_frame(0);
        if(errors || sent!==2) $fatal(1,"Continuous throughput frame failed");
        $display("POINT_CONTINUOUS_PASS: 65536 words accepted on consecutive clocks");
        reset_now(); continuous_frame(1);
        if(errors!==1 || received || sent) $fatal(1,"Missing TLAST not diagnosed");
        send_word(32'h01002200,1,15); drain();
        if(errors!==1 || received!==1 || sent!==1) $fatal(1,"Late TLAST not propagated");
        $display("POINT_MISSING_LATE_TLAST_PASS: malformed packet diagnosed, late last preserved");
        $display("POINT_AXIS_SIM_PASS: checked=%0d accepted=%0d; reset, stalls, counters passed",checked,incoming);
        $finish;
    end
    initial begin #50000000; $fatal(1,"Simulation timeout"); end
endmodule
