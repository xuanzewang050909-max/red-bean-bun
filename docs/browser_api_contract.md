# 浏览器服务与实验数据契约 v1

**W3 实体板浏览器已完成并独立核验31任务、7,340,032输出字、147PNG及参数/周期回读。20帧全前台实际展示0.193518FPS。下一步为 W4a 无损PNG对照与PS分段计时。** C2同图AH Dice0.521735、VK0.505010，与已测W2相同；亮区改进已进入真实浏览器，仍有误检和召回损失。PS图像窗口平均4.421秒，占工作者89.425%，尚未拆分归因。W4a保留同一PL算法/固件，32项主机检查与50任务主机界面流程通过，实体板NOT_RUN。见[W3板测复核](../results/browser_w3_2026-10-14/board_execution_2026-10-14/verification_report.md)和[W4a完整操作步骤](browser_w4a_board_steps.md)。旧包与原始记录保留，不重跑已完成W3。

W3与W1共用API路径及单工作者/有界队列/导出/客户端计时模型，独立版本保留旧包。8090在加载前保留，9090仍用于Jupyter。W3请求增加必需 `algorithm` 字段（A/C2），`threshold` 为整数1..255；没有CPU分割回退。

## 接口

|接口|行为与证据|
|---|---|
|GET `/api/capabilities`|真实硬件ABI/bit与HWH SHA、时钟依据、支持尺寸/模式/阈值/周期/计数、版本；W3为A/C2、T1..255、RQ21周期；旧W1仍为固定28|
|GET `/api/images`|公开样本ID、RGB输入SHA、尺寸/可用标注说明；GT不随输入送入算法|
|POST `/api/runs`|图像ID、尺寸、算法A/C2、阈值、处理模式和客户端nonce，能力/范围校验后创建真实新PL任务|
|GET `/api/runs/{run_id}`|状态、实际配置/帧ID、输入输出SHA/字节/错误、分段性能/指标、图像URL|
|GET `/api/runs/{run_id}/images/{kind}`|同帧原RGB/增强/二值mask/叠加PNG；增强/掩膜来自该任务真实DMA数组|
|GET `/api/runs/{run_id}/export`|PNG、原packed NPY、原JSON/CSV，附输入/输出/参数/固件/时钟/映射，独立可复算|
|POST `/api/runs/{run_id}/browser-timing`|关联nonce/frame/config的客户端单调时钟间隔、可见性/浏览器版本，单独存观测|
|GET `/api/status`|Overlay身份、DMA/帧计数、IDLE/RUNNING/FAULT、错误/队列，不把空闲写为PASS|
|GET `/api/session/export`|空闲时导出全会话任务/观测/CSV/环境/事件，有在途请求拒绝409|

一个在途任务、最多一个待执行请求；W1忙时409，超范围/固件不支持422，不默默回退默认。页面关掉不取消DMA，仅安全完成后处理下个任务。多客户端不能绕过工作者写GPIO/切bit。图像以任务ID/哈希及 `Cache-Control: no-store` 标记，不能从永久静态URL缓存取图冒充新计算。W1限制200任务，现场长时会话另在W5扩展；透明度仅页面显示，导出叠加PNG固定65%。

## 参数和数据真值

请求示例是约定，不是运行记录：`image_id=im0001, side=512, threshold=28, algorithm=C2, mode=final, client_nonce=<unique>`。枚举 `bypass=0`、`threshold_candidate=1`、`closed_candidate=2`、`final=3` 映射现有PL。算法标识独立为A或C2；旧方向算法B未移植，仍拒绝。mode0布局不同，不解码为增强/分割，相关指标为null并注明旁路。

提交顺序为验证→排队→工作者写配置→首握手全帧锁存→完成后回读已生效快照。W2 RQ21已冻结：控制bits1:0为stage，bit2为256/512，bit3为C2/A，bits7:4保留0，bits15:8为T，bits31:16为任务tag。observer标准AXI GPIO地址0x41210000、RQ21身份0x52513231，原控制0x41200000和DMA0x40400000不变。完成后读取原始pages并核对控制/tag/序号/实际字数/周期，GPIO软件影子值不作为回读。应用导出 `hardware_latched_parameter_readback` 原pages及 `applied_parameters`。运行时FCLK0寄存器须100MHz。

每结果至少有boot/run/frame/config ID与nonce、算法/version、请求及生效参数、bit/HWH/source SHA、sample/shape/原RGB和packed输入SHA、实际packed输出SHA、send/recv字节、帧计数前后/wrap、DMA状态/PL错误、原始计时及图像SHA。加载/复位只在无在途任务时进行，boot事件单列。

生产后端仅接受RGB、其派生FOV及参数，不导入CPU参考/GT；评价侧在收到**真实完成的PL掩膜**后，读取同样本/映射AH/VK。面积分母为有效FOV，分子为FOV内非零mask像素。优先新PL计数，PS独立复算校验；原固件暂用注明PS来源的计数。无匹配GT则Dice/IoU为null及原因，不能填0/100%或沿用上一图值。PS只解包/评价/展示合成，不做PL滤波分割。

导出保留输入/参数/输出一致关联。alpha仅改变展示，不计新PL参数任务；图像/阈值/处理模式改变则必须新DMA/PL帧。重复图片也要有新的run与帧计数，旧成功结果显示旧ID，不能标当前请求成功。

## 计时字段

|字段（未测value为null并注明原因）|来源与范围|
|---|---|
|`pl_core_cycles` / `pl_core_frame_ns`|新增观测：首算法输入接受→最后HLS结果首次有效，时钟来自配对实现；含流式停顿，另报input-starvation/output-backpressure，不等于无停顿算术耗时|
|`pl_drain_cycles` / `pl_drain_ns`|首输入接受→末输出握手，含最后输出等待，与core结束事件核对|
|`dma_transaction_ns`|板端recv.transfer之前→原recv.wait完成；往返与PL流式重叠，不能称纯搬运|
|`dma_mm2s_span_cycles` / `dma_s2mm_span_cycles`|可选标准监测：各方向首末数据握手/字节与停顿语义；未实现不能填值|
|`dma_loopback_transport_ns`|复用已测A0同尺寸/同驱动/同配置独立无医学算法loopback测速；新采集，不重建或以相减估计|
|`input_prepare_ns` / `config_ns` / `cpu_snapshot_ns`|板端读/预处理/打包、实际配置提交和完成输出复制分别记录|
|`inference_ns`|准备好输入配置提交前→真实输出原等待完成并取得CPU快照，不含GT参考|
|`pipeline_ns`|本次图像读取开始→真实输出快照，缓存输入组/SD读入组分开|
|`postprocess_ns` / `encode_ns` / `export_ns`|PS解包/评价、编码、归档分别记录，不写成PL时间|
|`browser_request_to_render_ms`|同浏览器performance.now：操作/发请求→当前全部图像解码/Canvas绘制后双rAF完成标记，含队列/网络/服务，是绘制近似|
|`browser_receive_to_render_ms`|同客户端收到当前结果体→解码/绘制完成标记，识别前端耗时|

CPU参考另记环境与同输入/算法/阈值/输出范围，不能填入PL字段。PS用perf_counter_ns，浏览器用performance.now，二者绝对值不能相减。双rAF为可复现完成近似，不是测到物理像素点亮；精确光学延迟另需独立观测。依据 [MDN计时](https://developer.mozilla.org/en-US/docs/Web/API/Performance/now)及[rAF说明](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)。

帧率是指定范围实际完成唯一帧数/单调循环时间，核心/推理/服务完整循环/浏览器新帧显示率分别报。重绘同图、轮询或60Hz rAF不增加算法帧数。统计附原样本/预热/mean/median/p95/重复组/错误率，重叠窗口不相加，不以总时间减核心制造纯DMA值。

W3新增 `observer_readback_ns` 为快照结束后的GPIO观测读取；推理截至CPU快照，原始保存从观测结束后开始，分段不重叠。核心时间保持独立重叠范围。连续FPS组锁定同一config ID；切参数终止旧组。输入阈值编辑即时标旧结果为过期，新的浏览器计时响应也须匹配当前选择版本。


## W4a 增量传输与计时契约

W4a请求在W3字段外增加必需 `png_profile=baseline|fast`，属于PS展示参数并计入config ID；不占用PL控制位。baseline调用Pillow默认PNG保存，fast只传 `compress_level=1`，始终保持原尺寸uint8灰度/RGB无损像素。切方案仍创建新PL任务，旧结果标过期且清除旧指标；不会只返回已有图片。

每张PNG保留 `encoding_details`：profile/options/shape/dtype/mode/bytes，四个原始单调纳秒边界以及fromarray/save/file_hash耗时。新增汇总 `array_decode_overlay_ns`、`png_fromarray_ns`、`png_save_ns`、`png_file_hash_ns`、`file_inventory_hash_ns`。原 `png_encoding_ns` 大窗口保留，不能再把大窗口或save窗口称纯压缩。

按钮一次运行3新帧预热再20新帧计时；预热记录独立保存、没有loop_id/FPS，计时组具有独立loop_id且锁定完整config ID。两组按默认/fast分开；混组、缺预热或隐藏页面不得判有效比较。下载独立核对两个profile的实际输出和解码PNG，允许PNG文件压缩字节不同。此实验不改变正式性能100帧和三配置三复测设计。
