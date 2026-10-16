"""One-time, explicit derivative of verified C5 build/simulation infrastructure."""
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[1]

def derive(src,dst,replacements):
    target=ROOT/dst
    text=(ROOT/src).read_text(encoding='utf-8')
    for old,new in replacements:
        if old not in text:raise ValueError('Missing derivative anchor: '+old)
        text=text.replace(old,new)
    if target.exists():
        if target.read_text(encoding='utf-8')!=text:raise ValueError('Changed derivative: '+dst)
        return
    target.write_text(text,encoding='utf-8',newline='\n')

def main():
    derive('rtl/core/retina_refined_guard.v','rtl/core/retina_detector_guard.v',[
        ('retina_refined_guard','retina_detector_guard'),('52513531','52513731'),('RQ51','RQ71'),
        ('C5[4], reserved[7:5]=0','C5[4], C7[5], reserved[7:6]=0'),
        ('(cfg_control[7:5]==0) && (!cfg_control[4] || cfg_control[3])',
         '(cfg_control[7:6]==0) && (!cfg_control[4] || cfg_control[3]) && (!cfg_control[5] || (cfg_control[4] && cfg_control[3]))')])
    common=[('retina_refined_guard','retina_detector_guard'),('retina_refined_hls','retina_detector_hls'),
        ('q4_refined','q4d_detector'),('Q4_REFINED','Q4D_DETECTOR'),('RQ51','RQ71'),('A/C2/C5','A/C2/C5/C7')]
    derive('vivado/scripts/build_q4_refined.tcl','vivado/scripts/build_q4d_detector.tcl',common)
    derive('vivado/scripts/export_q4_refined_hls.tcl','vivado/scripts/export_q4d_detector_hls.tcl',[
        ('retina_refined_hls','retina_detector_hls')])
    derive('vivado/scripts/simulate_q4_reset.tcl','vivado/scripts/simulate_q4d_reset.tcl',[
        ('q4_refined','q4d_detector'),('Q4_VENDOR','Q4D_VENDOR')])
    derive('scripts/run_q4_refined_simulation.ps1','scripts/run_q4d_detector_simulation.ps1',[
        ('q4_refined_hls_02','q4d_detector_hls_01'),('prepare_q4_refined_vectors','prepare_q4d_detector_vectors'),
        ('retina_refined_guard','retina_detector_guard'),('retina_q4_refined_axis_tb','retina_q4d_detector_axis_tb'),
        ('q4_refined_axis_sim','q4d_detector_axis_sim'),('Q4_REFINED_AXIS_SIM_PASS','Q4D_DETECTOR_AXIS_SIM_PASS')])
    derive('tests/retina_q4_refined_axis_tb.sv','tests/retina_q4d_detector_axis_tb.sv',[
        ('retina_q4_refined_axis_tb','retina_q4d_detector_axis_tb'),('retina_refined_guard','retina_detector_guard'),
        ('retina_refined_hls','retina_detector_hls'),('52513531','52513731'),('Q4_REFINED','Q4D_DETECTOR'),
        ('Q4_ACTUAL','Q4D_ACTUAL'),('A/C2/C5 and thresholds1/27/28/29/255','A/C2/C5/C7 and thresholds1/27/28/29/96/112/255')])
    target=ROOT/'tests/retina_q4d_detector_axis_tb.sv'
    text=target.read_text(); cases=json.loads((ROOT/'build/q4d_detector_vectors_01/vector_manifest.json').read_bytes())['cases']
    for r in cases:
        text,n=re.subn(r'(?m)^(\s*'+str(r['case'])+r": cfg=32'h)[0-9a-f]+;",lambda m:m[1]+f'{r["control_word"]:08x};',text)
        assert n==1
    text=text.replace('prepare(256,1,9)','prepare(256,3,9)').replace('prepare(512,2,10)','prepare(512,3,10)')
    text=text.replace('if(k==128) cfg=cfg^32\'h0000f80f;',"if(k==128) cfg=cfg^32'h0000f83f;")
    target.write_text(text,encoding='utf-8',newline='\n')
    print('C7_BUILD_TOOLS_DERIVED_NOT_EXECUTED')

if __name__=='__main__':main()
