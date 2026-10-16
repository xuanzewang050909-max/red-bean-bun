# C7实现记录（主机发布检查完成，板测NOT_RUN）

模型、36项特征、整数边界及训练协议见 `q4d_c7_experiment_decision.md`。最终模型SHA256为6f3d83ac760c91988f5edd27f45b6f69cc7c610ff13500d77161cfcc525f44a6，8棵深度6，原绿色17×17复制边界，推荐分数阈值112。人工标注只用于离线拟合/评分，不参与PL或PS推理；发布包不含CPU模型/特征计算。原A/C2/C5字节与输入几何保留。

## 已实际执行

- HLS01：18帧2,555,904输出字及9,720个独立标量特征值匹配；综合因嵌套原C5顶层的外部接口声明冲突失败，日志 `build/q4d_detector_hls_01.log` 保留。
- 派生 `retina_detector_c5.cpp` 仅去掉外部顶层4项INTERFACE声明并改函数/包含名，原C5计算原样；原源文件不改，主机检查验证精确差分。
- HLS02：同18帧/全部字和特征值再次通过，综合完成。估计139,789 LUT不可当成实际资源，更不能假设能装入Z2；必须等实际Vivado综合和布局布线。
- 导出01：2017.4日期core_revision溢出导致导出失败。复用已审查的 `scripts/repack_a4_ip.py`，仅在生成包装Tcl副本把Revision设为1，原脚本、diff及日志均保留；安装库、模型和RTL不改。实际重新包装日志 `build/q4d_ip_repack_02.log`，文件 `build/q4d_ip_export_metadata_01`。
- 实际RTL仿真01在时间0达到默认10000 delta限制。实际过程跟踪及源统计定位到c7_filter.v有22,648条逐条`#0`初始化；原默认限制小于初始化所需delta。50000限制启动探针已实际推进到1ns及201ns并释放reset，原失败保留；这不等于完整帧验证通过。调高限制的含义见[AMD UG900](https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/xsim-Executable-Options)，使用2017.4实际支持的参数，不修改生成RTL。
- 全工程 `build/q4d_detector_full_01` 使用HLS02实际生成RTL，PS/DDR/AXI DMA/GPIO/reset沿用旧A4结构；最终布线WNS=-2.047ns，拒绝发布，原日志保留。
- HLS03已检验等价树形归约：225像素区域的均值/最大/最小值改为平衡树，替代线性比较链，模型和特征定义不变，16位和始终不超过57375。02的95级窗口流水线及其文件保留，不覆盖；再次独立逐字和特征值验证通过后推进full_02。

## 发布前所需检查（现均已完成，汇总见文末）

真实生成RTL的多帧、背压、帧内改参、坏TLAST/TKEEP及在途复位；Z2实际资源、100MHz布线时序、DRC及厂商reset仿真；标准IP/HWH映射与生成/打包/实现RTL ROM逐字配对；浏览器/主机替身采集和归档检测；旧发布保护；最后才生成可供用户上传的包。主机替身或CPU参考均不能计为真实板测。

冻结CPU全组结果 `build/q4d_board_references_01/frozen_evaluation.json`，固定三图科学对照及逐图Dice下降名单 `build/q4d_frozen_visual_02`。可见部分粗亮边误检减少、部分分支恢复，但有残余亮边碎点和细线漏检；不称彻底修复。训练重代入、复用留出、AH/VK分开报告，原OOF失败不因最终模型分数提高而消失。

## HLS03 与控制接口增量（2026-10-15）

HLS03 已完成18帧2,555,904字与9,720特征值比较；精确平衡归约没有改变冻结模型或输出。C7 HLS估计从66,701 LUT/44,706 FF/95级降为38,182 LUT/11,666 FF/11级；整核估计111,270 LUT仍不可当实际器件资源。HLS02实际OOC综合41,695 LUT/28,771 FF/93.5 BRAM Tile/30 DSP，说明不能把HLS估计当放置结果；full_01仍留作历史。当前发布候选为HLS03→export_02→full_02，所有候选须布线检查通过。

export_02同样触发2017.4日期整数溢出，生成元数据修正在build/q4d_ip_export_metadata_02；实际重新包装日志q4d_ip_repack_03.log。没有修改算法RTL/ROM或安装库。

旧HLS02实际RTL诊断在首个65,536字整帧与观察器边界通过后，为等价优化版腾出资源而停止，retirement_note.txt明确不是全测试PASS。HLS03实际RTL默认编译在axis_sim_02通过首个整帧；axis_sim_03仅启用2017.4自身-O3/-Oenable_always_combine以减少仿真事件，生成HDL与测试输入/期望/检查均不改变。两者仍须比较，发布要求全部17完整帧与中途复位完成，不能因首帧匹配而跳过剩余验证。

C7 guard单元测试build/q4d_guard_sim_01已通过6帧589,824字，包含T=0/保留位/C5和C7依赖拒绝、帧中改配置、精确周期/背压/饱和、坏TLAST/TKEEP与中途复位。该测试核是明确标识的FIFO替身，只证明控制与观察器，不是算法或板测。full_02实际厂商reset IP仿真已通过（q4d_detector_reset_session_01.log）。

## full_02实际实现与并行RTL检查

full_02已实际生成配对bit/HWH并通过100MHz布线：38,373 LUT、24,833 FF、97.5 BRAM Tile、30 DSP；WNS=0.107ns、WHS=0.026ns、WPWS=3.750ns。`build/q4d_detector_hardware_check_01.json`逐一核对旧A4标准IP参数、PS/DDR/DMA/reset连线、地址、时钟、生成/打包/实现RTL及ROM字节。DRC无Error或Critical Warning；DPIP-1=22、DPOP-1=23、DPOP-2=29、RTSTAT-10=1为已逐项审查的DSP流水/功耗建议，不是豁免时序或实测功耗。旧复位参数只读警告保留。

原单进程axis_sim_02/03的已完成整帧均一致，为缩短总验证时间停下部分诊断后，使用同一2017.4实际生成RTL、同一完整scoreboard和输入/期望向量分成8组。范围1–3、3–5、5–7、7–9、9–11、11–13、13–15、15–18，每个相邻向量切换仍有覆盖；7个首帧有意重复，不能计为24个独立测试向量。最后一组保持坏帧→中途复位→512黑帧恢复的顺序。各组开始独立复位，不宣称一次连续18用例进程通过。

`q4d_sharded_rtl_01`首次启动因厂商Windows批处理拆开未加引号的`RANGE_FIRST=N`而失败，日志保留。`q4d_sharded_rtl_02`使用加引号的运行参数，actual RTL、ROM、时序和检查不变。`scripts/check_q4d_sharded_rtl.py`要求全部组完成并核对源码、可执行快照、向量、帧配置、完整输出字数和复位；未完成时禁止生成正式板包。

独立快照审查最初错误地把`webtalk`使用统计也当成编译产物，结束后的组因此报快照不一致（`q4d_rtl_gate_pending_02.log`）。实际比对证实9个静态组件——编译选项、exe、初始内存、重定位和类型/调试表——字节全部一致，差异仅3个厂商运行使用统计文件。审查改为明确检查这9项及全部RTL/ROM/向量；只排除日志、波形和`webtalk`。修正后仍在未完成的第3组拒绝发布（`q4d_rtl_gate_pending_03.log`），没有跳过任何完整帧。

主机软件检查使用`build/q4d_host_candidate_01`中的实际full_02硬件配对和最终应用候选，目录在deploy之外，明确HOST_TEST_DOUBLE。第一次49项中3项因测试仍引用尚未发布的Notebook路径而报错；修正测试路径，并让归档器在读取Notebook前就拒绝HOST_TEST证据。错误日志保留，只有对应复核通过后才计为通过；复核不重复计数。网页本地预览在127.0.0.1:8098，已验证C7→C5→C7、阈值112/28自动切换、历史结果标记与当前指标清空、禁用C7未实现的中间模式；不计板测或性能。

## 最终发布检查完成

8组实际RTL全部完成：17个独立完整帧共2,490,368字，加7个有意重复的切换种子帧，总计24帧3,145,728字。所有原相邻切换均保留；坏TLAST/TKEEP、帧内配置、背压和在途复位后的512恢复通过。各组独立复位的范围已明确，不将其描述为一次连续18用例。最终审查`build/q4d_sharded_rtl_verified_01.json`状态为PASS_ACTUAL_C7_RTL_SHARDED_NOT_BOARD。

49项不同主机检查最终全部通过，初次46成功/3错误以及对应3项复核日志一起保留；重复检查不新增计数。HOST替身160帧26,214,400字、800PNG/235,929,600通道值仅为应用和归档验证。正式发布后又实际执行3项配对和Notebook校验解压检查，均通过；正式包内应用、硬件、数据字节与上述主机检查候选一致。179份受保护旧文件和旧C5发布校验均未改变。

实际full_02资源为38,373 LUT、24,833 FF、97.5 BRAM Tile、30 DSP，100MHz WNS0.107ns、WHS0.026ns。新核心周期、DMA、完整推理、浏览器延迟、FPS与真实输出质量仍需本轮实体板测，不能使用旧C5时延或HOST替身计时。

最终上传目录`build/deploy/q4d_c7_upload_r1`只有两文件；ZIP含138成员，必须成对上传：

|文件|字节数|SHA256|
|---|---:|---|
|q4d_c7_experimental_r1.zip|14771015|9b0817670b34f1f0038ba545b56b318fff1ca74dae6c4cb6af026d50b14f5129|
|q4d_quality_start.ipynb|8200|ecc677a036b1490fa6182ba6fc911aef4230b28804cc2ffa9780953e5827200e|

归档证据见`results/q4d_detector_2017_4_r1`，完整人工操作见[q4d_c7_board_steps.md](q4d_c7_board_steps.md)。C7状态HOST_RELEASE_VERIFIED_BOARD_NOT_RUN，quality_accepted=false，保留C5对照及[全部质量取舍](q4d_c7_frozen_review.md)。
