"""Gate the real B host build. No fake board/FPS/visual PASS is produced."""
import argparse
import copy
import difflib
import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import check_b_hardware as hardware
from a1_point_board_test import notebook_code_hash
from b_integration_board_test import FIXED,NOTEBOOK,REVISION,validate_b_package

ROOT=Path(__file__).resolve().parents[1]
info=hardware.info
require=hardware.require


def read(path):
    return Path(path).read_text(encoding='utf-8-sig',errors='replace')


def timing_gate(timing,drc,utilization):
    for marker in ('All user specified timing constraints are met.',
                   'There are 0 register/latch pins with no clock.',
                   'There are 0 pins that are not constrained for maximum delay.',
                   'There are 0 combinational loops in the design.'):
        require(marker in timing,'Missing timing check: '+marker)
    match=re.search(r'WNS\(ns\).*\n\s*-+.*\n\s*([^\n]+)',timing)
    require(match is not None,'Missing routed timing')
    values=match.group(1).split()
    require(len(values)==12,'Unexpected timing columns')
    require(all(float(values[i])>=0 for i in (0,4,8)) and all(int(values[i])==0 for i in (2,6,10)),'Timing violation')
    require(not re.search(r'\|\s*(?:Error|Critical Warning)\s*\|',drc,re.I),'DRC error/critical warning')
    warnings=re.findall(r'\|\s*([\w-]+)\s*\|\s*Warning\s*\|',drc)
    require(warnings==['DPIP-1','DPOP-1','DPOP-2','RTSTAT-10'],'Unreviewed DRC warning')
    # Every DSP advisory is restricted to the frozen A4 divider or the two
    # unchanged official HLS color matrices, all of which meet routed timing.
    for line in drc.splitlines():
        if line.startswith('DSP '):
            require(any(p in line for p in ('system_i/segmentation_filter/inst/response_carrier_U0/',
                'system_i/video/hdmi_in/color_convert/inst/','system_i/video/hdmi_out/color_convert/inst/')),'Unreviewed DSP location')
    counts={}
    for name in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):
        value=re.search(r'\|\s*'+name+r'\s*\|\s*(\d+(?:\.\d+)?)\s*\|',utilization)
        require(value is not None,'Missing utilization: '+name)
        counts[name]=float(value.group(1))
    return {'wns_ns':float(values[0]),'whs_ns':float(values[4]),'wpws_ns':float(values[8]),
        'resources':counts,'reviewed_drc_warnings':warnings,'board_status':'NOT_RUN'}


def constraints_gate(source,target):
    selected=[]
    for line in source.splitlines():
        if line.strip().startswith('set_property') and any(prefix in line for prefix in
            ('sws_2bits','btns_4bits','leds_4bits','rgbleds_6bits','hdmi_in_','hdmi_out_')):
            selected.append(line.strip())
    actual=[line.strip() for line in target.splitlines() if line.strip() and not line.strip().startswith('#')]
    clock='create_clock -period 8.333333 -waveform {0.000 4.1666665} [get_ports hdmi_in_clk_p]'
    require(len(selected)==36,'Expected original Z2 GPIO/HDMI pins')
    require(Counter(actual)==Counter(selected+[clock]),'Changed retained board pin or unreviewed constraint')
    return {'original_gpio_hdmi_pin_assignments_unchanged':36,'rx_period_ns':8.333333,
        'external_serial_clock_policy':'Only inapplicable unconditional rgb2dvi_clocks.xdc excluded; actual MMCM/BUFR clocks auto-derived'}


def compiled_sources(build):
    """Compare actual project RTL with the immutable, already tested IP exports."""
    project=build/'b_integration.srcs/sources_1/bd/system'
    a4=json.loads(read(ROOT/'results/a4_segmentation_2017_4/release_manifest.json'))
    baseline=ROOT/'build/deploy/a4_segmentation_2017_4_r1'
    for name,recorded in a4['artifacts'].items():
        require(info(baseline/name)==recorded,'A4 release changed: '+name)
    exports={'a4':ROOT/'build/a4_hls_02/solution1/impl/ip/hdl/verilog'}
    for name in ('color_convert','pixel_pack','pixel_unpack'):
        exports[name]=ROOT/'build/official_v2.2.1/boards/ip/hls'/name/'solution1/impl/ip/hdl/verilog'
    matches={}
    for group,folder in exports.items():
        require(folder.is_dir(),'Missing official HLS export '+str(folder))
        sources=sorted(p for p in folder.iterdir() if p.suffix in ('.v','.dat'))
        require(sources,'Empty compiled IP '+group)
        records={}
        for source in sources:
            expected=info(source)
            if group=='a4':
                require(expected==a4['hls_provenance']['generated_verilog_and_rom'][source.name],'A4 RTL export changed')
            copies=list(project.rglob(source.name))
            require(copies,'Source absent from actual B project '+source.name)
            require(all(info(p)==expected for p in copies),'Project differs from frozen export '+source.name)
            records[source.name]={'source':str(source.relative_to(ROOT)).replace('\\','/'),**expected,
                'actual_project_copies':[str(p.relative_to(build)).replace('\\','/') for p in copies]}
        matches[group]=records
    for name in ('a0_dma_board_test.py','a1_point_board_test.py','a2_gaussian_board_test.py','a3_background_board_test.py','a4_segmentation_board_test.py'):
        require(info(ROOT/'scripts'/name)==a4['artifacts'][name],'Measured transfer/helper changed: '+name)
    for name in ('rtl/core/retina_gaussian_guard.v','hls/retina_segmentation_hls.cpp','hls/contrast_lut_values.h'):
        require(info(ROOT/name)==a4['source_files'][name],'Frozen A4 source changed: '+name)
    for folder,top in (('rgb2dvi_v1_2','rgb2dvi.vhd'),('dvi2rgb_v1_7','dvi2rgb.vhd'),
        ('axi_dynclk_v1_0','axi_dynclk.vhd'),('color_swap_1.0','color_swap.v')):
        base=ROOT/'references/PYNQ/v2.2.1/boards/ip'/folder
        source_tops=list(base.rglob(top));require(len(source_tops)==1,'Ambiguous pinned video top '+top)
        src=source_tops[0].parent
        require(src.is_dir(),'Missing pinned video RTL: '+folder)
        roots=sorted({p.parent for p in project.rglob(top)})
        require(roots,'Pinned video RTL absent from actual project: '+top)
        records={}
        for source in sorted(p for p in src.rglob('*') if p.suffix in ('.v','.vhd','.xdc')):
            relative=source.relative_to(src);expected=info(source)
            # Vivado separates shared RTL from instance-scoped XDC files.
            copies=list(project.rglob(source.name)) if source.suffix=='.xdc' else [p/relative for p in roots]
            require(copies and all(info(p)==expected for p in copies),'Pinned video RTL/constraint changed: '+str(relative))
            records[str(relative)]={**expected,'actual_project_copies':[str(p.relative_to(build)).replace('\\','/') for p in copies]}
        matches[folder]=records
    originals={}
    for tag in ('v2.2.1','v3.0.1'):
        base=ROOT/'references/PYNQ'/tag;manifest=json.loads(read(base/'SOURCE_MANIFEST.json'))
        for record in manifest['files']:
            require(info(base/record['path'])=={k:record[k] for k in ('bytes','sha256')},'Fixed reference modified: '+tag+'/'+record['path'])
        originals[tag]={'commit':manifest['commit'],'files_checked':len(manifest['files']),'manifest':info(base/'SOURCE_MANIFEST.json')}
    return {'status':'PASS_FROZEN_A4_AND_OFFICIAL_VIDEO_GENERATED_RTL_BYTE_COMPARISON',
        'reused_a4_csim_rtl_and_board_evidence':'results/a4_segmentation_2017_4/release_manifest.json and board_execution_2026-10-12; no new algorithm synthesis',
        'exports':matches,'original_snapshots_unchanged':originals,'a4_manifest':info(baseline/'a4_manifest.json')}


def build_gate(build,results,reset_sim):
    log=read(results/'build_05.log')
    require('\nB_BITSTREAM_TIMING_CHECKED_BOARD_NOT_RUN' in log and not re.search(r'^ERROR:',log,re.M),'Incomplete/failed full B build')
    critical=[s.strip() for s in log.splitlines() if s.startswith('CRITICAL WARNING:')]
    reviewed={f'CRITICAL WARNING: [PSU-{i+1}]  Parameter : PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_{i} has negative value {value} . PS DDR interfaces might fail when entering negative DQS skew values.'
        for i,value in enumerate(('-0.051','-0.006','-0.009','-0.033'))}
    require(set(critical)<=reviewed,'Unreviewed critical warnings: '+str(set(critical)-reviewed))
    checks=timing_gate(read(build/'timing_summary.rpt'),read(build/'drc.rpt'),read(build/'utilization.rpt'))
    checks['reviewed_critical_warnings']=dict(Counter(critical))
    for snapshot,source in (('build_script_used.tcl','vivado/scripts/build_b_integration.tcl'),
        ('gaussian_guard_used.v','rtl/core/retina_gaussian_guard.v'),('constraints_used.xdc','vivado/constraints/b_integration.xdc')):
        require(info(build/snapshot)==info(ROOT/source),'Build input changed: '+source)
    policy=read(build/'external_serial_clock_constraints.txt')
    require('USED_IN_SYNTHESIS=0' in policy and 'USED_IN_IMPLEMENTATION=0' in policy,'Inapplicable RGB clock XDC still used')
    xpr=read(build/'b_integration.xpr')
    require('constraints_used.xdc' in xpr,'Constraints snapshot not referenced')
    excluded=[]
    for node in ET.fromstring(xpr).findall('.//CompFileExtendedInfo'):
        for attr in node.findall('Attr'):
            if attr.get('Name') in ('UsedInSynthesis','UsedInImplementation') and attr.get('Val')=='0':
                excluded.append((node.get('CompFileName'),node.get('FileRelPathName'),attr.get('Name')))
    require(set(excluded)=={('system_rgb2dvi_0_0.xci','src/rgb2dvi_clocks.xdc','UsedInSynthesis'),
        ('system_rgb2dvi_0_0.xci','src/rgb2dvi_clocks.xdc','UsedInImplementation')},'Other IP constraints excluded')
    checks['constraint_derivation']=constraints_gate(read(ROOT/'references/PYNQ/v2.2.1/boards/Pynq-Z2/base/vivado/constraints/top.xdc'),read(build/'constraints_used.xdc'))
    initial=json.loads(read(results/'initial_sources.json'))
    prepared='build\\official_v2.2.1\\boards\\Pynq-Z2\\base\\base\\base.srcs\\sources_1\\bd\\system\\system.bd'
    require(info(ROOT/prepared)==info(build/'original_official_system.bd')==initial['files'][prepared],'Original prepared Base changed')
    skew=read(build/'bus_skew.rpt')
    require('VIOLATED' not in skew and 'Timing constraints are not met' not in skew,'Bus skew violation')
    clocks=read(build/'clocks.rpt')
    require('rgb2dvi_0/U0/SerialClk' not in clocks,'Invalid old generated clock still present')
    for name in ('clk_fpga_0','clk_fpga_1','hdmi_in_clk_p','axi_dynclk_0_PXL_CLK_O'):
        require(name in clocks,'Required video/system clock missing '+name)
    reset_log=reset_sim/'b_reset_sim.sim/sim_1/behav/xsim/simulate.log'
    reset=read(reset_log)
    require('B_RESET_SIM_PASS:' in reset and 'Fatal:' not in reset and 'ERROR:' not in reset,'Actual generated reset simulation failed')
    require(info(reset_sim/'reset_tb_used.sv')==info(ROOT/'tests/b_reset_tb.sv'),'Reset bench changed')
    checks['actual_generated_reset_simulation']=info(reset_log)
    tests=read(results/'host_tests_release.log')
    count=re.search(r'Ran (\d+) tests',tests)
    require(count and int(count.group(1))>=16 and '\nOK' in tests and 'FAILED' not in tests,'B host fault tests incomplete')
    testsources=json.loads(read(results/'host_test_sources.json'))
    for path,recorded in testsources['sources'].items():require(info(ROOT/path)==recorded,'Source changed after host tests: '+path)
    checks['host_test_count']=int(count.group(1))
    return checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('build',type=Path);parser.add_argument('reset_sim',type=Path)
    parser.add_argument('destination',type=Path);parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args();build=args.build;results=args.results
    require(not args.destination.exists() and not (results/'release_manifest.json').exists(),'Refusing to overwrite a release')
    metadata=hardware.check(build);checks=build_gate(build,results,args.reset_sim);reuse=compiled_sources(build)
    notebook=ROOT/'notebooks'/NOTEBOOK;nb=json.loads(read(notebook));cells=[c for c in nb['cells'] if c['cell_type']=='code']
    require(len(cells)==9 and all(c['execution_count'] is None and not c['outputs'] for c in cells),'Clean nine-stage notebook required')
    mappings={name:ROOT/'scripts'/name for name in FIXED if name.endswith('.py')}
    mappings.update({name:ROOT/'build/deploy/a4_segmentation_2017_4_r1'/name for name in FIXED if name.endswith('.npy')})
    mappings.update({name:build/'deploy'/name for name in FIXED if name.endswith(('.bit','.hwh'))})
    mappings[NOTEBOOK]=notebook
    require(info(mappings['b_integration.bit'])==info(build/'b_integration.runs/impl_1/system_wrapper.bit'),'Wrong actual routed bitstream')
    require(info(mappings['b_integration.hwh'])==metadata['hwh'],'Wrong actual HWH')
    source_files={p:info(ROOT/p) for p in ('scripts/package_b.py','scripts/check_b_hardware.py','scripts/b_integration_board_test.py',
        'scripts/build_b_notebook.py','tests/test_b_integration.py','tests/b_reset_tb.sv','vivado/scripts/build_b_integration.tcl',
        'vivado/scripts/simulate_b_reset.tcl','vivado/constraints/b_integration.xdc','notebooks/b_integration_check.ipynb',
        'docs/b_integration_validation_steps.md','docs/b_integration_reuse_audit.md')}
    ips=metadata['ip_dict'];names=('axi_dma_0','point_control','video/axi_vdma','video/hdmi_out/pixel_unpack',
        'video/hdmi_out/color_convert','video/hdmi_out/frontend/axi_dynclk','video/hdmi_out/frontend/vtc_out')
    manifest={'revision':REVISION,'host_status':'PASS_ROUTED_TIMING_DRC_REAL_RESET_FROZEN_RTL_DERIVATION_AND_HOST_FAULT_TESTS',
        'board_status':'NOT_RUN','vivado':'2017.4','pynq_target':'3.0.1','scope':'Same B bitstream frozen M0 algorithm A + official HDMI; board digital/display/FPS pending; no clinical quality PASS',
        'build_directory':str(build.resolve()),'host_checks':checks,'reuse_provenance':reuse,
        'control_addresses':{n:hex(ips[n]['phys_addr']) for n in names},
        'driver_metadata':{n:{'type':ips[n]['type'],'parameters':ips[n]['parameters']} for n in names},
        'test_contract':{'validation_frames':61,'benchmark_frames':309,'total_frames':370,'words':70647808,
            'benchmark_groups':[[256,False],[512,False],[512,True]],'timed_frames_per_group':100,'warmup_per_group':3,'display_submissions':105},
        'timing_meaning':'Monotonic perf_counter_ns completed transactions and whole checked loops; not PL-only cycles or measured display Hz',
        'source_files':source_files,'notebook_validation':{'algorithm':'sha256-code-cells-v1','sha256':notebook_code_hash(nb),'code_cells':9},
        'failed_attempts':'failure_record.json preserves incomplete builds, rejected 04 constraints and initial coarse host timer test; only build 05 is supplied'}
    with tempfile.TemporaryDirectory() as tmp:
        staged=Path(tmp)
        for name,path in mappings.items():shutil.copyfile(path,staged/name)
        guide=read(ROOT/'docs/b_integration_validation_steps.md')+'\n\n第三方许可（原文）\n'
        for name in ('LICENSE','THIRD_PARTY_LIC'):
            guide+='\n'+read(ROOT/'references/PYNQ/v2.2.1'/name)+'\n'
        (staged/'使用说明.txt').write_text(guide,encoding='utf-8',newline='\n')
        require(set(p.name for p in staged.iterdir())==FIXED|{NOTEBOOK},'Unexpected release inventory')
        manifest['artifacts']={p.name:info(p) for p in sorted(staged.iterdir())}
        payload=json.dumps(manifest,indent=2,ensure_ascii=False)+'\n';(staged/'b_manifest.json').write_text(payload,encoding='utf-8',newline='\n')
        validate_b_package(staged,manifest)
        saved=copy.deepcopy(nb)
        for cell in saved['cells']:
            if cell['cell_type']=='code':cell['execution_count']=1;cell['outputs']=[{'name':'stdout','output_type':'stream','text':'HOST SAVE METADATA PROBE ONLY - NOT BOARD EVIDENCE\n'}]
        (staged/NOTEBOOK).write_text(json.dumps(saved),encoding='utf-8');validate_b_package(staged,manifest)
        shutil.copyfile(notebook,staged/NOTEBOOK);validate_b_package(staged,manifest)
        args.destination.mkdir(parents=True)
        for path in staged.iterdir():shutil.copyfile(path,args.destination/path.name)
    for name in ('timing_summary.rpt','drc.rpt','utilization.rpt','clocks.rpt','clock_interaction.rpt','bus_skew.rpt',
        'check_timing.rpt','configuration.txt','reconstructed_bd.tcl','original_official_bd.tcl','pruning.txt',
        'build_script_used.tcl','gaussian_guard_used.v','constraints_used.xdc','external_serial_clock_constraints.txt'):
        shutil.copyfile(build/name,results/name)
    shutil.copyfile(build/'original_official_system.bd',results/'original_official_system.bd')
    shutil.copyfile(build/'b_integration.srcs/sources_1/bd/system/system.bd',results/'generated_system.bd')
    shutil.copyfile(args.reset_sim/'reset_tb_used.sv',results/'reset_tb_used.sv')
    shutil.copyfile(args.reset_sim/'b_reset_sim.sim/sim_1/behav/xsim/simulate.log',results/'vendor_reset_simulate.log')
    (results/'host_metadata_final.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    (results/'release_manifest.json').write_text(payload,encoding='utf-8',newline='\n')
    (results/'release_integrity.json').write_text(json.dumps({'status':'PASS_B_HOST_RELEASE_AND_SAVED_NOTEBOOK_VALIDATION','board_status':'NOT_RUN',
        'package_files':{p.name:info(p) for p in sorted(args.destination.iterdir())}},indent=2)+'\n',encoding='utf-8')
    diff=''.join(difflib.unified_diff(read(ROOT/'references/PYNQ/v2.2.1/boards/Pynq-Z2/base/vivado/constraints/top.xdc').splitlines(True),
        read(build/'constraints_used.xdc').splitlines(True),fromfile='pinned-official-top.xdc',tofile='B-constraints-used.xdc'))
    (results/'constraints_derivation_final.diff').write_text(diff,encoding='utf-8',newline='\n')
    print('B_RELEASE_READY_HOST_ONLY_BOARD_PENDING',args.destination)


if __name__=='__main__':main()
