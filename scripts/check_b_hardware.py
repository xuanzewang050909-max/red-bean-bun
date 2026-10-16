"""Host evidence gate: pinned Base derivation, actual HWH parser and A4 reuse.

Only architecture constants are stubbed for the unchanged official parser.
This never accesses hardware, constructs video drivers or declares a board PASS.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
SPIRIT = '{' + NS['s'] + '}'


def require(condition, message):
    if not condition: raise ValueError(message)


def info(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def semantic(node):
    # Ignore GUI/vendor annotations only. Standard config values, interfaces,
    # clocks, signal/bus connectivity and component identities remain checked.
    children = [semantic(c) for c in node if c.tag != SPIRIT + 'vendorExtensions'
                and c.get(SPIRIT + 'referenceId') != 'bd:xciName']
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(),
            tuple(sorted(children, key=repr)))


def video_objects(tree):
    result = {}
    for kind in ('component', 'design'):
        for node in tree.findall('.//s:' + kind, NS):
            lib = node.findtext('s:library', '', NS); name = node.findtext('s:name', '', NS)
            if lib.startswith('BlockDiagram/system_imp/video_imp') or (lib == 'BlockDiagram/system_imp' and name in ('video', 'video_imp')):
                result[(kind, lib, name)] = semantic(node)
    return result


def ps_parameters(tree):
    nodes = [c for c in tree.findall('.//s:componentInstance', NS) if c.findtext('s:instanceName', '', NS) == 'ps7_0']
    require(len(nodes) == 1, 'Expected one PS')
    return {c.get(SPIRIT + 'referenceId'): c.text for c in nodes[0].findall('./s:configurableElementValues/s:configurableElementValue', NS)
            if not c.get(SPIRIT + 'referenceId', '').startswith('bd:')}


def parse_hwh(path):
    sys.dont_write_bytecode = True
    architecture = types.ModuleType('pynq.ps')
    architecture.CPU_ARCH = architecture.ZYNQ_ARCH = 'armv7l'
    architecture.ZU_ARCH = 'aarch64'; architecture.CPU_ARCH_IS_SUPPORTED = True
    sys.modules['pynq.ps'] = architecture
    source = ROOT / 'references/PYNQ/v3.0.1/pynq/pl_server/hwh_parser.py'
    spec = importlib.util.spec_from_file_location('b_official_hwh_parser', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.HWH(hwh_name=str(Path(path).resolve()))


def check(build):
    build = Path(build)
    bd = build / 'b_integration.srcs/sources_1/bd/system/system.bd'
    hwh = build / 'b_integration.srcs/sources_1/bd/system/hw_handoff/system.hwh'
    original = build / 'original_official_system.bd'
    original_tree, current_tree = ET.parse(original), ET.parse(bd)
    before, after = video_objects(original_tree), video_objects(current_tree)
    adapter_key=('design','BlockDiagram/system_imp/video_imp/axi_interconnect_0_imp','s00_couplers_imp')
    require(before.keys() == after.keys(), 'Lost official video objects')
    # The standard interconnect now receives AXI4LITE from the root (the only
    # AXI4 audio control slave was deleted). Vivado removes this exact, redundant
    # generated converter. Predict its entire new connectivity, not a blanket
    # waiver for an interconnect subtree. Unique XCI filenames may be renumbered.
    source=next(d for d in original_tree.findall('.//s:design',NS) if d.findtext('s:library','',NS)==adapter_key[1] and d.findtext('s:name','',NS)==adapter_key[2])
    expected_adapter=copy.deepcopy(source)
    instances=expected_adapter.find('s:componentInstances',NS)
    converter=next(c for c in instances if c.findtext('s:instanceName','',NS)=='auto_pc')
    ref=converter.find('s:componentRef',NS)
    require(ref.get(SPIRIT+'name')=='axi_protocol_converter' and ref.get(SPIRIT+'version')=='2.1','Wrong original adapter')
    values={c.get(SPIRIT+'referenceId'):c.text for c in converter.findall('./s:configurableElementValues/s:configurableElementValue',NS)}
    require(values['SI_PROTOCOL']=='AXI4' and values['MI_PROTOCOL']=='AXI4LITE','Wrong original protocol conversion')
    instances.remove(converter)
    expected_adapter.find('s:interconnections',NS).clear()
    for connection in expected_adapter.findall('./s:adHocConnections/s:adHocConnection',NS):
        for child in list(connection):
            if child.get(SPIRIT+'componentRef')=='auto_pc': connection.remove(child)
    for connection in expected_adapter.findall('./s:hierConnections/s:hierConnection',NS):
        if connection.get(SPIRIT+'interfaceRef')=='M_AXI/auto_pc_to_s00_couplers':
            connection.set(SPIRIT+'interfaceRef','M_AXI/s00_regslice_to_s00_couplers')
            connection.find('s:activeInterface',NS).set(SPIRIT+'componentRef','s00_regslice')
    expected_video=dict(before);expected_video[adapter_key]=semantic(expected_adapter)
    require(before and expected_video == after, 'Official video changed beyond exact generated AXI4LITE adapter pruning')
    old_ps, new_ps = ps_parameters(original_tree), ps_parameters(current_tree)
    differences = {k: {'before': old_ps.get(k), 'after': new_ps.get(k)} for k in old_ps.keys() | new_ps.keys() if old_ps.get(k) != new_ps.get(k)}
    allowed = {'PCW_USE_M_AXI_GP1', 'PCW_USE_S_AXI_GP0', 'PCW_GPIO_EMIO_GPIO_ENABLE',
        'PCW_GPIO_EMIO_GPIO_IO', 'PCW_GPIO_EMIO_GPIO_WIDTH', 'PCW_I2C1_PERIPHERAL_ENABLE',
        'PCW_I2C1_I2C1_IO', 'PCW_I2C1_GRP_INT_ENABLE', 'PCW_S_AXI_HP2_FREQMHZ',
        'PCW_EN_I2C1','PCW_EN_EMIO_I2C1','PCW_EN_EMIO_GPIO','PCW_I2C1_BASEADDR','PCW_I2C1_HIGHADDR',
        'PCW_P2F_I2C1_INTR','PCW_S_AXI_GP0_ID_WIDTH','PCW_M_AXI_GP1_ENABLE_STATIC_REMAP',
        'PCW_M_AXI_GP1_ID_WIDTH','PCW_M_AXI_GP1_THREAD_ID_WIDTH','PCW_M_AXI_GP1_SUPPORT_NARROW_BURST'}
    require(set(differences) <= allowed, 'Unexpected board/DDR/MIO PS change: ' + str(set(differences) - allowed))
    parser = parse_hwh(hwh)
    dma = parser.ip_dict['axi_dma_0']; gpio = parser.ip_dict['point_control']; vdma = parser.ip_dict['video/axi_vdma']
    require(dma['type'] == 'xilinx.com:ip:axi_dma:7.1' and dma['phys_addr'] == 0x40400000 and not dma['interrupts'], 'Algorithm DMA mapping/IRQ changed')
    require(gpio['phys_addr'] == 0x43C80000 and gpio['type'] == 'xilinx.com:ip:axi_gpio:2.0', 'Algorithm control mapping changed')
    require(vdma['type'] == 'xilinx.com:ip:axi_vdma:6.3' and vdma['phys_addr'] == 0x43000000, 'Official VDMA mapping changed')
    require({'mm2s_introut', 's2mm_introut'} <= vdma['interrupts'].keys(), 'Lost VDMA interrupts')
    for key, number in {'c_include_sg':0, 'c_micro_dma':0, 'c_sg_length_width':23, 'c_m_axi_mm2s_data_width':64,
        'c_m_axi_s2mm_data_width':32, 'c_m_axis_mm2s_tdata_width':32, 'c_s_axis_s2mm_tdata_width':32}.items():
        require(int(dma['parameters'][key]) == number, 'Wrong algorithm DMA parameter ' + key)
    for key, value in {'C_NUM_FSTORES':4, 'C_INCLUDE_MM2S':1, 'C_INCLUDE_S2MM':1, 'C_M_AXI_MM2S_ADDR_WIDTH':32, 'C_M_AXI_S2MM_ADDR_WIDTH':32}.items():
        require(int(vdma['parameters'][key]) == value, 'Wrong official VDMA parameter ' + key)
    addresses = {'video/hdmi_out/frontend/axi_dynclk':0x43C10000, 'video/hdmi_out/frontend/vtc_out':0x43C20000,
        'video/hdmi_out/color_convert':0x43C60000, 'video/hdmi_out/pixel_unpack':0x43C70000,
        'switches_gpio':0x41200000, 'system_interrupts':0x41800000}
    for name, addr in addresses.items(): require(parser.ip_dict[name]['phys_addr'] == addr, 'Original control address changed ' + name)
    tree = ET.parse(hwh)
    modules = {m.get('FULLNAME').lstrip('/'):m for m in tree.findall('.//MODULE')}
    params = lambda m: {p.get('NAME'):p.get('VALUE') for p in m.findall('./PARAMETERS/PARAMETER')}
    ps = params(modules['ps7_0'])
    for key, value in {'PCW_M_AXI_GP0_FREQMHZ':100, 'PCW_S_AXI_HP2_FREQMHZ':100, 'PCW_S_AXI_HP0_FREQMHZ':142, 'PCW_FPGA0_PERIPHERAL_FREQMHZ':100, 'PCW_FPGA1_PERIPHERAL_FREQMHZ':142}.items():
        require(float(ps[key]) == value, 'Wrong propagated clock ' + key)
    require(int(ps['PCW_DDR_RAM_HIGHADDR'],0) == 0x1fffffff, 'DDR window changed')
    def connected(module, port, peer, peer_port):
        p=modules[module].find(f"./PORTS/PORT[@NAME='{port}']")
        require(p is not None and (peer,peer_port) in {(c.get('INSTANCE'),c.get('PORT')) for c in p.findall('./CONNECTIONS/CONNECTION')}, 'Wrong net ' + module + '/' + port)
    connected('ps7_0','S_AXI_HP2_ACLK','ps7_0','FCLK_CLK0')
    connected('ps7_0','S_AXI_HP0_ACLK','ps7_0','FCLK_CLK1')
    for name, port in {'point_stage':'aclk','segmentation_filter':'ap_clk','axi_dma_0':'m_axi_mm2s_aclk','loopback_fifo':'s_axis_aclk','memory_axi':'ACLK','reset_100m':'slowest_sync_clk'}.items():
        connected(name,port,'ps7_0','FCLK_CLK0')
    connected('reset_100m','aux_reset_in','const_one','dout')
    connected('reset_100m','dcm_locked','const_one','dout')
    for key in ('C_EXT_RESET_HIGH','C_AUX_RESET_HIGH'): require(params(modules['reset_100m'])[key] == '0', 'Reset polarity changed')
    a4 = ET.parse(ROOT / 'build/deploy/a4_segmentation_2017_4_r1/a4_segmentation.hwh')
    old_modules = {m.get('FULLNAME').lstrip('/'):m for m in a4.findall('.//MODULE')}
    reused = ('axi_dma_0','point_control','loopback_fifo','memory_axi','reset_100m','const_one','const_zero','point_stage','segmentation_filter')
    module_changes={}
    for name in reused:
        a,b=params(old_modules[name]),params(modules[name])
        module_changes[name]={k:{'before':a.get(k),'after':b.get(k)} for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
        allowed_keys={'Component_Name'}|({'C_BASEADDR','C_HIGHADDR'} if name=='point_control' else set())
        require(set(module_changes[name])<=allowed_keys,'A4 functional IP parameters changed: '+name)
        if name=='point_control': require(b['C_BASEADDR']=='0x43C80000' and b['C_HIGHADDR']=='0x43C8FFFF','Wrong new GPIO range')
    require(info(build/'gaussian_guard_used.v') == info(ROOT/'rtl/core/retina_gaussian_guard.v'), 'Frame guard changed')
    require(info(build/'build_script_used.tcl') == info(ROOT/'vivado/scripts/build_b_integration.tcl'), 'Build source changed')
    require(not any(name.startswith(('iop_', 'trace_analyzer', 'audio_codec')) for name in modules), 'Pruned hardware still present')
    return {'status':'PASS_B_HOST_DERIVATION_AND_OFFICIAL_HWH_PARSER', 'board_status':'NOT_RUN',
        'video_objects_unchanged':len(before)-1,'one_generated_adapter_checked':'Exact predicted removal of redundant AXI4-to-LITE converter; preserved register slice and clock/reset nets',
        'a4_modules_functional_parameters_unchanged':list(reused),'instance_name_and_gpio_address_changes':module_changes, 'ps_changes':differences,
        'ip_dict':parser.ip_dict,'clock_dict':parser.clock_dict,'interrupt_controllers':parser.interrupt_controllers,
        'interrupt_pins':parser.interrupt_pins,'hwh':info(hwh),'bd':info(bd),'original_bd':info(original),
        'parser':info(ROOT/'references/PYNQ/v3.0.1/pynq/pl_server/hwh_parser.py'),
        'limit':'Host parser uses architecture constants only; real video driver construction and display require board execution'}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('build',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); report=check(args.build)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'], 'video objects:',report['video_objects_unchanged'])


if __name__=='__main__': main()
