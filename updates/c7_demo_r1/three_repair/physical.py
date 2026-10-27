"""One physical build only after actual complete numerical and integrated gates."""
from identify import *
import subprocess,time
BIN=Path('E:/vivado/Vivado/2017.4/bin');BUILD=Path('D:/PLD/tmp/three_repair_design_r1')
def call(name,tcl):
    log=Path('D:/PLD')/('three_repair_'+name+'.console.log');assert not log.exists()
    cmd=[str(BIN/'vivado.bat'),'-mode','batch','-notrace','-source',str(ROOT/'three_repair/hardware'/tcl),'-log',str(BUILD/(name+'_tool.log')),'-journal',str(BUILD/(name+'.jou'))]
    t=time.perf_counter()
    with log.open('x') as f:p=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    record=dict(returncode=p.returncode,seconds=time.perf_counter()-t,command=cmd,log=ref(log))
    (OUT/(name+'_execution.json')).write_text(json.dumps(record,indent=2));assert p.returncode==0,(name,record)
    return record
def main():
    for r in json.loads((OUT/'implementation_seal.json').read_text())['files']:assert ref(Path(r['path']))==r
    for name,status in [('integer/receipt.json','INTEGER_C_EXACT'),('rtl_receipt.json','RTL_REFERENCE_EXACT'),('integration/receipt.json','INTEGRATED_SIM_PASS')]:
        assert json.loads((OUT/name).read_text())['status']==status
    rtl=json.loads((OUT/'rtl_receipt.json').read_text());assert ref(ROOT/'three_repair/hardware/repair.cpp')==rtl['core']
    assert len(rtl['frames'])==15
    assert not (BUILD/'physical_started').exists()
    (OUT/'physical_budget.json').write_text(json.dumps(dict(attempts_started=1,maximum=3,reason='First selected three-profile core, production50MHz integration',board_operations=0),indent=2))
    call('physical_1','physical.tcl');call('boundary_1','inspect_boundary.tcl')
if __name__=='__main__':main()
