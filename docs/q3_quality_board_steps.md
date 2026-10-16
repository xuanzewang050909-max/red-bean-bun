# Q3 全20图真实FPGA质量验证操作步骤

W4a真实对照已复核：50任务、13,107,200输出字和250张PNG一致。默认/快速无损PNG各3预热+20前台计时，0.184570→0.584349 FPS（约3.17倍）。只改变PS编码设置，PL算法及医学像素未变。

Q3包通过14项不同主机检查；80次HOST替身任务、13,107,200输出字及400张PNG的核验仅证明采集/验证程序，不是这轮真实板测结果。Q3实体板状态NOT_RUN，质量结论待真实下载。测试亮区误检改善是否跨图成立，同时报告真血管漏检。算法A/C2和阈值28冻结，不根据留出或VK重选参数。

1. 确认上轮已正常结束并下载，关闭旧8090实验网页；在Jupyter Running页关闭上轮已经成功完成的测试内核。不要关闭失败或仍有在途DMA的内核。
2. Jupyter新建 `retina_q3_quality_r1` 文件夹，上传 `D:\PLD\retina_fpga\build\deploy\q3_quality_upload_r1` 中仅有的两个文件：`q3_full_quality_r1.zip`、`q3_quality_start.ipynb`。ZIP不必手动解压。
3. 打开 `q3_quality_start.ipynb`，代码框依次Shift+Enter，当前框结束且无红色报错后再继续，不使用Run All。

|代码框|完成标志|
|---|---|
|1 验证并展开|`PACKAGE_BYTES_PASS`|
|2 环境检查|`Q3_PRECHECK_PASS`（也打印原服务预检查和环境）|
|3 加载一次并启动服务|`BROWSER_SERVICE_READY`|
|4 自动收集80帧|每帧打印 `Q3_FRAME_SAVED: n/80`；最后 `Q3_COLLECTION_COMPLETE`|
|5 浏览器预览后核对|先完成下文两次浏览器操作；状态 `completed: 82`、`READY/IDLE`、`pending: 0`、无error/保留缓冲|
|6 打包|`Q3_RESULTS_READY`|
|7 正常关闭|`BROWSER_SERVICE_CLOSED_IDLE`|

第4框自动完成20张图×256/512×A/C2共80次新PL收发。期间不要在其他网页提交FPGA任务；不用手动逐帧点击。等待每帧打印，不按一次总时长判断卡死。全部原始NPY、PNG、配置回读、计时和评分保存；集合完成不等于医学质量达标。

4. **第4框完成后、第5框之前**：打开 `http://192.168.2.99:8090/`，按Ctrl+F5，页眉应显示Q3。固定 **512×512、C2、最终掩膜/模式3、阈值28、快速无损PNG**。先选 **im0002** 点击运行FPGA，等待同帧四图并截图；再选 **im0324** 点击运行并截图。保持页面前台；这两次预览不计入前80帧固定质量样本。不要点击“预热3帧+测量20帧”。单次预览“未形成连续样本”正常，本轮不测浏览器连续FPS。
5. 回Notebook完成第5、6、7框。Ctrl+S，File → Download as → Notebook，下载运行后的 `q3_quality_start.ipynb`；回文件列表下载同目录 `q3_results_bundle.zip`。反馈两文件“已下载”和两张预览截图。**使用Notebook第6框的Q3包**，网页导出的普通会话包不含固定采集队列元数据。

遇到红色报错或一分钟没有新的帧完成打印就停下，保留输出和内核；不重复运行、重载Overlay、释放缓冲或关闭失败内核。板测失败记录也保留。

下载后项目用 `scripts/verify_q3_archive.py` 独立逐字核验全部原始输出、PNG、参数/计数/时序、CSV、Notebook；再按原10训练/10留出分别统计AH和VK的Dice/IoU/Precision/Recall，以及亮核、亮带、细标注代理和FOV边缘。区域定义、门槛与候选已在69aaa7e预注册；完整FOV不缩小，没有全亮区硬删除。未过门槛如实报告，不改变原A28。

后续W4仍需同PS CPU对照、纯DMA独立测量、3预热+100计时×三配置×三复测，以及资源/功耗与W5长时稳定性。本轮不替代这些项目，也不再引入HDMI。
