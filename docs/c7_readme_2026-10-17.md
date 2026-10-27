# red-bean-bun

PYNQ-Z2上的C7眼底血管候选检测与浏览器展示工程。检测核心在FPGA PL执行，板载ARM负责DMA调度、评价与PNG展示，电脑负责浏览器显示。

## 当前状态（2026-10-17）

- 可信C7，Vivado 2017.4，100MHz。原算法进一步优化暂缓。
- 展示支持20张STARE图、8张讲解样例、前后切图、256/512、旁路及C2中间模式。
- 新展示39次任务：10027008输出字、195PNG核对一致。
- 64GB卡迁移后8次PL短测：1900544输出字、36PNG核对一致；两尺寸与旁路恢复通过。
- 原1000帧长稳与W4/W5证据保留。PL核心约3.04ms，不代表端到端帧率；原正式浏览器测速约0.57FPS。
- 实际仪器功耗未测，视频待录。旧展示中断原因尚未确定；后续通过不等于根因已修复。非临床诊断产品。

## 入口

- [设计与交付说明](docs/c7_delivery_report.md)
- [Vivado工程与重建限制](docs/c7_vivado_handoff.md)
- [20图展示操作](docs/c7_showcase_steps.md)
- [64GB迁移结果](docs/c7_sd64_migration_result.md)
- [新展示核验](results/c7_showcase_r1/board_restart_2026-10-16/verification.json)
- [新卡PL核验](results/c7_showcase_r1/board_sd64_2026-10-16/verification.json)
- `hls/`、`rtl/`、`vivado/`：算法及硬件构建源码。
- `pynq_showcase/`、`ui_showcase/`：板端服务与网页。
- `delivery/`：已核验配对bit/HWH、生成RTL/IP及实现报告。
- `scripts/`、`tests/`：数据准备、打包与离线核验。

## 公开范围与复现条件

此仓库是独立公开快照，原开发仓库与完整历史保留在本地。历史文档中的状态和绝对路径反映当时环境，以本页及最新核验记录为准。

STARE再分发许可未确认，因此不发布原始图像、标注、派生图片/数组、含数据的部署ZIP、桌面截图或整卡镜像。请从[数据来源说明](data/README.md)获取数据并按其使用条件操作；`scripts/fetch_stare.ps1`提供下载入口。硬件文档从制造商获取，本地来源清单不替代其授权。

展示打包入口`scripts/package_c7_showcase.py`依赖已准备的C7/W5b基线数据包；GitHub克隆本身不是完整即用板包。需要按原数据准备流程恢复依赖，不能把本地缺失的build目录当成已包含。Vivado跨机器重建、仿真向量路径和版本限制见上方交付说明；原受控脚本保留原样，未宣称一键重建已验证。

第三方源码保留各自版权与许可证。未为整个工程擅自添加统一开源许可证。`PUBLICATION_MANIFEST.json`记录公开文件身份及排除项。
