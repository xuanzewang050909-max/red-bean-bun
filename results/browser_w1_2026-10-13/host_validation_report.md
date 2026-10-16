# W1 浏览器应用主机验证与交付

2026-10-13。**HOST PASS；首次新浏览器实体板测试 NOT_RUN。** 本轮不生成新 bit/HWH，不改冻结 M0、官方驱动或原发布。使用原 A4，实验与演示无需 HDMI。

## 交付

上传 `build/deploy/browser_a4_w1_r1.zip` 和 `build/deploy/browser_start.ipynb` 两文件；ZIP 为33附件加manifest，原A4十二文件逐字节相同。操作见 [完整指南](../../docs/browser_w1_steps.md)。启动Notebook6代码框，先校验ZIP/展开，再核对源、版本、原HWH参数/地址并保留8090端口，加载一次，运行交互，导出，最后仅空闲无故障时结束服务。

W1开放im0001/im0002、256/512、模式0–3及固定阈值28。增强/mask/响应只解包实际DMA完成后的只读普通CPU快照；叠加由该mask显示混合，不执行CPU医学算法。新服务不导入医疗参考或旧A1–A4医疗测试脚本；原十二文件中的历史助手保留原字节但不由应用执行。只有原A0 bounded poll助手被加载使用。GT隔离在完成后的评价侧；预检查的GT文件SHA仅是包完整性检查。

## 证据

- [最后23项测试日志](host_tests_ownership_final.log)：无跳过。执行原官方 `_SDMAChannel.transfer/wait` 类代码及原poll，MMIO/PL/CMA为明确HOST测试替身，不是实体板。两图/两尺寸/四模式、接收先启动/发送flush/官方接收invalidate、只读独立快照、完整字/字节/状态/计数及wrap检查。
- 13类native故障与快照失败、第二次分配失败/部分释放、线程所有权保护；故障引用保留、后续拒绝、不重载或CPU回退。另测取消异步等待时Native继续正常完成后才释放，独立failure.json不被迟到结果覆盖，服务仍停机。
- 真实本机HTTP：一个工作者和一个待执行槽、立即预留active、nonce去重、422/409、同帧图/不可缓存头、旁路无旧评分/掩膜、过期/重放/非有限客户端时间拒绝、可见连续唯一帧FPS及隐藏无效、只在空闲导出、原NPY/JSON/CSV/浏览器观测；SD记录失败仍保护状态。
- [浏览器QA](browser_qa.json)、[最终界面截图](host_preview_final.jpg)：本机127.0.0.1、黄色HOST横幅、两图/两尺寸/两模式4任务+20连续任务、旧帧导出禁用、控制/完成状态/实际下载，页面控制台无错误/警告。导出带 `HOST_TEST_` 前缀，生产ZIP没有测试替身或CPU黄金生成器。
- 下载HOST会话原数据由独立M0工具重新检查 **24帧 / 6,094,848字**，全部输入/输出/PNG像素/当前评分/原纳秒边界一致；20客户端循环样本和FPS公式复算。不是本次PL质量、速度或功耗测量。浏览器只读DOM工具不提供canvas像素读取，所以不宣称客户端像素SHA；服务器PNG全像素检查与浏览器目视检查分别记录。
- [发布核验](release_validation.json)：45份W0保护的原件/旧发布/原任务书/参考/证据原SHA保持；原A4十二文件原字节一致；新6个Python模块、3个UI文件与部署包一致，Python3.10语法、Notebook6框/ZIP SHA/完整目录验证通过。

最后源码增量加强服务异常/日志/取消等待保护，并统一新JSON/启动Notebook输出为LF，保证部署与Git源字节配对；由最后23项测试覆盖。浏览器截图与下载采集时的UI、输入、GT和A4字节与最终包完全相同，捕获后的代码差异明确记录在发布JSON，不把旧截图当作新故障路径真机测试。

初次打包将灰度STARE标注当RGB归约，导致AxisError，已修正为按二维灰度前景读取；[原失败](initial_host_failure.json)保留。原预处理未改，im0001两尺寸与原A4输入逐字匹配，带/不带标注准备出的算法输入一致。原17/22项成功日志和初始预览亦保留。

## 能力与未完成项

端到端浏览器计时来自客户端performance.now，绘制用双rAF近似；不相减板端与PC绝对时钟，不把显示回调当算法帧。DMA事务含PL流式重叠，完整推理含配置/分配/原生收发/快照，worker另列SD预打包输入读取、核验/哈希/释放/保存窗口、评分/PNG。服务记录及网络/轮询开销计入实际展示循环。

原阈值固定28，无核心周期或latched参数回读；这些及纯DMA搬运保持null。W1最多200任务，非30分钟/1000帧稳定验收。两图当前评分不是20图训练/留出macro实验；CPU对照、正式三组/三次性能复测、纯PL/搬运、DDR分析、功耗估计、可调固件和最终报告/视频尚待后续。G01–G09不由HOST结果置PASS，旧6.734FPS不改称浏览器速度。

接收真实板端 `browser_start.ipynb`、`browser_session_bundle.zip` 和截图后，用 `scripts/verify_browser_w1_archive.py` 校验完整字、PNG、配置/配对/字节/连贯PL计数、评分、原时钟和CSV/客户端循环；该入口明确拒绝HOST TEST证据。

## 复现

```powershell
.\.venv\Scripts\python.exe -X utf8 -B scripts/package_browser_w1.py
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -p test_browser_w1.py -v
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_browser_w1_release.py
```

不要覆盖已交付ZIP后与旧启动Notebook混用；重新打包需使用配套生成的Notebook及新SHA。真实PYNQ依赖在预检查打印，不向板端安装Windows依赖。Tornado线程执行器用法参见[官方协程文档](https://www.tornadoweb.org/en/stable/guide/coroutines.html#calling-blocking-functions)；客户端时钟/绘制范围依据[MDN performance.now](https://developer.mozilla.org/en-US/docs/Web/API/Performance/now)与[requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)。
