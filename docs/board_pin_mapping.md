# PYNQ-Z2 原理图—管脚—Vivado端口—软件对应表

状态：静态资料交叉核验，实际PCB修订版未知。参考图纸文件名`TUL_PYNQ_Schematic_R12.pdf`，内部图签是R10/2018-01-09；这里的管脚不能被解释为已核对用户实体板。PL约束取TUL Master XDC和固定版本Pynq-Z2 Base XDC，PS DDR/MIO由Z2 preset及PS固定接口管理。

## 1. HDMI（原理图第6、10、11页）

P/N表严格按实际网络和XDC保留，不交换极性或借用其他板卡。TMDS使用`TMDS_33`；HPD、RX DDC使用`LVCMOS33`。TX DDC位于1.8V PS Bank 501，经U8电平转换，不能当作PL LVCMOS33端口。

|原理图网络|Zynq封装脚（P/N顺序）|Base Vivado顶层端口|IP/软件|
|---|---|---|---|
|HDMI_TX_CLK_P / CLK_N|L16 / L17|`hdmi_out_clk_p/n`|`rgb2dvi_0/TMDS`；HDMIOutFrontend、VideoOut|
|HDMI_TX_D0_P / D0_N|K17 / K18|`hdmi_out_data_p/n[0]`|同上|
|HDMI_TX_D1_P / D1_N|K19 / J19|`hdmi_out_data_p/n[1]`|同上|
|HDMI_TX_D2_P / D2_N|J18 / H18|`hdmi_out_data_p/n[2]`|同上|
|HDMI_TX_HPDN|R19|`hdmi_out_hpd[0]`|`hdmi_out/frontend/hdmi_out_hpd_video`；见下方方向疑点|
|HDMI_TX_SCL / SDA|B13 / B9，MIO50 / 51|`FIXED_IO_mio[50/51]`，无独立PL XDC|PS I2C；原官方输出模式驱动不能假定已读取EDID|
|HDMI_TX_CEC|G15|Base未使用|本项目不接入CEC|
|HDMI_RX_CLK_P / CLK_N|N18 / P19|`hdmi_in_clk_p/n`|`dvi2rgb_0/TMDS`；HDMIInFrontend、VideoIn|
|HDMI_RX_D0_P / D0_N|V20 / W20|`hdmi_in_data_p/n[0]`|同上|
|HDMI_RX_D1_P / D1_N|T20 / U20|`hdmi_in_data_p/n[1]`|同上|
|HDMI_RX_D2_P / D2_N|N20 / P20|`hdmi_in_data_p/n[2]`|同上|
|HDMI_RX_HPD|T19|`hdmi_in_hpd[0]`|AXI GPIO；驱动控制接收端HPD，经Q7转换|
|HDMI_RX_SCL / SDA|U14 / U15|`hdmi_in_ddc_scl_io/sda_io`|dvi2rgb内EDID/DDC通路，经U7转换|
|HDMI_RX_CEC|H17|Base未使用|本项目不接入CEC|

**资料疑点：** TX连接器HPD经Q8反相后到R19，电路显示为接收显示器状态；官方Base的同名GPIO却配置`C_ALL_OUTPUTS=1`，输出端口接R19，OEM Board Files也把它列成GPIO输出预设。这里存在图纸/参考配置方向不一致。由于下载图纸修订标识本身不一致，暂不能判定实体板电路或新版本意图。保留证据，板卡到手后核对修订/电路和官方原始行为；不把这个GPIO当作普通输出驱动高电平，也不把它未经验证改成“已正常读HPD”。显示模式先用官方受支持的固定VideoMode。

## 2. 用户交互GPIO（第3、11页）

|网络|封装脚，按索引升序|Base顶层端口|软件对应|
|---|---|---|---|
|BTN0..3|D19,D20,L20,L19|`btns_4bits_tri_i[0..3]`|`btns_gpio.channel1` / 原Base `buttons`|
|SW0..1|M20,M19|`sws_2bits_tri_i[0..1]`|`switches_gpio.channel1` / `switches`|
|LED0..3|R14,P14,N16,M14|`leds_4bits_tri_o[0..3]`|`leds_gpio.channel1` / `leds`|
|LED4_B/G/R|L15,G17,N15|`rgbleds_6bits_tri_o[0..2]`|`rgbleds_gpio`；原Base RGBLED(4)|
|LED5_B/G/R|G14,L14,M15|`rgbleds_6bits_tri_o[3..5]`|同上；RGBLED(5)|

GPIO均按对应XDC使用LVCMOS33。按钮按下为高，普通LED高电平点亮；RGB颜色次序按官方B/G/R连接和驱动处理。按键消抖可用软件或小型计数器完成，属于新增交互功能，不修改已有AXI GPIO内部RTL。

## 3. PS MIO 外设（第5、7、8、10页）

这些封装脚经PS专用IO连接，顶层均属于`FIXED_IO_mio[n]`，**不增加手写PL管脚约束**。软件继续使用镜像自带Linux/PS驱动。下表脚号从放大后的原理图第10页读取，不把MIO序号当作封装脚号。

|网络/功能|MIO→封装脚|PS与软件|
|---|---|---|
|UART_TXD_IN|14→C5|FT2232HL TX进入PS UART0 RX；串口启动/调试|
|UART_RXD_OUT|15→C8|PS UART0 TX进入FT2232HL RX；设备名由启动日志确认|
|ETH_TXCK|16→A19|PS Ethernet0 RGMII / RTL8211E / Linux网络|
|ETH_TXD0..3|17→E14，18→B18，19→D10，20→A17|同上|
|ETH_TXCTL|21→F14|同上|
|ETH_RXCK|22→B17|同上|
|ETH_RXD0..3|23→D11，24→A16，25→F15，26→A15|同上|
|ETH_RXCTL|27→D13|同上|
|ETH_MDC / MDIO|52→C10，53→C11|PS管理接口 / Linux PHY驱动|
|ETH_RST_B / INT_B|9→B5，10→E9|PS GPIO/驱动管理；复位影响PHY CLK125|
|OTG_DATA0..3|32→A14，33→D15，34→A12，35→F12|PS USB0 ULPI / TUSB1210 / Linux USB|
|OTG_DATA4..7|28→C16，37→A10，38→E13，39→C18|同上|
|OTG_DIR / STP / NXT / CLK|29→C13，30→C15，31→E16，36→A11|同上；PHY有独立26MHz参考|
|OTG_RESETN / OC|46→D16，11→C6|USB PHY复位/过流辅助信号，由匹配镜像管理|
|SD_CLK / CMD|40→D14，41→C17|PS SDIO0，SD启动/文件系统|
|SD_D0..3|42→E12，43→A9，44→F13，45→B15|同上|
|SD_CD|47→B14|卡检测|

手册把SD范围概括为MIO40..47，但MIO46实际是USB RESETN；不能把整段MIO40..47都配置成SD数据。UART网络名称从USB桥视角命名，避免再次把TX/RX反接。网络IP/主机名尚未知，未连接或扫描推测的设备。

## 4. DDR3专用Bank 502（第10、13页）

官方板级规格及preset采用512MiB、16位DDR3、525MHz/1050Mb/s配置。下载手册同时写“256Mx16/512MB”和`MT41K512M16HA-125:A`，原理图IC1也标后者，但只连接A0..14且PS窗口为512MiB。型号/容量描述有不一致，等待核对实物颗粒；不据型号文字把RAM范围改成1GiB。

以下按索引升序列出**Zynq封装脚**，不是DDR颗粒封装脚。Vivado对应PS `DDR`外部接口，软件由FSBL/镜像PS初始化，PL DMA/VDMA通过HP访问，应用用PYNQ连续缓冲。专用DDR管脚不从Master PL XDC重新约束。

|原理图网络|Zynq脚（索引升序）|PS DDR端口|
|---|---|---|
|MEM_ADD0..14|N2,K2,M3,K3,M4,L1,L4,K4,K1,J4,F5,G4,E4,D4,F4|`DDR_addr[0..14]`|
|MEM_BANK0..2|L5,R4,J5|`DDR_ba[0..2]`|
|DDR3_D0..15|C3,B3,A2,A4,D3,D1,C1,E1,E2,E3,G3,H3,J3,H2,H1,J1|`DDR_dq[0..15]`|
|MEM_DM0..1|A1,F1|`DDR_dm[0..1]`|
|MEM_DQS0_P/N，1_P/N|C2/B2，G2/F2|`DDR_dqs_p/n[0..1]`|
|MEM_CLK0_P/N|L2/M2|`DDR_ck_p/n[0]`|
|MEM_MA0_CKE0 / CS_L0 / ODT0|N3 / N1 / N5|`DDR_cke/cs_n/odt[0]`|
|MEM_RAS# / CAS# / WE# / RESET#|P4 / P5 / M5 / B4|`DDR_ras_n/cas_n/we_n/reset_n`|
|DDR3_VREF / DDR_VRP / DDR_VRN|P6,H6 / H5 / G5|PS DDR参考/校准，维持原电路|

图纸网络总线标签含`MEM_ADD[15..0]`，但PS符号没有连接A15，不能为未连接位编造脚号。PS DDR DQ16..31未接入当前16位存储器。

## 5. 时钟、供电、复位和启动（第9、10、12、14、15页）

|项目|图纸对应|工程/软件措施|
|---|---|---|
|PS时钟|OSC3 50MHz→PS_CLK E7；另一路给Ethernet参考|PS preset保持50MHz；FCLK由PYNQ/PS设置|
|PL 125MHz|Ethernet PHY CLK125→H16|Master XDC已有该参考；算法优先使用FCLK0，不依赖PHY复位状态|
|PS系统复位|PS_RST→B10，SRST按钮/缓冲|保持官方启动与复位路径|
|PS上电复位|PG_ALL→PS_POR_B C7|电源监控，不用PL逻辑替代|
|PL配置复位|PROG_B→L6|用于PL配置；按键操作会破坏已加载Overlay状态|
|启动模式|JP1选择JTAG/QSPI/SD，经MIO启动绑带|板卡到手按手册图示确认SD启动，不猜跳线方向|
|电源选择|J9选USB供电或外部REG/DC；外部输入范围见手册（7–15V、推荐12V）|实测前核对跳线和电源；当前未上电测试|
|PL Bank0/13/34/35|VCC3V3|按官方XDC使用LVCMOS33/TMDS_33，不擅改标准|
|PS Bank500 / 501|3.3V / 1.8V|MIO由preset管理；HDMI TX DDC经过电平转换|
|DDR Bank502|1.5V，VREF约0.75V|采用PS DDR控制器|
|核心/辅助电源|约1.0V / 1.8V|不重写板级初始化|

供电/复位/启动结论来自资料，尚未核对实体PCB。后续布局布线必须保留官方IP内置generated-clock/CDC/TMDS约束，并删除真正不用的顶层端口对应XDC，不能只删BD后继续约束不存在的端口。

## 6. 约束复用方法

1. 保存TUL完整Master XDC和所属Tag的Base XDC。
2. 以派生Base顶层端口名沿用所属Tag的约束；A工程仅用PS固定接口，不启用整份带扩展IO的Master XDC。
3. 对保留HDMI/GPIO管脚按脚号和IOSTANDARD交叉核验；Master XDC的`hdmi_tx_*`、`hdmi_rx_*`需与Base的`hdmi_out_*`、`hdmi_in_*`显式映射。
4. 发现同名/方向/修订不一致时记录来源和证据，不以另一个开发板约束补齐未知项。
5. 实体PCB确认后更新本表，生成板级DRC和时序报告，再记录实际可用管脚。

来源文件及下载SHA见[资源审查报告](board_reference_audit.md)，逐IP接口见[结构分析](base_overlay_analysis.md)。
