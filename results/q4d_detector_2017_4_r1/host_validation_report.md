# C7主机实现与发布核验

状态：**HOST_RELEASE_VERIFIED_BOARD_NOT_RUN**。2026-10-15归档；质量验收为false，下一项是用户在真实PYNQ-Z2运行新包。独立复核脚本为`scripts/archive_q4d_host.py`，完整来源、字节数和SHA在[verification.json](verification.json)。旧C5结果、失败日志、179个受保护文件和旧发布包保持原字节。

## 已完成的验证

|范围|实际结果|证据|
|---|---|---|
|C仿真|18帧、2,555,904输出字、9,720独立标量特征值一致|build/q4d_detector_hls_03/solution1/csim/report/retina_detector_hls_csim.log|
|实际生成RTL|17个独立完整帧、2,490,368字；含重复种子共24帧3,145,728字；8组全通过|build/q4d_sharded_rtl_verified_01.json及group_01至group_08/xsim.log|
|切换与异常|原相邻向量切换、背压、帧内配置、坏TLAST/TKEEP及在途复位恢复均覆盖；各组单独复位|同上，不能描述成一次连续18用例进程|
|控制与厂商复位|guard FIFO替身6帧589,824字通过；实际厂商reset IP仿真通过|build/q4d_guard_sim_01/session.log、build/q4d_detector_reset_session_01.log|
|完整100MHz实现|38,373 LUT、24,833 FF、97.5 BRAM Tile、30 DSP；WNS0.107ns、WHS0.026ns、WPWS3.750ns|build/q4d_detector_full_02的timing_summary/utilization/drc报告|
|硬件来源|原A4标准IP、连线、映射与实际生成/打包/实现RTL和ROM字节配对通过|build/q4d_detector_hardware_check_01.json、verification.json|
|主机应用|49项不同检查通过；首次46成功3错误、对应3项纠正复核均保留|build/q4d_host_suite_01.log、build/q4d_host_recheck_02.log|
|HOST替身归档|160帧、26,214,400字、800PNG/235,929,600通道值核对|上述主机检查；不能计为板测|
|浏览器本地预览|C7/C5选择与阈值切换、历史结果提示、未实现模式禁用、无JS告警/错误|build/q4d_host_ui_state_01.json及q4d_host_ui_preview_01.jpg|
|最终发布|实际执行ZIP/Notebook清单配对及校验解压3项，均通过；属于49项内的重复复核|build/q4d_final_package_recheck_01.log|

DRC无Error/Critical Warning，DSP流水和功耗建议保留并审查；资源不是HLS估计，功耗没有实测。正式包所有硬件/应用/数据字节与通过主机检查的候选一致。Python运行源通过3.10语法检查。主机替身证据由正式归档器明确拒绝，不允许混作真实PL输出。

## 输出包与下一步

`D:\PLD\retina_fpga\build\deploy\q4d_c7_upload_r1`仅两文件：

|文件|字节数|SHA256|
|---|---:|---|
|q4d_c7_experimental_r1.zip|14771015|9b0817670b34f1f0038ba545b56b318fff1ca74dae6c4cb6af026d50b14f5129|
|q4d_quality_start.ipynb|8200|ecc677a036b1490fa6182ba6fc911aef4230b28804cc2ffa9780953e5827200e|

ZIP含138成员。按[板测步骤](../../docs/q4d_c7_board_steps.md)上传新目录，从第1框顺序运行；固定160帧加浏览器对照/阈值/3预热20计时预计193任务。下载真实`q4d_results_bundle.zip`和执行Notebook后，才能独立核验新板输出、延迟与前台FPS。后续原W4完整性能、纯DMA及同PS CPU对照、W5长时稳定实验继续保留。

## 质量收益与限制

冻结选择、最终模型及协议先于全20图/AH/VK评价，之后没有反向调参。C7是可选实验，保留A/C2/C5。512训练OOF亮带真血管召回保护未通过；复用留出im0324及im0004存在退化，不用整体均值掩盖。详见[冻结审查](../../docs/q4d_c7_frozen_review.md)。

原im0001中央同一亮带：真实C5与冻结C7的CPU参考比较，双标注均否认的误检1933→1007，同时AH真血管TP88→70、FN14→32。这是训练图的冻结后诊断，不是C7实板结果，也不是独立新验证。整图AH骨架覆盖65.48%→70.41%、细标注代理召回42.94%→50.21%，仍有暗线漏检、亮边碎点和断裂。原区域审查JSON、对照PNG与全FOV骨架PNG一并归档，不能称彻底修复。

实现完成不等于视觉验收。C7的实际延迟/FPS不得借用C5的3.039ms或HOST计时；DMA事务包含流式PL运算，不等于独立纯搬运时间。不得在PS/浏览器补线掩饰检测不足。
