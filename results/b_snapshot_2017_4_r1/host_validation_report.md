# B 输出暂存 r1：主机验证和实体板对比交付

2026-10-12：29项主机检查通过，无跳过，22文件/7代码框包已组装。本轮板测 **NOT_RUN**、改善 **NOT_MEASURED**。原缓存版的5.016FPS、排版105.156ms和核验/哈希70.830ms属于上次真实数据，不能作为本轮测量或先宣称快于直接读。

本轮只在原官方接收wait完成之后进行一次np.copyto，把262,144个packed uint32复制到复用的1MiB普通CPU数组；接收之间只读，返回存储借用至下次capture。原DMA接收缓冲始终由原分配器和驱动管理、按原wait完成失效操作；CPU类不调用任何flush/invalidate/freebuffer/allocate/newframe/writeframe/mmap，也不改变缓存/映射策略。两组使用同一已测CachedCanvas和算法缓冲对，保留完整每字比较、字节数、FPGA计数、每帧黄金哈希、原生帧分配/复制/刷新/中断等待/提交与视频状态。

CPU复制成本单独增加为第2段，12个原始边界计算11段耗时，总和严格等于每帧时间；每组3预热排除，30计时帧完整循环包含复制、检查和簿记成本。直接组只选择原DMA数组视图，没有复制；候选组每帧复制一次。整体FPS比较包含复制成本，不能只拿候选排版或比较单项的减少宣称整机改善。两组按direct→snapshot固定顺序运行，输入为固定STARE。

29项检查覆盖所有随机32位数据、源不变/不共享内存、存储复用/每次全量刷新、借用数据只读、格式/别名/非法目标拒绝、复制异常仍恢复只读、无原生源修改操作。上次下载的真实数组原SHA相同，262,144字与SHA直接一致，在0、29、99、100、-1标记处整幅921,600像素逐一一致，见[pixel_equivalence_verification.json](pixel_equivalence_verification.json)。这是主机上的实际数组检查，不代表新实时DMA策略已板测。

合成驱动检查同一工程下68个算法帧和34次CPU捕获（1次门禁+候选33帧）、原接收wait后复制、同一算法缓冲对复用于两组，全部样本/字节/计数/黄金哈希一致。每帧11段精确加总，源选择0成本合法，DMA零/逆序/重叠/篡改簿记拒绝。四份raw数组及两份最终图像一致；原生帧提交后不手动释放，各帧仍由原写入口刷新一次。DMA/字节/计数、CPU副本、核验后数据改变、视频/地址、时钟/其他Overlay等错误不能继续打包或释放可能在途引用。合成计时不计作实体板证据。第一次探测因测试替身缺invalidate接口出错，已以明确mock接口补齐，运行时未改变，失败日志保留。

源复核原布局包18文件原字节不变，13条原生DMA/显示操作AST顺序及原生帧复制语句一致，选择CPU副本位于原接收wait之后；新源仅增复制路径/独立时间段/哈希保护/记录，受控循环diff见[source_reuse_verification.json](source_reuse_verification.json)。官方DMA/VDMA/视频层/缓冲源码仍匹配固定PYNQ3.0.1源清单，未重建硬件。cacheable属性在原PynqBuffer中由coherent推导，不用该属性推断内核页映射或收益。

包目录`D:\PLD\retina_fpga\build\deploy\b_snapshot_2017_4_r1`，新建retina_b_snapshot_r1并按[完整7框步骤](../../docs/b_snapshot_compare_steps.md)执行。第5框核对实际DMA/CPU复制的每字、哈希和4标记全幅图像，保存两份原数组；第6框测两组，另存两份最终原数组；第7框打包10个结果文件并关闭原生显示。下载执行Notebook和b_snapshot_bundle.zip，再独立复核新数据。

源/包/三Notebook自动保存与代码修改边界证据：[29项日志](host_tests.log)、[受测源与初次错误说明](host_test_sources.json)、[初次替身错误日志](host_tests_first_probe_failed.log)、[像素证明](pixel_equivalence_verification.json)、[包验证](package_validation.json)、[发布清单](release_manifest.json)。没有新的SD端到端、纯PL周期、CPU算法比较、扫描频率、临床或完整性能接受结论。
