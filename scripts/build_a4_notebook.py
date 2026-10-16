"""Create the clean six-stage A4 board notebook; no simulated board outputs."""
import json
from pathlib import Path
from build_a0_notebook import cell

ROOT = Path(__file__).resolve().parents[1]


def main():
    cells = [cell("markdown", """# A4：完整固定分割算法，真实FPGA逐像素验证

把交付包的全部12个文件上传到新文件夹 `retina_a4_r1`。延续已验证的高斯、亮度增强和局部背景响应，加入阈值28、零边界CROSS闭运算、3×3邻域计数去孤点及最终FOV过滤，完成固定算法A。PS/DDR/DMA/FIFO/GPIO/100MHz/reset和帧适配器沿用A3。

一次运行一个代码框（Shift+Enter），出现对应完成标志才继续。先保存并下载旧A3记录，再在首页Running中关闭已完成的旧A3内核；不要Run All。加载A4后显示器可能无信号，本测试使用网线传输与网页查看结果。

若出现红色报错，或一分钟没有新进展，保留输出并停止，不重复运行、不释放缓冲、不切换Overlay。本次验证硬件输出是否与固定参考算法逐像素一致；图像质量、最终HDMI整合及FPS分别验证。
""")]
    stages = [
        ("1. 准备函数", "左侧显示 In [数字] 且无红色报错即完成；没有PASS打印是正常的，此步不加载FPGA。",
         "from a4_segmentation_board_test import prepare_a4, load_a4, smoke_a4, full_a4, show_a4_results\n"),
        ("2. 检查文件", "应出现 A4_PRECHECK_PASS，FPGA尚未改变。",
         "if 'a4_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\na4_retained = []\na4_context = prepare_a4('.', a4_retained)\n"),
        ("3. 加载", "应出现 A4_LOAD_PASS；尚未传输数据。",
         "load_a4(a4_context)\n"),
        ("4. 首帧验证", "完整256×256暗条纹分割逐像素验证，出现 A4_SMOKE_PASS。确认网页正常、PuTTY回车仍有提示符，再继续。",
         "smoke_a4(a4_context)\n"),
        ("5. 完整验证", "另有60帧，含256/512、四种模式、边角/黑白/棋盘/条纹/精确阈值边界/随机/FOV/孤点/断线和真实STARE图。连续输出 SEGMENTATION_FRAME_PASS，最终应出现 A4 SEGMENTATION PASS: 61 complete frames matched。左侧回到In [数字]后继续。",
         "a4_result = full_a4(a4_context)\n"),
        ("6. 查看FPGA结果并打包", "应显示原始绿色、FPGA增强、黑白血管候选掩膜、FPGA响应四图，打印 A4_RESULTS_READY。第三图采用最近邻缩放，保持黑白。图片来自已逐字验证的实际DMA输出；此框只运行一次。",
         "show_a4_results(a4_context)\n"),
    ]
    for title, description, source in stages:
        cells.extend([cell("markdown", f"## {title}\n{description}\n"), cell("code", source)])
    cells.append(cell("markdown", """## 7. 下载记录

按Ctrl+S保存。File → Download as → Notebook，下载运行后的 `a4_segmentation_check.ipynb`。回到文件列表，下载 `a4_results_bundle.zip`（含原JSON、六份实际STARE输出数组和预览）。两份文件下载到Windows后反馈，项目再独立复核并记录板测结果。

发布时板测状态为NOT_RUN。只有以上步骤在实体板运行完成，才可记录固定算法A的板测通过；不代表医学分割质量、最终HDMI整合或性能指标已通过。板上时钟尚未校准，原始时间保留。
"""))
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3 (ipykernel)",
                "language": "python", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 4}
    (ROOT / "notebooks/a4_segmentation_check.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
