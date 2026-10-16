"""Release the staged W2 board test only after actual host gates pass."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from check_w2_hardware import check, info, require
from a1_point_board_test import notebook_code_hash

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_app'))
from w2_quality_board_test import REVISION,NOTEBOOK,FIXED


def notebook():
    def cell(kind,source):
        c=dict(cell_type=kind,metadata={},source=source.splitlines(keepends=True))
        if kind=='code':c.update(execution_count=None,outputs=[])
        return c
    stages=[
        ('1. 准备函数','左侧变成 In [数字] 且无红色报错即完成；没有打印正常。此步骤不加载 FPGA。',
         'from w2_quality_board_test import prepare_w2, load_w2, smoke_w2, baseline_w2, candidate_w2, finish_w2\n'),
        ('2. 核对文件','应出现 W2_PRECHECK_PASS，此步骤不加载 FPGA。Notebook 允许自动保存输出，但代码严格校验。',
         "if 'w2_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\nw2_retained = []\nw2_context = prepare_w2('.', w2_retained)\n"),
        ('3. 只加载一次','应出现 W2_LOAD_PASS；核对官方 DMA/GPIO 驱动、计数器身份与复位状态，尚未收发。',
         'load_w2(w2_context)\n'),
        ('4. 单帧验证','应出现 W2_SMOKE_PASS。一幅完整 256×256 图像逐字核对，并核对 PL 实际锁存参数和周期数。',
         'smoke_w2(w2_context)\n'),
        ('5. 原算法回归','继续运行原 A4 的剩余 60 帧，连同上一步共 61 帧。最后 W2_BASELINE_PASS。',
         'baseline_w2(w2_context)\n'),
        ('6. C2 与真实改参','19 帧包含 A/C2 切换、T=1/27/28/29/255、256/512 和不同处理阶段。每帧重新送入 PL，并读取真实参数与计数。最后 W2_CANDIDATE_PASS。',
         'candidate_w2(w2_context)\n'),
        ('7. 查看实际结果并打包','上排 A，下排 C2，均来自已完成且逐字核验的实际 DMA 输出。四列为原绿色、增强、掩膜、叠加；显示 W2_RESULTS_READY。只运行一次。',
         'finish_w2(w2_context)\n')]
    cells=[cell('markdown','# W2 + Q2：亮区误检候选、真实阈值与 PL 计时\n\n本轮使用真实 PYNQ-Z2、以太网和浏览器中的 Jupyter，无 HDMI。新 C2 使用双侧灰度支持和软惩罚；改善程度待真实板输出复核，并不保证所有亮区误检消失。原 A28 基线保留。\n\n逐框 Shift+Enter，当前框结束且无报错再继续。红色报错或一分钟无新进展就停止并保留输出；不重复运行、不关闭失败内核、不重载 Overlay 或释放缓冲。原服务应先正常结束，不能与旧浏览器服务同时操作 FPGA。\n')]
    for title,description,code in stages:cells += [cell('markdown','## '+title+'\n'+description+'\n'),cell('code',code)]
    cells.append(cell('markdown','## 下载记录\n\nCtrl+S；File → Download as → Notebook，下载运行后的 `w2_quality_check.ipynb`。回文件列表下载 `w2_results_bundle.zip`，两份下载后反馈。可同时保存第7框的对比截图。\n\n每帧保存原始输出、哈希、收发字节数、真实锁存参数、核心/背压周期和 PS 时间戳。预计算参考数组仅用于比较，不用于显示。核心时间包含流式等待，DMA 事务与 PL 重叠；不能相减得到纯 DMA。当前推理时间从配置开始到 DMA 完成后普通 CPU 快照结束，不含输入加载、分配、校验和导出。正式全数据精度、浏览器延迟/FPS、CPU 对照及稳定性仍是后续步骤。发布时板测状态 NOT_RUN，不能预填实测结果。\n'))
    return dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3 (ipykernel)',language='python',name='python3')),nbformat=4,nbformat_minor=4)


def assemble(destination,hardware):
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('w2_quality.bit','w2_quality.hwh'):shutil.copy2(ROOT/'build/w2_quality_full_01/deploy'/name,destination/name)
    for name in ('w2_quality_board_test.py','a0_dma_board_test.py','a1_point_board_test.py'):shutil.copy2(ROOT/'scripts'/name,destination/name)
    shutil.copy2(ROOT/'pynq_app/quality_observer.py',destination/'quality_observer.py')
    for name in ('w2_vectors.json','w2_vectors.npz'):shutil.copy2(ROOT/'build/w2_board_vectors_01'/name,destination/name)
    nb=notebook();(destination/NOTEBOOK).write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    (destination/'使用说明.txt').write_text('全部11个文件上传到新 retina_quality_w2_r1 文件夹。打开 w2_quality_check.ipynb，按顺序运行7框。最后下载运行后的Notebook和w2_results_bundle.zip。异常停止并保留内核及输出；不重复运行/重载FPGA。无HDMI；此包发布状态NOT_RUN，实际板测后才判断C2效果。\n',encoding='utf-8')
    manifest=dict(revision=REVISION,board_status='NOT_RUN',hardware_clock_hz=100_000_000,
                  source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  candidate='C2_l9_d12345_m1_p28',frames=80,words=13303808,
                  notebook_validation=dict(algorithm='sha256-code-cells-v1',sha256=notebook_code_hash(nb)),
                  hardware=dict(resources=hardware['resources'],wns_ns=hardware['wns_ns'],whs_ns=hardware['whs_ns']),
                  artifacts={name:info(destination/name) for name in sorted(FIXED|{NOTEBOOK})})
    (destination/'w2_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def gates():
    hardware=check(ROOT/'build/w2_quality_full_01')
    required=[('build/w2_guard_unit_01_session.log','W2_GUARD_UNIT_PASS: complete_frames=6 checked_words=589824'),
              ('build/w2_quality_axis_sim_03_session.log','W2_Q2_QUALITY_AXIS_SIM_PASS: cases=17 checked=2490368'),
              ('build/w2_quality_reset_01_session.log','W2_VENDOR_RESET_SIM_PASS'),
              ('build/w2_board_host_03.log','Ran 7 tests'),('build/w2_observer_host_01.log','Ran 10 tests'),
              ('build/w2_package_host_02.log','Ran 8 tests'),('build/w2_archive_host_02.log','Ran 3 tests')]
    for path,marker in required:
        content=(ROOT/path).read_text(encoding='utf-8-sig')
        require(any(line.startswith(marker) for line in content.splitlines()),'Gate incomplete: '+path)
        require(not re.search(r'(?m)^(Fatal:|ERROR:|FAILED \()',content),'Gate failed: '+path)
        if 'host_' in path:require('\nOK\n' in content,'Host tests incomplete: '+path)
    guard=ROOT/'rtl/core/retina_quality_guard.v';tb=ROOT/'tests/retina_w2_quality_axis_tb.sv'
    for source in (guard,tb):require(info(source)==info(ROOT/'build/w2_quality_axis_sim_03'/source.name),'Simulation source changed '+source.name)
    return hardware


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    args=parser.parse_args();hardware=gates();manifest=assemble(args.destination,hardware)
    print('W2_HOST_PACKAGE_READY_NOT_BOARD_PASS:',len(manifest['artifacts'])+1,'files;',args.destination)
