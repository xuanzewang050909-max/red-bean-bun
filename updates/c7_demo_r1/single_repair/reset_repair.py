"""Offline reset reproduction and bounded second-build preparation. No board API."""
from software import *
import subprocess, shlex

FIX=ROOT/'results/single_repair_reset_repair_r1'
OLD=Path('D:/PLD/tmp/single_repair_design_r1')
NEW=Path('D:/PLD/tmp/single_repair_design_r2')
BIN=Path('E:/vivado/Vivado/2017.4/bin')

def ref(p):
    p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def write(p,x):
    with Path(p).open('x',encoding='utf8') as f:json.dump(x,f,indent=2,ensure_ascii=False)

def run(label,args,cwd):
    log=Path('D:/PLD')/('single_repair_resetfix_'+label+'.log')
    assert not log.exists()
    t=time.perf_counter()
    with log.open('x') as f:p=subprocess.run(list(map(str,args)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
    write(FIX/(label+'.json'),dict(command=list(map(str,args)),returncode=p.returncode,seconds=time.perf_counter()-t,log=ref(log)))
    assert p.returncode==0,log
    return log.read_text(errors='replace')

def reproduce():
    FIX.mkdir(exist_ok=False)
    sim=OLD/'sim_export/single_repair/xsim'
    bd=OLD/'single_repair.srcs/sources_1/bd/single_repair'
    reset=bd/'ip/single_repair_reset_50m_0/synth/single_repair_reset_50m_0.vhd'
    assert "C_AUX_RESET_HIGH => '0'" in reset.read_text()
    write(FIX/'source_binding.json',dict(parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        user_fact='重启或断电过板卡',old_volatile_scene='UNAVAILABLE_AFTER_REBOOT; do not read old physical addresses',
        old_zip=ref('C:/Users/Gabriel/Downloads/single_image_existing_a980b3cb.zip'),
        old_top=ref(bd/'synth/single_repair.v'),old_reset=ref(reset),old_hwh=ref(bd/'hw_handoff/single_repair.hwh'),
        frozen_core=ref(ROOT/'single_repair/hardware/repair.cpp'),frozen_algorithm=ref(OUT/'frozen_algorithm.json'),
        frozen_output=ref(OUT/'selected/arrays.npz'),hardware_operations=0))
    tb='''`timescale 1ns/1ps
module reset_repro_tb;
reg clk=0;always #10 clk=~clk;
reg ext_n=0;wire old_p,old_i,new_p,new_i;
single_repair_reset_50m_0 old_reset(.slowest_sync_clk(clk),.ext_reset_in(ext_n),.aux_reset_in(1'b0),.mb_debug_sys_rst(1'b0),.dcm_locked(1'b1),.peripheral_aresetn(old_p),.interconnect_aresetn(old_i));
single_repair_reset_50m_0 fixed_reset(.slowest_sync_clk(clk),.ext_reset_in(ext_n),.aux_reset_in(1'b1),.mb_debug_sys_rst(1'b0),.dcm_locked(1'b1),.peripheral_aresetn(new_p),.interconnect_aresetn(new_i));
initial begin
repeat(200)@(negedge clk);
if({old_p,old_i,new_p,new_i}!==4'b0000)$fatal(1,"INITIAL_RESET_ASSERTION");
ext_n=1;repeat(500)@(negedge clk);
if({old_p,old_i}!==2'b00)$fatal(1,"OLD_RESET_NOT_HELD");
if({new_p,new_i}!==2'b11)$fatal(1,"FIXED_RESET_NOT_RELEASED");
$display("RESET_DEFECT_REPRODUCED old_aux0_held=1 fixed_aux1_released=1 clock_ns=20 release_wait_cycles=500");
ext_n=0;repeat(100)@(negedge clk);
if({new_p,new_i}!==2'b00)$fatal(1,"EXTERNAL_RESET_ASSERTION");
ext_n=1;repeat(500)@(negedge clk);
if({new_p,new_i}!==2'b11)$fatal(1,"SECOND_RELEASE");
$display("ACTUAL_RESET_IP_REASSERT_RELEASE_PASS");$finish;
end
initial begin repeat(2000)@(posedge clk);$fatal(1,"RESET_TEST_BOUND");end
endmodule
'''
    p=sim/'reset_repro_tb.sv';assert not p.exists();p.write_text(tb)
    run('repro_compile',[BIN/'xvlog.bat','--sv','--work','xil_defaultlib',p.name],sim)
    opts=(sim/'elab.opt').read_text().replace('--snapshot single_repair','--snapshot reset_repro').replace('xil_defaultlib.single_repair','xil_defaultlib.reset_repro_tb').replace('elaborate.log','reset_repro_elab.log')
    run('repro_elab',[BIN/'xelab.bat',*shlex.split(opts)],sim)
    result=run('repro_sim',[BIN/'xsim.bat','reset_repro','-runall','-log','reset_repro_sim.log'],sim)
    assert 'RESET_DEFECT_REPRODUCED' in result and 'ACTUAL_RESET_IP_REASSERT_RELEASE_PASS' in result and 'Fatal:' not in result
    write(FIX/'reset_reproduction.json',dict(status='ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED',clock_ns=20,
        original_aux_polarity='ACTIVE_LOW',original_aux_constant=0,fixed_aux_constant=1,
        testbench=ref(p),simulation_only=True,model_forwards=0,board_operations=0,
        limitation='Live board bus response unavailable after reboot; this confirms a sufficient offline integration defect, not a recovered live trace.'))
    print('ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED')

def gate_reproduce():
    """Use the generated functional netlist (Verilog primitives/glbl), not a reset stub.

    The earlier mixed-language behavioral trial is retained as a failed test.
    This path does not change its assertions or overwrite its evidence.
    """
    sim=OLD/'sim_export/single_repair/xsim'
    s=(sim/'reset_repro_tb.sv').read_text().replace('module reset_repro_tb','module reset_repro_gate_tb')
    s=s.replace('if({old_p,old_i,new_p,new_i}', '$display("INITIAL old=%b%b new=%b%b",old_p,old_i,new_p,new_i);\nif({old_p,old_i,new_p,new_i}')
    p=sim/'reset_repro_gate_tb.sv'
    net=OLD/'single_repair.srcs/sources_1/bd/single_repair/ip/single_repair_reset_50m_0/single_repair_reset_50m_0_sim_netlist.v'
    # Existing commands may be sealed after their successful execution; never rerun.
    if p.exists():
        assert p.read_text()==s
        for label in ['gate_compile','gate_elab','gate_sim']:
            r=json.loads((FIX/(label+'.json')).read_text());assert r['returncode']==0 and ref(r['log']['path'])==r['log']
        result=Path(json.loads((FIX/'gate_sim.json').read_text())['log']['path']).read_text()
    else:
        p.write_text(s)
        run('gate_compile',[BIN/'xvlog.bat','--sv','--work','reset_repro_lib',str(net),str(p),'glbl.v'],sim)
        run('gate_elab',[BIN/'xelab.bat','--relax','--debug','typical','-L','unisims_ver','--snapshot','reset_repro_gate','reset_repro_lib.reset_repro_gate_tb','reset_repro_lib.glbl'],sim)
        result=run('gate_sim',[BIN/'xsim.bat','reset_repro_gate','-runall','-log','reset_repro_gate_sim.log'],sim)
    assert 'RESET_DEFECT_REPRODUCED' in result and 'ACTUAL_RESET_IP_REASSERT_RELEASE_PASS' in result and 'Fatal:' not in result
    write(FIX/'reset_reproduction.json',dict(status='ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED',clock_ns=20,
        original_aux_polarity='ACTIVE_LOW',original_aux_constant=0,fixed_aux_constant=1,
        testbench=ref(p),actual_generated_functional_netlist=ref(net),simulation_only=True,model_forwards=0,board_operations=0,
        retained_failure='repro_sim: mixed-language behavioral initial reset assertion; functional primitive netlist passes unchanged assertions',
        limitation='Live board bus state unavailable after reboot. Reproduced sufficient design defect, not recovered live trace.'))
    print('ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='gate':gate_reproduce()
    else:reproduce()
