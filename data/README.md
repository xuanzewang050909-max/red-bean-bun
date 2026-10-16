# STARE 本地数据

原始来源：[Clemson STARE 血管实验页面](https://cecas.clemson.edu/~ahoover/stare/probing/index.html)。本机已取得 20 张 700×605 RGB 图像及 AH、VK 两套人工标注；原始 tar、索引页及 URL/下载时间/SHA256 清单保存在 `data/raw/stare/`。

公开下载不等于具有再分发许可。原始页未核实到明确的开源数据许可，因此原始图像、标注及下载包仅供本地研究，不提交 Git；对外发布数据或派生图片前仍需核对数据使用条件。来源要求引用 Hoover、Kouznetsova、Goldbaum 的 *Locating Blood Vessels in Retinal Images by Piecewise Threshold Probing of a Matched Filter Response*, IEEE Transactions on Medical Imaging, 19(3), 203–210, 2000。

下载：`powershell -File scripts/fetch_stare.ps1`。使用 Windows 系统证书验证，不关闭 TLS 检查。压缩包只读取已验证的平面文件名，不把不可信 tar 路径解压到文件系统。

处理产物在 `build/m0_stare_02/`。NPZ 为离线评价容器，含 RGB、FOV、GT 和独立 `packed_input` 数组；GT 仅用于阈值训练与质量评价。FPGA 输入只允许取 `packed_input`，不可发送完整 NPZ 或 GT。`prepare_sample` 禁止标注覆盖 RGB 生成的 FOV，`pack_input` 只接受 RGB 与布尔 FOV。

板端继续使用镜像自带 NumPy/OpenCV，不把主机的 `requirements.txt` 安装到板端。
