# C7 W4b：浏览器正式性能七框步骤

W4.1 真实 ARM/PL 对照已核验，详见 `docs/c7_w4_processing_results_2026-10-16.md`。本轮只测试浏览器完整链路，C7 算法、bit/HWH、原 DMA 驱动、增强/掩膜/叠加像素规则不变。质量研究仍留在后续。

本轮状态：`BOARD_NOT_RUN`。Windows 负责浏览器交互、解码和绘制；板载 ARM 负责调度、文件/网络、评价和编码；增强与分割在真实 PL 执行。包内没有 CPU 算法参考或回退。

1. 打开 <http://192.168.2.99:9090/tree>，在 **Running** 页关闭上一轮已经成功结束的测试内核。若旧内核还有错误或在途操作，保留现场，不直接关闭。
2. 新建 **retina_c7_w4_browser_r1**，上传以下目录中的**两个文件**，不要在 Windows 解压 ZIP：
   `D:\PLD\retina_c7_system\build\deploy\c7_w4_browser_r1\upload`
   - `c7_w4_browser_r1.zip`
   - `c7_w4_browser.ipynb`
   断电不会删除 SD 上旧目录；本轮使用全新文件夹，不删除旧结果，不改 `exist_ok=False`。若同名目录已用过，改建 `retina_c7_w4_browser_r1_attempt2`。
3. 打开 Notebook，逐个代码框按 **Shift+Enter**，等结束且无红色报错再继续。不要 Run All。

| 框 | 操作与完成标志 |
|---|---|
| 1 | 文件校验/解压：`W4B_PACKAGE_PASS` |
| 2 | 检查环境/保留 8090：`W4B_PRECHECK_PASS`；此时未加载 FPGA |
| 3 | 只加载一次：`BROWSER_SERVICE_READY` |
| 4 | `W4B_BROWSER_READY`；然后进行下方浏览器操作，先不要运行第 5 框 |
| 5 | 浏览器全部结束后统计：`W4B_SUMMARY_READY`，应有三轮，每轮 100 个计时样本 |
| 6 | 安全关闭：`W4B_CLOSED_IDLE` |
| 7 | 打包：`W4B_RESULTS_READY`；打包期间会打印 `W4B_EXPORT_PROGRESS` |

**第 4 框之后：** 打开 <http://192.168.2.99:8090/>，按 **Ctrl+F5**，确认页眉 **W4b · C7 正式性能**。固定 im0001、512×512、C7、阈值112、最终模式3、快速无损 PNG，参数框锁定正常。

点击一次 **“开始3轮：每轮预热3帧＋测量100帧”**。自动完成三轮，每轮3帧预热＋100帧计时，共 **309 次新的 PL 处理**。保持此页前台，不切换标签页、不最小化、不刷新、不锁屏或休眠。预计约10分钟，实际耗时以板测为准。

出现 **`W4B_BROWSER_COMPLETE`、完成309/309、READY / IDLE** 后截图，再返回 Notebook 运行第5、6、7框。三轮 FPS 各自用该轮100个唯一已绘制结果除以同一客户端单调时钟的总时间，包含 HTTP、轮询、传输/解码/绘制及任务间等待，剔除预热。双 rAF 是绘制近似，不是物理扫描时间。

最后 **Ctrl+S**，通过 **File → Download as → Notebook (.ipynb)** 下载运行后的 `c7_w4_browser.ipynb`；再从同目录下载 **`c7_w4_browser_results.zip`**。必须使用第7框生成的完整包，网页会话导出不包含正式汇总。完成后告诉我“已下载”，并提供完成画面。

红色报错、网页显示停止或 **60秒无新进展**：停止操作，保留输出与内核，不重试、重载 FPGA、重启或释放失败缓存。隐藏/中断的三轮不能算正式通过；不要为了凑计数重新开始。

## 下载后的独立审查

原件复制到新的 `build/board_results/c7_w4_browser_<日期>/`，不覆盖历史。运行：

```powershell
& 'D:/PLD/retina_fpga/.venv/Scripts/python.exe' -X utf8 -B scripts/verify_c7_w4_browser.py <结果ZIP> <运行后Notebook> <全新核验目录> --release build/deploy/c7_w4_browser_r1
```

核对完整309份输入/输出、81,002,496个输出字、1,545 PNG、真实锁存参数/连续 PL计数、包身份、原始时间边界、三轮各100次前台绘制、CSV、生命周期、七框原代码及安全关闭。主机替身不能当板测；有实际观测后才报告数据，不自动提升为实时或质量达标。

后续：独立纯DMA/功耗 → W5稳定性与交互恢复 → 材料初版 → 质量优化 → 最终回归。
