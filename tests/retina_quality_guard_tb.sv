`timescale 1ns/1ps
// Control/observer unit test. The FIFO below is an explicit test surrogate,
// not HLS algorithm RTL and never evidence of medical computation or board FPS.
module retina_quality_guard_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst=0, sv=0, sl=0, mr=0;
    reg [31:0] cfg=0, sd=0, selector=0;
    reg [3:0] sk=15;
    wire sr,mv,ml,hv,hr,rv,rr,start,idle;
    reg done=0,hready=0;
    wire [31:0] md,hd,rd,control,status,observed,saturated;
    wire [3:0] mk;
    retina_quality_guard dut(.aclk(clk),.aresetn(rst),.cfg_control(cfg),.hls_control(control),
        .hls_start(start),.hls_idle(idle),.hls_done(done),.hls_ready(hready),.status_word(status),
        .observe_select(selector),.observe_data(observed),
        .s_axis_tdata(sd),.s_axis_tkeep(sk),.s_axis_tlast(sl),.s_axis_tvalid(sv),.s_axis_tready(sr),
        .m_hls_tdata(hd),.m_hls_tvalid(hv),.m_hls_tready(hr),
        .s_hls_tdata(rd),.s_hls_tvalid(rv),.s_hls_tready(rr),
        .m_axis_tdata(md),.m_axis_tkeep(mk),.m_axis_tlast(ml),.m_axis_tvalid(mv),.m_axis_tready(mr));
    // Same traffic, intentionally tiny counters to force saturation without
    // simulating 2^32 clocks. Production BD must retain COUNTER_WIDTH=32.
    retina_quality_guard #(.COUNTER_WIDTH(8)) overflow_dut(.aclk(clk),.aresetn(rst),.cfg_control(cfg),
        .hls_start(),.hls_control(),.hls_idle(idle),.hls_done(done),.hls_ready(hready),.status_word(),
        .observe_select(selector),.observe_data(saturated),
        .s_axis_tdata(sd),.s_axis_tkeep(sk),.s_axis_tlast(sl),.s_axis_tvalid(sv),.s_axis_tready(),
        .m_hls_tdata(),.m_hls_tvalid(),.m_hls_tready(hr),
        .s_hls_tdata(rd),.s_hls_tvalid(rv),.s_hls_tready(rr),
        .m_axis_tdata(),.m_axis_tkeep(),.m_axis_tlast(),.m_axis_tvalid(),.m_axis_tready(mr));

    reg running=0;
    reg [31:0] fifo[0:7];
    reg [2:0] wp=0,rp=0;
    integer occupancy=0,stub_out=0,stub_n=0;
    assign idle=!running;
    assign hr=running && occupancy<8;
    assign rv=running && occupancy>0;
    assign rd=fifo[rp];
    always @(posedge clk) begin
        if(!rst) begin
            running<=0; done<=0; hready<=0; wp<=0; rp<=0; occupancy<=0; stub_out<=0; stub_n<=0;
        end else begin
            done<=0; hready<=0;
            if(!running && start && !hready) begin
                running<=1; stub_out<=0; stub_n<=control[2]?65536:262144;
            end
            if(hv&&hr) begin fifo[wp]<=hd^control; wp<=wp+1'b1; end
            if(rv&&rr) begin
                rp<=rp+1'b1; stub_out<=stub_out+1;
                if(stub_out==stub_n-1) begin running<=0; done<=1; hready<=1; end
            end
            case({hv&&hr,rv&&rr})
                2'b10: occupancy<=occupancy+1;
                2'b01: occupancy<=occupancy-1;
                default: occupancy<=occupancy;
            endcase
        end
    end

    integer cycle=0, n=0, in_count=0, core_count=0,out_count=0;
    integer first_core=-1,last_valid=-1,last_accept=-1,gaps=0,stalls=0;
    integer frame_cases=0,words_checked=0,frame_serial=0,last_stall=0;
    integer previous_id=0;
    reg [31:0] expected_control=0,previous_control=0;
    reg checking=0,auto_ready=0,was_stalled=0;
    reg [31:0] held_data;
    reg held_last;
    function automatic [31:0] word_at(input integer i);
        word_at=(32'h13579bdf+(i*32'h10201));
    endfunction
    always @(negedge clk) begin
        if(auto_ready) begin
            if(out_count==n-1 && last_stall<40) begin mr=0; last_stall=last_stall+1; end
            else mr=(cycle%4)!=0;
        end
    end
    always @(posedge clk) begin
        cycle=cycle+1;
        if(!rst) was_stalled=0;
        else if(checking) begin
            if(was_stalled && (!mv || md!==held_data || ml!==held_last || mk!==15))
                $fatal(1,"Unstable stalled output");
            was_stalled=mv&&!mr; held_data=md; held_last=ml;
            if(sv&&sr) in_count=in_count+1;
            if(first_core>=0 && core_count<n && !hv) gaps=gaps+1;
            if(first_core>=0 && rv&&!rr) stalls=stalls+1;
            if(hv&&hr) begin
                if(first_core<0) first_core=cycle;
                core_count=core_count+1;
            end
            if(rv && out_count==n-1 && last_valid<0) last_valid=cycle;
            if(mv&&mr) begin
                if(out_count>=n || md!==(word_at(out_count)^expected_control) || mk!==15 || ml!==(out_count==n-1))
                    $fatal(1,"Guard stream mismatch frame=%0d word=%0d cfg=%08x",frame_cases+1,out_count,control);
                if(out_count==n-1) last_accept=cycle;
                out_count=out_count+1; words_checked=words_checked+1;
            end
        end
    end

    task automatic page(input integer index,input [31:0] expected);
        begin
            @(negedge clk); selector=index; #1;
            if(observed!==expected) $fatal(1,"Observer page %0d actual=%08x expected=%08x",index,observed,expected);
        end
    endtask
    task automatic reset_now;
        begin
            @(negedge clk); rst=0; sv=0; mr=0; checking=0; auto_ready=0;
            repeat(5) @(negedge clk); rst=1;
            repeat(5) @(negedge clk);
            previous_id=0; previous_control=0; frame_serial=0;
            if(status!==0 || mv || hv || start) $fatal(1,"Reset did not clear guard");
            page(0,32'h52513231); page(1,0); page(2,0); page(3,0); page(4,0);
            page(5,0); page(6,0); page(7,0); page(8,0); page(9,0); page(10,0); page(11,0);
            page(12,32); page(99,32'hffffffff);
        end
    endtask
    task automatic begin_frame(input [31:0] requested);
        begin
            @(negedge clk);
            cfg=requested; expected_control=requested; n=cfg[2]?65536:262144;
            in_count=0; core_count=0; out_count=0; first_core=-1; last_valid=-1; last_accept=-1;
            gaps=0; stalls=0; last_stall=0; checking=1; auto_ready=1; was_stalled=0;
            frame_serial=frame_serial+1;
        end
    endtask
    task automatic send_frame(input integer corrupt);
        integer k;
        begin
            for(k=0;k<n;k=k+1) begin
                @(negedge clk); sv=1; sd=word_at(k); sk=(corrupt&&k==18)?3:15;
                sl=(k==n-1)||(corrupt&&k==9);
                @(posedge clk); while(!sr) @(posedge clk);
                if(k==128) begin
                    // Invalid/different next configuration must not affect this frame.
                    @(negedge clk); sv=0; cfg=32'hffff00f0;
                    page(2,expected_control); page(3,previous_control); page(4,previous_id);
                    if(control!==expected_control || status[31]) $fatal(1,"Frame parameters not locked");
                end
                if(k%257==63) begin @(negedge clk); sv=0; repeat(3) @(negedge clk); end
            end
            @(negedge clk); sv=0;
        end
    endtask
    task automatic finish_frame;
        begin
            while(out_count!=n || dut.busy || !idle) @(negedge clk);
            repeat(4) @(negedge clk); auto_ready=0;
            if(in_count!=n || core_count!=n || last_accept-last_valid<25 || gaps<=0 || stalls<=0)
                $fatal(1,"Test stimulus did not cover timing boundaries");
            page(1,2); page(2,expected_control); page(3,expected_control); page(4,frame_serial);
            page(5,last_valid-first_core);
            if(saturated!==255) $fatal(1,"Core counter did not saturate");
            page(6,last_accept-first_core);
            if(saturated!==255) $fatal(1,"Drain counter did not saturate");
            page(7,gaps); if(saturated!==((gaps>255)?255:gaps)) $fatal(1,"Gap saturation mismatch");
            page(8,stalls); if(saturated!==((stalls>255)?255:stalls)) $fatal(1,"Stall saturation mismatch");
            page(9,n); page(10,n); page(11,frame_serial); page(1,2);
            if(saturated!==10) $fatal(1,"Saturated snapshot overflow flag missing");
            previous_id=frame_serial; previous_control=expected_control;
            frame_cases=frame_cases+1; checking=0;
            $display("W2_GUARD_FRAME_PASS: frame=%0d words=%0d cfg=%08x core=%0d drain=%0d gaps=%0d stalls=%0d",frame_cases,n,expected_control,last_valid-first_core,last_accept-first_core,gaps,stalls);
        end
    endtask
    initial begin
        reset_now();
        // Illegal threshold and reserved bits cannot start or accept a frame.
        cfg=32'h12340007; sv=1; repeat(8) @(negedge clk);
        if(sr || start || hv || dut.issued_id || !status[31]) $fatal(1,"Zero threshold was not rejected");
        sv=0; reset_now();
        cfg=32'h12341cf7; sv=1; repeat(8) @(negedge clk);
        if(sr || start || hv || dut.issued_id || !status[31]) $fatal(1,"Reserved bits were not rejected");
        sv=0; reset_now();
        $display("W2_GUARD_REJECTION_PASS: no input handshake for threshold zero/reserved bits");
        begin_frame(32'h10010104); send_frame(0); finish_frame(); // A,256,bypass,T1
        begin_frame(32'h1002ff0b); send_frame(0); finish_frame(); // C2,512,final,T255
        begin_frame(32'h10031b0d); send_frame(0); finish_frame(); // C2,256,initial,T27
        begin_frame(32'h10041d06); send_frame(0); finish_frame(); // A,256,closed,T29
        begin_frame(32'h10051c0f); send_frame(1); finish_frame(); // C2,256,final,T28
        if(status!==((3<<28)|(5<<14)|5)) $fatal(1,"Malformed TLAST/TKEEP status changed");
        $display("W2_GUARD_FRAMING_PASS: preserved native counters/TLAST/TKEEP sticky errors");
        begin_frame(32'h20001c0f);
        fork : interrupted_frame
            send_frame(0);
            begin
                wait(mv); @(negedge clk); auto_ready=0; mr=0;
                repeat(12) @(negedge clk);
                if(!mv || !dut.busy) $fatal(1,"No live output to reset");
                rst=0; sv=0; checking=0;
                repeat(5) @(negedge clk);
                disable interrupted_frame;
            end
        join
        reset_now();
        begin_frame(32'hffff1c0f); send_frame(0); finish_frame();
        if(status!==16385) $fatal(1,"Reset recovery has stale frame state");
        $display("W2_GUARD_UNIT_PASS: complete_frames=%0d checked_words=%0d; locked parameters, exact observer clocks, atomic snapshots, saturation, framing and reset; SURROGATE_CORE_ONLY",frame_cases,words_checked);
        $finish;
    end
    initial begin #100000000; $fatal(1,"Guard unit test timeout"); end
endmodule
