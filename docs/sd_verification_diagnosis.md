# 官方镜像写卡后校验失败诊断

日期：2026-10-11。用户报告写入成功，随后提供Win32磁盘映像工具1.0“校验失败的扇区：0”截图。

**结论：完整IMG逐字节相等检查确实失败，但系统载荷与官方镜像一致；差异仅为Windows在启动文件系统添加的辅助文件与访问日期记录。不需要为了消除这些差异重新写卡，可以继续板端启动验证。这个结论不代表板卡已成功启动。**

## 实际检查范围

以管理员权限只读打开已确认USB Disk 1；核对F盘、非系统盘、整卡15931539456字节、分区偏移及官方BOOT.BIN指纹后，与电脑官方IMG比对完整7858807808字节。未修复、格式化、改写MBR或删除卡内文件。

- 电脑IMG完整SHA256仍为`f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861`，与解压准备记录一致。
- 只有6个512字节扇区存在差异，全部位于启动分区；MBR、启动分区前间隙、分区间间隙完全一致。
- Linux分区完整7721444352字节逐块一致；镜像与SD该分区SHA256均为`8825a8f5e0a439a286779453b008e9b73f322d4368fac2e199d933ab1841cf9e`。
- BOOT.BIN、boot.py、boot.scr、image.ub、REVISION五个启动文件大小与SHA256全部一致；之前的逐文件校验记录见[sd_write_check.json](../results/board/2026-10-11/sd_write_check.json)。

## 差异解释

|实际差异扇区|含义及证据|
|---|---|
|23、159|FAT的两份副本，各有6字节从00变为ff，给原空闲簇1850、1851、1852设置链尾标志；两份副本变化一致|
|288|根目录：五个原文件目录项的访问日期由2022-10-22变为2026-10-11；另外新增System Volume Information长文件名及目录项|
|15104|簇1850，System Volume Information新目录内容|
|15112|簇1851，12字节WPSettings.dat；挂载路径文件内容与差异采样及不同字节数量一致|
|15120|簇1852，76字节IndexerVolumeGuid；挂载路径文件内容与差异采样及不同字节数量一致|

FAT16数据区始于全卡扇区320，簇大小8扇区，因此上述三个簇对应扇区号可直接核对。首次差异实际在扇区23，**不是扇区0**；MBR磁盘签名也未改变。

完整差异计数与采样见[sd_compare_result.json](../results/board/2026-10-11/sd_compare_result.json)，分类见[sd_compare_classification.json](../results/board/2026-10-11/sd_compare_classification.json)。GUI校验失败截图已保留；不将GUI结果改为PASS，也不声称整张卡与IMG严格相等。

## 工具提示为何显示0

从[Win32 Disk Imager官方源码仓库](https://sourceforge.net/p/win32diskimager/code/)取得实际v1.0.0 Tag，Commit `faf7aa25ac343b183811115359a18673fa279fae`。其校验按1024扇区批量memcmp，在失败对话框输出当前批起始下标i。因此第一批任一扇区不一致，都可能显示0，并不提供精确差异扇区。

源码还表明，失败对话框返回之后才解除卷锁。首次辅助比对因工具仍锁卷而PermissionError，已保存[首次尝试记录](../results/board/2026-10-11/sd_compare_first_attempt_locked.json)。用户明确确认关闭工具之后，第二次只读比对完成，状态见[sd_compare_status.json](../results/board/2026-10-11/sd_compare_status.json)。

核对用原始源码及GPL许可保存在`results/board/2026-10-11/disk_imager_v1_0_source/`，来源和文件SHA256见[manifest.json](../results/board/2026-10-11/disk_imager_v1_0_source/manifest.json)；未修改工具源码、未重建或替换已安装工具。

## 下一步

关闭写卡工具后，在Windows安全弹出SD卡；开发板保持OFF时装卡，保持Boot=SD、Power=USB，用PROG-UART连接电脑并开启电源。按现场观察（本板ON之后才出现串口）重新确认COM号，在PuTTY使用115200/8N1/无流控；连接后如空白可按SRST/PSRST抓复位启动日志，不按PROG。

目前仅完成镜像准备、原卡备份、用户写卡反馈及只读系统载荷校验。Linux启动/Jupyter/Base/GPIO/HDMI/帧缓存/DMA均未证明通过。
