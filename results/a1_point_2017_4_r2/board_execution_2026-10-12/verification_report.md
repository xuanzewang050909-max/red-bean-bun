# A1 r2 实体板执行记录复核与归档

日期：2026-10-12（Asia/Shanghai）。**结论：PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED。** 用户在 PYNQ-Z2 上运行修正后的 A1 Notebook，完成首帧与连续验证共17个完整帧。下载的 Notebook 与 JSON 已逐字节归档，SHA256 见[归档清单](archive_manifest.json)。

|核查项|结果|
|---|---|
|真实执行记录|五个代码单元按1–5完成，无异常输出，准备/加载/首帧/最终 PASS 均存在|
|交付配对|板端 manifest 与 r2 发布清单完全一致，原 r1 bit/HWH 保持原哈希；软件修正源码 Commit `2c845bfe16096ee346dd7555cdf1c70cabf3bd2e`|
|Notebook 校验|运行后的代码单元规范化哈希匹配，允许执行输出与元数据变化；板端固定文件校验 PASS|
|运行环境|PYNQ3.0.1、Python3.10.4、内核5.15.19-xilinx-v2022.1，与板端基线一致|
|测试覆盖|256/512，两尺寸各含旁路/绿色/LUT、递增和随机；另含两尺寸LUT全黑/全白；首帧256绿色递增|
|逐帧收发|17帧，256帧每次262144字节，512帧每次1048576字节；请求字数与收发字节数一致|
|DMA状态|每帧两个通道均空闲、非停止、无DMA错误；板端通过标准驱动完成传输|
|FPGA状态|每帧输入/输出计数同步增加，最终均为17，错误位全0|
|DDR缓冲|TX/RX地址8字节对齐，位于合法窗口，传输范围不重叠|
|独立复算|主机重新生成17帧输入、独立LUT期望，输入/期望/实际输出记录哈希逐帧匹配；Notebook的17条完成行顺序也匹配|
|板端时间|原样保留未校准时间 `2022-10-22T03:12:35.461607+00:00`，不作为本次日历时间|

原始记录：[执行 Notebook](a1_point_check_executed.ipynb)、[板端 JSON](a1_point_result.json)。复核结果：[逐帧独立核对](independent_frame_verification.json)，复现入口为 `scripts/archive_a1_board_results.py`。归档脚本拒绝覆盖既有归档，校验完整发布包后才复制真实记录。

修复前 Notebook 完整文件哈希导致的预检查失败及用户截图，保留在上级目录 `failure_record.json` 与 `r1_precheck_failure_user_screenshot.png`。原 r1 发布清单、主机构建与 Git 配对记录维持原始内容；其中 `board_status=NOT_RUN` 是发布时状态，本次板测状态由本归档单独记录。

## 通过范围与下一阶段

确认现有 Vivado2017.4 A1 点运算硬件在 PYNQ3.0.1 实体板上完成旁路、绿色通道及直接 LUT(G)，并验证标准DMA/GPIO/DDR与帧控制。板端进行了逐字比较；主机独立核对确定性图案哈希和状态，未下载原始DMA输出缓冲，也未重新操作板卡。

该版没有3×3高斯、局部背景、血管分割或HDMI。下一阶段先审查并比对厂商Gaussian/Filter2D候选的固定核、舍入及replicate边界，再接入A通路并逐像素验证。最终B仍需同时包含完整医学分析和官方HDMI。当前结果不证明算法FPS或临床性能。
