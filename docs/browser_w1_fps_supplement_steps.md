# W1 前台连续显示补测

**2026-10-14完成记录：** 新20帧全部前台，原始DMA/图像/评分/计时严格核验通过，实测0.187173 FPS。见[补测报告](../results/browser_w1_fps_2026-10-14/board_execution_2026-10-14/verification_report.md)。以下保留原操作过程，当前无需重复执行。此包使用原A4算法A，未包含亮区改进。

2026-10-13。上一轮24次真实任务、6,094,848个输出字、120张PNG以及评分/计数/时间已独立核验。连续20帧中第2、5、14、15帧记录页面隐藏，整组可见FPS为null。本轮只补显示计时，不重做四项图像/模式/尺寸切换。

复用原发布ZIP、启动Notebook、原A4 bit/HWH、官方驱动和全部记录逻辑，不修改板端包。原会话与第一次严格审核失败记录保留；新会话结合原会话的已核验覆盖范围验收。

## 1. 新建补测目录

在Jupyter Running页关闭上一轮已正常完成的启动Notebook内核。上一轮已打印 `BROWSER_SERVICE_CLOSED_IDLE`，属于安全结束；不要把此操作用于FAULT或DMA未完成的内核。

新建 `retina_browser_w1_fps_r1`，进入后上传以下两个原文件，名称保持不变：

- `D:\PLD\retina_fpga\build\deploy\browser_a4_w1_r1.zip`
- `D:\PLD\retina_fpga\build\deploy\browser_start.ipynb`

打开新目录的 `browser_start.ipynb`，每框Shift+Enter，当前框结束且无报错再继续。

|代码框|完成标志|
|---|---|
|1：核对并展开包|`PACKAGE_BYTES_PASS`|
|2：检查环境|`BROWSER_PRECHECK_PASS`|
|3：启动服务|`BROWSER_SERVICE_READY`，本会话只加载一次|
|4：查看状态，浏览器测试完成后运行|`completed: 20`、`accepted: 20`、`hardware_state: IDLE`、`active_run_id: None`、`pending: 0`、`retained_buffer_count: 0`、`error: None`|
|5：打包|`BROWSER_RECORDS_READY` 和 `DOWNLOAD: browser_session_bundle.zip`|
|6：正常关闭|`BROWSER_SERVICE_CLOSED_IDLE`|

若因为页面隐藏而追加了一组20帧，第4框计数应为40，记录仍全部保留，不能删掉第一组。上限为200任务，未达上限的可见性补测无需重载FPGA。

## 2. 只补连续20帧

第3框成功后，打开 `http://192.168.2.99:8090/`；如浏览器还保留旧应用页面，正常刷新一次以获取新会话，之后开始测试再保持页面。

选择 `im0001`、`512 × 512`、最终掩膜 `final`、阈值固定28。直接点击“连续20帧”，不必先点击单次运行。本轮每帧仍重新执行真实PL计算，参数和原始记录仍绑定独立任务ID。

从点击到20/20完成，保持应用标签在前台，窗口不最小化，不切换Jupyter/其他标签，不锁屏。可在结束后截图和返回Notebook。依上一轮数据整组约需2分钟；每帧主要时间是PS解包/叠加/PNG及哈希，不是约32ms的推理本身。

结束时应显示具体 `… FPS`；第1帧显示“未形成连续样本”正常。如果到20/20仍为该提示，整组可能出现隐藏记录。保持当前页面在前台再点击一次“连续20帧”，作为新的完整连续组；不要改原记录的可见性或自行把20/耗时标成有效FPS。

## 3. 留证并下载

连续组完成、出现数字FPS后，截图保存当前任务ID、FPS、延迟与20/20提示。回Notebook运行第4、5、6框；Ctrl+S，下载执行后的 `browser_start.ipynb` 和同目录 `browser_session_bundle.zip`。保存为新文件即可，不覆盖上一轮原件。

红色报错/FAULT，或一分钟没有任何进展：停止操作并保留输出、启动Notebook和引用；不重复运行、不关闭失败内核、不重载Overlay。普通可见性无效并不表示DMA故障，允许在服务正常IDLE时开启下一组20帧。

## 项目离线核验

补测使用严格的可见20帧规则，且重新核验上一轮两图/两模式/两尺寸及全部原数组，不能仅拿一份手写PASS作为覆盖证据：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B scripts/verify_browser_w1_archive.py NEW_ARCHIVE NEW_NOTEBOOK NEW_DESTINATION --prior-archive build/board_results/browser_w1_2026-10-13/browser_session_bundle.zip --prior-notebook build/board_results/browser_w1_2026-10-13/browser_start.ipynb
```

新包的会话ID和原包SHA必须不同，原A4/应用manifest仍须精确匹配。缺有效前台组继续判失败。此补测仍不是3预热+100计时的正式性能实验，不补出核心周期、纯DMA或可调阈值，也不提升医学质量结论。
