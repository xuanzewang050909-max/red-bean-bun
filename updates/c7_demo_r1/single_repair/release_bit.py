from physical_gate import *
import subprocess
def main():
    gate=json.loads((OUT/'physical_gates.json').read_text());assert gate['status']=='OFFLINE_PHYSICAL_GATES_PASS'
    for k in ['dcp','hwh','top']:
        assert ref(gate[k]['path'])==gate[k],k
    log=Path('D:/PLD/single_repair_write_bit_r2.log');assert not log.exists()
    cmd=['E:/vivado/Vivado/2017.4/bin/vivado.bat','-mode','batch','-notrace','-source',str(ROOT/'single_repair/hardware/write_bit.tcl'),'-log','D:/PLD/tmp/single_repair_bit_tool_r2.log','-journal','D:/PLD/tmp/single_repair_bit_r2.jou']
    t=time.perf_counter()
    with log.open('x') as f:r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0 and (BUILD/'single_repair_release.bit').is_file(),str(log)
    assert 'CRITICAL WARNING:' not in log.read_text() and 'ERROR:' not in log.read_text()
    assert ref(gate['dcp']['path'])==gate['dcp'] and ref(gate['hwh']['path'])==gate['hwh']
    record=dict(status='SAME_BUILD_BIT_GENERATED',seconds=time.perf_counter()-t,command=cmd,bit=ref(BUILD/'single_repair_release.bit'),hwh=gate['hwh'],dcp=gate['dcp'],log=ref(log),hardware_operations=0,physical_builds=1,previous_release='release_bit.json',repair='Explicit original board.repoPaths resolves Board49-67 metadata warning; same unchanged routed DCP, no new physical build.')
    (OUT/'release_bit_r2.json').write_text(json.dumps(record,indent=2));print(record['status'],record['bit']['sha256'])
if __name__=='__main__':main()
