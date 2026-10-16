`timescale 1ns/1ps
module retina_gaussian_axis_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst=0,sv=0,sl=0,mr=0;
    reg [31:0] cfg=0,sd=0;
    reg [3:0] sk=15;
    wire sr,mv,ml,hv,hr,rv,rr,start,done,idle,hready;
    wire [31:0] md,hd,rd,control,status;
    wire [3:0] mk;
    retina_gaussian_guard guard(clk,rst,cfg,control,start,idle,done,hready,status,
        sd,sk,sl,sv,sr,hd,hv,hr,rd,rv,rr,md,mk,ml,mv,mr);
    retina_gaussian_hls compute(.ap_clk(clk),.ap_rst_n(rst),.ap_start(start),.ap_done(done),.ap_idle(idle),.ap_ready(hready),
        .control_V(control),.source_V_V_TDATA(hd),.source_V_V_TVALID(hv),.source_V_V_TREADY(hr),
        .result_V_V_TDATA(rd),.result_V_V_TVALID(rv),.result_V_V_TREADY(rr));
    reg [31:0] input_image[0:262143],expected[0:262143];
    integer n=0,read_index=0,checked=0,case_count=0;
    reg active_check=0,random_ready=1,was_stalled=0;
    reg [31:0] held_data;
    reg held_last;
    reg [31:0] ready_rng=32'h621817aa, data_rng=32'h154271b1;
    integer i,j,dy,dx,y,x,yy,xx,g,total,v;
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
                    $fatal(1,"GAUSSIAN mismatch frame=%0d index=%0d actual=%08x expected=%08x last=%0d",case_count,read_index,md,expected[read_index],ml);
                read_index=read_index+1; checked=checked+1;
            end
        end
    end
    task automatic prepare(input integer side,mode,pattern);
        integer k,a,b,wy,wx,s,gold;
        begin
            n=side*side; read_index=0; active_check=1;
            for(k=0;k<n;k=k+1) begin
                a=k/side; b=k%side;
                data_rng=data_rng^(data_rng<<13); data_rng=data_rng^(data_rng>>17); data_rng=data_rng^(data_rng<<5);
                case(pattern)
                    0:g=(b*11+a*17)&255;
                    1:g=data_rng&255;
                    2:g=((b==0||b==side-1||b==side/2)&&(a==0||a==side-1||a==side/2))?255:0;
                    3:g=((a&1)^(b&1))?255:0;
                    4:g=255;
                    default:g=0;
                endcase
                input_image[k]=(((a+b)&1)<<24)|(((k*7)&255)<<16)|(g<<8)|((k*13)&255);
            end
            for(k=0;k<n;k=k+1) begin
                a=k/side; b=k%side; s=0;
                for(wy=-1;wy<=1;wy=wy+1) for(wx=-1;wx<=1;wx=wx+1) begin
                    yy=a+wy; xx=b+wx;
                    if(yy<0)yy=0; if(yy>=side)yy=side-1;
                    if(xx<0)xx=0; if(xx>=side)xx=side-1;
                    s=s+((input_image[yy*side+xx]>>8)&255)*(wy==0?2:1)*(wx==0?2:1);
                end
                gold=(s+8)/16;
                if(mode==1)gold=(input_image[k]>>8)&255;
                if(mode==3) begin gold=(gold*255+96)/192; if(gold>255)gold=255; end
                expected[k]=(mode==0)?input_image[k]:((input_image[k]&32'hff000000)|((input_image[k]>>8)&255)|(gold<<8));
            end
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
                if(k==128) cfg=cfg^7; // Current mode/size must remain locked.
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
            $display("GAUSSIAN_AXIS_FRAME_PASS: case=%0d words=%0d status=%08x",case_count,n,status);
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
        prepare(256,2,0); send_frame(0); drain();
        prepare(512,3,1); send_frame(0); drain();
        prepare(256,2,2); send_frame(0); drain();
        prepare(256,3,3); send_frame(0); drain();
        prepare(256,2,4); send_frame(0); drain();
        prepare(256,0,1); send_frame(0); drain();
        prepare(256,1,0); send_frame(0); drain();
        prepare(256,2,0);
        $readmemh("stare_256_input.hex",input_image,0,65535); $readmemh("stare_256_expected.hex",expected,0,65535);
        send_frame(0); drain();
        prepare(512,3,0);
        $readmemh("stare_512_input.hex",input_image,0,262143); $readmemh("stare_512_expected.hex",expected,0,262143);
        send_frame(0); drain();
        if(status!==((9<<14)|9)) $fatal(1,"Valid frame counters or errors wrong");
        $display("GAUSSIAN_VALID_PASS: 9 frames, all modes, 256/512, corners, STARE, random stalls, config lock");
        prepare(256,2,2); send_frame(1); drain();
        if(status!==((3<<28)|(10<<14)|10)) $fatal(1,"Malformed TLAST/TKEEP not flagged");
        $display("GAUSSIAN_BAD_INPUT_PASS: complete-length early TLAST and partial keep flagged");
        prepare(256,3,1);
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
        prepare(256,3,5); send_frame(0); drain();
        if(status!==16385) $fatal(1,"Post-reset frame contaminated");
        $display("GAUSSIAN_AXIS_SIM_PASS: cases=%0d checked=%0d; generated vendor RTL, full frames, backpressure, reset recovery",case_count,checked);
        $finish;
    end
    initial begin #200000000; $fatal(1,"Gaussian RTL timeout status=%08x in=%0d out=%0d busy=%0d idle=%0d done=%0d",status,guard.input_index,read_index,guard.busy,idle,done); end
endmodule
