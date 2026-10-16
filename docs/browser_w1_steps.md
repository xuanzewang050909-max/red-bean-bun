# W1：原 A4 FPGA 输出到浏览器的完整上板步骤

2026-10-13。首次24任务已完成并[独立核验实际输出](../results/browser_w1_2026-10-13/board_execution_2026-10-13/verification_report.md)；连续组有4帧隐藏，前台FPS待补。本页保留首次完整步骤，已有运行无需重复；当前只执行[前台20帧补测](browser_w1_fps_supplement_steps.md)。直接使用已板测A4 bit/HWH，无需HDMI、安装新Vivado或重跑A0–A4/旧B。

## 上传文件

- `D:\PLD\retina_fpga\build\deploy\browser_a4_w1_r1.zip`
- `D:\PLD\retina_fpga\build\deploy\browser_start.ipynb`

上传两个文件即可，**不要解压后逐个上传**。ZIP 中为原 A4 十二文件的原字节、独立服务与离线界面、两图两尺寸的 RGB-only FOV 输入及独立评价标注（33 份附件加 manifest）。启动 Notebook 自带 ZIP SHA，验证后展开。

Windows 只运行浏览器。PL 实际做增强/背景响应/分割；PS 管理输入、配置、DMA、解包、评分、PNG 编码和网络，没有 CPU 分割后备。主机预览有黄色 HOST TEST 横幅及导出名前缀，不是板测；正式板端页面不会显示该横幅。

## 1. 新建目录并上传

保持板卡和网线连接，确认旧 B/其他 Notebook 已完成、无在途 DMA，本次不要再执行它们。打开原 Jupyter，IP 若仍为 `192.168.2.99`，入口为 `http://192.168.2.99:9090/tree`。

在根目录新建文件夹，命名 `retina_browser_w1_r1`。进入后 Upload 选择上述两个文件，再点文件列表中的 Upload。文件名不要带“(1)”后缀。打开 `browser_start.ipynb`。

每个代码框选中后 Shift+Enter，等待 `In [数字]` 且无红色报错；`In [*]` 仍在运行。**不要 Run All，不要重复运行已完成的框。**

## 2. 验证包（Notebook 第 1 框）

应出现 `PACKAGE_BYTES_PASS: original A4 and browser application bytes checked; FPGA untouched`。验证 ZIP 字节/目录后展开到新子目录 `browser_a4_w1_r1`，尚未导入板级驱动或访问 FPGA。

## 3. 环境预检查（第 2 框）

应出现 `BROWSER_PRECHECK_PASS`、实际版本/驱动文件信息和 `Port reserved: 8090`。检查原 A4 SHA、地址/参数，**FPGA 未改变**。

使用板上已测 PYNQ 3.0.1 / Python 3.10，需要已有 NumPy、Pillow、Tornado ≥6.1。Windows 依赖不带到板端。若报缺依赖、版本、包字节、旧导入或端口占用错误，保留原报错并反馈，勿继续加载或自行升级镜像。

## 4. 加载一次并启动（第 3 框）

应出现 `BROWSER_SERVICE_READY: A4 loaded once; no frame has been sent yet`，并打印 `http://实际板卡IPv4:8090/`。A4 只加载一次，尚未收发图像。保留启动 Notebook 和内核；此后不要运行其他 Overlay 或重跑加载框。

## 5. 浏览器切换验证

Windows 浏览器打开打印的应用地址；IP 未变则为 `http://192.168.2.99:8090/`。9090 是 Jupyter，8090 是新应用。

依次选择并点击“运行 FPGA”，**每次等完成再执行下一项**：

|次序|图像|尺寸|PL 模式|正常证据|
|---|---|---|---|---|
|1|im0001|512|最终掩膜，模式 3|四图；收发各 1,048,576 B；计数 1|
|2|im0002|512|最终掩膜，模式 3|第二图、新任务 ID；计数 2|
|3|im0002|512|初始阈值候选，模式 1|新 PL 模式、新任务 ID；计数 3|
|4|im0001|256|最终掩膜，模式 3|四图尺寸改变；收发各 262,144 B；计数 4|

原图从同一实际 RGB 输入解包；增强/mask/response 从该次 DMA 完成后的只读普通 CPU 快照解包，叠加由真实 mask 着色。每任务保存输入/输出 packed NPY、SHA、GPIO 提交、字节、计数及分段时间。

当前阈值固定 **28**，禁用输入框是 W1 能力限制；可调阈值与核心周期在 W2 派生固件补齐。模式0为输入旁路，只有原图、没有增强/分割评分；模式1/2是中间候选，正式 M0 基线仍为模式3/28。

更改选择时旧图变暗并标历史，指标清空，当前任务导出禁用；新任务成功后才更新。透明度滑块只改变页面显示，不计新 PL 帧，导出叠加 PNG 固定65%。面积由 PS 对实际 mask 在有效 FOV 内计数；AH/VK Dice/IoU 只评价当前图/模式，不是20图留出整体精度。眼底边界、亮区候选属于现有算法结果，W1不声称提高医学质量。

## 6. 连续20帧与状态（第 4 框）

选 `im0001 / 512 / 最终掩膜模式3`，点击“连续运行20帧”。保持页面在前台可见，等最后提示 `连续帧 20 / 20`。正常应累计 **24 个新 PL 任务**。

单硬件工作者，最多一个待执行；nonce重试不重复计算。W1会话最多200任务，防止记录无限增长；不是W5长时验收。

- DMA事务：接收启动前至原官方等待完成，包含流式PL重叠。
- 完整推理：准备好的输入配置提交前至DMA完成并取得普通CPU快照，含分配/原生收发/快照。
- 浏览器延迟：客户端请求、队列/轮询、传输、解码/画布至双rAF近似标记；不相减PS与PC绝对时钟。
- 展示FPS：连续、唯一、可见的新结果数/客户端完整循环。首帧不足连续样本，隐藏过的组不报FPS。
- 核心周期、纯DMA搬运：原硬件无观测，保存null/显示“未测”，不能相减造值。

另存预打包输入SD读取、结构核验/哈希/缓冲释放/原始数据保存窗口、评分/PNG编码时间。W1是含记录开销的诊断负载，预处理输入已准备好；不是完整SD RGB预处理、CPU对照、正式三组性能实验或实时达标证明。

截图完整页面（任务/计数/指标/状态）。第4框打印状态，须 `READY / IDLE`、`active_run_id=None`、`pending=0`。停止后续请求不取消当前DMA，要等待正常完成。

## 7. 导出记录（第 5 框）

运行第5框，等 `BROWSER_RECORDS_READY` 及 `DOWNLOAD: browser_session_bundle.zip`，完整会话包复制到当前 Notebook 同目录。含每任务原NPY/PNG/JSON、评分/原纳秒、浏览器观测、CSV、实际环境、固件/服务manifest和事件日志。网页也可导出；有在途任务时先等完成。

## 8. 安全结束、下载（第 6 框）

执行第6框，无故障/在途缓冲时出现 `BROWSER_SERVICE_CLOSED_IDLE`。HTTP应用关闭，记录保留，Jupyter仍可下载。

Ctrl+S；File → Download as → Notebook下载执行后的 `browser_start.ipynb`。回当前文件夹下载 `browser_session_bundle.zip`。反馈这两个文件和浏览器截图。

项目收到后用 `scripts/verify_browser_w1_archive.py` 独立核验全部输出字、四图/响应像素、输入/配置/固件/计数、评分和客户端时间/FPS。界面“完成”、旧A4板测或主机替身通过不直接升级为新浏览器验收PASS。

## 异常

红色报错、FAULT或超过一分钟无进展时，保留页面、启动 Notebook、原报错和任务记录，停止后续请求并反馈。不要反复执行、关闭失败内核、手动释放在途缓冲或切Overlay。服务不自动重载/重启或用CPU图像代替输出。仅加载前的包/依赖预检查失败可按明确恢复说明换新目录/内核；DMA在途失败先审查记录再决定恢复。
