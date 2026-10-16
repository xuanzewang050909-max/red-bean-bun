"""Create the clean six-stage A3 board notebook; no simulated board outputs."""
import json
from pathlib import Path
from build_a0_notebook import cell

ROOT = Path(__file__).resolve().parents[1]


def main():
    cells = [cell("markdown", """# A3：局部背景与血管响应，真实FPGA逐像素验证

把交付包的全部11个文件上传到新文件夹 `retina_a3_r1`。本阶段在已验证高斯和亮度增强后，复用2017.4厂商15×15 BoxFilter，得到精确整数背景，再计算较暗结构的响应。PS/DDR/DMA/FIFO/GPIO/100MHz/reset和帧适配器均沿用A2。

一次运行一个代码框（Shift+Enter），出现对应完成标志才继续。先结束已完成的旧A2内核；不要Run All。加载A3后显示器可能无信号，因为本测试使用网线传输与网页查看结果。

若出现红色报错，或一分钟没有新进展，保留输出并停止，不重复运行、不释放缓冲、不切换Overlay。此阶段尚未加入阈值和形态学，因此响应图中的亮处是被突出的暗结构，不是最终血管分割。
""")]
    stages = [
        ("1. 准备函数", "左侧显示 In [数字] 且无红色报错即完成；没有PASS打印是正常的，此步不加载FPGA。",
         "from a3_background_board_test import prepare_a3, load_a3, smoke_a3, full_a3, show_a3_results\n"),
        ("2. 检查文件", "应出现 A3_PRECHECK_PASS，FPGA尚未改变。",
         "if 'a3_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\na3_retained = []\na3_context = prepare_a3('.', a3_retained)\n"),
        ("3. 加载", "应出现 A3_LOAD_PASS；尚未传输数据。",
         "load_a3(a3_context)\n"),
        ("4. 首帧验证", "完整256×256暗条纹图逐像素验证，出现 A3_SMOKE_PASS。确认网页正常、PuTTY回车仍有提示符，再继续。",
         "smoke_a3(a3_context)\n"),
        ("5. 完整验证", "另有44帧，含256/512、四种模式、边角/棋盘/黑白/条纹/取整/随机和真实STARE图。连续输出 BACKGROUND_FRAME_PASS，最终应出现 A3 BACKGROUND PASS: 45 complete frames matched。",
         "a3_result = full_a3(a3_context)\n"),
        ("6. 查看FPGA结果并打包", "应显示原始绿色、FPGA增强、FPGA背景、FPGA响应四图，打印 A3_RESULTS_READY。图片来自已经逐字验证通过的实际DMA输出；此框只运行一次。",
         "show_a3_results(a3_context)\n"),
    ]
    for title, description, source in stages:
        cells.extend([cell("markdown", f"## {title}\n{description}\n"), cell("code", source)])
    cells.append(cell("markdown", """## 7. 下载记录

按Ctrl+S保存。File → Download as → Notebook，下载运行后的Notebook。回到文件列表，下载 `a3_results_bundle.zip`（含原JSON、四份实际STARE输出数组和预览）。下载完成后反馈，项目再独立复核并记录板测结果。

发布时板测状态为NOT_RUN。只有以上步骤在实体板运行完成，才可记录本阶段通过；不代表完整分割、最终HDMI整合或性能指标已通过。板上时钟尚未校准，原始时间保留。
"""))
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3 (ipykernel)",
                "language": "python", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 4}
    (ROOT / "notebooks/a3_background_check.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
