# A2 实体板执行记录与原始输出核验

日期：2026-10-12（Asia/Shanghai）。**结论：PASS_BOARD_RECORDS_AND_RAW_ARRAYS_VERIFIED_AND_ARCHIVED。** 用户在PYNQ-Z2执行A2的六个代码单元，下载执行Notebook和结果ZIP。本机已检查完整发布配对、37帧记录、4份实际DMA输出数组及预览图，全部通过。

## 通过的内容

|核查项|真实结果|
|---|---|
|执行记录|代码单元按1–6完成，无异常；预检查、加载、首帧、完整验证和打包标志均唯一且位置正确|
|版本配对|板端记录的manifest与固定发布清单完全一致；本机重新校验十文件包的固定文件SHA256及Notebook代码契约|
|运行环境|PYNQ3.0.1、Python3.10.4、内核5.15.19-xilinx-v2022.1，与已测基线相同|
|成熟IP/驱动|Vivado/HLS2017.4构建，PYNQ官方DMA和AxiGPIO驱动绑定；PS/DDR、DMA、GPIO和100MHz基础结构沿用A1|
|测试覆盖|首帧256高斯渐变，加36帧：256/512、模式0–3、渐变/固定种子随机，以及高斯和高斯+LUT的棋盘/九点边角脉冲/全黑/全白/真实STARE|
|帧数|256尺寸19帧，512尺寸18帧；旁路4、绿色4、高斯15、高斯+LUT14，共37帧|
|数据长度|共5,963,776个32位输入字；发送与接收各23,855,104字节；每帧记录的字数与收发字节数一致|
|DMA/DDR|每帧两个DMA通道空闲、非停止、无错误；TX/RX地址8字节对齐、位于合法DDR窗口且互不重叠|
|帧计数|输入和输出完成计数逐帧同步，从1到37；最终状态606245（0x00094025），错误位为0|
|独立数值参考|主机使用M0九点int32累加、复制边界及一次取整，区别于板测脚本的可分离uint16参考；重新生成37帧输入与期望，逐帧匹配输入/期望/实际输出SHA256|
|实际输出数组|256/512各有高斯及高斯+LUT两份uint32数组；共655,360个字逐个匹配，0个不一致；原G、中心FOV与诊断字节布局均包含在比较中|
|预览来源|ZIP预览的三幅图分别匹配原G、实际FPGA高斯和实际FPGA高斯+LUT数组的缩小图；Notebook嵌入PNG与ZIP预览全部像素相同|
|归档工具检查|19项主机检查通过，其中17项验证错误证据会被拒绝；这些检查没有再次操作板卡|

板端报告状态原样保留为`A2_PASS_37_GAUSSIAN_FRAMES_NOT_FULL_SEGMENTATION`。输入为已发布的RGB/FOV和确定性图案，没有向FPGA发送人工血管标注。

## 原始文件与可追溯记录

用户下载源文件为`C:/Users/Gabriel/Downloads/a2_gaussian_check.ipynb`与`a2_results_bundle.zip`。原始字节及用户截图保存在本地`D:/PLD/retina_fpga/build/board_results/a2_gaussian_2026-10-12/`，包含执行Notebook、原ZIP、原JSON、4个原NPY、原PNG和截图。每个文件的大小、绝对路径和SHA256见[归档清单](archive_manifest.json)。原始JSON另外逐字节保存在本目录。

含眼底图像的Notebook、PNG、NPY和ZIP留在已忽略的本地build目录；原始JSON、哈希清单、复核结果和报告加入Git。遵循已有STARE本地研究数据管理方式，不将派生图像混入可分发的源码。

|原文件|字节数|SHA256|
|---|---:|---|
|执行Notebook|165775|`60a72f5930241f204ba8289c58a0c2bde9fdba5409603e575aeb9a254fc82088`|
|结果ZIP|806837|`20aee252f3222d66bfa41c9f480f2076e52e41973785fa680ef4fe44c23bff14`|
|原板端JSON|38567|`dae049402356aa2007e92303396ff59b0e7711fda786b70f0eff0a8108557826`|
|预览PNG|117862|`e438c1900b890215a922a8171531daa1d17bccdf5452f4c29bb75a656092c098`|

硬件与发布源码Commit为`f96e3498cfe59628ee6b987a40f2d98d29f05850`，发布目录为`build/deploy/a2_gaussian_2017_4_r1`，只包含修正版`build/a2_gaussian_02`。完整发布清单SHA256为`d05d69d3b4735604aa8fdb97822f775352ba4357683ada778305d5bf2658e60e`。发布时的`board_status=NOT_RUN`保留原值，本次板测状态由本归档单独记录，避免改写发布历史。

运行后Notebook的完整文件哈希变化是正常的；本次代码单元SHA256仍匹配发布契约`543414cd161c165085348b435b3cb5aa29d9ef88950630ca32a6f3909cd4f737`。预检查时保存的完整Notebook哈希只代表当时文件，不能与添加后续输出的下载文件作等值要求。

板卡时间没有校准，原时间`2022-10-22T04:20:33.014819+00:00`未更改。主机核验时间另存为`2026-10-11T17:48:41.845787+00:00`（北京时间2026-10-12 01:48:41），不以板端旧日历时间推断测试日期或性能。

数值证据：[原始JSON](a2_gaussian_result.json)、[37帧独立复算](independent_frame_verification.json)、[4份原数组逐字核对](raw_array_verification.json)、[预览核对](preview_verification.json)、[归档工具检查及源码哈希](host_archive_checks.json)。归档入口为`scripts/archive_a2_board_results.py`，读取固定平面ZIP文件名并检查CRC、大小、重复/未知路径及链接；不执行Notebook，也不解压任意归档路径。完成所有数值校验后才创建归档，拒绝覆盖已有记录。

本地可用以下命令检查归档工具，原图仅从上述本地归档读取：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_a2_archive.py' -v
```

## 结果含义与下一阶段

左图是原始绿色通道，中图是FPGA完成的3×3高斯，右图是FPGA高斯之后的固定LUT。3×3高斯只对小范围像素平滑，缩小预览时可能与原图很接近；LUT提高亮度，右图变亮符合预期。三幅图当前都不是血管二值分割结果。

37帧在板端均进行逐字比较，主机对37帧的确定性输入/期望/输出哈希进行独立复算。主机还直接逐字检查了下载的4份真实STARE缓冲；其余33帧没有保存原缓冲，不能称为37份原数组均已下载。

本阶段证明2017.4构建的高斯/G/FOV/LUT与标准DMA通路可在PYNQ3.0.1实体板工作。尚未验证15×15局部背景、血管响应/阈值/形态学及完整分割。最终B还必须把完整算法与官方VDMA/HDMI放在同一bitstream，A2没有HDMI；此前Base显示通过不能代替最终B整合。当前记录不提供算法FPS、端到端延迟或临床质量结论。

下一阶段依照已有算法A，先审查厂商box/Filter2D的15×15定点、复制边界和资源成本，复用兼容模块生成局部背景，再接入医疗特有的血管响应。仍使用Windows和现有Vivado/HLS2017.4。
