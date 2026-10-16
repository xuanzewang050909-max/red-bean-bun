# W4a：无损 PNG 对照与 PS 分段板测

本轮保持真实 W2/C2 医学硬件与 W3 驱动，比较默认 PNG 与快速无损 PNG。新增分段记录用于定位约 5 秒浏览器等待；实际提速待板测。32 项主机检查通过，不能作为板端性能结论。

1. 在旧 W3 Notebook 确认上一轮已经出现 `BROWSER_SERVICE_CLOSED_IDLE`。在 Jupyter **Running** 页关闭之前成功完成的内核；保留任何失败内核及输出。关闭旧 8090 实验页面。
2. 在 Jupyter 新建文件夹 **retina_browser_w4a_r1**，上传 `D:\PLD\retina_fpga\build\deploy\browser_w4a_upload_r1` 中 **两个文件**：`browser_w4a_png_r1.zip`、`browser_w4a_start.ipynb`。ZIP 不需要手工解压。
3. 打开 **browser_w4a_start.ipynb**，依次选中前三个代码框，按 **Shift+Enter**；当前框变为 `In [数字]` 且无报错后再继续。不要 Run All，也不要重复运行已完成的框。

|代码框|完成标志|
|---|---|
|1 验证并展开|`PACKAGE_BYTES_PASS`|
|2 检查环境/端口|`BROWSER_PRECHECK_PASS`|
|3 加载一次/启动|`BROWSER_SERVICE_READY`；状态 IDLE，completed 0|

4. 打开 **http://192.168.2.99:8090/**，确认页眉 **W4a**。如显示旧 W3，刷新一次；仍是旧版则停止反馈。统一设置 **im0001、512×512、阈值28、最终掩膜·模式3**，按下表每行点击一次“运行 FPGA”，等待任务完成再下一行：

|顺序|PL 算法|图像传输方案|
|---|---|---|
|1|A · 原始基线|原方案 · 默认 PNG|
|2|A · 原始基线|快速候选 · 无损 PNG|
|3|C2 · 双侧支持|原方案 · 默认 PNG|
|4|C2 · 双侧支持|快速候选 · 无损 PNG|

同算法两种传输方案的增强、掩膜、叠加和 Dice 应一致；A 与 C2 本来会不同。原方案/快速候选只改变 PS 无损编码，每次点击仍触发新 PL 计算。PNG 文件大小或文件哈希可以不同，下载后将比较解码像素与原始 DMA 数组。保持叠加透明度65%。

5. 固定 **im0001 / 512 / C2 / T28 / 最终掩膜**，做两组：先选“**原方案 · 默认 PNG**”，点“**预热 3 帧 + 测量 20 帧**”；待显示“连续帧 20 /20”且 IDLE 后截图。再选“**快速候选 · 无损 PNG**”，点相同按钮，完成后再次截图。截图尽量包含方案、性能卡片和下方“PS 分段耗时”。两组运行时保持实验网页前台、不切标签、不改参数；不要中途导出。每组真实运行23帧，前三帧预热不计入FPS，20个后续新任务才计时。
6. 返回 Notebook，按顺序运行后三个代码框：

|代码框|完成标志|
|---|---|
|4 查看状态|`hardware_state: IDLE`，`completed: 50`，`pending: 0`，`retained_buffer_count: 0`，`error: None`|
|5 打包|`BROWSER_RECORDS_READY`，生成 `browser_w4a_session_bundle.zip`|
|6 安全关闭|`BROWSER_SERVICE_CLOSED_IDLE`|

如果额外手动点击了几次，completed 可能大于50，不必重跑；全部保留并反馈。两组连续测试各只做一次，若中途切后台请保留现状说明原因，不能将无效组当作前台 FPS。

7. 按 **Ctrl+S**；**File → Download as → Notebook** 下载运行后的 **browser_w4a_start.ipynb**。回文件列表下载 **browser_w4a_session_bundle.zip**。两份文件下载到 Windows 默认“下载”文件夹后，发两组截图并告诉我“已下载”。无需逐个下载大量 PNG/NPY。

遇到红色报错、FAULT 或一分钟没有新进展，立即停下并保留输出；不重复运行，不关闭失败内核，不释放在途缓冲，不切换 Overlay。尚未完成时不要运行第6框。8090被占用时保留第2框报错，不继续加载。

## 记录范围

该包一次加载、4 手动帧和46预热/计时帧共50帧，原 A/C2 和阈值真实由 PL 执行。板端分别记录核心周期、DMA事务、完整推理、数组解包/叠加、PIL转换、PNG编码及写入、PNG哈希、文件清单哈希与字节数；浏览器用自身单调时钟记录请求至绘制近似。PNG编码段不是纯压缩，DMA与PL重叠，不能相减得到纯搬运。

W4a仍为定位实验。完整 W4+Q3 的20图、256/512、AH/VK固定划分、同PS CPU对照、三性能配置各3预热+100计时及三次复测，以及W5稳定性仍按原设计继续。纯DMA独立搬运未测。此次不重新筛选医学参数。

下载后使用 `scripts/verify_browser_w4a_archive.py` 独立核验全字、PNG、评分、参数回读、每帧原始时间、两组预热/前台观测及CSV。主机报告：[host_validation_report.md](../results/browser_w4a_2026-10-14/host_validation_report.md)。
