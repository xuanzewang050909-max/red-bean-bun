# C7真实板结果独立复核（2026-10-15）

状态Q4D_REAL_PL_DATA_VERIFIED_EXPERIMENTAL_QUALITY_REVIEW_PENDING，质量未最终验收。原件保留在`build/board_results/q4d_quality_2026-10-15`，原始板上墙钟、发布NOT_RUN、quality_pass=false等历史值不改。

- ZIP：237272623字节，SHA256 bac5c69893f2e749cb4414b72551c948f0f2ea77efd4c1835e124abb93fe7bf0。
- 执行Notebook：21059字节，SHA256 489fc17f50e99bbb8d925dc6bbb484fae43d9559b756f1d5455698a591b11ace。
- 会话30039c7b4a97421fbbfbaf6a404ee6e1，194实际任务、35,127,296完整输出字、970PNG全部独立一致。160固定帧20图×两尺寸×A/C2/C5/C7顺序及请求配对通过，额外合法任务保留。
- 一次加载；导出时READY/IDLE、pending=0、error=None、retained_buffer_count=0，随后成功安全关闭。RQ71参数/标记/序号/周期、PNG内容/哈希、CSV与Notebook均核验。
- 三图C5/C7配对、C7阈值96/128及C5阈值20/36前台预览完整。3预热＋20计时前台循环完整，无隐藏帧，实际浏览器循环0.5931567506 FPS；这是本次诊断，不能当W4正式性能验收。
- 160固定队列的C7/512核心窗口平均3.039606ms，DMA事务平均5.05360795ms，完整推理平均27.06646275ms。DMA含流式计算，不是纯搬运；逐帧、分布及原始边界保留在verification.json。

C7真实输出符合冻结参考，故既有im0001亮带误检下降和im0324漏检退化均被实板重现。全20图×AH/VK、训练重代入/复用留出、两尺寸逐图指标全部在verification.json的quality.groups中。不能把实现一致称为全部图像质量改善；用户已要求继续提升细血管，并严格保护C7亮区误检水平。

下一阶段按docs/q4f_c8_plan.md和冻结有限协议进行亮区保护下的细血管恢复。旧模型/输出不修改、GT只评价，CPU模拟改善须经真实PL实现及新板测才能确认为新版本。原W4/W5和最终工程交付继续保留。
