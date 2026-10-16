# 原卡启动文件只读检查

日期：2026-10-11。Windows读卡器挂载F盘，用户提供boot目录截图。仅从卡读取数据；未格式化、修复或写卡，未执行任何卡内程序。

## 结论

**当前启动文件存在明确的目标器件及板级配置不匹配，不能用作PYNQ-Z2基线。** 不能仅凭这些文件判断板卡损坏，亦未证明串口空白只有这一个原因。应保留原卡并使用正确的官方PYNQ-Z2镜像继续验证。

## 文件证据

- `system.bit`的原生头部：设计`orb_fpga_wrapper;UserID=0XFFFFFFFF;Version=2018.3`；目标器件`7z015clg485`；生成日期2024/11/08，22:32:25。
- PYNQ-Z2厂商原始board.xml指定`xc7z020clg400-1`，与上述器件不符。
- 从`system.bit`提取完整3510668字节配置负载，逐32位字节反转后，与`BOOT.BIN`中偏移104256处完全一致。因此问题不仅在额外存放的system.bit文件：该配置负载确实包含于启动镜像中。
- 外部`system.dtb`和`image.ub`内嵌设备树均启用UART1（0xe0001000），禁用UART0（0xe0000000）；serial0别名指向UART1。厂商Z2 preset启用UART0并使用MIO14/15，禁用UART1。`ttyPS0`编号由别名决定，不能只看该名字判断物理UART正确。
- 两份设备树的memory reg为`00000000 40000000`，声明1GiB；厂商Z2 preset DDR上限0x1fffffff对应512MiB，存在不匹配。
- FIT描述包含PetaLinux内核`4.14-xilinx-v2018.3`，BOOT.BIN中的U-Boot横幅为`U-Boot 2018.01 (Nov 08 2024 - 14:41:43 +0000) Xilinx Zynq ZC702`，并出现SLAM-ZYNQ工程构建路径。单独u-boot.bin来自另一个ORB_ZYNQ2路径及更早日期。ZC702字符串本身不足以确认实体目标板型号，应以器件/配置证据为准。
- 没有读取根文件系统，故尚未取得发行版、PYNQ包是否存在及其版本。

解析结果与六个文件SHA256：见[sd_boot_inspection.json](sd_boot_inspection.json)。六个原始启动文件已保存至同目录`sd_boot_backup/`，每份拷贝均与原文件SHA256一致。**这是启动文件备份，不是完整SD卡备份；不包括第二分区内的用户文件及系统。**

## 卡和分区的主机观测

- Disk 1，Generic STORAGE DEVICE，USB，MBR，总容量15931539456字节。
- 分区1：F盘，FAT32，boot，大小104857600字节，偏移1048576；Windows卷HealthStatus为Warning。未修复，不能从该状态独立判定损坏。
- 分区2：无盘符，Windows类型Unknown，大小15825633280字节，偏移105906176；尚未检查具体文件系统。Windows无法识别Linux文件系统时也会显示Unknown，不能据此判定空白或损坏。

## 后续验证与版本要求

PYNQ官网Previous board images目前列出PYNQ-Z2 v3.0.1和v3.1.1下载。先选v3.0.1作为预构建官方Demo的启动验证候选，项目已固定并审查其源码Commit。官方网页v3.0.1链接重定向后的[AMD下载](https://download.amd.com/opendownload/xlnx/pynq_z2_v3.0.1.zip)经HTTP HEAD只读检测返回200，application/zip，Content-Length为1811523457字节。尚未下载ZIP、校验镜像内容或写卡，不能将HEAD响应当作镜像完整性验证。

可使用官方预构建镜像先验证启动、Jupyter和Base，不需要先在Windows安装Linux，也不需要先编译Vivado工程。正式开发仍须匹配镜像、官方Tag/Commit及Vivado：本机只有2017.4，不得假定其能重建3.0/3.1 Base。v3.0.1源基线要求2022.1，3.1源码基线要求2024.1。尚未写入任何候选镜像，未改变原来的工程构建基线。

原卡第二分区数据是否需要保留未知；若后续重新写入此卡，须先决定保留方式并取得覆盖授权，或使用另一张卡保留原卡。当前只备份了启动文件。

来源：

- 项目固定原始厂商文件：`references/board/pynq-z2/pynq-z2/A.0/board.xml`和`preset.xml`。
- [PYNQ官方镜像下载页面](https://www.pynq.io/index.html#boards)。
- [PYNQ v3.0.1镜像构建规则](https://github.com/Xilinx/PYNQ/blob/v3.0.1/sdbuild/Makefile)。

本记录不是板端测试通过记录；所有Demo状态保持未验证。
