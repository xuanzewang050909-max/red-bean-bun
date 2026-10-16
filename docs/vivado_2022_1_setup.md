# Vivado 2022.1 配套环境准备

**2026-10-11 决策更新：用户同意先用现有 Vivado 2017.4，暂缓此安装流程。** A0先验证标准 DMA；B候选复用官方 v2.2.1 Base并检查与板上 PYNQ 3.0.1 的适配。下文2022.1为后备路线，不是运行PYNQ 3.0.1或开发A0的强制条件。见 [A0 验证步骤](a0_dma_validation_steps.md)。

日期：2026-10-11，Asia/Shanghai。尚未下载或安装新工具，未构建 A0。

## 已确认的选择依据

实测 PYNQ-Z2 运行 PYNQ 3.0.1，板端四个 Base Tcl 的 SHA256 匹配已固定 v3.0.1 的 Z2 源码。官方 base.tcl 声明 2022.1，因此 A0 与最终派生 B 的首选构建版本为 Vivado 2022.1。现有 2017.4 保留用于历史参考验证，不覆盖、不卸载。

## 官方安装入口

[AMD 2022.1 下载页](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2022-1.html) 选 Vivado ML Edition – 2022.1 – Apr 26, 2022 下的 **AMD Unified Installer 2022.1: Windows Self Extracting Web Installer**，页面标注 EXE、205.92 MB。网页登录及下载资料由用户按真实账号完成。

此 EXE 是联网安装入口，实际组件还需继续下载。选择 Vivado ML Standard 及 Zynq-7000 所需器件；B 的官方视频 HLS IP 还需匹配的 Vitis HLS，不能把 Lab Edition 当成完整综合工具。组件名称和最终磁盘需求以实际安装界面为准。

拟装目录 E:\vivado，与原有版本分目录；下载缓存也优先安排在 E，避免 C/D 空间压力。最近检查 E 空闲约 103.58 GiB，不能在没有安装摘要前声称足够，需核对实际组件占用和下载/解压峰值。

## 主机兼容性实测要求

本机为 Windows 11 家庭版。官方 [UG973 2022.1 支持系统列表](https://docs.amd.com/r/2022.1-English/ug973-vivado-release-notes-install-license/Supported-Operating-Systems) 列出 Windows 10 Professional/Enterprise，未列 Windows 11。Windows 版存在不等同于本机已获官方支持；安装后必须先测试启动、XC7Z020 IP/许可、简单综合和 xsim，再进行 A0。出现实际兼容失败后依据日志处理或转用支持的构建主机；当前不要求用户先安装 Linux，也不假定 Windows 11 一定成功。

## A0 准备架构

复用 Z2 PS preset（xc7z020clg400-1）与板端启动环境：PS GP0 控制互连；PS HP0 连接成熟双向 Simple AXI DMA；DMA MM2S → 标准 AXIS Data FIFO → S2MM；PS FCLK0 100 MHz 与 proc_sys_reset 同步复位。流接口 32 位，存储接口 64 位，SG=0，长度字段至少 21 位（计划 23 位），保留 TLAST/TKEEP。

验证递增/随机图案、256/512 尺寸、连续多帧，逐字比对、DMA 状态与超时。输出带代码 Commit、工具版本、bit/HWH 配对和时序报告。不得把已通过的输出 VDMA 或仅 S2MM 的 Trace DMA 当作双向 A0 通过。具体 Tcl/地址/IP 参数需要在 2022.1 的 IP Catalog 和 validate_bd_design 中确认；尚无 A0 bitstream。
