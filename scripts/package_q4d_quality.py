"""New optional C7 PL package. Preserve old releases; never ship CPU medical code."""
import argparse, ast, json, shutil, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from pynq_q4d.protocol import REVISION, MODES, PNG_PROFILES, file_info, require, sha, validate_package, write_json
from package_q3_quality import startup_notebook as old_notebook
from q4d_board import validate_q4d
BASE=ROOT/'build/deploy/q3_full_quality_r1'
OUT=ROOT/'build/deploy/q4d_c7_experimental_r1'
UPLOAD=ROOT/'build/deploy/q4d_c7_upload_r1'
BUILD=ROOT/'build/q4d_detector_full_02'

def startup_notebook(digest):
    from package_q4_quality import startup_notebook as c5_notebook
    nb=c5_notebook(digest)
    for cell in nb['cells']:
        text=''.join(cell['source']).replace('q4','q4d').replace('Q4','Q4D').replace('q4d_c5','q4d_c7')
        cell['source']=text.splitlines(True)
    nb['cells'][0]['source']=['# Q4d · C7真实FPGA检测实验\n','原绿色局部特征和固定判别树均在PL执行；保留A/C2/C5。质量尚未验收，亮区误检及细血管仍可能残留。\n','固定20图×两尺寸×A/C2/C5/C7共160帧；C7分数阈值112，旧算法响应阈值28。两种阈值含义不同。无HDMI、无PS补掩膜。每框只运行一次，不要Run All。\n','关机后须从新的上传文件夹第1框开始，不能在没有前面上下文的新内核直接运行第5框。实验服务8090在第3框后启动，Jupyter管理页面仍9090。\n']
    instructions={
      4:['## 4. 自动核对160帧\n','逐帧打印Q4D_FRAME_SAVED，最后Q4D_COLLECTION_COMPLETE。20图、两尺寸、四算法输出SHA匹配仅代表实现一致，质量另审。期间不要在网页提交任务。\n'],
      5:['## 5. 浏览器视觉与参数对照\n','打开 http://192.168.2.99:8090/ 并Ctrl+F5，页眉须Q4d · C7。固定512、最终掩膜模式3、快速无损PNG。\n','按im0001、im0002、im0324顺序，每张先C5/阈值28运行，再C7/阈值112运行并截图，共6次。切换算法自动恢复对应推荐阈值，运行后检查硬件参数回读。观察亮边误检、细分支及跨亮区真血管。\n','保持网页前台：im0001/C7分别阈值96、128各运行一次；然后im0001/C5阈值20、36各运行一次。每次等图像更新。\n','再选im0001/C7、阈值112，点击预热3帧+测量20帧。保持网页前台至完成并截图。返回运行本状态框，预期completed=193、READY/IDLE、pending=0、无error或保留缓冲。额外点击记录照实保留，不为凑数重置。\n'],
      6:['## 6. 导出完整记录\n','应出现Q4D_RESULTS_READY。下载本Notebook同目录q4d_results_bundle.zip；普通网页会话导出不能代替固定队列包。\n'],
      7:['## 7. 安全结束并下载\n','应出现BROWSER_SERVICE_CLOSED_IDLE。Ctrl+S，再File → Download as → Notebook下载q4d_quality_start.ipynb，同时在文件列表下载q4d_results_bundle.zip。\n','红色报错或一分钟无进展：保留输出和内核，不重复执行、重新加载或释放失败缓冲。\n']}
    code_index=0
    for cell in nb['cells']:
        if cell['cell_type']=='markdown':
            for number,text in instructions.items():
                if ''.join(cell['source']).startswith('## '+str(number)+'.'):cell['source']=text
        else:
            code_index+=1
            if code_index==5:
                cell['source']=["if 'browser_context' not in globals():\n", "    raise RuntimeError('当前内核没有实验上下文，请回到运行第1–4框的同一Notebook；不要重复加载FPGA')\n", "print(browser_context['manager'].status())\n"]
            ast.parse(''.join(cell['source']),feature_version=(3,10))
    return nb

def build(host_only=False):
    global OUT, UPLOAD
    if host_only:
        # Independent application checks can run while actual RTL simulation
        # finishes. This uses the real routed pair, never a fabricated bit/HWH.
        # It is outside deploy, is not published, and cannot satisfy release gates.
        OUT=ROOT/'build/q4d_host_candidate_01/package'
        UPLOAD=ROOT/'build/q4d_host_candidate_01/upload'
    require(not OUT.exists() and not UPLOAD.exists(),'Preserve earlier package')
    hardware=json.loads((ROOT/'build/q4d_detector_hardware_check_01.json').read_bytes())
    require(hardware['status']=='PASS_Q4D_HOST_ROUTED_HARDWARE_NOT_BOARD','Routed hardware gate missing')
    if not host_only:
        from check_q4d_sharded_rtl import check as check_rtl
        check_rtl(ROOT/'build/q4d_sharded_rtl_02')
    guard=(ROOT/'build/q4d_guard_sim_01/session.log').read_text(encoding='utf-8-sig')
    require('Q4D_GUARD_UNIT_PASS:' in guard and 'Fatal:' not in guard and 'Error:' not in guard,'C7 control/observer guard gate missing')
    require((ROOT/'build/q4d_guard_sim_01/retina_detector_guard.v').read_bytes()==(ROOT/'rtl/core/retina_detector_guard.v').read_bytes(),'Guard source changed after test')
    reset=(ROOT/'build/q4d_detector_reset_session_01.log').read_text(encoding='utf-8-sig')
    require('Q4D_VENDOR_RESET_SIM_PASS' in reset and '\nERROR:' not in reset,'Actual vendor reset missing')
    protocol=json.loads((ROOT/'docs/q4d_board_protocol_r1.json').read_bytes())
    expected=json.loads((ROOT/'build/q4d_board_references_01/reference_hashes.json').read_bytes())
    require(expected['protocol_sha256']==sha((ROOT/'docs/q4d_board_protocol_r1.json').read_bytes()),'Fixed cohort changed')
    protocol['expected_output_sha256']=expected['expected_output_sha256']
    original=json.loads((BASE/'browser_manifest.json').read_bytes())
    OUT.mkdir(parents=True)
    for name in ('q4d_detector.bit','q4d_detector.hwh'):
        require(file_info(BUILD/'deploy'/name)==hardware['artifacts'][name],'Routed pair changed')
        shutil.copyfile(BUILD/'deploy'/name,OUT/name)
    shutil.copyfile(BASE/'a0_dma_board_test.py',OUT/'a0_dma_board_test.py')
    names={'q4d_detector.bit','q4d_detector.hwh','a0_dma_board_test.py','q4d_hardware_manifest.json'}
    for folder,dest in (('pynq_q4d','pynq_q4d'),('ui_q4d','ui')):
        (OUT/dest).mkdir()
        for p in (ROOT/folder).iterdir():
            if p.suffix in ('.py','.js','.css','.html'):
                name=dest+'/'+p.name;shutil.copyfile(p,OUT/name);names.add(name)
    for sizes in original['images'].values():
        for entry in sizes.values():
            for name in [entry['input']]+[v['path'] for v in entry['evaluation_only'].values()]:
                require(file_info(BASE/name)==original['artifacts'][name],'Original data changed')
                (OUT/name).parent.mkdir(exist_ok=True);shutil.copyfile(BASE/name,OUT/name);names.add(name)
    paired=['q4d_detector.bit','q4d_detector.hwh','a0_dma_board_test.py','pynq_q4d/quality_observer.py']
    write_json(OUT/'q4d_hardware_manifest.json',dict(revision='q4d_rq71_c7_experimental_r1',board_status='NOT_RUN',hardware_clock_hz=100000000,observer_identity=0x52513731,candidate=protocol['candidate'],routed_gate=file_info(ROOT/'build/q4d_detector_hardware_check_01.json'),artifacts={n:file_info(OUT/n) for n in paired},resources=hardware['resources'],wns_ns=hardware['wns_ns'],whs_ns=hardware['whs_ns']))
    browser=dict(revision=REVISION,board_status='NOT_RUN',phase='Q4D_C7_OPTIONAL_EXPERIMENT_NOT_QUALITY_ACCEPTANCE',images=original['images'],modes=MODES,algorithms=['A','C2','C5','C7'],threshold_range=[1,255],png_profiles=PNG_PROFILES,candidate=protocol['candidate']['id'],artifacts={n:file_info(OUT/n) for n in sorted(names)},scope=protocol['scope'],ps_role='DDR/DMA/config/readback/evaluate/display/export; no CPU vessel calculation',hardware=hardware['artifacts'])
    write_json(OUT/'browser_manifest.json',browser);validate_package(OUT)
    write_json(OUT/'q4d_protocol.json',protocol)
    shutil.copyfile(ROOT/'scripts/q4d_board.py',OUT/'q4d_board.py')
    names.update({'browser_manifest.json','q4d_protocol.json','q4d_board.py'})
    write_json(OUT/'q4d_manifest.json',dict(revision=REVISION,board_status='NOT_RUN',decision_commit='6c13730',artifacts={n:file_info(OUT/n) for n in sorted(names)}))
    validate_q4d(OUT);UPLOAD.mkdir(parents=True)
    bundle=UPLOAD/'q4d_c7_experimental_r1.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names|{'q4d_manifest.json'}):z.write(OUT/name,name)
    nb=startup_notebook(file_info(bundle)['sha256'])
    write_json(UPLOAD/'q4d_quality_start.ipynb',nb)
    if not host_only:write_json(ROOT/'notebooks/q4d_quality_start.ipynb',nb)
    return dict(status='HOST_CANDIDATE_ONLY_RTL_PENDING_DO_NOT_UPLOAD' if host_only else 'PACKAGE_READY_BOARD_NOT_RUN',fixed_frames=160,planned_words=26214400,zip_members=len(names)+1,upload={p.name:file_info(p) for p in UPLOAD.iterdir()})
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-only',action='store_true',help='Unpublished actual-bit candidate for software tests; RTL release gate remains required')
    print(json.dumps(build(parser.parse_args().host_only),indent=2))
