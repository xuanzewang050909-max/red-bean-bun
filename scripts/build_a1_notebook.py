import json
from pathlib import Path
from build_a0_notebook import cell

ROOT = Path(__file__).resolve().parents[1]


def main():
    cells = [cell("markdown", """# A1 r1：绿色通道与 LUT 单级验证

上传同一交付文件夹的全部7个文件到板端新文件夹 `retina_a1_r1`。本工程使用原 A0 的 PS/DDR/DMA/FIFO/复位，新增点处理与官方 GPIO 参数控制。只验证旁路、绿色通道、直接 LUT(G)，没有完整医学分割和 HDMI。显示器无信号是预期现象。

**一次只运行一个代码单元，核对 PASS 后再继续。不要 Run All，不运行其他加载 Overlay 的 Notebook。** 报错或一分钟无进展，保留输出并暂停；不重跑、不释放在途缓冲或切换 Overlay。软件轮询超时无法恢复阻塞的硬件总线。
"""), cell("markdown", "## 1. 准备函数\n选中下一单元，Shift+Enter；In [数字] 且无红色报错表示完成。此步不加载FPGA。\n"),
        cell("code", "from a1_point_board_test import prepare_a1, load_a1, smoke_a1, full_a1\n"),
        cell("markdown", "## 2. 检查文件\n应出现 A1_PRECHECK_PASS，FPGA未改变。\n"),
        cell("code", "if 'a1_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\na1_retained = []\na1_context = prepare_a1('.', a1_retained)\n"),
        cell("markdown", "## 3. 加载\n应出现 A1_LOAD_PASS。尚未传输数据；显示器可能无信号。\n"),
        cell("code", "load_a1(a1_context)\n"),
        cell("markdown", "## 4. 首帧验证\n此次必须发送完整256×256帧，应出现 A1_SMOKE_PASS。确认网页、串口仍正常，再继续。\n"),
        cell("code", "smoke_a1(a1_context)\n"),
        cell("markdown", "## 5. 连续验证\n验证256/512、旁路/绿色/LUT、递增/随机/黑/白共另外16帧。最终应出现 A1 POINT PASS: 17 complete frames matched。\n"),
        cell("code", "a1_result = full_a1(a1_context)\n"),
        cell("markdown", "## 6. 保存原始记录\nCtrl+S；File → Download as → Notebook 下载执行后的Notebook；回文件列表下载 a1_point_result.json。把完成输出反馈给项目，板级状态只依据真实记录。\n")]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}},
                "nbformat": 4, "nbformat_minor": 4}
    (ROOT / "notebooks/a1_point_check.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
