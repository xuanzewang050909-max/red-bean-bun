"""Produce an unexecuted, self-contained board notebook from the test source."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cell(kind, text):
    result = {"cell_type": kind, "metadata": {}, "source": text.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def main():
    source = (ROOT / "scripts/a0_dma_board_test.py").read_text(encoding="utf-8")
    cells = [cell("markdown", """# PYNQ-Z2 A0 r2：分步 DMA 验证

旧 A0 已撤回。请将本版 `a0_dma.bit`、`a0_dma.hwh`、`a0_manifest.json` 与本 Notebook 全部上传到新文件夹 `retina_a0_r2`，勿与旧文件混用。

目标环境：板上 PYNQ 3.0.1；Vivado 2017.4 标准 DMA/FIFO，无医学算法和 HDMI。保持供电及网线，不运行其他加载 Overlay 的 Notebook。此前死机已通过断电恢复；无需重写 SD 卡。

**每次只运行一个单元，核对输出后再继续。不要点 Run All。** 红色报错或一分钟无进展时，截图最后输出并停止；不要反复运行、释放缓冲或切换 Overlay。软件超时只适用于能够返回的状态读取，不能使卡住的 AXI 访问恢复。
"""), cell("markdown", """## 1. 准备函数

选中下面代码，按 Shift+Enter。仅定义函数，不加载 FPGA。
"""), cell("code", source), cell("markdown", """## 2. 检查文件与环境

运行后应出现 `PRECHECK_PASS`。核对哈希、版本及硬件描述，此步不改变 FPGA。先把此输出反馈给项目审查，再进入加载测试。
"""), cell("code", """if 'a0_context' in globals():
    raise RuntimeError('Already prepared. Do not rerun; continue to the next phase.')
if 'a0_retained_buffers' not in globals():
    a0_retained_buffers = []
a0_context = prepare_test('.', a0_retained_buffers)
"""), cell("markdown", """## 3. 只加载 FPGA

确认前一步通过，再运行下面单元。预期 `LOAD_PASS`；此时尚未收发数据。加载 A0 后显示器可能无信号，因为本工程不含 HDMI。反馈加载结果后再进入短包测试。
"""), cell("code", "load_test(a0_context)\n"), cell("markdown", """## 4. 一次短包收发

使用官方 DMA 驱动，发送并逐字核对 17 个数据字。预期 `SMOKE_PASS`；这只表示一次短包成功，完整 70 次测试仍未完成。确认串口、网页仍正常，再继续。
"""), cell("code", "smoke_test(a0_context)\n"), cell("markdown", """## 5. 完整收发验证

短包通过后运行。含短包、256×256 和 512×512、递增/随机、连续多帧；预计 70 条 PASS，最后 `A0 DMA PASS: all 70 transfers matched.`。只有真实运行到结束才能记为板级通过。
"""), cell("code", "a0_result = full_test(a0_context)\n"), cell("markdown", """## 6. 保存真实记录

Ctrl+S；File → Download as → Notebook 下载执行记录。回到文件列表，下载 `a0_dma_result.json`。每个硬件阶段开始前记录状态，保留板端未校准时间；若死机，断电后可尝试取回最后落盘记录。

通过范围仅为本版 A0 的 DMA/FIFO/DDR 与官方驱动适配。没有医学算法、最终 HDMI 整合或实时性能验证。
""")]
    notebook = {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10.4"}},
        "nbformat": 4, "nbformat_minor": 4}
    path = ROOT / "notebooks/a0_dma_loopback.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
