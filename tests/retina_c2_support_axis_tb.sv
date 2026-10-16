`timescale 1ns/1ps
// Actual generated RTL probe. Independent vectors contain no GT.
module retina_c2_support_axis_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst=0,start=0,sv=0,mr=0;
    reg [31:0] side=0,sd=0;
    wire sr,mv,done,idle,hready;
    wire [31:0] md;
    retina_c2_support_hls compute(.ap_clk(clk),.ap_rst_n(rst),.ap_start(start),.ap_done(done),.ap_idle(idle),.ap_ready(hready),
        .side_V(side),.source_V_V_TDATA(sd),.source_V_V_TVALID(sv),.source_V_V_TREADY(sr),
        .result_V_V_TDATA(md),.result_V_V_TVALID(mv),.result_V_V_TREADY(mr));
    reg [31:0] input_image[0:262143],expected[0:262143];
    integer n=0,read_index=0,sent=0,case_count=0,full_words=0,total_checked=0;
    integer cycles=0,no_progress=0,stall_left=0;
    reg active=0,was_stalled=0,stall_injected=0;
    reg [31:0] held_data,ready_rng=32'h2c241014;
    always @(negedge clk) begin
        ready_rng={ready_rng[30:0],ready_rng[31]^ready_rng[21]^ready_rng[1]^ready_rng[0]};
        if(!rst) begin mr=0;stall_left=0;end
        else begin
            if(active && n==262144 && read_index>=4096 && !stall_injected) begin stall_left=257;stall_injected=1;end
            if(stall_left>0)begin mr=0;stall_left=stall_left-1;end
            else mr=ready_rng[0]|ready_rng[1];
        end
    end
    always @(posedge clk)begin
        cycles=cycles+1;
        if(start&&hready)begin #1;start=0;end
    end
    always @(posedge clk) begin
        if(!rst)begin was_stalled=0;no_progress=0;end
        else begin
            if(was_stalled && (!mv || md!==held_data)) $fatal(1,"C2 unstable stalled output");
            was_stalled=mv&&!mr;held_data=md;
            if(sv&&sr) sent=sent+1;
            if(mv&&mr)begin
                if(!active || read_index>=n) $fatal(1,"C2 unexpected extra output");
                if(md!==expected[read_index]) $fatal(1,"C2 mismatch vector=%0d pixel=%0d actual=%08x expected=%08x",case_count+1,read_index,md,expected[read_index]);
                read_index=read_index+1;total_checked=total_checked+1;
            end
            if(!active || (sv&&sr) || (mv&&mr))no_progress=0;
            else no_progress=no_progress+1;
            if(no_progress>=10000)$fatal(1,"C2 finite FIFO no progress: case=%0d in=%0d out=%0d",case_count+1,sent,read_index);
        end
    end
    task automatic prepare(input integer size,vector_index);
        integer k;
        begin
            @(negedge clk);side=size;n=size*size;read_index=0;sent=0;active=1;stall_injected=0;
            for(k=0;k<n;k=k+1)begin input_image[k]=32'bx;expected[k]=32'bx;end
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
                19: begin $readmemh("case_19_input.hex",input_image,0,n-1); $readmemh("case_19_expected.hex",expected,0,n-1); end
                20: begin $readmemh("case_20_input.hex",input_image,0,n-1); $readmemh("case_20_expected.hex",expected,0,n-1); end
                21: begin $readmemh("case_21_input.hex",input_image,0,n-1); $readmemh("case_21_expected.hex",expected,0,n-1); end
                22: begin $readmemh("case_22_input.hex",input_image,0,n-1); $readmemh("case_22_expected.hex",expected,0,n-1); end
                23: begin $readmemh("case_23_input.hex",input_image,0,n-1); $readmemh("case_23_expected.hex",expected,0,n-1); end
                24: begin $readmemh("case_24_input.hex",input_image,0,n-1); $readmemh("case_24_expected.hex",expected,0,n-1); end
                25: begin $readmemh("case_25_input.hex",input_image,0,n-1); $readmemh("case_25_expected.hex",expected,0,n-1); end
                26: begin $readmemh("case_26_input.hex",input_image,0,n-1); $readmemh("case_26_expected.hex",expected,0,n-1); end
                27: begin $readmemh("case_27_input.hex",input_image,0,n-1); $readmemh("case_27_expected.hex",expected,0,n-1); end
                28: begin $readmemh("case_28_input.hex",input_image,0,n-1); $readmemh("case_28_expected.hex",expected,0,n-1); end
                29: begin $readmemh("case_29_input.hex",input_image,0,n-1); $readmemh("case_29_expected.hex",expected,0,n-1); end
                30: begin $readmemh("case_30_input.hex",input_image,0,n-1); $readmemh("case_30_expected.hex",expected,0,n-1); end
                31: begin $readmemh("case_31_input.hex",input_image,0,n-1); $readmemh("case_31_expected.hex",expected,0,n-1); end
                32: begin $readmemh("case_32_input.hex",input_image,0,n-1); $readmemh("case_32_expected.hex",expected,0,n-1); end
                33: begin $readmemh("case_33_input.hex",input_image,0,n-1); $readmemh("case_33_expected.hex",expected,0,n-1); end
                34: begin $readmemh("case_34_input.hex",input_image,0,n-1); $readmemh("case_34_expected.hex",expected,0,n-1); end
                35: begin $readmemh("case_35_input.hex",input_image,0,n-1); $readmemh("case_35_expected.hex",expected,0,n-1); end
                36: begin $readmemh("case_36_input.hex",input_image,0,n-1); $readmemh("case_36_expected.hex",expected,0,n-1); end
                37: begin $readmemh("case_37_input.hex",input_image,0,n-1); $readmemh("case_37_expected.hex",expected,0,n-1); end
                38: begin $readmemh("case_38_input.hex",input_image,0,n-1); $readmemh("case_38_expected.hex",expected,0,n-1); end
                39: begin $readmemh("case_39_input.hex",input_image,0,n-1); $readmemh("case_39_expected.hex",expected,0,n-1); end
                40: begin $readmemh("case_40_input.hex",input_image,0,n-1); $readmemh("case_40_expected.hex",expected,0,n-1); end
                41: begin $readmemh("case_41_input.hex",input_image,0,n-1); $readmemh("case_41_expected.hex",expected,0,n-1); end
                42: begin $readmemh("case_42_input.hex",input_image,0,n-1); $readmemh("case_42_expected.hex",expected,0,n-1); end
                43: begin $readmemh("case_43_input.hex",input_image,0,n-1); $readmemh("case_43_expected.hex",expected,0,n-1); end
                44: begin $readmemh("case_44_input.hex",input_image,0,n-1); $readmemh("case_44_expected.hex",expected,0,n-1); end
                45: begin $readmemh("case_45_input.hex",input_image,0,n-1); $readmemh("case_45_expected.hex",expected,0,n-1); end
                46: begin $readmemh("case_46_input.hex",input_image,0,n-1); $readmemh("case_46_expected.hex",expected,0,n-1); end
                47: begin $readmemh("case_47_input.hex",input_image,0,n-1); $readmemh("case_47_expected.hex",expected,0,n-1); end
                default: $fatal(1,"C2 unknown vector");
            endcase
            for(k=0;k<n;k=k+1)if((^input_image[k])===1'bx||(^expected[k])===1'bx)$fatal(1,"C2 missing vector pixel %0d",k);
            start=1;
        end
    endtask
    task automatic send_frame;
        integer k;
        begin
            for(k=0;k<n;k=k+1)begin
                @(negedge clk);sv=1;sd=input_image[k];
                @(posedge clk);while(!sr)@(posedge clk);
                if(k%257==0)begin @(negedge clk);sv=0;repeat(3)@(negedge clk);end
            end
            @(negedge clk);sv=0;
        end
    endtask
    task automatic drain;
        integer first_cycle;
        begin
            first_cycle=cycles;
            while(read_index!=n||!idle||start)@(negedge clk);
            repeat(8)@(negedge clk);
            if(sent!=n)$fatal(1,"C2 wrong input count");
            case_count=case_count+1;full_words=full_words+n;active=0;
            $display("C2_SUPPORT_RTL_FRAME_PASS: frame=%0d side=%0d words=%0d drain_cycles=%0d",case_count,side,n,cycles-first_cycle);
        end
    endtask
    task automatic run_frame(input integer size,vector_index);
        begin prepare(size,vector_index);send_frame();drain();end
    endtask
    task automatic reset_now;
        begin
            @(negedge clk);rst=0;sv=0;start=0;active=0;
            repeat(8)@(negedge clk);rst=1;
            repeat(8)@(negedge clk);
            if(!idle)$fatal(1,"C2 reset did not become idle");
        end
    endtask
    initial begin
        reset_now();
        if($test$plusargs("RESET_ONLY"))run_frame(32,1);
        else begin
        run_frame(32,1);
        run_frame(32,2);
        run_frame(32,3);
        run_frame(32,4);
        run_frame(32,5);
        run_frame(32,6);
        run_frame(32,7);
        run_frame(32,8);
        run_frame(32,9);
        run_frame(32,10);
        run_frame(32,11);
        run_frame(32,12);
        run_frame(32,13);
        run_frame(32,14);
        run_frame(32,15);
        run_frame(32,16);
        run_frame(32,17);
        run_frame(32,18);
        run_frame(32,19);
        run_frame(32,20);
        run_frame(32,21);
        run_frame(32,22);
        run_frame(256,23);
        run_frame(512,24);
        run_frame(256,25);
        run_frame(512,26);
        run_frame(32,27);
        run_frame(256,28);
        run_frame(512,29);
        run_frame(256,30);
        run_frame(512,31);
        run_frame(256,32);
        run_frame(512,33);
        run_frame(256,34);
        run_frame(512,35);
        run_frame(256,36);
        run_frame(512,37);
        run_frame(256,38);
        run_frame(512,39);
        run_frame(256,40);
        run_frame(512,41);
        run_frame(256,42);
        run_frame(512,43);
        run_frame(256,44);
        run_frame(512,45);
        run_frame(256,46);
        run_frame(512,47);
        if(case_count!=47 || full_words!=3955712)$fatal(1,"C2 missing complete cases");
        end
        prepare(256,23);
        fork : interrupted
            send_frame();
            begin
                wait(mv);@(negedge clk);stall_left=64;
                repeat(20)@(negedge clk);
                if(!mv)$fatal(1,"C2 reset probe output not stalled");
                rst=0;sv=0;start=0;active=0;
                repeat(8)@(negedge clk);
                disable interrupted;
            end
        join
        // The interrupted sender can drive TVALID again during synchronous reset.
        // Clear the source only AFTER that concurrent sender has been disabled.
        $display("C2_RESET_ABORTED_SENDER_STATE: valid=%0d word=%08x",sv,sd);
        sv=0;start=0;
        rst=1;repeat(8)@(negedge clk);
        if(!idle)$fatal(1,"C2 active reset did not become idle");
        run_frame(256,23);
        if($test$plusargs("RESET_ONLY"))begin
            run_frame(512,24);
            if(case_count!=3||full_words!=328704)$fatal(1,"C2 focused reset coverage missing");
            $display("C2_SUPPORT_RESET_FOCUS_PASS: full_frames=%0d full_words=%0d total_checked=%0d; identical generated RTL, source quiesced after abort",case_count,full_words,total_checked);
            $finish;
        end
        if(case_count!=48||full_words!=4021248)$fatal(1,"C2 recovery frame missing");
        $display("C2_SUPPORT_AXIS_SIM_PASS: full_frames=%0d full_words=%0d total_checked=%0d; generated RTL, finite FIFO, random gaps/backpressure, 257-cycle stalls, active reset recovery",case_count,full_words,total_checked);
        $finish;
    end
    initial begin #400000000; $fatal(1,"C2 RTL timeout in=%0d out=%0d",sent,read_index); end
endmodule
