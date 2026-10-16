# C7 W4.1：同板 CPU / FPGA 处理性能操作

本轮是系统性能实验，不改 C7 算法、分割图或浏览器。亮区误检与细血管优化留到系统初版后继续，不能视为已经解决。发布状态 **BOARD_NOT_RUN**。

## 七步操作

1. 打开 <http://192.168.2.99:9090/tree>。仅关闭已经正常完成、安全结束的旧实验内核。若旧任务仍运行或有FAULT/红色报错，保留并反馈，勿重载FPGA。
2. 在Jupyter新建 **retina_c7_w4_processing_r1** 文件夹。上传下面目录中的**两个文件**（ZIP不要手动解压）：

   `D:\PLD\retina_c7_system\build\deploy\c7_w4_processing_r1\upload`

   - `c7_w4_processing_r1.zip`
   - `c7_w4_processing.ipynb`

3. 打开Notebook，从顶部开始，依次选中代码框按 **Shift+Enter**。等当前结束且无报错再继续；不要点击Run All。

   |代码框|完成标志|
   |---|---|
   |1 校验/解压|`W4_PACKAGE_PASS`|
   |2 环境检查|`W4_PRECHECK_PASS`|
   |3 加载一次|`W4_LOAD_PASS`|
   |4 测256|`W4_256_COMPLETE`|
   |5 测512|`W4_512_COMPLETE`|
   |6 汇总|`W4_SUMMARY_READY`|
   |7 安全结束/打包|`W4_RESULTS_READY`，显示`CLOSED_IDLE`|

4. 第4、5框各有3轮，每轮CPU和PL分别 **3帧预热＋100帧计时**。每种尺寸各309次CPU＋309次真实PL；两尺寸总计618次CPU＋618次PL。固定im0001/C7/T112/最终模式，每帧打印进度；ARM计算可能较慢，不预先承诺耗时。不在其他Notebook运行任务，也不要在8090提交任务。本轮没有启动8090服务，全部操作在Jupyter完成。
5. 第6框核查12组各100个计时样本，预热没有混入。输出正确性逐帧核对；PS CPU输出只是对照。真实PL核心、DMA事务、完整推理和调用时间分开，不相加/相减冒充纯DMA或浏览器FPS。
6. 第7框完成后按 **Ctrl+S**，再 **File → Download as → Notebook** 下载运行后的 `c7_w4_processing.ipynb`；回到同一文件夹，下载 `c7_w4_processing_results.zip`。
7. 下载完成后告诉我“已下载”。若任何框红色报错或60秒没有新进度，立即停止并保留输出/内核，不重跑，不重启，不切换Overlay，不释放失败缓冲。第2框OpenCV缺失/端口占用是在加载FPGA前停止，也先反馈原文。若失败不会要求继续第6/7框；Notebook和现场文件仍保留。

## 本轮测量范围

- C7 bit/HWH/100MHz观察器/官方DMA与PYNQ3.0.1驱动复用已验版本，只下载一次。
- 输入读取与模型加载在计时外，CPU特征、树推理和输出分配在计时内；PL `inference_ns` 从配置前至普通数组快照就绪，调用时间还含原驱动校验/哈希/缓冲释放。CPU与PL调用范围均记录，不把纯核时间作为系统加速比。
- 每轮交替CPU/PL先后顺序，保存每组前后CPU频率、负载、内存和可读取的温度信息；不假定恒温或固定CPU频率。
- CPU对照使用固定NumPy/OpenCV整数同输出模型，OpenCV线程1、禁OpenCL；不是最优手写ARM实现。输入不含GT，完整返回增强/分数/掩膜/rawG四通道；不执行最终被C7覆盖的C5运算来拖慢CPU。
- 实际归档循环FPS包含逐帧核对、数组落盘和日志同步，是实验取证开销下的循环速度，不是浏览器显示FPS。
- 剩余W4：512浏览器3×(3+100)、独立纯DMA回环、功耗。之后W5至少30分钟且1000任务，再材料初版、恢复质量优化、最终回归。

## 回收后独立核验（由Codex执行）

将原始两文件保存在全新 `build/board_results/c7_w4_processing_<日期>/`，保留下载原件和SHA。运行：

```powershell
& D:/PLD/retina_fpga/.venv/Scripts/python.exe -X utf8 -B D:/PLD/retina_c7_system/scripts/verify_c7_w4_results.py D:/PLD/retina_c7_system/build/deploy/c7_w4_processing_r1 <结果ZIP绝对路径> <运行后Notebook绝对路径> <全新核验JSON绝对路径>
```

核验1236个完整数组、618个实际PL序号/字节/参数/硬件周期、CPU/PL证据分离、单调时间窗口、12组统计和安全关闭。任何一项失败保留失败，不修改原始数据后强行通过。通过也只能标记W4.1处理性能已核验。

## C7回滚与保留

本轮算法/bit没有变化。只有本轮已`CLOSED_IDLE`且无失败时，才关闭成功内核，按原 `D:/PLD/retina_fpga/docs/q4d_c7_board_steps.md` 的可信C7启动步骤恢复原浏览器；保留旧结果，不重跑已完成质量队列。若本轮FAULT/超时，停止并反馈，不自动卸载/切换。原C7/C8/R1/R2工作树和失败证据全部保留。
