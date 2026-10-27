"""Package closed repair evidence using the existing copy/archive/seal tools."""
from reset_repair import *
from make_delivery import cp,entries,archive,COPIES
import ast, shutil

PKG=Path('D:/PLD/review_packages/C7_SingleImage_Repair_Board_r2')
REVIEW=Path('D:/PLD/review_packages/C7_SingleImage_Repair_ResetFix_Review_r1')
OLDPKG=Path('D:/PLD/review_packages/C7_SingleImage_Repair_Board_r1')

def main():
    assert not PKG.exists() and not REVIEW.exists()
    gate=json.loads((FIX/'physical_gates.json').read_text())
    release=json.loads((FIX/'release_bit.json').read_text())
    assert gate['status']=='OFFLINE_PHYSICAL_GATES_PASS' and gate['physical_builds']==2
    assert release['status']=='SAME_BUILD_BIT_GENERATED'
    for k in ['bit','dcp','hwh']:assert ref(release[k]['path'])==release[k]
    old=json.loads((OLDPKG/'payload/manifest.json').read_text())
    for name,r in old['files'].items():
        p=OLDPKG/'payload'/name
        assert p.stat().st_size==r['bytes'] and ref(p)['sha256']==r['sha256'],name
    sources=json.loads((FIX/'source_binding.json').read_text())
    for k in ['frozen_core','frozen_algorithm','frozen_output']:assert ref(sources[k]['path'])==sources[k]
    assert release['bit']['sha256']!=old['files']['single_repair.bit']['sha256']
    assert release['hwh']['sha256']!=old['files']['single_repair.hwh']['sha256']
    code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    PKG.mkdir();payload=PKG/'payload';payload.mkdir()
    unchanged={}
    for name,r in old['files'].items():
        if name in ['single_repair.bit','single_repair.hwh','physical_gates.json']:continue
        cp(OLDPKG/'payload'/name,payload/name);unchanged[name]=r['sha256']
    for source,name in [(release['bit']['path'],'single_repair.bit'),(release['hwh']['path'],'single_repair.hwh'),
        (FIX/'physical_gates.json','physical_gates.json'),(FIX/'reset_reproduction.json','reset_reproduction.json'),
        (FIX/'integration/receipt.json','reset_integration_receipt.json')]:cp(source,payload/name)
    for source,name in [(ROOT/'single_repair/Single_Image_Repair_Operator_r2.ipynb','Single_Image_Repair_Operator_r2.ipynb'),
        (ROOT/'single_repair/BOARD_STEPS_r2.md','BOARD_STEPS.md'),(OLDPKG/'verify_download.py','verify_download.py')]:cp(source,PKG/name)
    manifest=dict(schema='single-image-board-package-v1',release_revision='RESET_FIXED_R2',
        algorithm=old['algorithm'],clock_mhz=50,processing_shape=[512,512],
        hardware_release=gate['status'],board_status='BOARD_NOT_RUN',implementation_commit=code_commit,
        default_hardware_access=False,expected_arrays='Host verification only; never written to PL',
        previous_manifest=ref(OLDPKG/'payload/manifest.json'),unchanged_payload_sha256=unchanged,files=entries(payload))
    write(payload/'manifest.json',manifest)
    nb=json.loads((PKG/'Single_Image_Repair_Operator_r2.ipynb').read_text(encoding='utf8'))
    for p in payload.glob('*.py'):ast.parse(p.read_text(encoding='utf8'))
    for c in nb['cells']:
        if c['cell_type']=='code':assert c['execution_count'] is None;ast.parse(''.join(c['source']))
    first=''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])+'\nassert "pynq" not in sys.modules\n'
    r=subprocess.run([sys.executable,'-X','utf8','-B','-c',first],cwd=PKG,text=True,capture_output=True)
    write(FIX/'delivered_interface_test.json',dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,
        hardware_operations=0,model_forwards=0,scope='Actual r2 first notebook cell only; unchanged hardware runner'))
    assert r.returncode==0 and 'RESET_FIXED_R2' in r.stdout and 'OFFLINE_PACKAGE_VERIFIED' in r.stdout,r.stderr
    boardzip=archive(PKG)
    write(FIX/'board_release_receipt.json',dict(status='READY_FOR_BOARD_AUTHORIZATION',zip=boardzip,
        manifest=ref(payload/'manifest.json'),code_commit=code_commit,board_status='BOARD_NOT_RUN'))
    status=dict(status='READY_FOR_BOARD_AUTHORIZATION',revision='RESET_FIXED_R2',
        old_board_attempt='INCOMPLETE_FIRST_CONTROL_ACCESS; preserved',
        offline_defect='ACTIVE_LOW_AUX_RESET_TIED_LOW_REPRODUCED',
        visual_repair='UNCHANGED_SINGLE_IMAGE_REVIEW_WITH_UNCERTAINTY',integer='REUSED_UNCHANGED_CORE_EXACT',
        rtl='REUSED_UNCHANGED_CORE_EXACT',reset_integration='PASS',physical='PASS',
        new_board_status='BOARD_NOT_RUN',latency_target='UNSET',hardware_operations=0,model_forwards=0,
        physical_builds_total=2,physical_build_limit=3,software_candidates_total=11,
        old_pixels=6457,added_pixels=3083,final_pixels=9540,old_deleted=0,uncertain_pixels=2441,
        implementation_commit=code_commit,live_bus_root_cause='NOT_OBSERVED_AFTER_REBOOT',
        independent_gt_accuracy='NOT_CLAIMED')
    write(FIX/'status.json',status)
    report=f'''# 单图补标复位连接修复 r2

状态：READY_FOR_BOARD_AUTHORIZATION；新候选 BOARD_NOT_RUN，LATENCY_TARGET_UNSET。仅离线工作，未连接板卡。

旧包、原会话54a5300886c64d79ae27cd8acf7434af及失败证据保留。用户确认旧尝试后重启/断电。旧记录最后停在0x18指针写入，不能恢复其当时总线状态，也不读取旧DDR地址。ALREADY_ATTEMPTED是第二次调用的保护，不是第一处故障。

实际生成reset IP的C_AUX_RESET_HIGH=0，却把aux_reset_in接到0。生成的功能门级网表复现：保持0时复位不释放，接1后释放，重新施加/释放外部复位也通过。这是确认的集成缺陷，足以阻断控制访问；不能据此声称恢复了旧板端总线轨迹。r2只将aux接1，并显式固定两路复位极性。原算法、HLS核、参数、图像、参考输出和板端驱动均未改变。

旧集成测试直接驱动核心/互连resetn，漏测真实复位链，这是上一版验证遗漏。r2使用新生产顶层接线和真实reset IP网表；复位IP本身源码及CDC依赖逐字与原生成网表来源一致。未用自写复位桩或强制输出代替。原混合语言行为级试验在初始断言处失败，日志保留；采用实际生成的功能门级网表后，同样断言通过。集成入口首次缺少尚未OOC生成的r2 reset功能网表，前置检查失败且未开始仿真；已显式记录只复用源码完全相同的旧reset IP网表。

新生产接线仿真覆盖50MHz时钟、外部复位断言/释放、PS GP0控制链、AW/W先后次序、B/R背压、指针写入和读回、真实DDR转换互连、20个计算阶段及全部10998个工作区字。PS发起端及DDR存储为测试边界模型，不冒称实板。结果与不变整数参考逐字一致。完整512核级RTL、边缘/空图等既有数值证据因核心不变而复用；未重新运行模型或软件候选。

正式物理构建累计2/3轮。新50MHz同次构建：WNS {gate['wns_ns']} ns，WHS {gate['whs_ns']} ns，WPWS {gate['wpws_ns']} ns；完全路由 {gate['routed_nets']} 条，路由错误0、未约束端点0、DRC错误/严重警告0。实际资源：{gate['resources']}。保留并审阅普通警告：{gate['drc_warnings']}。真实生成顶层、最终DCP控制/DDR端点和复位来源均核对；旧/新DCP提取的实际复位单元功能仿真分别确认旧版不释放、新版释放；未添加虚假时序例外。位流仅在完整物理门禁通过后从同一个DCP生成，与同次HWH配套。

只读DCP检查日志中保留Board49-67板卡定义检索警告，不能把“DRC严重警告0”写成全部控制台警告0。新工程构建与正式位流生成均显式配置既有PYNQ-Z2板卡定义路径；器件、50MHz约束、完整路由、STA和DRC报告均已独立核验。正式发布生成日志另行要求没有ERROR或CRITICAL WARNING。

单图结果不变：旧6457、新增3083、最终9540、删除旧像素0、不确定2441；没有独立GT准确率或完整拓扑保证。旧图、细末梢和交汇处的不确定性仍保留。本轮没有扩大软件搜索，也没有改变参考答案。

新板测包：{boardzip['path']}。新目录single_image_repair_r2；先仅运行离线第一格，确认RESET_FIXED_R2，再由用户手动确认执行第二格一次。成功后第三格显示真实PL对比，最后一格导出结果。不得删除旧attempt标记重试旧位流。完整操作见包内BOARD_STEPS.md。
'''
    with (FIX/'report.md').open('x',encoding='utf8') as f:f.write(report)
    REVIEW.mkdir()
    for p in FIX.rglob('*'):
        if p.is_file():cp(p,REVIEW/'results'/p.relative_to(FIX))
    for name in ['reset_repair.py','integration_resetfix.py','physical_resetfix.py','physical_gate_resetfix.py',
        'release_bit_resetfix.py','deliver_resetfix.py','routed_reset_test.py','BOARD_STEPS_r2.md','Single_Image_Repair_Operator_r2.ipynb']:
        cp(ROOT/'single_repair'/name,REVIEW/'source'/name)
    for name in ['create_bd_r2.tcl','physical_r2.tcl','inspect_boundary_r2.tcl','write_bit_r2.tcl','probe_old_reset.tcl',
        'export_old_routed_reset.tcl','export_old_routed_top.tcl','ps7_verified_50m.tcl','repair.cpp','geometry.hpp']:
        cp(ROOT/'single_repair/hardware'/name,REVIEW/'source/hardware'/name)
    for name in ['board_run.py','transport.py','evidence_io.py','refinement_clock_contract.py','registers.h']:
        cp(payload/name,REVIEW/'source/board'/name)
    bd=NEW/'single_repair.srcs/sources_1/bd/single_repair';sim=NEW/'sim_export/single_repair/xsim'
    for p in NEW.iterdir():
        if p.is_file() and p.suffix in ['.rpt','.tsv','.txt','.xdc']:cp(p,REVIEW/'physical_reports'/p.name)
    cp(release['dcp']['path'],REVIEW/'physical_reports/routed.dcp')
    cp(bd/'synth/single_repair.v',REVIEW/'generated/single_repair.v')
    cp(bd/'hdl/single_repair_wrapper.v',REVIEW/'generated/single_repair_wrapper.v')
    cp(release['hwh']['path'],REVIEW/'generated/single_repair.hwh')
    for name in ['routed_reset.v','routed_functional.v']:cp(NEW/name,REVIEW/'generated'/name)
    for mode in ['old','new']:
        cp(Path('D:/PLD/tmp')/('single_repair_routed_reset_'+mode)/'routed_reset_tb.sv',REVIEW/'testbenches'/('routed_reset_'+mode+'.sv'))
    for name in ['integrated_tb.sv','tb_hp0_memory.sv','reset_actual_gate.v']:cp(sim/name,REVIEW/'testbenches'/name)
    for name in ['reset_repro_tb.sv','reset_repro_gate_tb.sv']:
        cp(OLD/'sim_export/single_repair/xsim'/name,REVIEW/'testbenches'/name)
    for p in Path('D:/PLD').glob('single_repair_resetfix_*.log'):
        # Only closed logs with completed command receipts; active delivery stdout is excluded.
        if p.name=='single_repair_resetfix_delivery.log':continue
        cp(p,REVIEW/'logs'/p.name)
    for name in ['comparison.png','right_lower.png','lower_left.png','uncertain.png']:
        cp(OUT/'selected'/name,REVIEW/'unchanged_visual'/name)
    for name in ['frozen_algorithm.json','rtl_receipt.json','integer/receipt.json']:
        cp(OUT/name,REVIEW/'reused_evidence'/name)
    write(REVIEW/'source_copy_manifest.json',dict(copies=COPIES,implementation_commit=code_commit))
    write(REVIEW/'delivery_manifest.json',dict(files=entries(REVIEW),manifest_excludes_itself=True,archive_receipts_outside=True))
    reviewzip=archive(REVIEW)
    write(FIX/'delivery_receipt.json',dict(status='DELIVERY_SEAL_VERIFIED',board_zip=boardzip,review_zip=reviewzip,board_status='BOARD_NOT_RUN'))
    print(json.dumps(dict(board_zip=boardzip,review_zip=reviewzip,status=status['status']),indent=2))

if __name__=='__main__':main()
