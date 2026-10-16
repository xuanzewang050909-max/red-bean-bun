# B 分段诊断：第2框 Notebook 哈希报错恢复

适用错误：`RuntimeError: Profiling package mismatch: b_integration_check.ipynb`，出现在第2框 `prepare_profile` 的文件校验阶段。

这是分段诊断r1的新校验缺陷：旧B Notebook也被列入了完整JSON字节哈希，输出、执行次数或元数据保存变化就会阻断后面的正确代码哈希校验。截图只证明完整文件发生变化，无法从中确定改动字段；修正后仍要求旧B和新诊断Notebook的执行代码分别匹配固定发布，若代码也改变会继续报错。此处尚未创建Overlay、加载FPGA或分配DMA缓冲。

1. 在网页按 **Ctrl+S** 保存这次错误记录。保持当前 **retina_b_profile_r1** 文件夹，不新建、不删除已有文件。
2. 回到这个文件夹的文件列表，点击 **Upload**，选择电脑目录 `D:\PLD\retina_fpga\build\deploy\b_profile_notebook_fix_r2` 的全部 **3 个文件**：`b_profile_board_test.py`、`b_profile_manifest.json`、`分段计时说明.txt`。逐个完成上传，遇到同名文件选 **Overwrite（覆盖）**。配对bit/HWH及其他文件不需要重新上传。
3. 返回原 **b_performance_profile.ipynb** 页面，点 **Kernel → Restart** 并确认重启。此步骤只适用于上面的加载前文件校验错误；不要选择 Restart & Run All。
4. 重新运行第 **1** 框，再运行第 **2** 框，等待 **B_PROFILE_PRECHECK_PASS**。若仍有红色错误，保存输出并反馈，不进入第3框。
5. 第2框通过后，按原顺序继续：第 **3** 框 `B_PROFILE_LOAD_PASS`；第 **4** 框 `B_PROFILE_HDMI_READY`；第 **5** 框 `B_PROFILE_COMPLETE`；第 **6** 框 `B_PROFILE_RESULTS_READY`。每次只运行一框，等 `In [数字]` 且无报错再继续。
6. Ctrl+S，下载运行后的 **b_performance_profile.ipynb** 和同目录 **b_profile_bundle.zip**，完成后反馈“已下载”。

修正包只修改Notebook校验及软件revision/manifest/说明；计时流程、30帧负载、驱动、算法和硬件不变。完整修正版17文件在 `D:\PLD\retina_fpga\build\deploy\b_profile_2017_4_r2`，用于尚未上传的情况。原r1包和失败截图保留。

如果第3框以后出现DMA/显示传输错误或一分钟无进展，停止并保留输出和缓冲，不套用本页的重启方法。
