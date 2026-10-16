# 用户提供的PYNQ资料包审查

日期：2026-10-11。原文件：`E:\BaiduNetdiskDownload\Pynq资料（含实验指导书等）.zip`，8756488字节。仅查看、校验CRC并提取文档和配置文件；未执行软件、未修改Vivado安装、未导入许可证、未改写SD卡。

**结论：有可用的PYNQ-Z2板级配置、引脚约束和入门教材；没有SD系统镜像，也没有完整工程或医学算法模块。不能用这个资料包替代正确的PYNQ-Z2启动镜像。**

压缩包包含10个文件，展开总计9933841字节，ZIP CRC检查通过。归档SHA256为`9ef9500720b157ddf9239a34a1d42b65185b8fd7cdab0dca4e4f065d1bc9580e`。文件清单及提取文件哈希见[manifest.json](../results/board/2026-10-11/vendor_package/manifest.json)。包内文档作为用户提供的参考资料，其实验步骤不构成自动改变项目要求或机器配置的指令。

## 可用资料与使用边界

|资料|检查结果|项目使用方式|
|---|---|---|
|board_files/pynq-z2/A.0/board.xml、part0_pins.xml、preset.xml|三份文件与已冻结厂商原件逐字节一致，FPGA为xc7z020clg400-1|可复用；继续使用项目中现有厂商版本，无需重复覆盖安装目录|
|引脚约束文件/pynq-z2_v1.0.xdc|与已冻结厂商Master XDC逐字节一致|可复用；按实际顶层端口选择所需约束，不直接启用全部接口|
|实验指导书/Pynq实验指导书v1.0.pdf|东南大学教材，50页；实验一FPGA、实验二Zynq、实验三PYNQ|适合入门；先读实验三，再做官方Base验证；实验一、二可在独立验证阶段学习|
|原理图/TUL_PYNQ Schematic_R12.pdf|15页TUL图纸，文件名R12，内部图签R10，日期2018-03-19，PDF标题TUL_PYNQ_R12_0319_S|作为补充版本保留；与原冻结PDF字节不同，不能覆盖原文件，不能据此判定实体PCB修订版|
|原理图/PYNQ-Z2_PA_v3.pdf|2页产品规格/宣传资料；列明XC7Z020、512MB DDR3、HDMI等|适合了解硬件；不是详细电路原理图|
|实验指导书/往年开发平台指导书（含大量入门基础）/EES-A7实验指导书 .pdf|102页，针对XC7A15T-1CSG324C/Artix-7平台|仅参考Verilog、仿真、综合等通用概念；板级器件、引脚、外设与程序下载配置不适用于PYNQ-Z2|
|Vivado Lisence/vivado-license.lic|仅确认归档中存在此文件，未解析或导入|当前主机已有许可已通过XC7Z020综合及实现检查，现阶段不需要更换许可证|
|board_files/pynq-z2/A.0/pynq_z2.jpg|板卡图片|仅用于外观参考，未用于核对实体PCB修订或跳线状态|

板级文件逐字节比较及preset参数差异检查见[official_comparison.json](../results/board/2026-10-11/vendor_package/official_comparison.json)。匹配文件不代表板级实测已通过。

## 建议的阅读顺序

阅读器页码与书内印刷页码不同，以下同时标明：

1. 阅读器第40页／书内第36页：实验三PYNQ基本开发流程，理解浏览器、Python和板上Linux的关系。
2. 第41页／书内第37页：硬件准备、Windows烧写SD镜像、SD启动与网线连接。教材要求另外下载镜像，包里没有镜像。
3. 第46页／书内第42页：USB串口与PuTTY设置。与用户目前已确认的115200、8N1、无流控一致，无须因本教材而重复更改串口参数。
4. 第47页／书内第43页：Base按键控制LED。等正确镜像启动并取得实际PYNQ版本后，运行该镜像自带的Notebook副本。
5. 第49页／书内第45页：HDMI面部识别示例，仅作视频输入输出与Notebook使用参考；并未说明算法在PL中实现，不能算本项目的医学分析RTL成果。需要HDMI信号源和显示器等硬件。

## 不能直接照搬的步骤

- 第5页／书内第1页说明实验一、二把启动跳线设为JTAG，这是独立硬件/SDK下载实验的流程。当前验证PYNQ镜像时必须保持SD启动，不因该段说明切换JTAG。
- 教材使用Vivado2017.4，与本机工具相同，可用于基本操作学习；这不能证明本机2017.4可重建PYNQ3.0.1 Base，后者官方工程要求2022.1。
- 第42页／书内第38页使用`http://pynq:9090`和`http://192.168.2.99:9090`。PYNQ3.0官方设置指南使用默认HTTP地址`http://192.168.2.99`或DHCP分配的实际板卡IP，不应固定照抄9090。主机名解析、IP和服务状态仍待实际连接验证。
- 音频、PmodOLED等例子可用于以后学习，本阶段先完成启动/Jupyter/GPIO/HDMI/帧缓存/DMA验证。
- 暂未识别到教材资料的明确开源再分发许可证；本地学习和参考之外，如需把教材或衍生教学内容对外发布，应另核实授权。现阶段保留原始归档来源，不将学校教材标为AMD官方开源源码。

## 对当前启动问题的影响

该包的板卡配置确实是PYNQ-Z2，但其中没有BOOT.BIN、image.ub、IMG镜像、BIT/HWH组合或可独立构建的HDMI/DMA工程。**它不能修复原卡中已确认的Zynq-7015目标器件不匹配。** 原卡证据见[sd_image_check.md](../results/board/2026-10-11/sd_image_check.md)。仍应先获取正确官方镜像，保存原卡数据后再进行写卡与真机验证；Windows电脑不需要安装Linux来运行预构建PYNQ镜像。

官方交叉核对：[PYNQ3.0 Z2设置指南](https://pynq.readthedocs.io/en/v3.0.0/getting_started/pynq_z2_setup.html)。原始资料均保存在`results/board/2026-10-11/vendor_package/`，原压缩包和项目`references/`没有修改。所有板级Demo仍未验证。
