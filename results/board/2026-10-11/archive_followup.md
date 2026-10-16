# 运行记录归档后续

用户在收到停止 HDMI、Ctrl+S 保存、下载 Notebook 的步骤后反馈“已保存”。本次尚未取得新的 close 输出截图或实际下载的执行 Notebook，不能仅据此声称本地执行文件归档已完成。

只读检查：Windows 默认下载文件夹为 C:\Users\Gabriel\Downloads；该目录当前未找到名称含 hdmi 的文件。项目内现有 hdmi_output_check.ipynb 是此前生成的未执行测试源文件，不能充作板端已执行文件。其他保存位置或网页保存状态待用户澄清，已发送问题。

环境准备：本机 E:\vivado\Vivado 下只见 2017.4；本次磁盘空闲约 C 46.83 GiB、D 46.22 GiB、E 103.58 GiB（检查瞬时值，安装容量尚未核实）。官方 PYNQ v3.0.1/Z2 Base Tcl 声明 2022.1。未下载/安装新工具，也未生成或测试 A0 DMA bitstream。

已准备 notebooks/board_environment_capture.ipynb，嵌入原环境采集脚本以便只上传一个文件。仅做语法检查，未在 Windows 假装板端运行，实际执行和生成 JSON 待用户完成。

## 下载文件已取得

用户确认下载到默认目录后重新检查，发现 C:\Users\Gabriel\Downloads\hdmi_output_check.ipynb（7629 字节）。已逐字节复制为 hdmi_output_check_executed.ipynb，源文件及归档 SHA256 一致：42af16d86e5892961f65c77574c6db955e716bd50d4a0c01a7212f369a17967a。

归档中含 Base 启动、模式/stride、纯红、空间标记、Submitted 100 frames. 和 HDMI output closed. 输出，未保存 error 输出。没有在 Windows 重新执行 Notebook，未修改该执行文件以补填结果；测试源 notebooks/hdmi_output_check.ipynb 保留未执行状态。

close 输出确认用户导出的记录包含该步骤成功执行；不能仅凭保存的执行计数推断完整事件顺序或归档时瞬时硬件状态。此前关于“本地未找到”的描述保留为检查当时状态。

板端原始 hdmi_framebuffer_100_frames.json 和完整 board_environment.json 尚未下载；采集 Notebook 仍等待现场执行与导出。
