"""Run actual generated RTL with stalled AXI memory, no hardware access."""
from identify import *
import subprocess,time,re,concurrent.futures
BUILD=Path('D:/PLD/tmp/three_repair_rtl_r1')
def execute(name,h,w,profile):
    log=Path('D:/PLD')/('three_repair_rtl_'+name+'.console.log')
    if name=='noise_2':
        assert log.exists() # already executed first as smoke gate
    else:
        assert not log.exists()
        cmd=[str(BUILD/'obj_dir/Vrepair_tb.exe'),f'+H={h}',f'+W={w}',f'+PROFILE={profile}','+DIR='+str(BUILD/name)]
        with log.open('x') as f:p=subprocess.run(cmd,cwd=BUILD,stdout=f,stderr=subprocess.STDOUT)
        assert p.returncode==0,(name,p.returncode)
    s=log.read_text();hit=re.findall(r'RTL_FRAME_EXACT h=(\d+) w=(\d+) cycles=(\d+) reads=(\d+) writes=(\d+) stalls=(\d+)',s)
    assert len(hit)==1 and 'CONTROL_ORDER_BACKPRESSURE_PASS' in s and not re.search(r'(?:%Error|Fatal:|%Fatal)',s),name
    hh,ww,cycles,reads,writes,stalls=map(int,hit[0]);assert (hh,ww)==(h,w)
    rec=dict(case=name,profile=profile,height=h,width=w,cycles=cycles,simulated_seconds_50mhz=cycles/50e6,ddr_read_beats32=reads,ddr_write_beats32=writes,stall_cycles=stalls,log=ref(log))
    (OUT/'integer'/f'{name}_rtl.json').write_text(json.dumps(rec,indent=2));return rec
def main():
    execute('noise_2',39,47,2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(execute,name,512,512,i) for i,name in enumerate(IDS)]
        for job in concurrent.futures.as_completed(jobs):print(json.dumps(job.result()),flush=True)
    for kind,h,w in [('empty',32,32),('uniform',33,41),('edges',35,37),('noise',39,47)]:
        for profile in range(3):
            if (kind,profile)!=('noise',2):print(json.dumps(execute(kind+'_'+str(profile),h,w,profile)),flush=True)
    records=[json.loads(p.read_text()) for p in sorted((OUT/'integer').glob('*_rtl.json'))]
    assert len(records)==15
    (OUT/'rtl_receipt.json').write_text(json.dumps(dict(status='RTL_REFERENCE_EXACT',frames=records,measurement='RTL_SIMULATION; not board time',core=ref(ROOT/'three_repair/hardware/repair.cpp'),rtl_top=ref(Path('D:/PLD/tmp/three_repair_hls_r1/solution/syn/verilog/valley_repair.v')),bench=ref(BUILD/'repair_tb.sv')),indent=2))
if __name__=='__main__':main()
