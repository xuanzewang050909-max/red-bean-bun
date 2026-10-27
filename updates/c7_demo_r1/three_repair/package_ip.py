"""Reproducible packaging-only workaround for 2017.4 timestamp revision overflow."""
from identify import *
from record_tools import run
import re
def main():
    src=Path('D:/PLD/tmp/three_repair_hls_r1/solution/impl/ip')
    dst=Path('D:/PLD/tmp/three_repair_ip_r1')
    assert not dst.exists();shutil.copytree(src,dst)
    p=dst/'run_ippack.tcl';s=p.read_text()
    patched,n=re.subn(r'set Revision\s+"\d+"','set Revision    "10280001"',s);assert n==1
    (dst/'run_ippack_original.tcl').write_text(s);p.write_text(patched)
    assert all((dst/f.relative_to(src)).read_bytes()==f.read_bytes() for f in (src/'hdl').rglob('*') if f.is_file())
    run('ip_pack_reproduction',['E:/vivado/Vivado/2017.4/bin/vivado.bat','-mode','batch','-notrace','-source',p,'-log','pack.log','-journal','pack.jou'],dst)
if __name__=='__main__':main()
