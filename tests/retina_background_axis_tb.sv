`timescale 1ns/1ps
// Reuse the A2 handshake/guard test; M0 golden images are prepared independently.
module retina_background_axis_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst=0,sv=0,sl=0,mr=0;
    reg [31:0] cfg=0,sd=0;
    reg [3:0] sk=15;
    wire sr,mv,ml,hv,hr,rv,rr,start,done,idle,hready;
    wire [31:0] md,hd,rd,control,status;
    wire [3:0] mk;
    retina_gaussian_guard guard(clk,rst,cfg,control,start,idle,done,hready,status,
        sd,sk,sl,sv,sr,hd,hv,hr,rd,rv,rr,md,mk,ml,mv,mr);
    retina_background_hls compute(.ap_clk(clk),.ap_rst_n(rst),.ap_start(start),.ap_done(done),.ap_idle(idle),.ap_ready(hready),
        .control_V(control),.source_V_V_TDATA(hd),.source_V_V_TVALID(hv),.source_V_V_TREADY(hr),
        .result_V_V_TDATA(rd),.result_V_V_TVALID(rv),.result_V_V_TREADY(rr));
    reg [31:0] input_image[0:262143],expected[0:262143];
    integer n=0,read_index=0,checked=0,case_count=0;
    reg active_check=0,random_ready=1,was_stalled=0;
    reg [31:0] held_data;
    reg held_last;
    reg [31:0] ready_rng=32'h621817aa;
    always @(negedge clk) begin
        ready_rng={ready_rng[30:0],ready_rng[31]^ready_rng[21]^ready_rng[1]^ready_rng[0]};
        if(random_ready) mr=ready_rng[0] | ready_rng[1];
    end
    always @(posedge clk) begin
        if(!rst) begin was_stalled=0; read_index=0; end
        else begin
            if(was_stalled && (!mv || md!==held_data || ml!==held_last || mk!==15)) $fatal(1,"Unstable stalled output");
            was_stalled=mv&&!mr; held_data=md; held_last=ml;
            if(mv&&mr) begin
                if(!active_check || read_index>=n) $fatal(1,"Unexpected/extra output");
                if(md!==expected[read_index] || mk!==15 || ml!==(read_index==n-1))
                    $fatal(1,"BACKGROUND mismatch frame=%0d index=%0d actual=%08x expected=%08x last=%0d",case_count,read_index,md,expected[read_index],ml);
                read_index=read_index+1; checked=checked+1;
            end
        end
    end
    task automatic prepare(input integer side,mode,vector_index);
        integer k;
        begin
            n=side*side; read_index=0; active_check=1;
            for(k=0;k<n;k=k+1) begin input_image[k]=32'bx; expected[k]=32'bx; end
            case(vector_index)
                1: begin $readmemh("case_01_input.hex",input_image,0,n-1); $readmemh("case_01_expected.hex",expected,0,n-1); end
                2: begin $readmemh("case_02_input.hex",input_image,0,n-1); $readmemh("case_02_expected.hex",expected,0,n-1); end
                3: begin $readmemh("case_03_input.hex",input_image,0,n-1); $readmemh("case_03_expected.hex",expected,0,n-1); end
                4: begin $readmemh("case_04_input.hex",input_image,0,n-1); $readmemh("case_04_expected.hex",expected,0,n-1); end
                5: begin $readmemh("case_05_input.hex",input_image,0,n-1); $readmemh("case_05_expected.hex",expected,0,n-1); end
                6: begin $readmemh("case_06_input.hex",input_image,0,n-1); $readmemh("case_06_expected.hex",expected,0,n-1); end
                7: begin $readmemh("case_07_input.hex",input_image,0,n-1); $readmemh("case_07_expected.hex",expected,0,n-1); end
                8: begin $readmemh("case_08_input.hex",input_image,0,n-1); $readmemh("case_08_expected.hex",expected,0,n-1); end
                9: begin $readmemh("case_09_input.hex",input_image,0,n-1); $readmemh("case_09_expected.hex",expected,0,n-1); end
                10: begin $readmemh("case_10_input.hex",input_image,0,n-1); $readmemh("case_10_expected.hex",expected,0,n-1); end
                11: begin $readmemh("case_11_input.hex",input_image,0,n-1); $readmemh("case_11_expected.hex",expected,0,n-1); end
                12: begin $readmemh("case_12_input.hex",input_image,0,n-1); $readmemh("case_12_expected.hex",expected,0,n-1); end
                13: begin $readmemh("case_13_input.hex",input_image,0,n-1); $readmemh("case_13_expected.hex",expected,0,n-1); end
                14: begin $readmemh("case_14_input.hex",input_image,0,n-1); $readmemh("case_14_expected.hex",expected,0,n-1); end
                default: $fatal(1,"Unknown vector index");
            endcase
            for(k=0;k<n;k=k+1) if((^input_image[k])===1'bx || (^expected[k])===1'bx) $fatal(1,"Missing/uninitialized vector word case=%0d index=%0d",vector_index,k);
            cfg=mode|((side==256)?4:0);
        end
    endtask
    task automatic send_frame(input integer corrupt);
        integer k;
        begin
            for(k=0;k<n;k=k+1) begin
                @(negedge clk); sv=1; sd=input_image[k]; sk=(corrupt&&k==18)?3:15;
                sl=(k==n-1)||(corrupt&&k==9);
                @(posedge clk); while(!sr) @(posedge clk);
                if(k==128) cfg=cfg^7;
                if((k%257)==0) begin @(negedge clk); sv=0; repeat(3) @(negedge clk); end
            end
            @(negedge clk); sv=0;
        end
    endtask
    task automatic drain;
        begin
            while(read_index!=n || guard.busy || !idle) @(negedge clk);
            repeat(8) @(negedge clk);
            case_count=case_count+1;
            $display("BACKGROUND_AXIS_FRAME_PASS: case=%0d words=%0d status=%08x",case_count,n,status);
            active_check=0;
        end
    endtask
    task automatic reset_now;
        begin
            @(negedge clk); rst=0; sv=0; active_check=0;
            repeat(8) @(negedge clk); rst=1;
            repeat(8) @(negedge clk);
            if(status!==0) $fatal(1,"Guard reset failed");
        end
    endtask
    initial begin
        reset_now();
        prepare(256,0,1); send_frame(0); drain();
        prepare(256,1,2); send_frame(0); drain();
        prepare(256,2,3); send_frame(0); drain();
        prepare(512,3,4); send_frame(0); drain();
        prepare(256,2,5); send_frame(0); drain();
        prepare(256,3,6); send_frame(0); drain();
        prepare(256,2,7); send_frame(0); drain();
        prepare(256,3,8); send_frame(0); drain();
        prepare(512,3,9); send_frame(0); drain();
        prepare(256,2,10); send_frame(0); drain();
        prepare(512,3,11); send_frame(0); drain();
        if(status!==((11<<14)|11)) $fatal(1,"Valid frame counters or errors wrong");
        $display("BACKGROUND_VALID_PASS: 11 frames, all modes, 256/512, borders, STARE, stripes, random stalls, config lock");
        prepare(256,3,12); send_frame(1); drain();
        if(status!==((3<<28)|(12<<14)|12)) $fatal(1,"Malformed TLAST/TKEEP not flagged");
        $display("BACKGROUND_BAD_INPUT_PASS: complete-length early TLAST and partial keep flagged");
        prepare(256,3,13);
        fork : reset_interruption
            send_frame(0);
            begin
                wait(mv); @(negedge clk); random_ready=0; mr=0;
                repeat(40) @(negedge clk);
                if(!mv) $fatal(1,"Output did not stall");
                rst=0; sv=0; active_check=0;
                repeat(8) @(negedge clk);
                disable reset_interruption;
            end
        join
        rst=1; random_ready=1;
        repeat(8) @(negedge clk);
        if(status!==0) $fatal(1,"Active reset state not clear");
        prepare(256,3,14); send_frame(0); drain();
        if(status!==16385) $fatal(1,"Post-reset frame contaminated");
        $display("BACKGROUND_AXIS_SIM_PASS: cases=%0d checked=%0d; generated vendor RTL, full frames, backpressure, reset recovery",case_count,checked);
        $finish;
    end
    initial begin #200000000; $fatal(1,"Background RTL timeout status=%08x in=%0d out=%0d busy=%0d idle=%0d done=%0d",status,guard.input_index,read_index,guard.busy,idle,done); end
endmodule
