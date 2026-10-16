`timescale 1ns/1ps
// Actual Q2 generated RTL plus the W2 atomic control/clock observer.
// Independent original A/C2 golden vectors are reused, never fabricated core outputs.
module retina_q4_refined_axis_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst=0,sv=0,sl=0,mr=0;
    reg [31:0] cfg=0,sd=0;
    reg [3:0] sk=15;
    reg [31:0] selector=0;
    wire [31:0] observed;
    wire sr,mv,ml,hv,hr,rv,rr,start,done,idle,hready;
    wire [31:0] md,hd,rd,control,status;
    wire [3:0] mk;
    retina_refined_guard guard(clk,rst,cfg,control,start,idle,done,hready,status,selector,observed,
        sd,sk,sl,sv,sr,hd,hv,hr,rd,rv,rr,md,mk,ml,mv,mr);
    retina_refined_hls compute(.ap_clk(clk),.ap_rst_n(rst),.ap_start(start),.ap_done(done),.ap_idle(idle),.ap_ready(hready),
        .control_V(control),.source_V_V_TDATA(hd),.source_V_V_TVALID(hv),.source_V_V_TREADY(hr),
        .result_V_V_TDATA(rd),.result_V_V_TVALID(rv),.result_V_V_TREADY(rr));
    reg [31:0] input_image[0:262143],expected[0:262143];
    integer n=0,read_index=0,checked=0,case_count=0;
    reg active_check=0,random_ready=1,was_stalled=0;
    reg [31:0] held_data;
    reg held_last;
    reg [31:0] ready_rng=32'h621817aa;
    integer no_progress_cycles=0;
    integer monitor_cycles=0;
    integer clock_tick=0,first_core_tick=-1,last_core_tick=-1,last_output_tick=-1;
    integer monitor_in=0,monitor_out=0,gap_cycles=0,stall_cycles=0,last_stall_cycles=0;
    integer issued_frames=0;
    reg [31:0] expected_cfg=0;
    always @(posedge clk) begin
        clock_tick=clock_tick+1;
        if(rst && active_check) begin
            if(first_core_tick>=0 && monitor_in<n && !hv) gap_cycles=gap_cycles+1;
            if(first_core_tick>=0 && rv&&!rr) stall_cycles=stall_cycles+1;
            if(hv&&hr) begin
                if(first_core_tick<0) first_core_tick=clock_tick;
                monitor_in=monitor_in+1;
            end
            if(rv && monitor_out==n-1 && last_core_tick<0) last_core_tick=clock_tick;
            if(rv&&rr) begin
                if(monitor_out==n-1) last_output_tick=clock_tick;
                monitor_out=monitor_out+1;
            end
        end
    end
    task automatic check_page(input integer page,input [31:0] expected);
        begin
            @(negedge clk); selector=page; #1;
            if(observed!==expected) $fatal(1,"Actual HLS observer page=%0d value=%08x expected=%08x",page,observed,expected);
        end
    endtask
    // A finite-FIFO deadlock must fail promptly instead of waiting for wall-clock hours.
    always @(posedge clk) begin
        if(!rst || !active_check) no_progress_cycles=0;
        else if((sv&&sr)||(mv&&mr)) no_progress_cycles=0;
        else no_progress_cycles=no_progress_cycles+1;
        if(no_progress_cycles>=10000)
            $fatal(1,"Q2 quality RTL no progress: case=%0d in=%0d out=%0d status=%08x",case_count+1,guard.input_index,read_index,status);
        if(rst && active_check) begin
            monitor_cycles=monitor_cycles+1;
            if((monitor_cycles%500000)==0)
                $display("Q4_REFINED_AXIS_PROGRESS: case=%0d in=%0d out=%0d",case_count+1,guard.input_index,read_index);
        end
    end
    always @(negedge clk) begin
        ready_rng={ready_rng[30:0],ready_rng[31]^ready_rng[21]^ready_rng[1]^ready_rng[0]};
        if(random_ready) begin
            if(read_index==n-1 && last_stall_cycles<64) begin
                mr=0; last_stall_cycles=last_stall_cycles+1;
            end else mr=ready_rng[0] | ready_rng[1];
        end
    end
    always @(posedge clk) begin
        if(!rst) begin was_stalled=0; read_index=0; end
        else begin
            if(was_stalled && (!mv || md!==held_data || ml!==held_last || mk!==15)) $fatal(1,"Unstable stalled output");
            was_stalled=mv&&!mr; held_data=md; held_last=ml;
            if(mv&&mr) begin
                if(!active_check || read_index>=n) $fatal(1,"Unexpected/extra output");
                if(md!==expected[read_index] || mk!==15 || ml!==(read_index==n-1))
                    $fatal(1,"Q4_REFINED mismatch frame=%0d index=%0d actual=%08x expected=%08x last=%0d",case_count,read_index,md,expected[read_index],ml);
                read_index=read_index+1; checked=checked+1;
            end
        end
    end
    task automatic prepare(input integer side,mode,vector_index);
        integer k;
        begin
            n=side*side; read_index=0; active_check=1;
            first_core_tick=-1; last_core_tick=-1; last_output_tick=-1;
            monitor_in=0; monitor_out=0; gap_cycles=0; stall_cycles=0; last_stall_cycles=0;
            issued_frames=issued_frames+1;
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
                15: begin $readmemh("case_15_input.hex",input_image,0,n-1); $readmemh("case_15_expected.hex",expected,0,n-1); end
                16: begin $readmemh("case_16_input.hex",input_image,0,n-1); $readmemh("case_16_expected.hex",expected,0,n-1); end
                17: begin $readmemh("case_17_input.hex",input_image,0,n-1); $readmemh("case_17_expected.hex",expected,0,n-1); end
                18: begin $readmemh("case_18_input.hex",input_image,0,n-1); $readmemh("case_18_expected.hex",expected,0,n-1); end
                default: $fatal(1,"Unknown vector index");
            endcase
            for(k=0;k<n;k=k+1) if((^input_image[k])===1'bx || (^expected[k])===1'bx) $fatal(1,"Missing/uninitialized vector word case=%0d index=%0d",vector_index,k);
            case(vector_index)
                1: cfg=32'h00001c04;
                2: cfg=32'h00001b1d;
                3: cfg=32'h00001d1e;
                4: cfg=32'h00001c03;
                5: cfg=32'h00001c0f;
                6: cfg=32'h00001c0b;
                7: cfg=32'h00001c1b;
                8: cfg=32'h00001c1f;
                9: cfg=32'h00001b1f;
                10: cfg=32'h00001d1b;
                11: cfg=32'h0000011f;
                12: cfg=32'h0000ff1b;
                13: cfg=32'h00001c1c;
                14: cfg=32'h00001c1b;
                15: cfg=32'h00001c1f;
                16: cfg=32'h00001c1f;
                17: cfg=32'h00001c1f;
                18: cfg=32'h00001c1b;
                default:$fatal(1,"Unknown quality control");
            endcase
            cfg=cfg|(vector_index<<16);
            expected_cfg=cfg;
        end
    endtask
    task automatic send_frame(input integer corrupt);
        integer k;
        begin
            for(k=0;k<n;k=k+1) begin
                @(negedge clk); sv=1; sd=input_image[k]; sk=(corrupt&&k==18)?3:15;
                sl=(k==n-1)||(corrupt&&k==9);
                @(posedge clk); while(!sr) @(posedge clk);
                if(k==128) cfg=cfg^32'h0000f80f;
                if((k%257)==0) begin @(negedge clk); sv=0; repeat(3) @(negedge clk); end
            end
            @(negedge clk); sv=0;
        end
    endtask
    task automatic drain;
        begin
            while(read_index!=n || guard.busy || !idle) @(negedge clk);
            repeat(8) @(negedge clk);
            check_page(0,32'h52513531); check_page(1,2);
            check_page(2,expected_cfg); check_page(3,expected_cfg); check_page(4,issued_frames);
            check_page(5,last_core_tick-first_core_tick); check_page(6,last_output_tick-first_core_tick);
            check_page(7,gap_cycles); check_page(8,stall_cycles);
            check_page(9,n); check_page(10,n); check_page(11,issued_frames); check_page(12,32);
            if(monitor_in!=n || monitor_out!=n || last_output_tick-last_core_tick<50)
                $fatal(1,"Actual HLS observer did not exercise last-output backpressure");
            $display("Q4_ACTUAL_HLS_OBSERVER_PASS: words=%0d cfg=%08x core=%0d drain=%0d gaps=%0d stalls=%0d",n,expected_cfg,last_core_tick-first_core_tick,last_output_tick-first_core_tick,gap_cycles,stall_cycles);
            case_count=case_count+1;
            $display("Q4_REFINED_AXIS_FRAME_PASS: case=%0d words=%0d status=%08x",case_count,n,status);
            active_check=0;
        end
    endtask
    task automatic reset_now;
        begin
            @(negedge clk); rst=0; sv=0; active_check=0;
            repeat(8) @(negedge clk); rst=1;
            repeat(8) @(negedge clk);
            issued_frames=0;
            if(status!==0) $fatal(1,"Guard reset failed");
            check_page(1,0); check_page(4,0); check_page(5,0);
        end
    endtask
    initial begin
        reset_now();
        prepare(256,0,1); send_frame(0); drain();
        prepare(256,1,2); send_frame(0); drain();
        prepare(256,2,3); send_frame(0); drain();
        prepare(512,3,4); send_frame(0); drain();
        prepare(256,3,5); send_frame(0); drain();
        prepare(512,3,6); send_frame(0); drain();
        prepare(512,3,7); send_frame(0); drain();
        prepare(256,3,8); send_frame(0); drain();
        prepare(256,1,9); send_frame(0); drain();
        prepare(512,2,10); send_frame(0); drain();
        prepare(256,3,11); send_frame(0); drain();
        prepare(512,3,12); send_frame(0); drain();
        prepare(256,0,13); send_frame(0); drain();
        prepare(512,3,14); send_frame(0); drain();
        prepare(256,3,15); send_frame(0); drain();
        if(status!==((15<<14)|15)) $fatal(1,"Valid frame counters or errors wrong");
        $display("Q4_REFINED_VALID_PASS: 15 frames, A/C2/C5 and thresholds1/27/28/29/255, 256/512, all stages, STARE/bright cross, cfg changes during frame");
        prepare(256,3,16); send_frame(1); drain();
        if(status!==((3<<28)|(16<<14)|16)) $fatal(1,"Malformed TLAST/TKEEP not flagged");
        $display("Q4_REFINED_BAD_INPUT_PASS: complete-length early TLAST and partial keep flagged");
        prepare(256,3,17);
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
        $display("W2_ABORTED_SENDER_STATE: valid=%0d word=%08x",sv,sd);
        // Kill the source thread before clearing its pins and releasing reset.
        sv=0; sl=0; sk=15;
        rst=1; random_ready=1;
        repeat(8) @(negedge clk);
        if(status!==0) $fatal(1,"Active reset state not clear");
        issued_frames=0;
        check_page(1,0); check_page(4,0); check_page(5,0);
        prepare(512,3,18); send_frame(0); drain();
        if(status!==16385) $fatal(1,"Post-reset frame contaminated");
        $display("Q4_REFINED_AXIS_SIM_PASS: cases=%0d checked=%0d; generated vendor RTL, full frames, backpressure, reset recovery",case_count,checked);
        $finish;
    end
    initial begin #400000000; $fatal(1,"Q2 quality RTL timeout status=%08x in=%0d out=%0d busy=%0d idle=%0d done=%0d",status,guard.input_index,read_index,guard.busy,idle,done); end
endmodule
