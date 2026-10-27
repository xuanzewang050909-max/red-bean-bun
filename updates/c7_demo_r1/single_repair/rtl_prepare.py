from software import *
import re,shutil
rtl=Path('D:/PLD/tmp/single_repair_hls_r1/solution/syn/verilog')
build=Path('D:/PLD/tmp/single_repair_rtl_r2');build.mkdir(exist_ok=False)
src=(rtl/'valley_repair.v').read_text();header=(rtl/'valley_repair_control_s_axi.v').read_text()
params={k:int(eval(v,{'__builtins__':{}},{})) for k,v in re.findall(r'parameter\s+(C_\w+)\s*=\s*([0-9 +/()]+);',src)}
ports=re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',src,re.M)
decl=[];con=[]
for io,width,name in ports:
    if name in ('ap_clk','ap_rst_n'):con.append('.%s(%s)'%(name,'clk' if name=='ap_clk' else 'resetn'));continue
    if width:
        for k in sorted(params,key=len,reverse=True):width=width.replace(k,str(params[k]))
    typ='reg' if io=='input' and name.startswith('s_axi') else 'wire'
    decl.append(f'{typ} {width or ""} {name};');con.append(f'.{name}({name})')
text='`timescale 1ns/1ps\nmodule repair_tb;\nreg clk=0;always #10 clk=~clk;reg resetn=0;\n'+ '\n'.join(decl)+'\n'
text+='valley_repair dut('+','.join(con)+');\n'
mem=Path('D:/PLD/retina_c7_isolated_recovery/hardware/atomic_bridge_bounded/tb_axi_memory.sv')
shutil.copy2(mem,build/'tb_axi_memory.sv')
signals=['ARVALID','ARREADY','ARADDR','ARLEN','ARSIZE','ARBURST','RVALID','RREADY','RDATA','RLAST','RRESP','AWVALID','AWREADY','AWADDR','AWLEN','AWSIZE','AWBURST','WVALID','WREADY','WDATA','WSTRB','WLAST','BVALID','BREADY','BRESP']
text+='integer h,w,n,i,j,op;reg [31:0] v; reg [63:0] cycle=0,start_cycle;wire [63:0] reads,writes,stalls;\nalways @(posedge clk)if(resetn)cycle<=cycle+1;\n'
text+='tb_axi_memory #(.WORDS(1572896)) ram(.clk(clk),.resetn(resetn),.bytes_limit(4*(6*n)),.read_beats(reads),.write_beats(writes),.stall_cycles(stalls),'+','.join('.%s(m_axi_ram_%s)'%(s,s) for s in signals)+');\n'
for n in ['RID','RUSER','BID','BUSER']:text+=f'assign m_axi_ram_{n}=0;\n'
text+='''reg [31:0] golden[0:1572863];string dir;
task wr(input [5:0] address,input [31:0] value,input integer order);
begin
 @(negedge clk);s_axi_control_AWADDR=address;s_axi_control_WDATA=value;s_axi_control_WSTRB=15;
 fork
 begin if(order==1)repeat(3)@(negedge clk);s_axi_control_AWVALID=1;do @(posedge clk);while(!s_axi_control_AWREADY);@(negedge clk);s_axi_control_AWVALID=0;end
 begin if(order==2)repeat(3)@(negedge clk);s_axi_control_WVALID=1;do @(posedge clk);while(!s_axi_control_WREADY);@(negedge clk);s_axi_control_WVALID=0;end
 join
 do @(posedge clk);while(!s_axi_control_BVALID);
 repeat(4)begin @(negedge clk);if(!s_axi_control_BVALID||s_axi_control_BRESP!=0)$fatal(1,"B_BACKPRESSURE");end
 s_axi_control_BREADY=1;@(posedge clk);@(negedge clk);s_axi_control_BREADY=0;
end endtask
task rd(input [5:0] address,output [31:0] value);
begin
 @(negedge clk);s_axi_control_ARADDR=address;s_axi_control_ARVALID=1;s_axi_control_RREADY=0;
 do @(posedge clk);while(!s_axi_control_ARREADY);@(negedge clk);s_axi_control_ARVALID=0;
 do @(posedge clk);while(!s_axi_control_RVALID);value=s_axi_control_RDATA;
 repeat(3)begin @(negedge clk);if(!s_axi_control_RVALID||s_axi_control_RDATA!==value||s_axi_control_RRESP!=0)$fatal(1,"R_BACKPRESSURE");end
 s_axi_control_RREADY=1;@(posedge clk);@(negedge clk);s_axi_control_RREADY=0;
end endtask
task invoke(input integer which,input integer expected_rc);
begin
 wr('h20,which,0);start_cycle=cycle;wr(0,1,0);v=0;
 while((v&2)==0)begin repeat(256)@(posedge clk);rd(0,v);if(cycle-start_cycle>1500000000)$fatal(1,"BOUNDED_CYCLE_LIMIT");end
 rd('h10,v);if(v!=expected_rc)$fatal(1,"RC expected=%0d got=%0d",expected_rc,v);
 $display("OP_DONE op=%0d cycles=%0d read=%0d write=%0d",which,cycle-start_cycle,reads,writes);
end endtask
initial begin
 s_axi_control_AWADDR=0;s_axi_control_AWVALID=0;s_axi_control_WDATA=0;s_axi_control_WSTRB=0;s_axi_control_WVALID=0;s_axi_control_BREADY=0;
 s_axi_control_ARADDR=0;s_axi_control_ARVALID=0;s_axi_control_RREADY=0;
 if(!$value$plusargs("H=%d",h))h=512;if(!$value$plusargs("W=%d",w))w=512;n=h*w;
 if(!$value$plusargs("DIR=%s",dir))$fatal(1,"DIR");
 for(i=0;i<6*n+32;i=i+1)ram.memory[i]=32'hdeadbeef;
 $readmemh({dir,"/input.hex"},ram.memory,0,n-1);$readmemh({dir,"/expected.hex"},golden,0,6*n-1);
 repeat(20)@(negedge clk);resetn=1;repeat(10)@(negedge clk);
 for(j=0;j<3;j=j+1)begin wr('h18,32'h1000+j*16,j);rd('h18,v);if(v!=32'h1000+j*16)$fatal(1,"PTR_READBACK");end
 if(reads!=0 || writes!=0)$fatal(1,"CONTROL_TEST_STARTED_ALGORITHM");
 $display("CONTROL_ORDER_BACKPRESSURE_PASS");
 wr('h18,0,0);wr('h28,h,0);wr('h30,w,0);wr('h38,6*n,0);
 invoke(1,3);if(reads!=0||writes!=0)$fatal(1,"WRONG_PHASE_WRITE");
 invoke(0,0);invoke(1,0);invoke(2,0);for(j=0;j<16;j=j+1)invoke(3,0);invoke(4,0);
 for(i=0;i<6*n;i=i+1)if(ram.memory[i]!==golden[i])$fatal(1,"WORD_DIFFERENCE at=%0d expected=%h got=%h",i,golden[i],ram.memory[i]);
 for(i=6*n;i<6*n+32;i=i+1)if(ram.memory[i]!==32'hdeadbeef)$fatal(1,"GUARD");
 invoke(4,3);
 $display("RTL_FRAME_EXACT h=%0d w=%0d cycles=%0d reads=%0d writes=%0d stalls=%0d",h,w,cycle,reads,writes,stalls);$finish;
end
endmodule
'''
(build/'repair_tb.sv').write_text(text)
for p in rtl.glob('*.dat'):shutil.copy2(p,build/p.name)
for case in ['native','empty','uniform','edges','noise']:
    d=build/case;d.mkdir()
    with np.load(OUT/'integer'/f'{case}.npz') as a:
        np.savetxt(d/'input.hex',a['input'].ravel(),fmt='%08x');np.savetxt(d/'expected.hex',a['memory'].ravel(),fmt='%08x')
(build/'sources.f').write_text('\n'.join(p.as_posix() for p in sorted(rtl.glob('*.v')))+'\n'+(build/'tb_axi_memory.sv').as_posix()+'\n'+(build/'repair_tb.sv').as_posix()+'\n')
(OUT/'integer/rtl_source_binding.json').write_text(json.dumps(dict(HLS_source=hashlib.sha256((Path(__file__).parent/'hardware/repair.cpp').read_bytes()).hexdigest(),top_sha256=hashlib.sha256(src.encode()).hexdigest(),memory_model_sha256=hashlib.sha256(mem.read_bytes()).hexdigest(),clock_ns=20,reset_cycles=20,control='AW/W concurrent and separated both orders, B/R response backpressure; no algorithm start during readback',scope='Actual HLS core, simulated DDR; production fabric separate'),indent=2))
print(build)
