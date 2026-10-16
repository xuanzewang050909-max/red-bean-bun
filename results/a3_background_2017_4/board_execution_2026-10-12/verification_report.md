# A3 实体板背景与响应：执行记录及原始输出核验

日期：2026-10-12（Asia/Shanghai）。**结论：PASS_BOARD_RECORDS_AND_RAW_ARRAYS_VERIFIED_AND_ARCHIVED。** 用户已在PYNQ-Z2完成六个代码单元并下载Notebook与结果ZIP。本机独立复算45帧记录，直接逐字检查四份实际DMA输出，核对四幅预览与Notebook，全部通过。

## 为什么第三幅图模糊

第三幅是局部背景估计：FPGA对第二幅增强图执行15×15均值滤波，保留缓慢变化的亮度，平滑细血管等细节。因此模糊符合本阶段的数值规格。它是计算中间结果，没有以清晰度作为验收目标。

|图像|实际来源与用途|
|---|---|
|第一幅 Raw green|输入原始绿色通道，提供对照|
|第二幅 FPGA enhanced|3×3高斯后固定LUT，作为后续分析输入|
|第三幅 FPGA background|15×15复制边界均值，估计局部背景亮度|
|第四幅 FPGA response|`clip(4×(背景−增强值),0,255)`，突出相对背景较暗的结构|

四幅图均来自下载的512×512模式3实际输出的四个字节。页面将每幅缩小为256×256；数值验收使用完整原数组。第三幅逐像素等于独立参考背景；第四幅目前是灰度响应，尚未完成阈值、形态学及最终FOV过滤，不能视为最终血管二值分割。

## 真实检查结果

|核查项|结果|
|---|---|
|执行记录|六代码单元按1–6完成，无异常；预检查、加载、首帧、完整验证及打包标志唯一且位置正确|
|发布配对|记录manifest与固定发布清单完全一致；本机重新核验11文件包的固定SHA256与Notebook代码契约|
|环境与驱动|PYNQ3.0.1、Python3.10.4、内核5.15.19-xilinx-v2022.1；官方DMA与AxiGPIO驱动绑定|
|复用通路|Windows/Vivado/HLS2017.4构建；PS/DDR/HP0、DMA/FIFO/GPIO/reset、帧适配器及100MHz沿用已测A2|
|覆盖|256/512、模式0–3、渐变/固定种子随机；背景与响应模式另含棋盘、九点边角脉冲、全黑/白、STARE、暗条纹与取整图案|
|帧数|256尺寸23帧、512尺寸22帧；模式0/1/2/3分别4/4/18/19帧，共45帧|
|长度|7,274,496个32位输入字；发送和接收各29,097,984字节，每帧字数与字节数匹配|
|DMA/DDR|每帧两个DMA通道空闲、非停止、无错误；TX/RX地址8字节对齐，处于合法DDR窗口且不重叠|
|FPGA计数|输入/输出完成计数从1同步增长至45，最终737325（0x000b402d），错误位为0|
|独立数值核验|使用M0九点int32高斯、int64积分均值、复制边界、一次取整与有符号饱和响应；45帧输入/期望/实际输出记录哈希全部匹配|
|直接检查原数组|256/512各有背景模式2与响应模式3；四份uint32输出共655,360字逐字匹配，0个不一致|
|字节对齐|原G、增强值、背景和模式2中心FOV均包含在整字比较中；模式3最高字节为响应，未按FOV屏蔽|
|真实预览|四个缩小图分别匹配实际模式3输出的四个字节；Notebook嵌入PNG与ZIP预览所有像素相同|
|归档工具|20项离线检查通过，含18项错误证据拒绝检查；原数组损坏检查覆盖6个模式/字节组合，第三幅预览即使重新签名也被拒绝|

板端原状态为`A3_PASS_45_BACKGROUND_FRAMES_NOT_FULL_SEGMENTATION`。45帧均在板端逐字比较，主机对45帧的记录哈希独立复算；其中四份STARE输出有下载的原缓冲，可在主机直接逐字检查。其余41帧没有下载原缓冲，不称为45份原数组均已归档。GT没有进入FPGA输入或分析通路。

## 证据与可追溯性

原下载文件为`C:/Users/Gabriel/Downloads/a3_background_check.ipynb`与`a3_results_bundle.zip`。原Notebook、ZIP、JSON、四个NPY、预览PNG和用户截图保存在本地`D:/PLD/retina_fpga/build/board_results/a3_background_2026-10-12/`，原字节未修改。原JSON同时逐字节保存在本目录。完整大小、绝对路径及SHA256见[归档清单](archive_manifest.json)。含眼底图像的文件留在已忽略的本地build目录，Git仅记录原JSON、哈希及核验元数据。

|原文件|字节数|SHA256|
|---|---:|---|
|执行Notebook|227615|`0d5541f31e6a50e50f6aa4fc12b440131df9b3d9c19b1cbaf5b92693f35eeb90`|
|结果ZIP|1249553|`a5045a8b19675c3a82609007ca757002a1e1919079740f98c4b128ae68a87c8e`|
|原JSON|52889|`af0fbedf61ecaa772cc3c62b4b28e00d945aeb5751a21719155cf6e236f83c7a`|
|预览PNG|163467|`a92ce1e96f55c30601e7aa0b3c551ab82d4eebb4301078ae89b1233dae8c5a43`|

硬件/发布源码Commit为`3d203d55e09d483dcb2638e53fa869f89c206d7e`。发布目录`build/deploy/a3_background_2017_4_r1`及清单原字节保持不变，清单SHA256为`27cd1ad1a6360ca65e3dd99afed2d2d7158d8721989f53784fa8877cba7b8d17`。发布时的NOT_RUN是历史状态，本次板测状态由本归档另行记录。

运行后Notebook含新增输出，完整文件哈希变化正常；六代码单元的契约SHA256仍为`a63c867bc18b026c641866f23b699517bad22eeb8939778f1780fb7b7304ce07`。板端未校准时间`2022-10-22T05:18:49.960253+00:00`原样保存；主机核验时间另记为`2026-10-11T18:43:12.845984+00:00`，即北京时间2026-10-12 02:43:12。

数值证据：[原JSON](a3_background_result.json)、[45帧独立复算](independent_frame_verification.json)、[四份原数组逐字检查](raw_array_verification.json)、[预览检查](preview_verification.json)、[20项归档工具检查及源码哈希](host_archive_checks.json)、[实际检查日志](host_archive_checks.log)。

归档入口`scripts/archive_a3_board_results.py`从未修改的A2归档工具派生，差异见[工具diff](../a2_to_a3_archive.diff)与[测试diff](../a2_to_a3_archive_tests.diff)。读取固定平面ZIP文件并检查CRC、大小、重复、未知路径及链接；不执行Notebook代码、不解压任意路径。全部核验通过后创建归档，拒绝覆盖已有记录。可在本机复查：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_a3_archive.py' -v
```

## 下一阶段

A3证明已选算法A的高斯/LUT/15×15背景/暗结构响应以及标准DMA通路在PYNQ3.0.1实体板工作。下一阶段先审查成熟阈值、膨胀/腐蚀和邻域过滤候选，接入已冻结的阈值、形态学及最终FOV过滤，生成并逐像素验证二值血管mask。背景模糊本身不需要修正。

当前未完成完整分割质量验收、最终B的算法与官方VDMA/HDMI同一bitstream整合、FPS或端到端延迟实测。A3没有HDMI，此前官方Base显示验证仍单独记录。
