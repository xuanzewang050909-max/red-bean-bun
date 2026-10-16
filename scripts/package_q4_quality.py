"""New optional C5 PL package. Preserve old releases; never ship CPU medical code."""
import ast, json, shutil, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_q4.protocol import REVISION, MODES, PNG_PROFILES, file_info, require, sha, validate_package, write_json
from package_q3_quality import startup_notebook as old_notebook
from q4_board import validate_q4
BASE=ROOT/'build/deploy/q3_full_quality_r1'
OUT=ROOT/'build/deploy/q4_c5_experimental_r1'
UPLOAD=ROOT/'build/deploy/q4_c5_upload_r1'
BUILD=ROOT/'build/q4_refined_full_01'

def startup_notebook(digest):
    nb=old_notebook(digest)
    for c in nb['cells']:
        s=''.join(c['source']).replace('q3_full_quality_r1','q4_c5_experimental_r1').replace('q3','q4').replace('Q3','Q4').replace('pynq_w4a','pynq_q4').replace('paired W2','paired Q4')
        if c['cell_type']=='markdown':s=s.replace('80帧','120帧').replace('共80','共120').replace('82','151')
        # The IP port is 8090, not a frame count.
        s=s.replace('1212090','8090').replace('12090','8090')
        c['source']=s.splitlines(True)
    nb['cells'][0]['source']=['# Q4 · C5真实FPGA实验对比\n','新增多尺度暗线支持和有限连接，保留A/C2。C5是折中实验，亮区误检并未完全解决，原严格质量门槛FAIL保留。\n','固定20图×两尺寸×A/C2/C5共120帧；逐帧核对真实DMA输出SHA。无HDMI，无PS分割或补线。每框只运行一次，不要Run All。\n']
    for c in nb['cells']:
        if c['cell_type']!='markdown':continue
        t=''.join(c['source'])
        if t.startswith('## 4.'):
            c['source']=['## 4. 自动核对120帧\n','运行后逐帧打印Q4_FRAME_SAVED，最后Q4_COLLECTION_COMPLETE。每帧实际DMA输出SHA须匹配独立参考；全匹配不等于医学质量通过。期间不要在网页提交任务。\n']
        elif t.startswith('## 5.'):
            c['source']=['## 5. 浏览器视觉与参数对照\n','打开 http://192.168.2.99:8090/ 并Ctrl+F5，页眉须Q4。固定512、最终掩膜模式3、阈值28、快速无损PNG。\n','按im0001、im0002、im0324顺序，每张先C2运行、再C5运行并截图，共6次。检查中央亮斑附近、主要血管与细血管；C5仅最终模式3启用。\n','再选im0001/C5，阈值20运行一次、36运行一次；观察参数回读与图像变化。恢复28，点击预热3帧+测量20帧，保持网页前台，结束后截图。\n','返回运行状态框：预期completed=151、READY/IDLE、pending=0、无error/保留缓冲。多点击产生的真实任务也保留，不要为凑次数重置。\n']
        elif t.startswith('## 6.'):
            c['source']=['## 6. 导出完整记录\n','应出现Q4_RESULTS_READY。下载本Notebook同目录q4_results_bundle.zip；不能用普通网页会话导出代替，它不包含固定队列核对记录。\n']
        elif t.startswith('## 7.'):
            c['source']=['## 7. 安全结束并下载\n','应出现BROWSER_SERVICE_CLOSED_IDLE。Ctrl+S，再File → Download as → Notebook下载q4_quality_start.ipynb，同时下载q4_results_bundle.zip。\n','若红色报错或一分钟无新进展：保留输出和内核，不重复执行、不重新加载、不释放失败缓冲。\n']
    for c in nb['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']),feature_version=(3,10))
    return nb

def build():
    require(not OUT.exists() and not UPLOAD.exists(),'Preserve earlier package')
    hardware=json.loads((ROOT/'build/q4_refined_hardware_check_01.json').read_bytes())
    require(hardware['status']=='PASS_Q4_HOST_ROUTED_HARDWARE_NOT_BOARD','Routed hardware gate missing')
    rtl=(ROOT/'build/q4_refined_axis_sim_02/xsim.log').read_text()
    require('Q4_REFINED_AXIS_SIM_PASS:' in rtl and 'Fatal:' not in rtl and 'Error:' not in rtl,'Actual generated RTL gate missing')
    reset=(ROOT/'build/q4_refined_reset_session_01.log').read_text(encoding='utf-8-sig')
    require('Q4_VENDOR_RESET_SIM_PASS' in reset and '\nERROR:' not in reset,'Actual vendor reset missing')
    protocol=json.loads((ROOT/'docs/q4_board_protocol_r1.json').read_bytes())
    expected=json.loads((ROOT/'build/q4_board_hashes_01.json').read_bytes())
    require(expected['protocol_sha256']==sha((ROOT/'docs/q4_board_protocol_r1.json').read_bytes()),'Fixed cohort changed')
    protocol['expected_output_sha256']=expected['expected_output_sha256']
    original=json.loads((BASE/'browser_manifest.json').read_bytes())
    OUT.mkdir(parents=True)
    for name in ('q4_refined.bit','q4_refined.hwh'):
        require(file_info(BUILD/'deploy'/name)==hardware['artifacts'][name],'Routed pair changed')
        shutil.copyfile(BUILD/'deploy'/name,OUT/name)
    shutil.copyfile(BASE/'a0_dma_board_test.py',OUT/'a0_dma_board_test.py')
    names={'q4_refined.bit','q4_refined.hwh','a0_dma_board_test.py','q4_hardware_manifest.json'}
    for folder,dest in (('pynq_q4','pynq_q4'),('ui_q4','ui')):
        (OUT/dest).mkdir()
        for p in (ROOT/folder).iterdir():
            if p.suffix in ('.py','.js','.css','.html'):
                name=dest+'/'+p.name;shutil.copyfile(p,OUT/name);names.add(name)
    for sizes in original['images'].values():
        for entry in sizes.values():
            for name in [entry['input']]+[v['path'] for v in entry['evaluation_only'].values()]:
                require(file_info(BASE/name)==original['artifacts'][name],'Original data changed')
                (OUT/name).parent.mkdir(exist_ok=True);shutil.copyfile(BASE/name,OUT/name);names.add(name)
    paired=['q4_refined.bit','q4_refined.hwh','a0_dma_board_test.py','pynq_q4/quality_observer.py']
    write_json(OUT/'q4_hardware_manifest.json',dict(revision='q4_rq51_c5_experimental_r1',board_status='NOT_RUN',hardware_clock_hz=100000000,observer_identity=0x52513531,candidate=protocol['candidate'],routed_gate=file_info(ROOT/'build/q4_refined_hardware_check_01.json'),artifacts={n:file_info(OUT/n) for n in paired},resources=hardware['resources'],wns_ns=hardware['wns_ns'],whs_ns=hardware['whs_ns']))
    browser=dict(revision=REVISION,board_status='NOT_RUN',phase='Q4_C5_OPTIONAL_EXPERIMENT_NOT_QUALITY_ACCEPTANCE',images=original['images'],modes=MODES,algorithms=['A','C2','C5'],threshold_range=[1,255],png_profiles=PNG_PROFILES,candidate=protocol['candidate']['id'],artifacts={n:file_info(OUT/n) for n in sorted(names)},scope=protocol['scope'],ps_role='DDR/DMA/config/readback/evaluate/display/export; no CPU vessel calculation',hardware=hardware['artifacts'])
    write_json(OUT/'browser_manifest.json',browser);validate_package(OUT)
    write_json(OUT/'q4_protocol.json',protocol)
    shutil.copyfile(ROOT/'scripts/q4_board.py',OUT/'q4_board.py')
    names.update({'browser_manifest.json','q4_protocol.json','q4_board.py'})
    write_json(OUT/'q4_manifest.json',dict(revision=REVISION,board_status='NOT_RUN',decision_commit='237d58d',artifacts={n:file_info(OUT/n) for n in sorted(names)}))
    validate_q4(OUT);UPLOAD.mkdir(parents=True)
    bundle=UPLOAD/'q4_c5_experimental_r1.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names|{'q4_manifest.json'}):z.write(OUT/name,name)
    nb=startup_notebook(file_info(bundle)['sha256'])
    write_json(UPLOAD/'q4_quality_start.ipynb',nb);write_json(ROOT/'notebooks/q4_quality_start.ipynb',nb)
    return dict(status='PACKAGE_READY_BOARD_NOT_RUN',fixed_frames=120,planned_words=19660800,zip_members=len(names)+1,upload={p.name:file_info(p) for p in UPLOAD.iterdir()})
if __name__=='__main__':print(json.dumps(build(),indent=2))
