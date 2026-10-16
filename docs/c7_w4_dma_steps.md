# C7系统 W4c：独立纯DMA七框操作

本轮复用已验证A0 r2回环硬件，C7算法与质量结果不变。新正式计时状态`BOARD_NOT_RUN`。没有HDMI，也不用打开8090实验页。Jupyter仍为 <http://192.168.2.99:9090/tree>。

1. 上一轮W4b两份下载现已完整核验并归档，七框与安全关闭通过，无需重跑。保留`c7_w4_browser_results.zip`与运行后的`c7_w4_browser.ipynb`；接下来使用新目录测独立DMA。
2. 在Running页关闭**已正常结束**的旧测试内核。错误或未结束的内核不能直接关闭/重载。
3. 新建 **retina_c7_w4_dma_r1**，上传下列目录的**全部两个文件**，不要手动解压：
   `D:\PLD\retina_c7_system\build\deploy\c7_w4_dma_r1\upload`
   文件为`c7_w4_dma_r1.zip`和`c7_w4_dma.ipynb`。如果这个板端文件夹已用过，另建`retina_c7_w4_dma_r1_attempt2`，不删除原结果、不修改exist_ok=False。
4. 打开Notebook，逐框Shift+Enter，当前框结束且无红色报错才继续，不Run All。

| 框 | 内容 | 完成标志 |
|---|---|---|
| 1 | 校验配对文件并解压到新子目录 | `W4C_PACKAGE_PASS` |
| 2 | 运行环境、8090已释放、剩余空间检查；尚未加载FPGA | `W4C_PRECHECK_PASS` |
| 3 | 加载可信回环overlay一次 | `W4C_LOAD_PASS` |
| 4 | 17字短包逐字核验 | `W4C_SMOKE_PASS` |
| 5 | 256：3轮×(3预热＋100计时) | `W4C_256_COMPLETE` |
| 6 | 512：3轮×(3预热＋100计时) | `W4C_512_COMPLETE` |
| 7 | 空闲核验、关闭、完整打包 | 先`W4C_CLOSED_IDLE`，再`W4C_RESULTS_READY` |

第5、6框每次显示`W4C_FRAME_SAVED`，最后619/619；第7框会显示`W4C_EXPORT_PROGRESS`。这次只在Jupyter运行，无需切换实验网页，不与其他板上实验并行。

5. **Ctrl+S**，通过File→Download as→Notebook下载运行后的`c7_w4_dma.ipynb`；回到同级文件列表下载`c7_w4_dma_results.zip`。下载完成后告诉我保存目录。

遇红色报错或一分钟无新进度：停止，保留输出和内核，不重复运行、不重载、不释放失败缓冲。第2框提示8090占用时，先保留错误，核对上一轮是否已安全关闭。

## 回收方法

原件复制到全新`build/board_results/c7_w4_dma_<日期>/`，然后在本工程运行：

```powershell
& 'D:/PLD/retina_fpga/.venv/Scripts/python.exe' -X utf8 -B scripts/verify_c7_w4_dma.py <结果ZIP> <运行后的Notebook> <全新核验目录> --release build/deploy/c7_w4_dma_r1
```

正式审查通过后才报告两尺寸每轮100样本的中位数/均值/p95和双向有效载荷吞吐。这是独立回环的主机可见事务时间，不是C7核心时间，也不是浏览器FPS。下一步功耗实测条件核对，然后W5稳定性与交互恢复。
