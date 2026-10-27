from software import *
import subprocess,re
BIN=Path('E:/vivado/Vivado/2017.4/bin');BUILD=Path('D:/PLD/tmp/single_repair_design_r1')
def main():
    records=[]
    for name in ['native','empty','uniform','edges','noise']:
        p=Path('D:/PLD')/('single_repair_rtl_'+name+'.log');s=p.read_text()
        hits=re.findall(r'RTL_FRAME_EXACT h=(\d+) w=(\d+) cycles=(\d+) reads=(\d+) writes=(\d+) stalls=(\d+)',s)
        assert len(hits)==1 and 'CONTROL_ORDER_BACKPRESSURE_PASS' in s and not re.search(r'(?:%Error|Fatal:|%Fatal)',s),('RTL_NOT_COMPLETE',name)
        h,w,cycles,reads,writes,stalls=map(int,hits[0]);records.append(dict(case=name,height=h,width=w,cycles=cycles,
          simulated_seconds_50mhz=cycles/50e6,ddr_read_beats32=reads,ddr_write_beats32=writes,stall_cycles=stalls,log=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    receipt=OUT/'rtl_receipt.json';assert not receipt.exists()
    receipt.write_text(json.dumps(dict(status='RTL_REFERENCE_EXACT',actual_generated_HLS=True,frames=records,
         measurement='RTL_SIMULATION_ONLY; randomized memory latency, not board measurements',core_sha256=hashlib.sha256((Path(__file__).parent/'hardware/repair.cpp').read_bytes()).hexdigest()),indent=2))
    integ=json.loads((OUT/'integration/receipt.json').read_text());assert integ['status']=='INTEGRATED_SIM_PASS'
    log=Path('D:/PLD/single_repair_physical_r1.log');assert not log.exists() and not (BUILD/'physical_started').exists()
    t=time.perf_counter();cmd=[str(BIN/'vivado.bat'),'-mode','batch','-notrace','-source',str(Path(__file__).parent/'hardware/physical.tcl'),'-log','D:/PLD/tmp/single_repair_physical_tool.log','-journal','D:/PLD/tmp/single_repair_physical.jou']
    with log.open('x') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
    (OUT/'physical_attempt_1.json').write_text(json.dumps(dict(returncode=p.returncode,seconds=time.perf_counter()-t,command=cmd,log=str(log),sha256=hashlib.sha256(log.read_bytes()).hexdigest(),physical_attempts=1,limit=3),indent=2))
    assert p.returncode==0,'PHYSICAL_BUILD_FAILED'
    print('PHYSICAL_ROUTE_COMPLETED_REQUIRES_FINAL_AUDIT')
if __name__=='__main__':main()
