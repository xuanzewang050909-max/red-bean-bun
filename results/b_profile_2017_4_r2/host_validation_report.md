# B 分段诊断 r2：继承 Notebook 保存校验修正

状态：**主机修正验证通过，修正版分段诊断实体板 NOT_RUN。** 原B同工程370帧功能/显示/速度基线继续有效。此次没有新的分段数字或优化结论。

真实截图显示第2框 `prepare_profile` 在 `validate_profile_package` 抛出 `Profiling package mismatch: b_integration_check.ipynb`。当次调用尚未进入 `b.prepare_b`，没有创建Overlay、下载FPGA或分配DMA。旧规则把继承的Notebook也纳入完整JSON SHA256，导致后面的原B代码哈希检查被遮挡。截图无法确定实际文件改动字段；r2仍要求两份Notebook的执行代码与固定发布一致，不会放行不同程序。

## 修正范围

- 只改诊断revision和校验：两份Notebook均使用原规范化代码单元SHA256，排除输出/执行次数/元数据/Markdown；bit/HWH、Python辅助脚本、输入、说明及原B manifest仍逐字校验。
- 实际测量函数、时间边界、原排版、官方驱动、缓存/所有权、帧数和负载均与r1相同。组装器按预定替换文本复现整个脚本，拒绝任何额外变更，计时契约亦须相等。
- 完整r2仍17文件，原B r2十三文件发布字节全部相同。最小修正包只有 `b_profile_board_test.py`、`b_profile_manifest.json`、`分段计时说明.txt`，其余14个发布文件相同。
- 当前加载前错误可替换3文件后重启当前Notebook内核、重跑1/2；不将此恢复方法用于DMA/VDMA在途失败。

## 主机验证

23项检查通过，见`host_tests.log`和`host_test_sources.json`。在原19项计时/所有权/故障/代码/源配对检查上，新增：旧Notebook非代码保存变化通过、旧Notebook执行代码修改拒绝、执行原r1源码复现截图错误且不进入Overlay预检查、实际三文件覆盖旧目录并保留变化的Notebook可恢复。预检查正例执行固定官方video初始化器，使用明确硬件facade；验证仅Overlay(download=False)，所有分配调用会被facade拒绝。新旧两份Notebook同步保存的组装探针通过，两份原文件最后恢复原发布字节。

第一次主机运行的2项错误来自测试临时复制误把Python生成的__pycache__目录当作文件，未涉及板卡；原失败日志和当时来源哈希保留为`host_tests_initial_failed.log`与`host_test_sources_initial_failed.json`。修正测试只复制发布清单文件，并避免在固定包内生成字节码，随后23项全部通过。

原r1发布清单、源Git历史和新收到的原截图均保留。完整r2在`build/deploy/b_profile_2017_4_r2`；三文件恢复包在`build/deploy/b_profile_notebook_fix_r2`。真正板端预检查和后续分段测量仍待用户执行，收到Notebook/ZIP后再独立复核。
