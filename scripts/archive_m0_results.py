"""Archive real CPU evaluation evidence, with hashes; never mark FPGA PASS."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = json.loads((args.evaluation / "evaluation.json").read_text())
    if report["status"] != "PASS_CPU_REFERENCE_EVALUATION_ONLY_NOT_FPGA":
        raise ValueError("Unexpected evaluation state")
    for name, expected in report["source_files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Evaluation source changed: " + name)
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in ("evaluation.json", "metrics.csv", "training_thresholds.json"):
        target = args.destination / name
        if target.exists():
            raise ValueError("Refusing to overwrite archived evidence")
        shutil.copyfile(args.evaluation / name, target)
    shutil.copyfile(ROOT / "data/raw/stare/download_manifest.json", args.destination / "dataset_download_manifest.json")
    rows = list(csv.DictReader((args.destination / "metrics.csv").open(encoding="utf-8")))
    assert len(rows) == 320
    assert set(report["split"]["train"]).isdisjoint(report["split"]["heldout"])
    table = ["|分辨率|算法|分组|标注|阈值|Dice|IoU|Precision|Recall|",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in report["summary"]:
        table.append(f'|{s["size"]}|{s["algorithm"]}|{s["split"]}|{s["observer"]}|{s["threshold"]}|'
                     + "|".join(f'{s["macro_" + metric]:.6f}' for metric in ("dice", "iou", "precision", "recall")) + "|")
    full_table = ["|512 留出集|标注|全图 macro Dice|全图 macro IoU|", "|---|---|---|---|"]
    for alg in ("A", "B"):
        for observer in ("ah", "vk"):
            group = [r for r in rows if (r["size"], r["algorithm"], r["split"], r["observer"], r["region"])
                     == ("512", alg, "heldout", observer, "full_image")]
            full_table.append(f'|{alg}|{observer}|{sum(float(r["dice"]) for r in group) / len(group):.6f}|'
                              f'{sum(float(r["iou"]) for r in group) / len(group):.6f}|')
    text = """# M0：真实 STARE 定点参考评价

状态：**CPU 参考评价完成；不是 FPGA 分割输出，不是板级算法通过，不是实时性能测试。**

来源为 [Clemson STARE 血管实验页](https://cecas.clemson.edu/~ahoover/stare/probing/index.html)，原始数据包、下载与成员哈希可核对。20 张原图与 AH/VK 标注均成功读取；256 和 512 两种等比例补边处理完成。

按样本名排序交替划分 10 张训练、10 张留出，名单见 evaluation.json。阈值仅使用训练组 AH 标注，搜索 4…128、步长 4；并列选较小阈值。算法选择仅使用 512 训练 AH macro Dice：B 必须超过 A 大于 0.01 才采用，否则选择成本较小的 A。VK 与留出组均不参与选择。

**实际选择 A；512 与 256 的阈值均为 28。** B 的阈值分别为 36 和 48。参数已冻结；留出集不用于后续反复调参，修改算法时需明确重新制定验证方案。

以下是每图指标再平均的 macro 值，评价区域为 RGB 生成的 FOV。GT 不进入 FOV 生成、像素打包或算法接口。FOV 收缩可能排除边缘标注，因此同时保留全图评价及每图的 FOV 外 AH/VK 像素数量。

""" + "\n".join(table) + "\n\n" + "\n".join(full_table) + """

## 质量限制

512 留出组 A/AH Dice 约 0.538，B 约 0.457；两者都有漏检和假阳性。B 的四个方向及固定尺度未带来整体收益，不能宣称高精度、诊断能力或已有稳定完整分割器。实际预览中的视盘、病灶和视网膜边界有假阳性。A 与 B 的留出最差样本均为 im0004，详见 metrics.csv。

FOV 使用 RGB 最大通道 >20、最大八连通区域、填孔，补边后 7×7 腐蚀；定义及被排除标注数量可由 evaluation.json 重现。默认采用 512；256 是调试模式，不视为相同质量。软件耗时仅记录 CPU 特征计算，不换算为 PL FPS。

## 复现及数值边界

主机虚拟环境与固定依赖见 requirements.txt；板端继续使用官方镜像依赖。运行 `python -m unittest discover -s tests -v`，再用 `python scripts/evaluate_stare.py --output build/m0_stare_NEW`；输出目录必须新建。最后用 archive_m0_results.py 保存报告。算法细节见 docs/algorithm_reference.md。

本次最终 15 项主机测试通过，涵盖原 A0 测试器的 6 项错误处理与 9 项定点/几何/标签隔离检查，真实输出在 host_tests_final.log。旧日志保留用于追踪开发过程。

当前工作目录 build/m0_stare_02 包含处理后的 NPZ、80 张掩膜及带 CPU 标识的预览，原数据不提交 Git。报告 source_files 记录实际运行的四个实现文件哈希；archive_manifest.json 记录归档证据哈希。原始文件许可与来源见 data/README.md。
"""
    (args.destination / "evaluation_report.md").write_text(text, encoding="utf-8")
    manifest = {"status": "ARCHIVED_CPU_EVIDENCE_ONLY", "files": {
        p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in args.destination.iterdir() if p.is_file() and p.name != "archive_manifest.json"}}
    (args.destination / "archive_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("M0_CPU_EVIDENCE_ARCHIVED")


if __name__ == "__main__":
    main()
