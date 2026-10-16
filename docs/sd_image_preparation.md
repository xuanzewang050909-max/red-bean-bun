# PYNQ-Z2 v3.0.1写卡前准备记录

日期：2026-10-11。用户已从官方链接下载镜像，并明确要求“不确定，先备份原卡”。当前先执行完整备份；本记录不授权自动覆盖SD卡，不代表板卡启动通过。

**后续完成状态：2026-10-11 16:47:49（Asia/Shanghai），原卡整卡备份状态COMPLETE，共15931539456字节，电脑备份文件完整重读SHA256与源读取流匹配。用户随后提供Win32磁盘映像工具1.0窗口截图，证明工具已打开：设备F盘，映像文件栏为空。重新只读核对F盘仍关联同一USB Disk 1、15931539456字节，原BOOT.BIN指纹一致。已准备指导选择官方IMG并由用户确认写入，但尚未取得任何写入成功或校验成功的证据。**

**后续写入反馈：用户明确反馈“写入成功”。Windows只读检查发现F盘标签变为PYNQ，文件系统FAT；BOOT.BIN、boot.py、boot.scr、image.ub、REVISION五个文件的大小及SHA256均与电脑官方IMG内文件一致。完整镜像范围尚未校验；也尚未用新卡在板端启动。证据及范围见[sd_write_check.json](../results/board/2026-10-11/sd_write_check.json)。下一步由用户在写卡工具中点击“仅校验”，不重复写入。**

## 官方镜像

后续GUI“仅校验”反馈失败；完整只读诊断确认MBR、全部启动文件及Linux分区一致，仅启动文件系统的6个扇区含Windows辅助文件/访问日期变化。保留严格逐字节校验失败状态，继续板端启动验证；详见[校验失败诊断](sd_verification_diagnosis.md)。

- 下载来源：[AMD官方PYNQ-Z2 v3.0.1 ZIP](https://download.amd.com/opendownload/xlnx/pynq_z2_v3.0.1.zip)。
- 用户下载文件：`C:\Users\Gabriel\Downloads\pynq_z2_v3.0.1.zip`，1811523457字节，与此前HTTP HEAD长度一致。
- 解压文件：`D:\PLD\retina_fpga\build\sd_images\pynq_z2_v3.0.1.img`，7858807808字节，ZIP CRC32为5aa11e6c，与ZIP目录记录一致。
- ZIP SHA256：`ea6372e2d95e241dc7f891d30abc8af2eaf6650c0c16788c27dafba97f41cf8b`。
- IMG SHA256：`f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861`。
- IMG启动分区REVISION文本为`Release 2022_10_22 93ddd21`和`Board 2022_10_22 93ddd21 https://github.com/Xilinx/PYNQ`，与本项目已固定v3.0.1源码Commit `93ddd21ab623883590a8c8b07f0b157b2855da4b`前缀一致；这是电脑IMG内容，尚不是板端采集的版本证据。
- 上述SHA256是本地测得的记录值，没有取得发行方公布的镜像SHA256，不能将本地记录等同发行方校验值匹配。ZIP CRC及长度检查仅确认下载/解压内部完整性。
- IMG的MBR签名55aa；MBR中分区类型为0x0c和0x83。另行读取启动分区BPB确认实际文件系统标识为FAT16（不按MBR类型推定文件系统），启动目录含BOOT.BIN、boot.py、boot.scr、image.ub、REVISION。完整镜像检查见[official_image_preparation.json](../results/board/2026-10-11/official_image_preparation.json)，启动目录及文件哈希见[official_image_boot_manifest.json](../results/board/2026-10-11/official_image_boot_manifest.json)。

## 原卡完整备份

本次Windows检测：F盘是USB读卡器中的boot分区，关联Disk 1，总容量15931539456字节，既不是Windows启动盘也不是系统盘。这个盘号/盘符只适用于本次连接，后续写卡前必须重新核对。

- 原卡备份路径：`D:\PLD\retina_fpga\build\sd_backups\original_card_20261011.img`。
- 运行脚本：[backup_original_sd_readonly.py](../scripts/backup_original_sd_readonly.py)。源设备只以rb打开，包含MBR、全部分区及未分配区域；没有使用任何SD写入、分区修复或格式化命令。
- 普通权限读取原始设备返回PermissionError，因此在用户要求备份后通过Windows管理员权限运行只读脚本。
- 启动前核对F盘对应USB Disk 1、容量、非系统盘、原分区偏移及BOOT.BIN指纹；已有备份/partial文件不会覆盖。
- 完整复制后重新读取电脑上的备份文件，要求长度相同且SHA256与源读取流相同，才将partial文件转为完整IMG。
- 实际状态及完成哈希以[sd_backup_status.json](../results/board/2026-10-11/sd_backup_status.json)为准。状态未达到COMPLETE时不得宣称备份完成或开始写卡。
- 本次完成备份SHA256：`d44796135aa498bd63f4294c0742ecfce867eb92314e4597c1366b913d9ab3f7`；文件位于build目录，未加入Git，需保留该实际IMG以便恢复原卡。
- 上一阶段的`sd_boot_backup/`只含6个启动文件；不能与本次整卡备份混淆。

## 写卡工具准备

采用PYNQ官方Windows写卡说明链接的[Win32 Disk Imager项目](https://sourceforge.net/projects/win32diskimager/)。

- 已下载至`D:\PLD\retina_fpga\build\tools\win32diskimager-1.0.0-install.exe`，12567188字节。
- SHA256为`a51c9fc75c9caa44df03502838f229a70d484963f54675c241799093a59d8874`，与[SourceForge下载页](https://sourceforge.net/projects/win32diskimager/files/latest/download)公布值相同。
- 安装包保存及校验后，用户已安装并打开工具，截图见`results/board/2026-10-11/win32diskimager_ready_user_photo.png`；尚未取得执行写入的证据。

当前下一步：在映像文件栏选择`D:\PLD\retina_fpga\build\sd_images\pynq_z2_v3.0.1.img`，设备保持已核对的F盘；实际窗口源文件/设备选择确认后，由用户点击“写入”并在工具的覆盖提示中确认。应选择官方IMG而不是原卡备份IMG，也不能把IMG复制为F盘中的普通文件。写入后使用Verify Only（当前中文界面“仅校验”）校验与官方IMG对应的字节范围；校验不证明Linux已启动。Windows提示格式化Linux分区时选择取消。

正式Overlay开发仍需匹配工具：该镜像的v3.0.1官方Base源码基线要求Vivado2022.1；本机2017.4不能据此认定可直接重建。当前只验证预构建官方镜像与Base。

依据：[PYNQ3.0 Windows写卡说明](https://pynq.readthedocs.io/en/v3.0.0/appendix/sdcard.html)、[Win32 Disk Imager发布说明](https://sourceforge.net/projects/win32diskimager/files/)。官方写卡页面示例中出现PYNQ-Z1字样，本项目只选择本地已确认的PYNQ-Z2镜像。
