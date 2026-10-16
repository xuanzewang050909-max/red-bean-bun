import json
from pathlib import Path
from build_a0_notebook import cell
ROOT=Path(__file__).resolve().parents[1]


def main():
    cells=[cell("markdown","""# A2：复用厂商3×3高斯滤波，真实眼底图逐像素验证

把同一交付包的全部10个文件传入新文件夹 `retina_a2_r1`。本版保留已验证PS/DDR/DMA/FIFO/GPIO/reset，采用本机2017.4厂商Filter2D生成的Verilog。验证绿色、固定整数高斯、LUT和中心FOV对齐，尚未做完整血管分割或HDMI整合。

一次运行一个代码框（Shift+Enter），核对PASS再继续。不要Run All；先结束旧A1内核，保留已下载的通过记录。加载A2后显示器无信号是预期现象。红色报错或一分钟没有新进展时保留输出并停止，不重复运行、不释放在途缓冲、不加载其他Overlay；反馈网页/串口是否仍响应。
""")]
    stages=[("1. 准备函数","In [数字] 且无红色报错即完成，此步不加载FPGA。",
             "from a2_gaussian_board_test import prepare_a2, load_a2, smoke_a2, full_a2, show_a2_results\n"),
            ("2. 检查文件","应出现 A2_PRECHECK_PASS，FPGA尚未改变。",
             "if 'a2_context' in globals():\n    raise RuntimeError('Already prepared; do not rerun')\na2_retained = []\na2_context = prepare_a2('.', a2_retained)\n"),
            ("3. 加载","应出现 A2_LOAD_PASS，尚未传输数据。","load_a2(a2_context)\n"),
            ("4. 首帧验证","完整256×256二维渐变图逐像素验证，应出现 A2_SMOKE_PASS。确认网页与串口响应后继续。","smoke_a2(a2_context)\n"),
            ("5. 完整验证","另有36个完整帧，含256/512、所有模式、边角/棋盘/黑白与真实STARE图。不断输出 GAUSSIAN_FRAME_PASS，最终 A2 GAUSSIAN PASS: 37 complete frames matched。打印PASS仅代表本阶段，不代表完整分割、HDMI或FPS。","a2_result = full_a2(a2_context)\n"),
            ("6. 查看FPGA结果并打包","应显示原始绿色、FPGA高斯、FPGA高斯+LUT三图，打印 A2_RESULTS_READY。仅从已经比对通过的实际DMA输出读取图像；此框不重复运行。","show_a2_results(a2_context)\n")]
    for title,description,source in stages:cells.extend([cell("markdown",f"## {title}\n{description}\n"),cell("code",source)])
    cells.append(cell("markdown","## 7. 下载记录\nCtrl+S保存；File → Download as → Notebook 下载运行后的Notebook。回到文件列表，下载 a2_results_bundle.zip（含JSON、4个真实输出数组及预览图）。两份下载完成后反馈，依据真实记录归档板级状态。\n"))
    notebook={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3 (ipykernel)","language":"python","name":"python3"}},"nbformat":4,"nbformat_minor":4}
    (ROOT/"notebooks/a2_gaussian_check.ipynb").write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")


if __name__=="__main__":main()
