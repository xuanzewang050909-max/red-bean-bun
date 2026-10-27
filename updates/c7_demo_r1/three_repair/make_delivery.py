"""Seal closed artifacts with the project's existing copy/archive helpers."""
from physical_gate import *
import ast,subprocess,runpy,shutil

# Reuse the existing recording/archive implementation, not another seal framework.
legacy=runpy.run_path(str(ROOT/'single_repair/make_delivery.py'))
cp,entries,archive,bit_payload=(legacy[k] for k in ('cp','entries','archive','bit_payload'))
PKG=Path('D:/PLD/review_packages/C7_ThreeImage_Completion_Board_r1')
REVIEW=Path('D:/PLD/review_packages/C7_ThreeImage_Completion_Review_r1')

def write(p,obj):
    with Path(p).open('x',encoding='utf8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)

def textfile(p,text):
    with Path(p).open('x',encoding='utf8') as f:f.write(text)

def main():
    assert not PKG.exists() and not REVIEW.exists()
    gate=json.loads((OUT/'physical_gates.json').read_text());release=json.loads((OUT/'release_bit.json').read_text())
    assert gate['status']=='OFFLINE_PHYSICAL_GATES_PASS' and release['status']=='SAME_BUILD_BIT_GENERATED'
    for k in ('bit','dcp','hwh'):assert ref(release[k]['path'])==release[k]
    for f in json.loads((OUT/'implementation_seal.json').read_text())['files']:assert ref(f['path'])==f
    fields,bits_sha=bit_payload(release['bit']['path']);assert fields['b']=='7z020clg400'
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    selected=json.loads((OUT/'candidates/v13/record.json').read_text())['frames']
    rtl=json.loads((OUT/'rtl_receipt.json').read_text())['frames']
    cases=['noise_0','noise_1','noise_2']+list(IDS)
    profile={case:i%3 for i,case in enumerate(cases)}
    PKG.mkdir();payload=PKG/'payload';payload.mkdir()
    for p in (ROOT/'three_repair/board').iterdir():
        if p.is_file():cp(p,payload/p.name)
    for src,name in [(release['bit']['path'],'single_repair.bit'),(release['hwh']['path'],'single_repair.hwh'),
      ('D:/PLD/tmp/three_repair_ip_r1/drivers/valley_repair_v1_0/src/xvalley_repair_hw.h','registers.h'),
      (OUT/'frozen_algorithm.json','frozen_algorithm.json'),(OUT/'source_manifest.json','input_source_manifest.json'),
      (OUT/'native_c7_provenance.json','native_c7_provenance.json'),(OUT/'implementation_seal.json','implementation_seal.json'),
      (OUT/'physical_gates.json','physical_gates.json')]:cp(src,payload/name)
    assert re.search(r'#define\s+XVALLEY_REPAIR_CONTROL_ADDR_PROFILE_DATA\s+0x40\b',(payload/'registers.h').read_text())
    for name in ['C7_ThreeImage_Operator_r1.ipynb','BOARD_STEPS.md','verify_download.py']:cp(ROOT/'three_repair'/name,PKG/name)
    # Reference arrays bind every output plane, but are never copied into PL memory.
    for image in IDS:
        n=512*512;expected=np.load(payload/(image+'_expected.npy'),allow_pickle=False)
        with np.load(OUT/'selected'/image/'arrays.npz',allow_pickle=False) as a:
            for k,shift in [('final',0),('added',1),('uncertain',2)]:assert np.array_equal(((expected[5*n:6*n].reshape(512,512)>>shift)&1)!=0,a[k])
    for p in payload.glob('*.py'):ast.parse(p.read_text(encoding='utf8'),filename=str(p))
    nb=json.loads((PKG/'C7_ThreeImage_Operator_r1.ipynb').read_text(encoding='utf8'))
    cells=[c for c in nb['cells'] if c['cell_type']=='code']
    for c in cells:ast.parse(''.join(c['source']));assert c['execution_count'] is None and c['outputs']==[]
    assert 'AUTHORIZED=False' in ''.join(cells[2]['source'])
    manifest=dict(schema='three-image-board-package-v1',algorithm='three-image-vessel-completion-v1',clock_mhz=50,processing_shape=[512,512],
      hardware_release=gate['status'],board_status='BOARD_NOT_RUN',implementation_commit=commit,
      case_order=cases,image_cases=list(IDS),cases={c:dict(profile=profile[c]) for c in cases},default_hardware_access=False,
      expected_arrays='Post-execution host verification only; not transferred to PL',files=entries(payload))
    write(payload/'manifest.json',manifest)
    # Actual delivered offline verification cell; do not import PYNQ or execute start.
    command='from pathlib import Path\n'+''.join(cells[1]['source'])+'\nassert "pynq" not in sys.modules\n'
    p=subprocess.run([sys.executable,'-X','utf8','-B','-c',command],cwd=PKG,text=True,capture_output=True)
    write(OUT/'delivered_interface_test.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,hardware_operations=0,
      scope='Actual delivered second code cell; AST-checked other cells, never executed hardware cell'))
    assert p.returncode==0 and 'OFFLINE_PACKAGE_VERIFIED' in p.stdout,p.stderr
    from test_host_verifier import check
    check(PKG)
    boardzip=archive(PKG)
    # Test actual extraction cell in fresh host-only directory, then byte-verify copies.
    unziptest=OUT/'notebook_extract_test';unziptest.mkdir()
    cp(boardzip['path'],unziptest/PKG.with_suffix('.zip').name)
    p=subprocess.run([sys.executable,'-X','utf8','-B','-c',''.join(cells[0]['source'])+'\nimport sys\nassert "pynq" not in sys.modules'],cwd=unziptest,text=True,capture_output=True)
    assert p.returncode==0,p.stderr
    for name,r in entries(payload).items():assert ref(unziptest/'payload'/name)['sha256']==r['sha256']
    write(OUT/'notebook_extract_test/receipt.json',dict(status='DELIVERED_EXTRACTION_EXACT',returncode=p.returncode,stdout=p.stdout,board_operations=0))
    notebook_copy=Path('D:/PLD/review_packages/C7_ThreeImage_Operator_r1.ipynb')
    cp(PKG/'C7_ThreeImage_Operator_r1.ipynb',notebook_copy)
    write(OUT/'board_release_receipt.json',dict(status='READY_FOR_BOARD_AUTHORIZATION',zip=boardzip,payload_manifest=ref(payload/'manifest.json'),
      notebook=ref(notebook_copy),code_commit=commit,bit_configuration_sha256=bits_sha,board_status='BOARD_NOT_RUN'))
    status=dict(status='READY_FOR_BOARD_AUTHORIZATION',SOFTWARE='THREE_IMAGE_VISUAL_REPAIR_REVIEWED_WITH_LIMITATIONS',
      INTEGER='EXACT_15_CASES',RTL='EXACT_15_CASES',INTEGRATION='GENERATED_CONTROL_DDR_RESET_PASS',ROUTE='PASS',RELEASE='SAME_BUILD_PASS',
      DRC='0_ERRORS_0_CRITICAL_24_REVIEWED_WARNINGS',BOARD='BOARD_NOT_RUN',LATENCY_TARGET='UNSET',
      images=[dict(id=r['id'],old=r['old'],added=r['added'],final=r['old']+r['added'],uncertain=r['uncertain'],old_deleted=0) for r in selected],
      software_configurations=13,physical_builds=1,model_training=0,model_forwards=0,board_operations=0,gt_loaded=False,manual_hints=False,
      implementation_commit=commit,limitations=['Targeted three-image settings; no independent GT accuracy or complete topology guarantee',
        'Faint central branches and far ends remain incomplete; im0291 radial texture deliberately not fully selected',
        'Native-resolution texture mapped into existing512 letterbox; no live web or board update in this task',
        'DRC warnings and reset-aborts-invalid-data restrictions remain explicit; board timing not measured'])
    write(OUT/'status.json',status)
    timings={r['case']:r for r in rtl if r['case'] in IDS}
    hw=f'''# 三图共同硬件实现与成本

新独立精修overlay，xc7z020clg400-1，Vivado/HLS 2017.4。真实PS FCLK0 50MHz，IO PLL除数5×4，20ns；未改可信C7时钟。物理构建1/3次。没有连接板卡。

实际最终布线：LUT {gate['resources']['LUT']:g}/53200，FF {gate['resources']['FF']:g}/106400，BRAM36等价 {gate['resources']['BRAM36_equivalent']:g}/140，DSP {gate['resources']['DSP']:g}/220。setup WNS +{gate['wns_ns']}ns、hold +{gate['whs_ns']}ns、脉宽 +{gate['wpws_ns']}ns；8008条可路由网全部完成，路由错误0，未约束端点0。分类为TOOL_MEASURED，不是板测。

最终DRC错误/严重警告0；24条warning完整保留：15条DSP流水线性能建议、8条原AXI协议转换FIFO异步复位驱动BRAM控制、1条含15个未使用FIFO状态网的报告。详见drc_review.json。禁止在活跃事务中热复位；复位/异常后全部工作区无效，不能声称保留数据。未降级检查、添加虚假时序例外或屏蔽warning。

实测工具仿真：实际生成控制/存储互连、HLS核、生产复位链，39×47工作区10998字全等，含AW/W不同到达顺序、响应背压与DDR停顿。完整原生三图HLS RTL全等；25.890/25.936/25.911秒是以50MHz折算的仿真周期，不能当作实板/网页响应时间。最终routed DCP边界316位和提取复位单元释放/再复位均核验。

每512帧6×262144个uint32工作区=6MiB，加32字guard；每阶段32×512字环形缓存=64KiB。输入1MiB；各阶段顺序0、1、2、3×16、4。首阶段初始化数据，阶段/尺寸/profile锁定，最终仅op4成功后有效。无动态分配、递归或无界硬件循环。

RTL原生32位主口每帧读取5,767,168拍=22MiB，写5,242,880拍=20MiB，合计42MiB有效负载。非流水区域算术/BRAM访问是主要周期成本。32→64位HP0转换及AXI3拆包可能使总线搬运字节高于有效负载；集成小图计数读取23,162、写36,660个64位拍，不能把它线性外推为原生实测DDR吞吐。理论50MHz×64位=400MB/s是接口每拍上限，不是可持续DDR带宽或整机速度。

PS只分配、传输入口、配置profile、等待、核验并展示。现有设计采用HLS m_axi直达HP0工作区，不需要额外DMA IP；控制使用PS GP0。输入缓存flush、结果invalidate、磁盘持久化、加载位流和网页展示时间均NOT_MEASURED。6MiB初始化和6MiB结果读取也不能省略于系统预算；重复PS/PL覆盖与DDR回读不可重复记成独立算法阶段。三张结果缓冲和三个小图缓冲保留供失败审查，不自动释放。

三个profile只选有限常数，几何ROM仅滤波偏移；最终mask/完整血管坐标未进入ROM。参考数组仅核验，不写PL。共同bit/HWH/寄存器头来自同一构建。没有observer插接，无监测模块破坏AXI路径。端到端、DDR实带宽、真实板测和网页集成尚未验证；LATENCY_TARGET_UNSET。
'''
    textfile(OUT/'hardware_feasibility.md',hw)
    rows='\n'.join(f"|{r['id']}|{r['old']}|{r['added']}|{r['old']+r['added']}|{r['uncertain']}|0|" for r in selected)
    textfile(OUT/'report.md',f'''# 三图专项补标：上板前交付

状态 **READY_FOR_BOARD_AUTHORIZATION**；新候选 **BOARD_NOT_RUN**。实际实现、视觉审阅、整数/C/RTL核验、真实集成仿真及最终布线已完成。尚未修改测试网页或运行板卡。新分支c7-three-image-completion，源码提交{commit}，算法与结果封存于implementation_seal.json（e0053aa来源）。旧工程和证据保留。

## 原图、真实旧mask及显示问题

只处理im0004/im0291/im0319，原生700×605 RGB，原规则线性缩至512×443、上34下35补边，无旋转、重裁剪或色序变化。与封存输入逐值一致。T112真实C7 Q7/M7/FOV及会话身份已核对，未用软件重建C7。当前渲染源码公式与旧mask逐像素一致，隐藏mask像素0；本次没有把显示修复计成检测改善。该结论是本机源码/归档比对，不是新板端网页截图证明。没有读取GT、AH/VK、LOCK或旧质量门禁。

## 三图实际结果

|图像|真实旧mask|新增|最终|待确认候选|删除旧像素|
|---|---:|---:|---:|---:|---:|
{rows}

- im0004：补出左中、上中及右下多段原可见长分支；不是仅加粗。离旧线超过3像素的新增2501。弱末端及模糊分叉尚未完整。
- im0291：上方/右侧和左下延伸获得实质补充，离旧线超过3像素新增504。下部放射状纹理、弱中央支路难以可靠区分，采用更强方向支持，不把整片暗纹涂成血管；修补最保守。
- im0319：右下长弯曲段及其他零散支路被补出，离旧线超过3像素新增1010；中央很淡横向线、细小端部仍不完整。

13份登记配置均对三图运行并查看整图，最终9个预登记局部放大也已实看。未用新增像素最大值选方案。图像证据见selected/<id>/：original、old/added/final/uncertain mask、final_overlay、comparison、old_new_colors及三个局部PNG。绿为原标注、青为新增。待确认mask是未采纳弱候选，不代表全部漏检清单；不能把它们视为确认血管。没有可靠独立GT评估，不给Dice/准确率/召回率，不保证所有新增都正确或完全无拓扑风险。

## 冻结算法与实际验证

一个共同整数核心、三个显式profile。RGB局部平滑→多尺度多方向双侧暗线→强弱/方向证据→16次有界分支传播→有限邻域支持→旧mask并集。新增无需接触旧mask，支持整段独立分支。无神经网络训练、人工提示点、最终mask查表或PS代算。全部参数、舍入、边界和输入映射冻结。

Python整数与C实现：3张原生图和12个空/均匀/噪声/边界构造，最终/新增/待确认及中间分数等零差异，guard无越界。生成HLS RTL同15例逐字一致；本次不是直接直连fixture代替集成。真实生成控制和DDR互连集成小图10998字全等；最终DCP连接/复位核验通过。错误profile/尺寸/阶段入口拒绝且工作区不变。日志持久化、失败保留、授权前导入、已封存数据重载及交付Notebook只读入口实际测试通过。

物理构建1次，50MHz，WNS +6.089ns / hold +0.027ns / pulse +8.750ns，资源4237 LUT、4823 FF、13 BRAM、6 DSP。DRC 24条已审警告仍保留，未标成零警告；详见hardware_feasibility.md。位流只在门禁通过后由同一routed DCP生成，bit/HWH/驱动匹配。

首次HLS IP包装因2017.4日期revision整数溢出失败；保留原失败日志，仅对新包装副本改revision元数据，全部生成RTL逐字不变。没有更换算法、布线策略或频率，没有再次物理构建。

## 交付与停止

板测包：{boardzip['path']}，SHA256 {boardzip['sha256']}。上传用Notebook单独路径：{notebook_copy}。操作说明见BOARD_STEPS.md；默认AUTHORIZED=False，必须另行授权才执行硬件格。先3个小工作区profile检查，再依次三张实际图，任何异常停止，不自动重试。

当前保持BOARD_NOT_RUN、LATENCY_TARGET_UNSET。视觉结果是三图专项补标，弱端部及纹理歧义尚存，不声称医学标注或跨图泛化合格。所有历史失败结论保持。本任务在上板前停止，不连接或操作板卡。
''')
    (OUT/'PROGRESS.md').write_text('Completed: source/display audit;13 configs×3; finalv13 views; integer/C/RTL15cases; generated integration and routed reset; physicalbuild1/3 at50MHz; same-build release and offline Notebook verified. No board operations. Sources and reports sealed separately from active console. See report.md/status.json. Next action requires new board authorization.\n')
    # Compact reproducible review: selected outputs, source, exact input and actual reports.
    REVIEW.mkdir()
    for p in (ROOT/'three_repair').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.tcl','.hpp','.cpp','.md','.ipynb','.json','.npy'):
            cp(p,REVIEW/p.relative_to(ROOT))
    for folder in ('selected','input','display_audit'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():cp(p,REVIEW/p.relative_to(ROOT))
    for p in OUT.iterdir():
        if p.is_file() and p.suffix in ('.json','.md'):cp(p,REVIEW/p.relative_to(ROOT))
    for folder in ('integer','integration','entry_test','board_unit','host_verifier_test','notebook_extract_test'):
        for p in (OUT/folder).glob('*'):
            if p.is_file() and p.suffix in ('.json','.log','.jsonl','.tcl','.sv','.py'):cp(p,REVIEW/p.relative_to(ROOT))
    for p in (OUT/'candidates').glob('*/record.json'):cp(p,REVIEW/p.relative_to(ROOT))
    for p in (Path('D:/PLD/tmp/three_repair_ip_r1')/'hdl/verilog').iterdir():
        if p.is_file():cp(p,REVIEW/'generated_rtl'/p.name)
    cp(ROOT/'single_repair/make_delivery.py',REVIEW/'single_repair/make_delivery.py')
    # Include actual generated fabric dependencies and board descriptors, not the entire tool environment.
    for p in BD.rglob('*'):
        if p.is_file() and p.suffix in ('.v','.vhd','.bd','.xci','.xdc','.mem','.dat'):
            cp(p,REVIEW/'generated_bd'/p.relative_to(BD))
    boarddef=Path('D:/PLD/retina_c7_system/references/board/pynq-z2/pynq-z2')
    for p in boarddef.rglob('*'):
        if p.is_file() and p.suffix in ('.xml','.xdc'):cp(p,REVIEW/'board_definition'/p.relative_to(boarddef))
    cp(BUILD/'sim_export/single_repair/xsim/reset_actual_gate.v',REVIEW/'testbenches/reset_actual_gate.v')
    cp(BUILD/'routed_reset.v',REVIEW/'testbenches/routed_reset.v')
    for p in BUILD.iterdir():
        if p.is_file() and p.suffix in ('.rpt','.tsv','.txt','.xdc'):cp(p,REVIEW/'physical_reports'/p.name)
    for p in [BD/'synth/single_repair.v',BD/'hdl/single_repair_wrapper.v']:cp(p,REVIEW/'generated_top'/p.name)
    cp(release['dcp']['path'],REVIEW/'physical_reports/routed.dcp')
    cp(release['hwh']['path'],REVIEW/'physical_reports/single_repair.hwh')
    cp(payload/'registers.h',REVIEW/'physical_reports/registers.h')
    for p in [Path('D:/PLD/tmp/three_repair_rtl_r1/repair_tb.sv'),Path('D:/PLD/tmp/three_repair_rtl_r1/tb_axi_memory.sv'),BUILD/'sim_export/single_repair/xsim/integrated_tb.sv',BUILD/'sim_export/single_repair/xsim/tb_hp0_memory.sv',Path('D:/PLD/tmp/three_repair_routed_reset_new/routed_reset_tb.sv')]:cp(p,REVIEW/'testbenches'/p.name)
    cp(Path('D:/PLD/tmp/three_repair_hls_r1/solution/syn/report/valley_repair_csynth.rpt'),REVIEW/'physical_reports/valley_repair_csynth.rpt')
    # Only completed subprocess logs with recorded SHA, never the active delivery console.
    logpaths=set()
    for p in OUT.rglob('*.json'):
        if 'notebook_extract_test' in p.parts:continue
        def visit(x):
            if isinstance(x,dict):
                if set(('path','sha256','bytes'))<=set(x) and str(x['path']).endswith('.log'):
                    src=Path(x['path']);assert ref(src)==x;logpaths.add(src)
                for value in x.values():visit(value)
            elif isinstance(x,list):
                for value in x:visit(value)
        visit(json.loads(p.read_text()))
    for p in sorted(logpaths):cp(p,REVIEW/'logs'/p.name)
    write(REVIEW/'source_copy_manifest.json',dict(copies=legacy['COPIES'],implementation_commit=commit,archive_helper=ref(ROOT/'single_repair/make_delivery.py')))
    write(REVIEW/'delivery_manifest.json',dict(schema='closed-file-review-v1',implementation_commit=commit,files=entries(REVIEW),board_package=boardzip,
      manifest_excludes_itself=True,archive_receipt_outside=True,active_console_excluded=True))
    reviewzip=archive(REVIEW)
    write(OUT/'delivery_manifest.json',dict(status='SEALED_AND_ZIP_VERIFIED',board=boardzip,review=reviewzip,files=entries(OUT/'selected'),
      notebook=ref(notebook_copy),review_manifest=ref(REVIEW/'delivery_manifest.json'),implementation_commit=commit,
      note='Full source/result identities in review/delivery_manifest; outer ZIP SHA outside ZIP; no self-hash cycle'))
    print(json.dumps(dict(status=status['status'],board=boardzip,review=reviewzip,notebook=str(notebook_copy)),indent=2))

if __name__=='__main__':main()
