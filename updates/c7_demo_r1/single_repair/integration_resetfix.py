from software import *
import re, subprocess, shlex, shutil
BUILD=Path('D:/PLD/tmp/single_repair_design_r2');BD=BUILD/'single_repair.srcs/sources_1/bd/single_repair';SIM=BUILD/'sim_export/single_repair/xsim'
BIN=Path('E:/vivado/Vivado/2017.4/bin');DEST=ROOT/'results/single_repair_reset_repair_r1/integration';DEST.mkdir(exist_ok=True)
def call(label,cmd):
    log=Path('D:/PLD')/('single_repair_resetfix_'+label+'.log')
    if log.exists():
        prior=json.loads((DEST/(label+'.json')).read_text())
        assert prior['returncode']==0 and prior['command']==list(map(str,cmd)) and prior['sha256']==hashlib.sha256(log.read_bytes()).hexdigest()
        return log.read_text(errors='replace')
    t=time.perf_counter()
    with log.open('x') as f:p=subprocess.run([str(x) for x in cmd],cwd=SIM,stdout=f,stderr=subprocess.STDOUT)
    (DEST/(label+'.json')).write_text(json.dumps(dict(returncode=p.returncode,seconds=time.perf_counter()-t,command=list(map(str,cmd)),log=str(log),sha256=hashlib.sha256(log.read_bytes()).hexdigest()),indent=2))
    assert p.returncode==0,(label,log)
    return log.read_text(errors='replace')
def main():
    s=(BD/'synth/single_repair.v').read_text();modules={m[1]:m[0] for m in re.finditer(r'\bmodule\s+(\w+)\s*\([\s\S]*?endmodule',s)};top=modules['single_repair']
    def instance(name):
        m=re.search(r'\b(\w+)\s+'+name+r'\s*\(([\s\S]*?)\);',top);assert m,name
        return m[1],dict(re.findall(r'\.(\w+)\(([^()]*)\)',m[2]))
    cm,cp=instance('control_axi');mm,mp=instance('memory_axi');km,kp=instance('repair_0')
    # Verify each actual control and DDR leaf endpoint in the generated top.
    pairs=[]
    for sig in ['AWADDR','AWVALID','AWREADY','WDATA','WSTRB','WVALID','WREADY','BRESP','BVALID','BREADY','ARADDR','ARVALID','ARREADY','RDATA','RRESP','RVALID','RREADY']:
        expected=cp['M00_AXI_'+sig.lower()]+('[5:0]' if sig in ('AWADDR','ARADDR') else '')
        assert expected==kp['s_axi_control_'+sig],sig;pairs.append(['control',sig,expected])
    for key in mp:
        if key.startswith('S00_AXI_'):
            sig=key[8:].upper();k='m_axi_ram_'+sig
            if k in kp:assert mp[key]==kp[k],(key,k);pairs.append(['DDR',sig,mp[key]])
    for m,p in [(cm,cp),(mm,mp),(km,kp)]:
        assert p
    # Generated simulation fabric top and synthesis fabric top must have same actual endpoint expressions.
    sim=(BD/'sim/single_repair.v').read_text()
    for name in ['control_axi','memory_axi','repair_0']:
        block=re.search(r'\b\w+\s+'+name+r'\s*\(([\s\S]*?)\);',sim)[1]
        assert dict(re.findall(r'\.(\w+)\(([^()]*)\)',block))==instance(name)[1]
    decl='\n'.join(re.findall(r'\bwire\s*(?:\[[^\]]+\]\s*)?\w+\s*;',top))
    ctrl='''reg [31:0] s_axi_control_AWADDR=0,s_axi_control_ARADDR=0,s_axi_control_WDATA=0;reg [3:0] s_axi_control_WSTRB=0;
reg s_axi_control_AWVALID=0,s_axi_control_WVALID=0,s_axi_control_BREADY=0,s_axi_control_ARVALID=0,s_axi_control_RREADY=0;
wire s_axi_control_AWREADY,s_axi_control_WREADY,s_axi_control_BVALID,s_axi_control_ARREADY,s_axi_control_RVALID;
wire [31:0] s_axi_control_RDATA;wire [1:0] s_axi_control_RRESP,s_axi_control_BRESP;
'''
    def portlist(mod):return re.findall(r'^\s*(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',modules[mod],re.M)
    def fabric(mod,name,ports):
        con=[]
        for io,width,p in portlist(mod):
            v=ports[p]
            if p.endswith('ACLK'):v='clk'
            # Reset ports retain their exact production-net expressions.
            elif name=='control_axi' and p.startswith('S00_AXI_'):
                sig=p[8:].upper();var='s_axi_control_'+sig
                v=var if re.search(r'\b'+var+r'\b',ctrl) else ('' if io=='output' else "32'd"+str(1 if sig in ['AWBURST','ARBURST','WLAST'] else 2 if sig in ['AWSIZE','ARSIZE'] else 0))
            con.append('.%s(%s)'%(p,v))
        return mod+' '+name+'('+',\n'.join(con)+');\n'
    code='`timescale 1ns/1ps\nmodule integrated_tb;reg clk=0;always #10 clk=~clk;reg ps_resetn=0;wire resetn;\n'+ctrl+decl+'\n'
    rm,rp=instance('reset_50m');om,op=instance('one');zm,zp=instance('zero')
    assert rp['aux_reset_in']==op['dout'] and rp['dcm_locked']==op['dout']
    assert rp['mb_debug_sys_rst']==zp['dout']
    assert rp['ext_reset_in']==instance('ps7_0')[1]['FCLK_RESET0_N']
    for p in [cp,mp]:
        assert p['ARESETN']==rp['interconnect_aresetn']
        assert p['S00_ARESETN']==p['M00_ARESETN']==rp['peripheral_aresetn']
    assert kp['ap_rst_n']==rp['peripheral_aresetn']
    for key,value in cp.items():
        if key.startswith('S00_AXI_'):assert value==instance('ps7_0')[1]['M_AXI_GP0_'+key[8:].upper()]
    code+='assign '+rp['slowest_sync_clk']+'=clk;assign '+rp['ext_reset_in']+'=ps_resetn;assign resetn='+rp['peripheral_aresetn']+';\n'
    # Reuse actual generated reset netlist only after byte identity of all reset
    # source dependencies. r2 modifies external wiring, not this reset IP itself.
    # No substitute reset logic or forced outputs. New routed reset is audited later.
    old_bd=Path('D:/PLD/tmp/single_repair_design_r1/single_repair.srcs/sources_1/bd/single_repair')
    reset_sources=['ip/'+rm+'/synth/'+rm+'.vhd',
        'ipshared/f86a/hdl/proc_sys_reset_v5_0_vh_rfs.vhd',
        'ipshared/cc5f/hdl/lib_cdc_v1_0_rfs.vhd']
    # Resolve the generated CDC dependency by filename rather than assuming its directory hash.
    reset_sources=reset_sources[:2]+[str(next(BD.glob('ipshared/*/hdl/lib_cdc_v1_0_rfs.vhd')).relative_to(BD))]
    for rel in reset_sources:assert (BD/rel).read_bytes()==(old_bd/rel).read_bytes(),rel
    gate=old_bd/'ip'/rm/(rm+'_sim_netlist.v');gate_text=gate.read_text()
    renamed=gate_text.replace(rm,rm+'_gate')
    assert renamed.replace(rm+'_gate',rm)==gate_text
    (SIM/'reset_actual_gate.v').write_text(renamed)
    code+=rm+'_gate reset_50m('+','.join('.%s(%s)'%(p,v) for p,v in rp.items())+');\n'
    for mod,name,ports in [(om,'one',op),(zm,'zero',zp)]:
        code+=mod+' '+name+'('+','.join('.%s(%s)'%(p,v) for p,v in ports.items())+');\n'
    code+=fabric(cm,'control_axi',cp)+fabric(mm,'memory_axi',mp)
    code+=km+' repair_0('+','.join('.%s(%s)'%(p,v) for p,v in kp.items())+');\n'
    memory=Path('D:/PLD/retina_c7_isolated_recovery/hardware/atomic_bridge_bounded/axi_repair_r1/tb_hp0_memory.sv')
    ms=memory.read_text();shutil.copy2(memory,SIM/'tb_hp0_memory.sv')
    ports=re.findall(r'\b(input|output)(?:\s+reg)?(?:\s+\[[^\]]+\])?\s+(\w+)',ms[:ms.index(');')])
    maps={'clk':'clk','resetn':'resetn','reads':'reads','writes':'writes','stalls':'stalls'}
    for io,p in ports:
        if p in maps:continue
        if p in ['ARID','AWID','WID']:
            assert instance('ps7_0')[1]['S_AXI_HP0_'+p]=="{1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}"
            maps[p]="3'b0"
        elif p in ['RID','BID']:
            assert 'M00_AXI_'+p.lower() not in mp and 'S_AXI_HP0_'+p not in instance('ps7_0')[1]
            maps[p]=''
        else:maps[p]=mp['M00_AXI_'+p.lower()]
    code+='wire [63:0] reads,writes,stalls;tb_hp0_memory ram('+','.join('.%s(%s)'%(p,v) for p,v in maps.items())+');\n'
    bench=Path('D:/PLD/tmp/single_repair_rtl_r2/repair_tb.sv').read_text();tasks=bench[bench.index('task wr'):bench.index('initial begin')]
    tasks=tasks.replace('input [5:0] address','input [31:0] address').replace('s_axi_control_AWADDR=address','s_axi_control_AWADDR=32\'h43c00000|address').replace('s_axi_control_ARADDR=address','s_axi_control_ARADDR=32\'h43c00000|address')
    code+='integer i,j,n;reg [31:0] v;reg [63:0] cycle=0,start_cycle;always @(posedge clk)if(resetn)cycle<=cycle+1;\n'+tasks
    code+='''reg [63:0] initmem[0:5498],gold[0:5498];
initial begin
 n=1833;
 $readmemh("input64.hex",initmem);$readmemh("expected64.hex",gold);
 for(i=0;i<5499;i=i+1)ram.memory[i]=initmem[i];
 repeat(200)@(negedge clk);
 if(resetn!==1'b0)$fatal(1,"PRODUCTION_RESET_NOT_ASSERTED");
 ps_resetn=1;repeat(500)@(negedge clk);
 if(resetn!==1'b1)$fatal(1,"PRODUCTION_RESET_NOT_RELEASED");
 $display("PRODUCTION_RESET_RELEASE_PASS actual_generated_reset_netlist=1 clock_ns=20");
 for(j=0;j<3;j=j+1)begin wr('h18,32'h1000+j*16,j);rd('h18,v);if(v!=32'h1000+j*16)$fatal(1,"INTEGRATED_PTR");end
 if(reads!=0||writes!=0)$fatal(1,"PRESTART_DDR");
 $display("INTEGRATED_CONTROL_PASS AW/W/b/r");
 wr('h18,0,0);wr('h28,39,0);wr('h30,47,0);wr('h38,10998,0);
 invoke(1,3);invoke(0,0);invoke(1,0);invoke(2,0);for(j=0;j<16;j=j+1)invoke(3,0);invoke(4,0);
 for(i=0;i<5499;i=i+1)if(ram.memory[i]!==gold[i])$fatal(1,"INTEGRATED_WORD index=%0d got=%h expected=%h",i,ram.memory[i],gold[i]);
 $display("INTEGRATED_NUMERIC_DDR_PASS words=10998 cycles=%0d reads=%0d writes=%0d stalls=%0d",cycle,reads,writes,stalls);$finish;
end
initial begin repeat(20000000)@(posedge clk);$fatal(1,"INTEGRATED_GLOBAL_BOUND");end
endmodule
'''
    (SIM/'integrated_tb.sv').write_text(code)
    with np.load(OUT/'integer/noise.npz') as q:
        mem=q['memory'];init=np.full(mem.size,0xdeadbeef,dtype='uint32');init[:1833]=mem[:1833]
        np.savetxt(SIM/'input64.hex',init.view('uint64'),fmt='%016x');np.savetxt(SIM/'expected64.hex',mem.view('uint64'),fmt='%016x')
    (DEST/'binding.json').write_text(json.dumps(dict(top=str(BD/'synth/single_repair.v'),sha256=hashlib.sha256(s.encode()).hexdigest(),connections=pairs,control=cp,memory=mp,kernel=kp,reset=rp,reset_netlist=dict(path=str(gate),sha256=hashlib.sha256(gate_text.encode()).hexdigest(),reused_unchanged_ip=True,source_byte_identity=reset_sources),boundaries='PS GP0 and HP0 external memory simulated; actual generated r2 control/memory fabrics and wiring, HLS wrappers/RTL, source-identical generated reset netlist',clock_ns=20),indent=2))
    call('int_vlog',[BIN/'xvlog.bat','--relax','-L','smartconnect_v1_0','-L','axi_protocol_checker_v2_0_1','-L','axi_vip_v1_1_1','-L','processing_system7_vip_v1_0_3','-L','xilinx_vip','-prj','vlog.prj'])
    call('int_vhdl',[BIN/'xvhdl.bat','--relax','-prj','vhdl.prj'])
    call('int_tb',[BIN/'xvlog.bat','--sv','--work','xil_defaultlib','integrated_tb.sv','tb_hp0_memory.sv','reset_actual_gate.v','glbl.v'])
    opts=(SIM/'elab.opt').read_text()
    call('int_full_top',[BIN/'xelab.bat',*shlex.split(opts.replace('--snapshot single_repair','--snapshot full_top'))])
    call('int_elab',[BIN/'xelab.bat',*shlex.split(opts.replace('--snapshot single_repair','--snapshot integrated_r2').replace('xil_defaultlib.single_repair','xil_defaultlib.integrated_tb'))])
    result=call('int_sim',[BIN/'xsim.bat','integrated_r2','-runall','-log','integration_sim_r2.log'])
    assert 'PRODUCTION_RESET_RELEASE_PASS' in result and 'INTEGRATED_NUMERIC_DDR_PASS' in result and 'INTEGRATED_CONTROL_PASS' in result and not re.search(r'\b(Fatal|Error|FATAL|ERROR):',result)
    (DEST/'receipt.json').write_text(json.dumps(dict(status='INTEGRATED_SIM_PASS',control_and_numeric=True,actual_reset_chain=True,full_top_elaborated=True,measurement='RTL_SIMULATION',summary=[l for l in result.splitlines() if 'PASS' in l],top_sha256=hashlib.sha256(s.encode()).hexdigest()),indent=2))
    print('INTEGRATED_SIM_PASS')
if __name__=='__main__':main()
