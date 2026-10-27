from candidates import *
from identify import ref
import hashlib
from pathlib import Path
import ctypes, subprocess
def main():
    p=Path(__file__).parent;dst=OUT/'integer';dst.mkdir(exist_ok=False)
    compiler=Path('E:/vivado/Vivado/2017.4/tps/win64/msys64/mingw64/bin/g++.exe')
    # Existing bundled compiler only.
    if not compiler.exists():
        options=list(Path('D:/PLD/tools').rglob('g++.exe'))
        assert options, 'NO_EXISTING_COMPILER';compiler=options[0]
    dll=dst/'repair.dll'
    cmd=[str(compiler),'-O2','-shared','-std=c++11',str(p/'hardware/repair.cpp'),'-o',str(dll)]
    with (dst/'compile.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    lib=ctypes.CDLL(str(dll));fn=lib.valley_repair
    fn.argtypes=[np.ctypeslib.ndpointer(dtype=np.uint32,flags='C_CONTIGUOUS')]+[ctypes.c_int]*5
    profiles=json.loads((OUT/'frozen_algorithm.json').read_text())['config']['profiles']
    records=[]
    def test(name,rgb,old,fov,profile,cfg,expected=None):
        h,w=old.shape;n=h*w;packed=rgb[:,:,2].astype('uint32')|(rgb[:,:,1].astype('uint32')<<8)|(rgb[:,:,0].astype('uint32')<<16)|(fov.astype('uint32')<<24)|(old.astype('uint32')<<25)
        m=np.full(6*n+32,0xdeadbeef,dtype='uint32');m[:n]=packed.ravel();before=m[:n].copy()
        t=time.perf_counter();ops=[0,1,2]+[3]*16+[4]
        for op in ops:assert fn(m,op,h,w,6*n,profile)==0,(name,op)
        r=expected or decide_cached(rgb,old,fov,cfg)
        got=m[5*n:6*n].reshape(h,w)
        diff={k:int(np.count_nonzero(v)) for k,v in dict(final=(got&1)!=r['final'],added=((got>>1)&1)!=r['added'],uncertain=((got>>2)&1)!=r['uncertain'],smooth=(m[n:2*n].reshape(h,w)&4095)!=r['smoothed'],score=(m[2*n:3*n].reshape(h,w)&65535)!=r['score'],direction=((m[2*n:3*n].reshape(h,w)>>16)&7)!=r['direction']).items()}
        assert not any(diff.values()),(name,diff)
        assert np.array_equal(before,m[:n]) and (m[6*n:]==0xdeadbeef).all()
        np.savez_compressed(dst/(name+'.npz'),input=packed,memory=m[:6*n],output=got)
        records.append(dict(name=name,profile=profile,shape=[h,w],differences=diff,seconds=time.perf_counter()-t,commands=len(ops),guard_words_unchanged=True))
    for profile,ident in enumerate(IDS):
        with np.load(OUT/'input'/f'{ident}.npz') as a:rgb=a['rgb'];old=a['old'];fov=a['fov']
        with np.load(OUT/'selected'/ident/'arrays.npz') as a:expected={k:a[k] for k in a.files}
        test(ident,rgb,old,fov,profile,profiles[ident],expected)
    rng=np.random.default_rng(591)
    for name,h,w,kind in [('empty',32,32,0),('uniform',33,41,1),('edges',35,37,2),('noise',39,47,3)]:
        rgb=rng.integers(0,256,(h,w,3),dtype='uint8') if kind>=2 else np.full((h,w,3),100*kind,dtype='uint8')
        old=rng.random((h,w))<.07 if kind>=2 else np.zeros((h,w),bool)
        fov=np.ones((h,w),bool) if kind else np.zeros((h,w),bool)
        for profile,ident in enumerate(IDS):test(name+'_'+str(profile),rgb,old,fov,profile,profiles[ident])
    m=np.full(128,0xcafebabe,dtype='uint32');before=m.copy()
    for args in [(1,32,32,6144),(0,513,512,1572864),(0,2,2,23),(5,2,2,24)]:assert fn(m,*args,0)!=0 and np.array_equal(m,before)
    (dst/'receipt.json').write_text(json.dumps(dict(status='INTEGER_C_EXACT',records=records,compiler=str(compiler),source_sha256=hashlib.sha256((p/'hardware/repair.cpp').read_bytes()).hexdigest(),invalid_commands_no_writes=True),indent=2))
    print('INTEGER_C_EXACT',records)
if __name__=='__main__':main()
