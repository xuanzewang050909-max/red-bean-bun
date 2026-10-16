# PYNQ-Z2 板级前置验证汇总

**最新板测进展（2026-10-11）：A0 r2完成17字短包及70次完整DMA回环；执行Notebook与原始JSON已逐字节归档，源码/交付配对、收发字节数及71次图案哈希复核通过。** [板测归档报告](../../a0_dma_2017_4_r2/board_execution_2026-10-11/verification_report.md)。首次失败证据另行保留；医学算法、最终HDMI整合及实时性能尚未验证。

日期：2026-10-11，Asia/Shanghai。记录基于用户现场执行、截图与观察反馈；没有远程代替用户执行。

|检查项目|当前结果|证据范围|
|---|---|---|
|PYNQ-Z2启动|通过|COM9 Linux shell 截图|
|Jupyter/Python访问官方Base|通过|网页登录截图；用户确认 Base GPIO 实际响应|
|官方HDMI输出|通过|720p60 BGR24 软件配置，正确色条/白框/十字照片及 30 秒稳定反馈|
|官方LED/GPIO|通过|官方 Notebook 副本，用户确认按钮/LED 行为|
|官方视频帧缓存|通过（输出侧）|100 帧完成输出截图及白条移动正常反馈；不是逐帧完整性回读|
|独立双向AXI DMA|通过（r2）|17字短包与完整70次回环通过；源码/manifest/字节数/71次哈希复核及原始文件归档|

运行 PYNQ 包版本 3.0.1；Jupyter 实际 URL 为 http://192.168.2.99:9090/tree，UART COM9。PCB修订未知；本机只有2017.4，官方v3.0.1 Base源码基线为2022.1。用户同意优先现有2017.4：A0复用本机标准IP，B候选从官方v2.2.1 Base派生，并独立验证与3.0.1驱动适配。预构建Base的板级PASS不等于派生工程PASS。

历史首轮色条异常已保留，后续空间标记和运动测试未复现；未确定根因，不声称代码修复。HDMI 执行 Notebook 已保存并归档，含 close 完成输出；板端原始 JSON 与完整环境采集报告已逐字节归档，四份 Tcl 与官方 v3.0.1 哈希匹配。独立DMA A0 r2已通过；Retina算法及最终整合Overlay尚未完成。

证据见 first_boot_check.md、official_image_first_boot.md、jupyter_access_check.md、gpio_base_check.md 和 hdmi_output_check.md；机器可读状态见 ../../audit/demo_status.json。

A0详情：[r2报告](../../a0_dma_2017_4_r2/build_report.md)。
