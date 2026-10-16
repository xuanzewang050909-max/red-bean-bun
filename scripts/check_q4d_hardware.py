"""Fail-closed host gate for C7 paired implementation and unchanged standard IP."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from check_b_hardware import parse_hwh, info, require

ROOT=Path(__file__).resolve().parents[1]


def check(build):
    build=Path(build)
    hwh=build/'deploy/q4d_detector.hwh'
    parsed=parse_hwh(hwh)
    modules={m.get('INSTANCE'):m for m in ET.parse(hwh).findall('.//MODULE')}
    old={m.get('INSTANCE'):m for m in ET.parse(ROOT/'build/deploy/a4_segmentation_2017_4_r1/a4_segmentation.hwh').findall('.//MODULE')}
    require(set(modules)-set(old)=={'quality_filter','point_observe'} and set(old)-set(modules)=={'segmentation_filter'},'Unexpected module changes')
    checked=[]
    for name in ('ps7_0','axi_dma_0','loopback_fifo','point_control','reset_100m','memory_axi','const_one','const_zero'):
        require(modules[name].get('VLNV')==old[name].get('VLNV'),'Reused IP type changed: '+name)
        params=[]
        for module in (old[name],modules[name]):
            params.append({p.get('NAME'):p.get('VALUE').replace('a4_segmentation','q4d_detector') for p in module.findall('./PARAMETERS/PARAMETER')})
        require(params[0]==params[1],'Reused parameters changed: '+name+' '+str([(k,params[0].get(k),params[1].get(k)) for k in set(params[0])|set(params[1]) if params[0].get(k)!=params[1].get(k)]))
        checked.append(name)
    for name,address,kind in (('axi_dma_0',0x40400000,'xilinx.com:ip:axi_dma:7.1'),('point_control',0x41200000,'xilinx.com:ip:axi_gpio:2.0'),('point_observe',0x41210000,'xilinx.com:ip:axi_gpio:2.0')):
        require(parsed.ip_dict[name]['phys_addr']==address and parsed.ip_dict[name]['type']==kind,'PYNQ mapping mismatch: '+name)
    require(modules['quality_filter'].get('VLNV')=='retinafpga.local:hls:retina_detector_hls:1.0','Wrong quality IP')
    def connection(owner,pin,other,port):
        require(modules[owner].find(f"./PORTS/PORT[@NAME='{pin}']/CONNECTIONS/CONNECTION[@INSTANCE='{other}'][@PORT='{port}']") is not None,'Missing wire '+owner+'/'+pin+' -> '+other+'/'+port)
    for owner,clock,reset in (('point_stage','aclk','aresetn'),('quality_filter','ap_clk','ap_rst_n'),('point_observe','s_axi_aclk','s_axi_aresetn')):
        connection(owner,clock,'ps7_0','FCLK_CLK0');connection(owner,reset,'reset_100m','peripheral_aresetn')
    for pin,other,port in (('cfg_control','point_control','gpio_io_o'),('status_word','point_control','gpio2_io_i'),('observe_select','point_observe','gpio_io_o'),('observe_data','point_observe','gpio2_io_i'),('hls_control','quality_filter','control_V'),('hls_start','quality_filter','ap_start'),('hls_idle','quality_filter','ap_idle'),('hls_done','quality_filter','ap_done'),('hls_ready','quality_filter','ap_ready')):
        connection('point_stage',pin,other,port)
    for signal in ('tdata','tvalid','tready'):
        connection('point_stage','m_hls_'+signal,'quality_filter','source_V_V_'+signal.upper())
        connection('point_stage','s_hls_'+signal,'quality_filter','result_V_V_'+signal.upper())
    for signal in ('tdata','tkeep','tlast','tvalid','tready'):
        connection('point_stage','s_axis_'+signal,'axi_dma_0','m_axis_mm2s_'+signal)
        connection('point_stage','m_axis_'+signal,'loopback_fifo','s_axis_'+signal)
    for pin in ('dcm_locked','aux_reset_in'): connection('reset_100m',pin,'const_one','dout')
    connection('reset_100m','ext_reset_in','ps7_0','FCLK_RESET0_N')
    parameters={p.get('NAME'):p.get('VALUE') for p in modules['point_stage'].findall('./PARAMETERS/PARAMETER')}
    require(int(parameters['COUNTER_WIDTH'])==32,'Counter width changed')
    timing=(build/'timing_summary.rpt').read_text()
    for marker in ('All user specified timing constraints are met.','There are 0 register/latch pins with no clock.','There are 0 pins that are not constrained for maximum delay.','There are 0 combinational loops in the design.'):
        require(marker in timing,'Timing gate missing '+marker)
    values=re.search(r'WNS\(ns\).*\n\s*-+.*\n\s*([^\n]+)',timing).group(1).split()
    require(len(values)==12 and all(float(values[i])>=0 for i in (0,4,8)) and all(int(values[i])==0 for i in (2,6,10)),'Timing violations')
    util=(build/'utilization.rpt').read_text()
    counts={name:float(re.search(r'\|\s*'+name+r'\s*\|\s*(\d+(?:\.\d+)?)\s*\|',util).group(1)) for name in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs')}
    drc=(build/'drc.rpt').read_text()
    require(not re.search(r'\|\s*(?:Error|Critical Warning)\s*\|',drc,re.I),'DRC failure')
    warnings=re.findall(r'\|\s*([\w-]+)\s*\|\s*Warning\s*\|',drc)
    require(warnings==['DPIP-1','DPOP-1','DPOP-2','RTSTAT-10'],'New DRC warning')
    warning_counts=Counter(re.findall(r'^(DPIP-1|DPOP-1|DPOP-2|RTSTAT-10)#\d+ Warning',drc,re.M))
    require(warning_counts=={'DPIP-1':22,'DPOP-1':23,'DPOP-2':29,'RTSTAT-10':1},'Unreviewed DRC count')
    dsp_details=[line for line in drc.splitlines() if line.startswith('DSP ')]
    # Actual routed C7 constant-arithmetic DSPs and the unchanged base response
    # stage have pipeline/power suggestions. All paths are still timed at 100MHz.
    # These are not ignored timing exceptions or a claim of measured power.
    c7_prefix='DSP q4d_detector_i/quality_filter/inst/c7_filter_U0/'
    base_prefix='DSP q4d_detector_i/quality_filter/inst/retina_detector_c5_U0/retina_refined_base_U0/response_carrier_U0/'
    require(len(dsp_details)==74 and sum(l.startswith(c7_prefix) for l in dsp_details)==71 and
            sum(l.startswith(base_prefix) for l in dsp_details)==3,'DSP advice outside reviewed arithmetic')
    log=(ROOT/'build/q4d_detector_full_02_session.log').read_text(encoding='utf-8-sig')
    require('\nQ4D_DETECTOR_BITSTREAM_GENERATED_TIMING_CHECKED (' in log and '\nERROR:' not in log,'Full build missing')
    def read_run(p):
        data=p.read_bytes()
        try:return data.decode('utf-8-sig')
        except UnicodeDecodeError:return data.decode('gb18030')
    logs = [log] + [read_run(p) for p in (build/'q4d_detector.runs').glob('*/runme.log')]
    critical=Counter(line.strip() for text in logs for line in text.splitlines() if line.startswith('CRITICAL WARNING:'))
    allowed={'CRITICAL WARNING: [BD 41-737] Cannot set the parameter POLARITY on /reset_100m/aux_reset_in. It is read-only.'}
    allowed.update(f'CRITICAL WARNING: [PSU-{i+1}]  Parameter : PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_{i} has negative value {v} . PS DDR interfaces might fail when entering negative DQS skew values.' for i,v in enumerate(('-0.051','-0.006','-0.009','-0.033')))
    require(set(critical) <= allowed, 'Unreviewed critical warning: '+str(critical))
    require(not any(line.startswith('ERROR:') for text in logs for line in text.splitlines()), 'Error in implementation run log')
    for saved,current in (('build_script_used.tcl','vivado/scripts/build_q4d_detector.tcl'),('quality_guard_used.v','rtl/core/retina_detector_guard.v')):
        require(info(build/saved)==info(ROOT/current),'Build source changed '+current)
    syn=ROOT/'build/q4d_detector_hls_03/solution1/syn/verilog'; packaged=ROOT/'build/q4d_detector_hls_export_02/solution1/impl/ip/hdl/verilog'
    generated={}
    implemented=list((build/'q4d_detector.srcs/sources_1/bd/q4d_detector/ipshared').glob('*/hdl/verilog/retina_detector_hls.v'))
    require(len(implemented)==1,'Ambiguous implemented HLS source')
    implemented=implemented[0].parent
    for source in sorted(syn.iterdir()):
        if source.suffix in ('.v','.dat'):
            require(info(source)==info(packaged/source.name),'RTL packaging mismatch '+source.name)
            used=(implemented/source.name) if source.suffix=='.v' else build/'q4d_detector.srcs/sources_1/bd/q4d_detector/ip/q4d_detector_quality_filter_0/hdl/verilog'/source.name
            require(info(source)==info(used),'Implemented RTL/ROM changed '+source.name)
            generated[source.name]=info(source)
    return dict(status='PASS_Q4D_HOST_ROUTED_HARDWARE_NOT_BOARD',hardware_clock_hz=100_000_000,
                wns_ns=float(values[0]),whs_ns=float(values[4]),wpws_ns=float(values[8]),resources=counts,
                original_a4_standard_ip_parameters_exact=checked,reviewed_warnings=warnings,
                reviewed_warning_counts=warning_counts,
                reviewed_critical_warnings=critical,generated_rtl_rom=generated,
                ip_dict={n:parsed.ip_dict[n] for n in ('axi_dma_0','point_control','point_observe')},
                artifacts={p.name:info(p) for p in (hwh,build/'deploy/q4d_detector.bit')},board_status='NOT_RUN')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('build',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); require(not args.output.exists(),'Preserve prior gate report')
    result=check(args.build); args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(result['status'],result['resources'],'WNS',result['wns_ns'],'WHS',result['whs_ns'])
