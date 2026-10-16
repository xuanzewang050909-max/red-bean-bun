# 当前工作：C8 细血管恢复（2026-10-15）

C7 下载已独立核验，无需重跑。用户要求亮区严格不劣C7且改善细血管/连续性，直到可人工板测。当前**没有通过全部门禁的C8上传包**。

## 冻结算法与证据

- C8S_t184_n3_s8，选择299bb1d、模型2c56349。规格 `docs/q4f_recovery_pl_spec.md`，协议 `docs/q4f_board_protocol_r1.json`。
- 保留全部C7 T112种子；C8分数≥184、3×3支持≥3、8次有限传播。rawG 17×17最大≥192或FOV/图像边界8像素内不新增。原亮核/亮带逐像素等同C7；256严格固定T112 C7。保护区外仍有新增误检，不能宣称普遍消除。
- CPU20图×两尺寸×AH/VK通过，`build/q4f_frozen_audit_r10`、`results/q4f_recovery_2017_4_r1/verification.json`。im0324 AH Dice .503471→.574878、细代理+7.2977pp；VK .402693→.471545。原im0001亮带双标注阴性FP1007→1007，变化0。复用基准，非新外部/板测结果。

## 当前实现（15:15）

- 新候选HLS23：`build/q4f_recovery_hls_23`，私有树`build/q4f_tree_sources23`，现已把两个等价树函数采用到canonical。8树改分时选择，II=6、禁循环展平；ROM/数学/算法不变，无false-dependence豁免。HLS22/局部probe23、25因估计长路径未采用；probe24符合预算。
- full26=`build/q4f_recovery_full_26`，export23，默认控制集、Performance_ExplorePostRoutePhysOpt。100MHz完整路由 WNS +0.207ns、WHS +0.014ns，44,360LUT /49,109FF /135.5BRAM Tile /93DSP，bit/HWH已生成，但**完整RTL失败，不能发布**。
- Csim23独立20帧3,473,408字/30,600特征通过`build/q4f_csim_audit_23.json`；C5 Csim23三帧589,824字。四态600分数及在途复位通过`build/q4f_component_sim_23/audit.json`，full26厂商reset日志通过。
- main RTL23与C5 RTL23在首帧尾触发未改的10,000周期无进展门禁：256输出60,671/65,536，512输出252,415/262,144；不能把部分匹配当PASS。正在用`build/q4f_tail_probe_23`仅加信号观察的副本定位，DUT不改。
- 全局TB限时从2s修正到8s：HLS23像素迭代552周期，最多4帧×262144×600周期×10ns=6.30s；原逐字计分板和10,000周期停滞检查保留。修改在RTL执行前；证据`build/q4f_hls23_release_sources/validation_budget.json`，46文件快照。
- 原HLS21整帧/组件全部通过，但full24、full25持续严重拥塞后中止（不是时序失败/通过），日志与进程归属保留在`results/q4f_recovery_2017_4_r1/interrupted_full24_route`、`interrupted_full25_route`。旧源保留`build/q4f_compact_sources19`及21快照。更早容量/时序失败归档不变。

## 接续

1. 修复并重新验证实际帧尾停滞；审查完整RTL与实际实现，全部通过后实际vendor reset、警告审查、hardware audit及release selection；hardware audit用绝对路径。实现失败继续工程优化，算法冻结不变。
2. `scripts/check_q4f_release_evidence.py`绑定源码/私有来源、所选同一来源的Csim、RTL、组件及真实路由bit。通过才`package_q4f_quality.py --host-only`，执行39项不同检查与HOST浏览器视觉审查，再最终打包和3项配对复核（不同项仍39）。
3. `archive_q4f_host.py`归档，核对179旧文件未变，发布BOARD_NOT_RUN。
4. 更新草稿`docs/q4f_c8_board_steps.md`，交付两文件后在对话给7框步骤。固定200帧+33人工=233；三图C7/C8、四阈值和3预热+20前台。C8分时电路必须重测时延，不能沿用C7 3.040ms。

Jupyter9090，应用8090，IP192.168.2.99。历史按需查`docs/history/agents_2026-10-15_before_compaction.md`。
