# 展示入口更新（2026-10-16）

最终Demo改用独立c7_showcase_r1（20张/8样例/可变次数），待短轮板测；入口见docs/c7_showcase_steps.md。旧handoff_r1/r2、七次Notebook与所有证据保留，暂不把旧快照称为最新展示版。视频由用户明确暂缓，等用户要求再录，覆盖下文历史录像前置。第二轮旧Demo数据见docs/c7_demo_followup_2026-10-16.md。

# C7交付材料入口（重启与视频待补）

2026-10-16：当前C7已获得用户视觉认可，算法进一步优化暂缓。软件演示、W4性能、W5a长稳和W5b限定交互已核验；用户确认尚未做最后要求的正常关机重启及录像，因此不能宣布最终提交完整。

## 交付目录

当前整理版：`D:/PLD/retina_c7_system/build/delivery/c7_handoff_r2`。r1原快照保留。

| 内容 | 交付目录内路径 | 用途 |
|---|---|---|
| 受控源码与历史审查记录 | source_snapshot.zip | 内含HLS/RTL、Vivado脚本、软件、测试、文档和受控results；源提交见manifest |
| 实际生成IP、RTL | generated_ip / generated_rtl | 不是CPU替代模型；125生成RTL/ROM文件已核对原清单 |
| 配对硬件 | hardware | 真实已验C7 bit/HWH |
| 布线报告及构建脚本 | reports | 查看100MHz时序、资源、DRC、时钟、BD拓扑 |
| 设计/质量/部署说明 | documents | 入口c7_delivery_report.md、c7_delivery_quality.md、c7_vivado_handoff.md |
| 板卡上传两文件 | board_upload | c7_delivery_demo.ipynb和原c7_w5b_interaction_r1.zip |
| 本轮真实七次演示原件 | demo_downloads | 原始ZIP及执行Notebook，勿替换为空Notebook |
| 七次演示核验及截图 | demo_evidence | 独立逐字核验JSON与01～07截图 |
| 内容身份清单 | handoff_manifest.json | 每文件长度/SHA256、源提交、当前交付状态 |

全套历史原始板测大ZIP仍在本地build/board_results及原工程，快照不代替它们的备份。仅board_upload两文件上传板卡；整个工程包留电脑，不占SD。source_snapshot.zip内文档相对引用按仓库结构使用，documents为便捷副本。

## 已完成与剩余

- 已完成：C7真实输出对照、资源/时序、同板ARM比较、正式浏览器测速、纯DMA、1000帧稳定性、42任务交互、七次软件演示、材料整理与完整性清单。
- 待人工：正常关机断电再上电，在新目录跑相同七次演示并录视频；回传结果后核验、把实际视频列入最终清单。
- 未测并如实披露：整板仪器功耗、物理网络故障/在途断电恢复、强制真实DMA故障；没有新外部医学验证或实时帧率达标结论。
- 暂缓：亮区/细血管新算法及新PL候选；旧失败记录保留。

## 视频讲解提纲（约3～5分钟，不强制时长）

1. 展示真实PYNQ-Z2、网线与供电，说明“眼底图像检测核心在PL；ARM调度DMA与生成展示；电脑浏览器显示”。正常关机、再上电过程可用手机单独一段记录；停机等待可注明后剪短。
2. Jupyter新目录启动，显示配对包检查、boot_id及一次加载。不要把录制好的图片装成实时执行。
3. 按七次表演示：C7四图；无GT显示未评价；旁路只剩原图；C2中间模式；刷新后回C7。C2中间图不能称C7中间层。
4. 展示任务证据，说明“核心约3.04ms，端到端浏览器约0.57FPS，二者不是同一指标”；不要用单图Dice作全数据准确率。
5. 正常关闭与导出。最后展示Vivado原full_02工程和时序/资源报告可另外录一段，避免录制时重新综合或升级IP。

录像可分成板卡重启、屏幕操作和Vivado展示三段，明确分段即可。截图只能佐证界面，不能冒充视频。原源码中绝对路径和迁移重建限制见c7_vivado_handoff.md。

## 原C7回滚与记录保护

当前实验正常CLOSED/IDLE且下载完成后可关闭对应内核；新的启动使用原两文件和全新目录。不删除旧会话、不覆盖既有解压目录、不修改exist_ok=False绕过保护。故障/在途DMA场景先保存现场并报告，不自动重载或释放缓冲。

详细七框操作见`D:/PLD/retina_c7_system/docs/c7_delivery_demo_steps.md`。本次补录目录改为retina_c7_demo_reboot_r2，其余步骤和参数完全相同。
