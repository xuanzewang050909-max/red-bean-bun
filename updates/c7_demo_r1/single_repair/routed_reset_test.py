"""Functional simulation of the reset cell extracted from the actual routed DCP."""
from reset_repair import *
import shutil

def main(mode):
    assert mode in ('old','new')
    net=FIX/'old_routed_reset.v' if mode=='old' else NEW/'routed_reset.v'
    sim=Path('D:/PLD/tmp')/('single_repair_routed_reset_'+mode)
    sim.mkdir(exist_ok=False)
    code='''`timescale 1ns/1ps
module routed_reset_tb;
reg clk=0;always #10 clk=~clk;reg ext_n=0;wire p;
routed_reset dut(.slowest_sync_clk(clk),.ext_reset_in(ext_n),.aux_reset_in(1'bAUX),.mb_debug_sys_rst(1'b0),.dcm_locked(1'b1),.peripheral_aresetn(p));
initial begin
 repeat(200)@(negedge clk);if(p!==1'b0)$fatal(1,"ROUTED_INITIAL_RESET");
 ext_n=1;repeat(500)@(negedge clk);if(p!==1'bRELEASE)$fatal(1,"ROUTED_RELEASE_EXPECTATION");
 ext_n=0;repeat(100)@(negedge clk);if(p!==1'b0)$fatal(1,"ROUTED_REASSERT");
 ext_n=1;repeat(500)@(negedge clk);if(p!==1'bRELEASE)$fatal(1,"ROUTED_SECOND_RELEASE");
 $display("ROUTED_RESET_MODE_PASS MODE released=RELEASE clock_ns=20");$finish;
end
initial begin repeat(2000)@(posedge clk);$fatal(1,"ROUTED_RESET_BOUND");end
endmodule
'''.replace('AUX','0' if mode=='old' else '1').replace('RELEASE','0' if mode=='old' else '1').replace('MODE',mode)
    tb=sim/'routed_reset_tb.sv';tb.write_text(code)
    shutil.copy2(OLD/'sim_export/single_repair/xsim/glbl.v',sim/'glbl.v')
    prefix='routed_'+mode
    run(prefix+'_compile',[BIN/'xvlog.bat','--sv','--work','xil_defaultlib',net,tb,sim/'glbl.v'],sim)
    run(prefix+'_elab',[BIN/'xelab.bat','--relax','-L','unisims_ver','--snapshot','routed_reset_snapshot','xil_defaultlib.routed_reset_tb','xil_defaultlib.glbl'],sim)
    s=run(prefix+'_sim',[BIN/'xsim.bat','routed_reset_snapshot','-runall','-log','routed_reset.log'],sim)
    assert 'ROUTED_RESET_'+mode+'_PASS '+mode+' released='+('0' if mode=='old' else '1') in s and 'Fatal:' not in s
    write(FIX/(prefix+'_receipt.json'),dict(status='ROUTED_RESET_EXPECTATION_VERIFIED',mode=mode,
        actual_routed_cell=ref(net),testbench=ref(tb),released_after_external_reset=(mode=='new'),
        tested_production_output='peripheral_aresetn; optimized unused outputs not claimed',
        clock_ns=20,cycles_limit=2000,simulation='FUNCTIONAL_ROUTED_CELL; no SDF, STA checked separately',board_operations=0))
    print('ROUTED_RESET_EXPECTATION_VERIFIED',mode)

if __name__=='__main__':main(sys.argv[1])
