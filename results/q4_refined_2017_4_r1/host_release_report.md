# Q4 C5 主机实现与板测发布记录

2026-10-14，状态 **HOST_RELEASE_READY_BOARD_NOT_RUN**。依据用户“继续工作直到需要人工网页操作；严格门槛反复失败可取最好整体折中候选”的明确授权，固定237d58d决策中的C5_l5_9_r8_m1_a4_g3。本轮不继续调候选，不将原121候选的严格失败改为通过。

## 结果与范围

|检查|真实主机结果|
|---|---|
|HLS Csim|18帧，2,555,904输出字全匹配|
|实际生成RTL|17完整帧，2,490,368字；两尺寸/阶段/A-C2-C5/动态阈值/帧内改参/背压/异常TLAST/TKEEP/中途复位与恢复|
|帧保护单元|另6帧589,824字；替身核心，仅用于guard配置/计数/饱和/复位，不能代替医疗RTL|
|厂商实际reset IP|通过，保留标准PS7与100MHz复位通路|
|Vivado 2017.4完整实现|24,630 LUT、18,044 FF、80 BRAM Tile、1 DSP|
|100MHz时序|WNS 0.517ns / WHS 0.025ns / WPWS 3.750ns；时序满足|
|RTL配对|98份生成RTL/ROM在综合、封装和实际实现之间逐字节一致|
|Python主机检查|26浏览器/原生驱动所有权/API/错误处理＋4自动批采集＋8发布/定点/复用＋7最终提取/手动证据/错误SHA，共45项不同测试通过|
|主机批采集替身|120任务，19,660,800字、600PNG、176,947,200解码通道值独立核对；明确HOST_TEST_DOUBLE_NOT_BOARD|
|旧文件保护|与D1前记录比较，179个生产/发布文件字节不变|

完整证据和来源哈希见[verification.json](verification.json)、[source_files.json](source_files.json)、[hardware_check.json](hardware_check.json)。测试原日志分四份归档，非每份重复计数；后7项在最终上传包上验证当前Notebook解压与篡改拒绝、全部手动覆盖门槛以及实际输出SHA错误停止行为。

## 复用与语义

原A/C2运算体保留，派生base只改函数名、删除嵌套顶层的四条接口pragma并增加来源注释；见[差异](base_derivation.diff)。原厂2017.4 Filter2D/filter_opr/Window/行缓存不改。PS7、AXI DMA、DDR/FIFO/GPIO/reset的原A4标准IP参数核对一致。RQ51使用新增bit4选择C5，要求bit3=1；阈值、尺寸、阶段、帧标记均锁存并回读。

C5只改最终阶段3的掩膜。阶段1/2明确仍为C2中间阶段；输出的原绿色、增强灰度和C2响应字段保持对应语义。它使用5/9两尺度双侧筛选和只运行一次的1—3像素有支持连接，新增像素不作为新种子继续生长。CPU不生成生产掩膜，PS只做输入/配置/DMA/只读快照、评价、编码与网络；GT仅评价，板包不含CPU医学参考或黄金输出数组。固定SHA只用于检查实际DMA。

所有A/C2/C5共享新增流式通路，因此原结果字节相同不意味着时延相同，不能照搬旧C2约3.023ms。本轮记录硬件周期窗口、含PL计算的DMA事务、完整推理、客户端请求到绘制；周期含流式等待，不把差值当纯DMA搬运。

## 未掩盖的失败与修正

- `q4_refined_hls_01` Csim通过，但嵌套旧顶层`control.V`接口导致综合失败。仅在派生base移除顶层接口pragma，正确构建为`q4_refined_hls_02`。
- 旧2017.4导出工具把2026年月日时间编码为超范围整数Revision。原失败日志和原`run_ippack.tcl`保留；只在生成工作副本把Revision改为1，未修改RTL/ROM、厂商安装或原库。首个repack调用工作目录错误也保留，正确封装日志为`hls/repack_success.log`。
- 首个RTL仿真调用因98文件拼接超Windows命令长度而未开始，改用xvlog工程文件。正确实际RTL证据为`q4_refined_axis_sim_02`，不将第一次当通过。
- 初版软件草稿含辅助函数旧端口默认值/旧标签，已保存在`build/q4_software_draft_01`；最终包使用8090，Notebook提取已执行核验。
- 构建脚本末尾发布审查只修正顶部来源注释，最终脚本与`implementation/build_script_used.tcl`的非注释语句完全一致。
- 复位aux_reset_in的只读POLARITY警告、原板DDR负DQS约束、已识别DSP流水线/未用FIFO提示均在实际结构/时序审查中记录；没有以屏蔽错误获取通过。

## 质量取舍与下一步

既有512训练AH：C2→C5 Dice .624639→.684965、clDice .679881→.724486、细代理Recall .516636→.527297；亮带FP4476→3129，亮带Recall .692175→.628809，新增像素Precision42.31%。256新增Precision仅20.26%。整体改善不能掩盖亮带真血管损失与误连风险；六项原严格门槛仍FAIL。此为CPU训练结果，非新板测结果。中央亮区仍有残余误检，长段细血管缺失未解决。保留原A/C2，最终采用须查看真实板输出、逐图误差和视觉对比。

仅上传`build/deploy/q4_c5_upload_r1`的两个文件：ZIP14,416,177字节、138成员，以及7,671字节Notebook。哈希在[package.json](package.json)。完整Vivado工程、生成RTL与bit/HWH保留在`build/q4_refined_full_01`和`build/q4_refined_hls_02`，未以空工程或仿真代替。

[用户操作步骤](../../docs/q4_c5_board_steps.md)：新目录retina_q4_c5_r1，120自动帧＋三图C2/C5对比＋两阈值＋3预热20计时，预计151任务一次加载。下载后`verify_q4_archive.py`逐字/PNG/Notebook/参数/计时/CSV/浏览器可见覆盖复核，训练/复用留出×AH/VK分开，不宣称新的盲测。后续W4正式性能/纯DMA/同PS CPU/功耗与W5≥30分钟且≥1000帧均保持，最终工程、RTL、驱动、页面、报告与视频尚待交付。实体板/最终质量/最终视觉/正式性能均未验收。
