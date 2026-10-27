"""Offline reset reproduction and bounded second-build preparation. No board API."""
from identify import *
import time
import subprocess, shlex

FIX=OUT
OLD=Path('D:/PLD/tmp/single_repair_design_r1')
NEW=Path('D:/PLD/tmp/single_repair_design_r2')
BIN=Path('E:/vivado/Vivado/2017.4/bin')

def ref(p):
    p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def write(p,x):
    with Path(p).open('x',encoding='utf8') as f:json.dump(x,f,indent=2,ensure_ascii=False)

def run(label,args,cwd):
    log=Path('D:/PLD')/('three_repair_'+label+'.log')
    assert not log.exists()
    t=time.perf_counter()
    with log.open('x') as f:p=subprocess.run(list(map(str,args)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
    write(FIX/(label+'.json'),dict(command=list(map(str,args)),returncode=p.returncode,seconds=time.perf_counter()-t,log=ref(log)))
    assert p.returncode==0,log
    return log.read_text(errors='replace')
