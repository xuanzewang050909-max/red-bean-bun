from physical_gate import *
import time
import subprocess
def main():
    gate=json.loads((OUT/'physical_gates.json').read_text());assert gate['status']=='OFFLINE_PHYSICAL_GATES_PASS'
    for k in ['dcp','hwh','top']:
        assert ref(gate[k]['path'])==gate[k],k
    log=Path('D:/PLD/three_repair_write_bit.log');assert not log.exists()
    cmd=['E:/vivado/Vivado/2017.4/bin/vivado.bat','-mode','batch','-notrace','-source',str(ROOT/'three_repair/hardware/write_bit.tcl'),'-log','D:/PLD/tmp/three_repair_bit_tool.log','-journal','D:/PLD/tmp/three_repair_bit.jou']
    t=time.perf_counter()
    with log.open('x') as f:r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0 and (BUILD/'single_repair_release.bit').is_file(),str(log)
    assert 'CRITICAL WARNING:' not in log.read_text() and 'ERROR:' not in log.read_text()
    assert ref(gate['dcp']['path'])==gate['dcp'] and ref(gate['hwh']['path'])==gate['hwh']
    record=dict(status='SAME_BUILD_BIT_GENERATED',seconds=time.perf_counter()-t,command=cmd,bit=ref(BUILD/'single_repair_release.bit'),hwh=gate['hwh'],dcp=gate['dcp'],log=ref(log),hardware_operations=0,physical_builds=1,scope='New three-profile core; bit from same audited routed DCP and HWH')
    (OUT/'release_bit.json').write_text(json.dumps(record,indent=2));print(record['status'],record['bit']['sha256'])
if __name__=='__main__':main()
