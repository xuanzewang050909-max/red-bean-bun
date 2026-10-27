"""Second physical build, only after repaired production-reset integration passes."""
from reset_repair import *

def main():
    r=json.loads((FIX/'integration/receipt.json').read_text())
    assert r['status']=='INTEGRATED_SIM_PASS' and r['actual_reset_chain']
    assert json.loads((FIX/'reset_reproduction.json').read_text())['status']=='ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED'
    source=json.loads((FIX/'source_binding.json').read_text())
    for k in ['frozen_core','frozen_algorithm','frozen_output']:assert ref(source[k]['path'])==source[k]
    assert json.loads((OUT/'rtl_receipt.json').read_text())['status']=='RTL_REFERENCE_EXACT'
    assert not (NEW/'physical_started').exists()
    run('physical_2',[BIN/'vivado.bat','-mode','batch','-notrace','-source',ROOT/'single_repair/hardware/physical_r2.tcl',
        '-log','D:/PLD/tmp/single_repair_physical2_tool.log','-journal','D:/PLD/tmp/single_repair_physical2.jou'],ROOT)
    write(FIX/'physical_attempt_2.json',dict(physical_builds_total=2,physical_build_limit=3,
        reason='Correct permanently asserted active-low auxiliary reset; same core/IP and algorithm',
        old_build_preserved=str(OLD),new_build=str(NEW),board_operations=0))
    run('boundary_audit',[BIN/'vivado.bat','-mode','batch','-notrace','-source',ROOT/'single_repair/hardware/inspect_boundary_r2.tcl',
        '-log','D:/PLD/tmp/single_repair_boundary2_tool.log','-journal','D:/PLD/tmp/single_repair_boundary2.jou'],ROOT)
    print('PHYSICAL2_AND_ROUTED_ENDPOINTS_COMPLETE; release gates still required')

if __name__=='__main__':main()
