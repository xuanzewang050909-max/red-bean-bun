"""Trace actual generated interfaces, not just BD address metadata."""
from identify import *
import re,xml.etree.ElementTree as ET
def main():
    bd=Path('D:/PLD/tmp/three_repair_design_r1/single_repair.srcs/sources_1/bd/single_repair')
    src=bd/'synth/single_repair.v';s=src.read_text()
    top=next(m[0] for m in re.finditer(r'\bmodule\s+(\w+)\s*\([\s\S]*?endmodule',s) if m[1]=='single_repair')
    def ports(name):
        m=re.search(r'\b(\w+)\s+'+name+r'\s*\(([\s\S]*?)\);',top);assert m,name
        return dict(re.findall(r'\.(\w+)\(([^()]*)\)',m[2]))
    ps=ports('ps7_0');ctrl=ports('control_axi');mem=ports('memory_axi');core=ports('repair_0');rst=ports('reset_50m')
    checks=[]
    for prefix,p,psprefix in [('S00_AXI_',ctrl,'M_AXI_GP0_'),('M00_AXI_',mem,'S_AXI_HP0_')]:
        for k,v in p.items():
            if not k.startswith(prefix):continue
            target=psprefix+k[len(prefix):].upper()
            assert target in ps and ps[target]==v,(k,target,ps.get(target),v)
            checks.append(dict(segment='PS_control' if p is ctrl else 'PS_DDR',fabric=k,ps=target,net=v))
    for k,v in core.items():
        if k.startswith('s_axi_control_'):
            sig=k[len('s_axi_control_'):];parent=ctrl['M00_AXI_'+sig.lower()]
            expected=parent+('[6:0]' if sig in ('AWADDR','ARADDR') else '')
            assert v==expected;(checks.append(dict(segment='core_control',core=k,net=v)))
        elif k.startswith('m_axi_ram_'):
            sig=k[len('m_axi_ram_'):];target='S00_AXI_'+sig.lower()
            assert target in mem and mem[target]==v,(k,mem.get(target),v)
            checks.append(dict(segment='core_DDR',core=k,net=v))
    clock=ps['FCLK_CLK0']
    for p in [ctrl,mem]:
        assert all(p[k]==clock for k in ['ACLK','S00_ACLK','M00_ACLK'])
        assert p['ARESETN']==rst['interconnect_aresetn'] and p['S00_ARESETN']==p['M00_ARESETN']==rst['peripheral_aresetn']
    assert core['ap_clk']==rst['slowest_sync_clk']==clock
    assert ps['M_AXI_GP0_ACLK']==ps['S_AXI_HP0_ACLK']==clock
    assert core['ap_rst_n']==rst['peripheral_aresetn']
    assert rst['aux_reset_in']==rst['dcm_locked']==ports('one')['dout'] and rst['mb_debug_sys_rst']==ports('zero')['dout']
    assert rst['ext_reset_in']==ps['FCLK_RESET0_N']
    (OUT/'production_interface_audit.json').write_text(json.dumps(dict(status='ACTUAL_TOP_INTERFACES_VERIFIED',source=ref(src),interfaces=checks,endpoint_count=len(checks),clock_net=clock,clock_mhz=50,reset='actual active-low external and auxiliary reset, aux tied1, lock1, debug0',observer='NOT_PRESENT; no interface takeover',scope='Generated production net expressions; integrated dynamic simulation and routed checks separately required'),indent=2))
    print('ACTUAL_TOP_INTERFACES_VERIFIED',len(checks))
if __name__=='__main__':main()
