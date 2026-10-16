# B 视频驱动导入修复：替换两文件后继续

当前截图报错 `ImportError: cannot import name 'AxiVDMA' from 'pynq.lib.video'`，位于第2框预检查的导入语句，尚未创建Overlay、加载FPGA或分配DMA缓冲。这是提供的r1测试脚本错误，原件和截图已经保留。

PYNQ 3.0.1 的 `video/__init__.py` 导入 `dma`、`hierarchies` 模块，没有把这些模块的驱动类直接导出。r2明确使用 `pynq.lib.video.dma.AxiVDMA`、`pynq.lib.video.hierarchies.VideoOut/HDMIWrapper` 和 `pynq.lib.video.common.VideoMode/PIXEL_BGR`。只改这三条导入及发布编号，保留版本、哈希、驱动类型和所有硬件检查。

1. 在 Windows 文件资源管理器地址栏粘贴 `D:\PLD\retina_fpga\build\deploy\b_video_import_fix_r2`，按回车。里面只有 **b_integration_board_test.py** 和 **b_manifest.json**。
2. 回 Jupyter 文件列表进入你已有的 **retina_b_r1** 文件夹。Upload这两个文件，分别确认上传和替换同名文件；两个都要替换，保持其他文件不动。
3. 返回 `b_integration_check.ipynb`，点 **Kernel → Restart** 并确认，等待内核空闲。当前预检查失败、未加载FPGA，适用此恢复步骤；只刷新网页不会让Python重读脚本。
4. 运行第1框“准备函数”：Shift+Enter，出现 `In [数字]` 且无红色报错即完成。
5. 运行第2框“检查文件”：应出现 **B_PRECHECK_PASS**。若仍报错，停在这里并保留截图，不运行加载框。
6. 预检查通过后，按原顺序继续第3框 `B_LOAD_PASS`、第4框 `B_DMA_SMOKE_PASS`。第5框显示蓝/绿/红彩条和白边、十字，观察约30秒并拍照。
7. 第6框等 `B_ALGORITHM_PASS`，第7框显示真实原图与绿色血管候选叠加，再拍显示器照片。
8. 第8框等 `B_TIMING_COMPLETE`，第9框等 `B_RESULTS_READY`。保存并下载运行后的Notebook和 `b_results_bundle.zip`，反馈两文件及两张照片。

修正包用于你已上传的文件夹；首次上传可使用完整十三文件目录 `build/deploy/b_integration_2017_4_r2`。完整r2沿用旧Notebook/使用说明，上传路径以本文为准。原r1完整包和失败证据保留，现已撤回其软件入口；原r1硬件bit/HWH、输入、A4辅助代码、Notebook完全相同，无需重新综合或写SD卡。

主机检查执行未修改官方视频包初始化代码的导出行为，复现旧导入错误，并验证新预检查不下载FPGA、不分配DMA缓冲；其余收发/显示所有权/计时回归一起运行。这仍不代表实体板驱动绑定、显示或速度已经通过。
