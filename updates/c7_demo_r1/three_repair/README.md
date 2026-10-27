# 三图专项血管补标

固定输入 im0004 / im0291 / im0319，512×512。与STARE原始700×605 RGB的既有letterbox映射逐值一致；真实C7 M7来自已封存PL输出。本任务不打开GT、不训练、不评价其他图。

同一个有界整数核心，profile寄存器0/1/2分别选择三套显式参数。输入为RGB/FOV/旧M7；不输入文件名、GT、ROI或血管坐标。旧M7仅用于最终并集，不作为新增唯一种子。所有新图像运算在PL：3×3平滑、多方向/多尺度双侧暗线、强弱候选、方向支持、16次有界传播、9×9支持清理和合并。

Python软件入口（原环境，不升级）：

```powershell
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B three_repair/run_frozen.py --input <打包输入.npy> --profile 0 --output <新的结果.npz>
```

输入uint32：B[7:0]、G[15:8]、R[23:16]、FOV[24]、旧mask[25]；高6位为0。打包不是新增识别。原始C7输入中的bit24为FOV，旧mask从原C7输出[23:16]读取。

源代码：`reference.py`为有限滤波和视图函数；`candidates.py:decide_cached`为共同整数流程；`run_frozen.py`读取冻结参数。`hardware/repair.cpp`为相同运算HLS核，`geometry.hpp`只存有限滤波偏移，不含血管答案。

内部6个uint32平面各N字：输入、Q4平滑/安全域、响应/方向/强弱标志、活动ping、活动pong、最终结果。最终字bit0=final、bit1=added、bit2=uncertain。外加32个guard字，不计入capacity。N=262144，工作区6MiB+128字节；输入1MiB。中间缓存32×512个uint32。实际资源、周期和传输计数见最终硬件报告，不能据此声称板测完成。

阶段顺序0→1→2→3×16→4，共20次。只有op4成功并持久化、逐字校验后输出才有效。profile/尺寸在op0锁定，运行中更换会返回错误。错误码1=尺寸，2=容量/操作码，3=阶段，4=配置/帧身份。无自动重试或失败后清理板端缓冲。

离线构建入口：`hardware/build_hls.tcl`生成HLS与IP包装中间文件；2017.4已知时间戳revision溢出通过`package_ip.py`对新包装副本修复，原失败日志保留。`rtl_prepare.py`、`run_rtl.py`运行实际HLS RTL；`hardware/create_bd.tcl`生成真实50MHz系统，`integration_test.py`验证实际控制/DDR互连及生产复位链；`physical.py`仅在完整仿真回执存在后启动一次物理构建；`routed_reset_test.py`、`physical_gate.py`检查最终DCP；`release_bit.py`只在全部门禁通过后写位流。

所有构建目录必须为新目录，不覆盖旧工程。完整实际执行证据位于`results/three_repair_r1`。本任务物理构建上限3次，无板卡操作权限。Notebook第一代码格只解压，第二代码格只核验；第三代码格必须在另行获得本版本板测授权后手动执行，默认AUTHORIZED=False。

结果是三图专项视觉补标，不声称独立GT准确率或完美拓扑。保留原有错误标注；弱而不确定的区域另列。没有将背景放射状纹理全部涂成血管。历史失败状态不改变。
