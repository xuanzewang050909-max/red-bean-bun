# B 同工程上板步骤

B 在一个 bitstream 中同时保留冻结的 A4 分割算法和官方 VDMA/HDMI。主机构建通过之后，实体板仍需按下面步骤验证；发布状态为 NOT_RUN。

1. 保存、下载旧 A4 记录；Jupyter 首页 **Running** 关闭已完成的 A4 和其他控制板卡的内核。显示器接板卡 **HDMI OUT**，选择对应输入源。保持网线和现有供电。
2. 首页新建文件夹，命名 `retina_b_r1`。Upload 交付包全部 **13 个文件**（包含配对 bit/HWH、六个脚本、Notebook、两份 NPY、说明、manifest），再逐个点 Upload 完成上传。
3. 打开 `b_integration_check.ipynb`。选第 1 个代码框按 **Shift+Enter**；In [数字] 且无红色报错表示准备函数完成，没有打印也正常。
4. 第 2 框预检查，等 `B_PRECHECK_PASS`；第 3 框加载，等 `B_LOAD_PASS`；第 4 框首帧，等 `B_DMA_SMOKE_PASS`。每次只运行一框。
5. 第 5 框启动显示，等 `B_COLOR_SUBMITTED`。应从左到右 **蓝、绿、红**，有白色外边框和中央十字，稳定约 30 秒；拍照。若显示异常，停止后反馈。
6. 第 6 框在彩条显示期间验证完整 61 帧，最终出现 `B_ALGORITHM_PASS`。第 7 框显示实际 FPGA 图像，出现 `B_MEDICAL_DISPLAY_SUBMITTED`，显示器与网页相同：左原绿色通道，右叠加绿色血管候选；观察并拍照。
7. 第 8 框测速度，三组各 3 帧预热加 100 帧计时。每 20 帧打印进度，最终 `B_TIMING_COMPLETE`；保留输出数字。它分别报告算法 DMA 事务速度和完整循环速度，不能用 60 Hz 配置替代算法 FPS。
8. 完成照片后运行第 9 框，`B_RESULTS_READY` 表示关闭官方显示并打包；屏幕变黑或无信号属于此步预期。Ctrl+S；**File → Download as → Notebook** 下载运行后的 Notebook。回到文件列表下载 `b_results_bundle.zip`，两份文件和两张显示器照片反馈项目独立复核。

若任何阶段红色报错或一分钟无新进展，保存输出并停止；不要重复运行、释放可能仍在传输的缓冲或切换 Overlay。此时不能直接运行“关闭显示”框，应先反馈错误确定恢复方式。Notebook 自动保存会改变输出和时间信息，因此只校验其代码哈希；脚本、bit/HWH 和输入文件仍严格校验原字节哈希。

固定算法和所有参考输入不含 GT。血管候选图不是医学诊断；质量、显示观察及速度证据分别记录。板上日期仍可能旧，保留原时间，以单调高精度 perf_counter_ns 测量耗时。来源、删除组及兼容性边界见 `docs/b_integration_reuse_audit.md`。软件调用原 PYNQ 3.0.1 官方驱动，不改 DMA/VDMA、帧缓存、HDMI/TMDS 或时钟底层。
