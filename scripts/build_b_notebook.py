"""Create staged B notebook with no synthetic hardware outputs."""
import json
from pathlib import Path
from build_a0_notebook import cell

ROOT=Path(__file__).resolve().parents[1]


def main():
    cells=[cell('markdown','''# B：同一 FPGA 工程内分割与官方 HDMI

将交付文件全部上传到新文件夹 `retina_b_r1`。先保存并下载旧 A4 记录，回到首页 Running，关闭已完成的旧 A4 内核及其他控制板卡的内核。显示器接板卡 **HDMI OUT**，输入源选择相应 HDMI；保留网线与现有供电。

每次选中一个代码框按 Shift+Enter，等 In [数字]、无报错并出现对应标志，再运行下一框。不要 Run All。同一 B bitstream 只加载一次，不切换其他 Notebook 的 Overlay。

若红色报错，或一分钟没有新进展，保存输出并停止；不重复运行、不释放缓冲、不关闭失败内核或切换 Overlay。保留文件后反馈。此程序输出源于冻结 M0 算法，医学质量另有离线评价；显示 60 Hz 不等于算法 60 FPS。
''')]
    stages=[
        ('1. 准备函数','In [数字] 且无报错即完成，无 PASS 打印是正常的。',
         'from b_integration_board_test import prepare_b, load_b, smoke_b, start_hdmi_b, full_b, display_medical_b, performance_b, finish_b\n'),
        ('2. 检查文件','应出现 B_PRECHECK_PASS，此步不加载 FPGA。',
         "if 'b_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\nb_retained = []\nb_context = prepare_b('.', b_retained)\n"),
        ('3. 只加载一次','应出现 B_LOAD_PASS，官方 DMA、GPIO、HDMI 层次和 VDMA 驱动已绑定；尚未收发。',
         'load_b(b_context)\n'),
        ('4. 算法首帧','完整 256×256 暗条纹分割应匹配，出现 B_DMA_SMOKE_PASS。确认网页与串口仍有响应再继续。',
         'smoke_b(b_context)\n'),
        ('5. 启动官方 HDMI','应出现 B_COLOR_SUBMITTED。显示器从左到右蓝、绿、红，四周白边、中央白十字。观察约 30 秒并拍照。若色序、边框、稳定性不符，停止后反馈；打印标志只代表提交成功。',
         'start_hdmi_b(b_context)\n'),
        ('6. 显示运行时验证算法','保持彩条显示，另外 60 帧逐字核验，最终 B_ALGORITHM_PASS: 61 complete frames matched while same-overlay HDMI running。',
         'full_b(b_context)\n'),
        ('7. 显示实际分割结果','出现 B_MEDICAL_DISPLAY_SUBMITTED。显示器与网页应相同：左侧原始绿色通道，右侧叠加绿色 FPGA 血管候选。观察并拍照，留存这两张显示器照片。',
         'display_medical_b(b_context)\n'),
        ('8. 测实际速度','先完成观察和拍照。共三组：256 算法 DMA、512 算法 DMA、512 完整显示提交循环；每组 3 帧预热 + 100 帧计时，均逐字核验。每 20 帧有进度；结束出现 B_TIMING_COMPLETE。计时来自单调高精度 perf_counter_ns，不受板上旧日期影响。',
         'b_result = performance_b(b_context)\n'),
        ('9. 关闭显示并打包','完成拍照后运行一次。屏幕可能变黑或无信号。应出现 B_RESULTS_READY，显示缓冲由官方驱动回收。',
         'finish_b(b_context)\n')]
    for title,description,source in stages:
        cells.extend([cell('markdown','## '+title+'\n'+description+'\n'),cell('code',source)])
    cells.append(cell('markdown','''## 10. 下载运行记录

Ctrl+S；File → Download as → Notebook 下载执行后的 `b_integration_check.ipynb`。回到文件列表下载 `b_results_bundle.zip`。反馈这两个文件和步骤 5、7 的显示器照片；项目会独立核验真机记录、原数组、计时、版本和同工程证据。

发布时板测为 NOT_RUN。即使程序无报错，显示观察仍为 PENDING，不能以提交打印代替目视确认。循环 FPS 包含检查、状态读取、哈希、排版和提交；单次 DMA 计时不包含模型生成或文件写入。均不是测得的显示刷新率或纯 PL 周期吞吐率。
'''))
    nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3 (ipykernel)','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':4}
    (ROOT/'notebooks/b_integration_check.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
