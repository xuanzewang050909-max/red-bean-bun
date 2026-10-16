# A4 完整定点血管分割：开发前复用审查

2026-10-12。基线A3实体板45帧已通过并归档。本审查先冻结数值与复用方案，再运行真实工具验证；现已完成A4主机及实体板61帧验证，原发布的NOT_RUN作为历史值保留。

## 已查候选与选择

读取本机Vivado/HLS2017.4实际安装头文件。Threshold二值模式比较是“>”，因此固定阈值27、maxval=1，逐位实现已选算法A的response>=28。先与输入RGB生成的FOV相与。

便捷Dilate/Erode接口在该版本固定BORDER_REPLICATE，不能直接满足M0闭运算图像外补0。原库morp_opr可选择BORDER_CONSTANT，其filter_opr特化fillvalue=0；直接使用未修改的dilate_kernel/erode_kernel、3×3十字和单次迭代。此内部入口与2017.4绑定，未来迁移须重新验证；不改安装头、不复制厂商行缓存。

孤立点清理用未修改Filter2D<BORDER_REPLICATE>的3×3全1整数核，输入为0/1，输出计数0..9。中心closed与count>=2及最终FOV相与。项目只组合医用判断、诊断字节和中心延迟；PS/DDR/HP0/DMA/FIFO/GPIO/reset/100MHz/帧guard和PYNQ驱动沿用已测A3。

xfOpenCV2017.4_release阈值/形态学已有候选，版本与边界/图像入口需适配；同版HLS已具备精确操作，无需引入新框架。Vitis Vision需另配工具，当前暂缓。没有使用人工血管GT作为运行输入，也不重选训练阈值。

## 冻结的模式与算法

输入低→高四字节仍为B/G/R/FOV(0或1)，完整256²/512²帧。所有模式均计算整条G→3×3高斯→固定LUT→15×15背景→饱和响应→阈值与FOV→十字膨胀→十字腐蚀→邻域清理→最终FOV流水线。

|模式|输出低→高四字节|
|---|---|
|0|原B/G/R/FOV原样旁路|
|1|原G/增强值/初始mask(0或255)/响应|
|2|原G/增强值/十字闭运算mask(0或255)/响应|
|3|原G/增强值/最终mask(0或255)/响应|

GPIO bits1:0为模式，bit2为256/512；首个接受像素锁存。阈值固定28，与M0训练选择一致。模式2可在FOV边缘扩展；模式3最终FOV外mask必须为0。响应始终保留原A3值。mask中间操作用0/1，显示字节映射为0/255。

## 验证门槛

先做独立C仿真：九点高斯、225点直接均值、布尔十字和邻域参考；重点检查阈值边界、图像四边补零、中心对齐、FOV全0/全1、暗点与断线。实际生成RTL再检查256/512、全部模式、真实STARE、随机背压、连续帧、配置锁存、畸形完整帧和在途复位恢复。最后完整100MHz布局布线、DRC/资源/HWH/厂商reset与软件故障保留检查。

发布配对bit/HWH/固定脚本/Notebook代码契约，不把主机PASS提升为板测、FPS或医学质量。最终B仍需算法与官方VDMA/HDMI同一bitstream。原始失败与来源diff保留，A0/A1/A2/A3固定发布均不修改。安装库哈希见results/a4_segmentation_2017_4/reuse_evidence.json，专有头不分发；PYNQ许可及嵌入OpenCV声明沿用此前使用说明。

## 实际编译及缓冲审查补充

2017.4综合实际读取common/technology/autopilot头；它与最初include审查目录的imgproc实现哈希不同，两者分别记录，未改安装库。形态学枚举的imgbase头在综合后另记于compiled_header_supplement.json，明确标注捕获阶段，原始开发前审查记录保留。

morp_opr<CROSS,1>会使旧版编译器对未执行的ITERATIONS>=2模板分支发出internal[-1]警告。常量ITERATIONS=1实际走单次filter_opr，不进入迭代分支；0/27/28/255阈值和常数全1图零边界腐蚀已有直接原语探针，再以整帧Csim及实际生成RTL验证选定路径。没有为了消除警告修改专有头文件。

第一次生成RTL测试的256帧通过，第一幅512帧在输入7476、输出0处停住。诊断显示aligned_closed深度1024已满，邻域Filter2D尚未产生输出。此版本撤回，不交付。Csim的无界流不能证明有限FIFO无死锁；实际RTL验证是必要门槛。

仅将项目aligned_closed容量提高至2048，容纳512宽复制边界窗口的两行及预热余量，重新生成a4_hls_02、a4_axis_sim_02和a4_segmentation_02。aligned_initial保持2048；原A3背景中心延迟和PS/DDR/DMA/时钟/复位等不变。测试台加入10000周期无输入/输出进展的失败检查，保留原失败及独立诊断日志；完整最终结果以构建报告和发布清单为准。正确第二次版本的实体板61帧现已通过独立归档。

最终第二次构建完成：Csim16帧2,031,616字、真实生成RTL17完整用例1,900,544字、标准复位/HWH及100MHz完整实现通过；WNS1.170/WHS0.020ns，6,636 LUT/7,293 FF/36 BRAM Tile/1 DSP。87项主机回归、16项组装包校验和17组最终派生源复现通过；六份实际编译库头未变，57个生成Verilog/ROM与IP包同哈希，十个复用BD模块与已测A3一致。十二文件发布包及真实警告处置见[构建报告](../results/a4_segmentation_2017_4/build_report.md)和[DRC审查](../results/a4_segmentation_2017_4/drc_review.md)。实体板61帧已完成，9,895,936字记录哈希与六份真实输出983,040字独立核验一致；26项归档检查通过，真实结果见[A4板测报告](../results/a4_segmentation_2017_4/board_execution_2026-10-12/verification_report.md)。原[操作步骤](a4_segmentation_validation_steps.md)与固定包保持不变。
