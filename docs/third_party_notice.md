# 第三方资源来源与许可记录

此文是工程来源记录，不给整个RetinaFPGA项目套用某个第三方许可证。每个快照保留原有头部与LICENSE，公开分发时仍按具体文件条款执行。当前仅本地Git保存，无发布/上传。

|资源|固定版本 / 本地位置|已查许可|执行要求|
|---|---|---|---|
|Xilinx/PYNQ源文件、驱动、Notebook、Tcl|v2.2.1、v3.0.1、v3.1.2；`references/PYNQ/`|根LICENSE为BSD 3-Clause；保留文件内版权和第三方说明|源码/二进制分发保留版权、条件和免责声明，不借作者名义背书|
|Digilent dvi2rgb/rgb2dvi/axi_dynclk|各Tag的`boards/ip/`|PYNQ `THIRD_PARTY_LIC`列MIT；旧rgb2dvi/dvi2rgb的VHDL头含BSD 3-Clause|原有声明均保留，分发随带两个层面的许可说明，不删头部|
|xfOpenCV|2017.4_release，Commit `6e6953c20dc12de828693d6ae34bbb9a9a55ac37`|LICENSE.txt：BSD 3-Clause，Xilinx 2017|只作为已查候选；保留许可/版权/原始头，未声称在Z2上验证|
|AMD/Xilinx标准PS/AXI DMA/VDMA/GPIO/VTC/时钟复位IP|本机Vivado2017.4对应IP目录|工具/IP许可（不是PYNQ的BSD整体覆盖）|使用合法已验证的本机工具，按IP许可交付bitstream；不发布安装包或专有工具头文件|
|Vivado HLS自带hls_video库|本机2017.4实际autopilot编译头及include审查头|工具附带许可与文件内OpenCV条款，未复制安装库进项目|A2/A3/A4复用未修改Filter2D/BoxFilter/Threshold/morp_opr/Mat/LineBuffer，生成物按工具条款处理；A4实际编译六份库头与审查来源分开记录，交付说明保留内嵌OpenCV版权/条件/免责声明|
|TUL原理图/手册/XDC/Board Files|厂商CDN及本地`references/board/`|未发现明确独立开源/再分发授权|内部审查保留；公开仓库/比赛材料引用来源，需分发完整文件时核对厂商条款|
|维护者PYNQ DMA教程|PYNQ官方社区链接|本次未拷贝完整外部工程，未确定个人仓库独立许可|复用方法与AMD/PYNQ已有IP；引入源码时先补许可、Commit、板卡及工具审查|
|Vitis Vision|2022.1官方功能文档|本次仅查文档，未导入源码|后续选用时固定实际版本，保存对应库LICENSE及源码头|

官方快照中的数据样图/人脸Haar文件也作为原Notebook资源保留，不把它们作为本项目医学数据。STARE的20原图与AH/VK标注已取得，来源/哈希及数据分发边界见[数据说明](../data/README.md)。A2/A3/A4只把原RGB生成的im0001输入和FOV作为板卡输入，标注不进入处理通路；数据和派生图仅用于本地研究，未公开发布。A4本地十二文件套件包含许可使用说明，不分发安装库专有头；A4实体板61帧与六份真实输出已核验，原图/输出/Notebook只存本地忽略目录，Git仅记录原JSON与核验元数据。

来源链接汇总见[board_reference_audit.md](board_reference_audit.md)第14节。第三方原始代码归其作者，`scripts/`中的工程审查包装和`docs/`为本项目新增文件；新增实现的许可尚未另行指定。
