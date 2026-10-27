"""Read actual reports, sealed source and routed design; no board access."""
from software import *
import re,xml.etree.ElementTree as ET
BASE=OUT;OUT=ROOT/'results/single_repair_reset_repair_r1'
BUILD=Path('D:/PLD/tmp/single_repair_design_r2')
BD=BUILD/'single_repair.srcs/sources_1/bd/single_repair'
def ref(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
    target=OUT/'physical_gates.json';assert not target.exists()
    timing=(BUILD/'final_timing_summary.rpt').read_text()
    row=re.search(r'WNS\(ns\)[\s\S]*?\n\s*-+[^\n]*\n\s*([^\n]+)',timing)[1].split()
    assert len(row)==12 and all(float(row[i])>=0 for i in [0,4,8]) and all(float(row[i])==0 for i in [1,2,5,6,9,10])
    assert 'All user specified timing constraints are met.' in timing
    utilization=(BUILD/'utilization_routed.rpt').read_text()
    resource_labels={'LUT':'Slice LUTs','FF':'Slice Registers','BRAM36_equivalent':'Block RAM Tile','DSP':'DSPs'}
    resources={key:float(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*([\d.]+)\s*\|',utilization)[1]) for key,label in resource_labels.items()}
    checks=(BUILD/'check_timing.rpt').read_text()
    assert len(re.findall('There are 0 ',checks))>=16 and not re.search(r'There are [1-9]',checks)
    route=(BUILD/'final_route_status.rpt').read_text()
    def count(label):return int(re.search(label+r'\.+\s*:\s*(\d+)',route)[1])
    assert count('routable nets')==count('fully routed nets')>0 and count('nets with routing errors')==0
    drc=(BUILD/'final_drc.rpt').read_text()
    rows=re.findall(r'\|\s*([A-Z]+-\d+)\s*\|\s*(\w+)\s*\|[^|]+\|\s*(\d+)\s*\|',drc)
    expected={'DPIP-1':5,'DPOP-1':4,'DPOP-2':4,'REQP-1840':8,'RTSTAT-10':1}
    assert {k:int(n) for k,s,n in rows}==expected and all(s=='Warning' for k,s,n in rows)
    audit=Path('D:/PLD/single_repair_resetfix_boundary_audit.log').read_text()
    assert 'ROUTED_BOUNDARY_AUDIT_PASS bits=314' in audit and 'ERROR:' not in audit
    xdc=(BUILD/'routed_constraints.xdc').read_text()
    assert len(re.findall(r'^set_false_path',xdc,re.M))==4 and not re.search(r'^set_multicycle_path',xdc,re.M)
    assert 'current_instance single_repair_i/reset_50m/U0' in xdc and xdc.count('# Scoped constraints for xpm_cdc_async_rst')==3
    assert len(re.findall(r'^create_clock',xdc,re.M))==1 and 'create_clock -period 20.000' in xdc
    hwh=BD/'hw_handoff/single_repair.hwh';root=ET.parse(hwh).getroot()
    ps=next(m for m in root.iter('MODULE') if m.get('INSTANCE')=='ps7_0')
    params={p.get('NAME'):p.get('VALUE') for p in ps.iter('PARAMETER')}
    assert float(params['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ'])==50 and params['PCW_FCLK0_PERIPHERAL_CLKSRC']=='IO PLL'
    div=[int(params['PCW_FCLK0_PERIPHERAL_DIVISOR'+str(i)]) for i in [0,1]];assert div[0]*div[1]==20
    mem=next(m for m in root.iter('MEMRANGE') if m.get('INSTANCE')=='repair_0')
    assert int(mem.get('BASEVALUE'),16)==0x43c00000 and int(mem.get('HIGHVALUE'),16)==0x43c0ffff
    reset=next(m for m in root.iter('MODULE') if m.get('INSTANCE')=='reset_50m')
    rparams={p.get('NAME'):p.get('VALUE') for p in reset.iter('PARAMETER')}
    assert rparams['C_EXT_RESET_HIGH']=='0' and rparams['C_AUX_RESET_HIGH']=='0'
    audit_table=(BUILD/'routed_boundary_audit_r2.tsv').read_text()
    assert 'ACTUAL_CORE_RESET_DRIVERS=' in audit_table and 'reset_50m' in audit_table.split('ACTUAL_CORE_RESET_DRIVERS=')[1].splitlines()[0]
    reset_receipt=json.loads((OUT/'reset_reproduction.json').read_text())
    assert reset_receipt['status']=='ACTUAL_GENERATED_RESET_DEFECT_REPRODUCED'
    assert json.loads((OUT/'integration/receipt.json').read_text())['actual_reset_chain']
    routed_reset_checks={}
    for mode in ['old','new']:
        record=json.loads((OUT/('routed_'+mode+'_receipt.json')).read_text())
        assert record['status']=='ROUTED_RESET_EXPECTATION_VERIFIED'
        assert record['released_after_external_reset']==(mode=='new')
        assert ref(record['actual_routed_cell']['path'])==record['actual_routed_cell']
        routed_reset_checks[mode]=record
    old_dcp=json.loads((BASE/'physical_gates.json').read_text())['dcp']
    assert ref(old_dcp['path'])==old_dcp
    bind=json.loads((OUT/'integration/binding.json').read_text());assert ref(bind['top'])['sha256']==bind['sha256']
    for name,expected_status in [('integer/receipt.json','INTEGER_C_EXACT'),('rtl_receipt.json','RTL_REFERENCE_EXACT'),('integration/receipt.json','INTEGRATED_SIM_PASS')]:
        assert json.loads(((OUT if name.startswith('integration') else BASE)/name).read_text())['status']==expected_status
    r=json.loads((BASE/'rtl_receipt.json').read_text())
    assert ref(Path(__file__).parent/'hardware/repair.cpp')['sha256']==r['core_sha256']
    sources={}
    for p in (Path('D:/PLD/tmp/single_repair_ip_r1')/'hdl/verilog').glob('*'):
        if not p.is_file():continue
        originals=list(Path('D:/PLD/tmp/single_repair_hls_r1').glob('*/syn/verilog/'+p.name))
        assert len(originals)==1 and ref(p)['sha256']==ref(originals[0])['sha256'],p
        sources[p.name]=ref(p)
    rec=dict(status='OFFLINE_PHYSICAL_GATES_PASS',physical_builds=2,tool='Vivado 2017.4',device='xc7z020clg400-1',
        clock_mhz=50,period_ns=20,clock_divisors=div,wns_ns=float(row[0]),whs_ns=float(row[4]),wpws_ns=float(row[8]),
        routed_nets=count('fully routed nets'),routing_errors=0,unconstrained_endpoints=0,drc_errors=0,drc_critical_warnings=0,resources=resources,
        drc_warnings=expected,drc_interpretation='Warning review is recorded; not zero-DRC. No rule disabled or severity changed.',
        constraints='Only generated PS clock and stock reset IP/XPM scoped exceptions; no user false/multicycle paths.',
        dcp=ref(BUILD/'single_repair.runs/impl_1/single_repair_wrapper_routed.dcp'),hwh=ref(hwh),
        reports={p.name:ref(p) for p in BUILD.glob('*.rpt')},top=ref(bind['top']),rtl=sources,
        reset_polarities=rparams,reset_release='GENERATED_AND_ROUTED_CELL_RELEASE_VERIFIED',
        routed_reset_checks=routed_reset_checks,old_dcp_unchanged=old_dcp,board_status='BOARD_NOT_RUN')
    target.write_text(json.dumps(rec,indent=2));print(rec['status'],rec['wns_ns'],rec['whs_ns'],rec['wpws_ns'])
if __name__=='__main__':main()
