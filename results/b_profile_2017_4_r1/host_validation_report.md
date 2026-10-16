# B 分段性能诊断 r1：主机交付检查

2026-10-12。状态：**主机检查通过，分段诊断实体板 NOT_RUN。** 已测 B r2 的功能/显示和512×512 DMA平均4.866ms、完整核验/排版/提交循环1.601FPS保留在原归档；当前没有新的板端分段数字或优化结论。

交付目录：`D:\PLD\retina_fpga\build\deploy\b_profile_2017_4_r1`，17文件。旧B r2十三文件（含bit/HWH、全部辅助脚本、输入、原Notebook、原manifest和原说明）逐字不变；另加profiling脚本、六框Notebook、独立manifest和操作说明。原发布和已下载结果均未覆盖，没有重新综合/实现。

## 计时契约

只加载一次相同B；原256短帧确认后启动官方720p60显示，再重复512×512 STARE模式3。固定3预热+30计时，共34个算法帧，连续输入/输出计数逐帧检查。每帧完整uint32比较，发收字节数与DMA/视频状态检查保留。真实输出和最后实际排版图像另存NPY/PNG。

|环节|范围|
|---|---|
|dma_transfer|原recv/send.transfer、原1ms有界idle轮询、原wait及缓存维护|
|word_compare|完整数组与冻结参考逐字比较|
|algorithm_status|收发字节数和GPIO计数/错误检查|
|ps_layout|原样调用B r2 medical_canvas，包括原图/叠加、PIL标题和白色进度标记|
|frame_allocate|官方newframe及布局、地址、公开缓存属性检查|
|frame_copy|将原排版BGR画布复制到官方显示帧|
|display_submit|官方writeframe与所有权转交，包含其内部flush和IRQ等待|
|video_status|官方MM2S状态及running检查|
|output_hash|实际输出字节化和SHA256|
|record_and_progress|逐帧记录构建及每5计时帧进度打印|

相邻边界的10个差值精确等于逐帧总时间；保留全部33帧边界，单独剔除3预热。完整循环保存起止纳秒，少量尾部计时记录赋值与帧间簿记以差额单列，不归到DMA或显示阶段。每阶段均值/中位数/p95/占比和循环FPS从真实原值计算。初始读图/参考生成/算法缓冲分配填充、预热、最终JSON/PNG/NPY/ZIP保存和关闭显示不计入循环。

官方PYNQ3.0.1 MM2S默认cacheable_frames=True；本程序仅记录实际属性，不改变缓存策略。writeframe保留完整官方调用，不另做一次flush或自行改中断/帧缓存。算法双缓冲只在全部成功且idle后释放；提交成功的显示帧交官方VDMA所有，不自行释放/复用。任何失败都保留可能在使用的引用并阻止后续阶段。

## 实际主机检查

19项检查通过，日志`host_tests.log`。覆盖原始时间边界/分段总和/预热/循环公式、缺帧/乱序/倒退/计时篡改拒绝、真实格式打包、原排版逐像素一致、一次官方提交刷新和所有权、输出/字节数/计数故障、错位DDR、显示提交故障、变更Overlay、失败阻止关闭、原13文件哈希、自动保存允许但代码变化拒绝、固定契约和NOT_RUN、旧结果保护及旧导入拒绝。

预检查测试实际执行固定PYNQ3.0.1 Common及video包初始化器，硬件依赖使用明确的主机facade；只创建Overlay(download=False)读取原HWH元数据，分配facade拒绝所有调用。动态收发/显示由合成主机数据模拟，**这些测试不是实体板结果**。新脚本和全部新Notebook代码按Python3.10语法解析；官方dma/hierarchies/buffer源码与原SOURCE_MANIFEST哈希对照一致。`host_test_sources.json`、`release_manifest.json`及`package_validation.json`记录精确来源和组装配对。

下一步用户按六框流程运行，下载`b_performance_profile.ipynb`和`b_profile_bundle.zip`。接收到真实结果后独立复算每阶段/循环时间、逐字核验实际数组及显示参考，再决定优化位置。固定输入的诊断FPS不等于SD读图到屏幕延迟、纯PL周期或显示扫描Hz；本次不改变医学算法/质量结论。
