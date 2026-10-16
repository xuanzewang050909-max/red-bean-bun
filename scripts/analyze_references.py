"""Static, reproducible inventory from pinned upstream Tcl and notebooks.

This reports source structure, not synthesis or a board-test pass. Original
snapshots are hash-verified before parsing; generated build copies are ignored.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAGS = ("v2.2.1", "v3.0.1", "v3.1.2")
FUNCTIONS = {
    "processing_system7": "Zynq PS、DDR/MIO、FCLK、GP/HP",
    "axi_interconnect": "AXI路由、宽度/时钟适配", "axi_protocol_converter": "AXI协议适配",
    "axi_vdma": "DDR与逐行视频流双向帧缓存", "axi_dma": "Trace采样流写DDR（非完整双向算法DMA）",
    "axi_gpio": "GPIO控制/状态", "proc_sys_reset": "复位同步与分发",
    "axi_dynclk": "可编程HDMI像素/5倍串行时钟", "rgb2dvi": "TMDS编码/串行输出",
    "dvi2rgb": "TMDS接收/解码、像素时钟恢复", "color_swap": "RGB通道重排",
    "color_convert": "可配置24位色彩矩阵", "pixel_pack": "24位视频打包到32位内存流",
    "pixel_unpack": "32位内存流解包到24位视频", "axis_register_slice": "AXIS握手流水级",
    "v_axi4s_vid_out": "AXIS到并行视频、FIFO与跨时钟", "v_vid_in_axi4s": "并行视频到AXIS",
    "v_tc": "视频时序发生/检测", "xlconcat": "位向量/中断拼接", "xlslice": "位向量选择",
    "microblaze": "外设IO处理器", "blk_mem_gen": "IOP程序/数据BRAM",
    "lmb_bram_if_cntlr": "MicroBlaze本地BRAM接口", "lmb_v10": "MicroBlaze本地存储总线",
    "axi_bram_ctrl": "PS访问IOP BRAM", "axi_intc": "AXI中断控制器",
    "axi_timer": "IOP定时/PWM", "axi_quad_spi": "IOP SPI", "axi_iic": "IOP I2C",
    "axi_uartlite": "IOP串口", "clk_wiz": "音频或局部时钟生成",
    "mdm": "MicroBlaze调试", "axis_data_fifo": "AXIS Trace缓冲",
    "trace_cntrl_32": "32位Trace触发/采样", "trace_cntrl_64": "64位Trace触发/采样",
    "audio_codec_ctrl": "音频编解码控制", "xadc_wiz": "Arduino模拟输入采样",
    "address_remap": "现代Base地址转换",
    "xlconstant": "常量驱动", "dff_en_reset_vector": "IOP输出带使能/复位寄存器",
    "io_switch": "IOP扩展IO路由选择", "interface_slice": "扩展接口位段选择",
    "mux_vector": "共享扩展IO多路选择", "wire_distributor": "扩展IO位向量路由",
}

def verify_sources():
    verified = []
    for tag in TAGS:
        folder = ROOT / "references/PYNQ" / tag
        manifest = json.loads((folder / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            data = (folder / item["path"]).read_bytes()
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Changed original: {tag}/{item['path']}")
        verified.append({"tag": tag, "commit": manifest["commit"], "verified_files": len(manifest["files"])})
    return verified

def parse_design(tag):
    relative = "boards/Pynq-Z2/base/base.tcl"
    source = (ROOT / "references/PYNQ" / tag / relative).read_text(encoding="utf-8")
    procs = list(re.finditer(r"(?m)^proc (create_hier_cell_\w+|create_root_design) \{[^\n]*\} \{", source))
    definitions = {}
    for i, match in enumerate(procs):
        end = procs[i + 1].start() if i + 1 < len(procs) else len(source)
        definitions[match.group(1)] = (source[match.end():end], source[:match.end()].count("\n") + 1)
    cells = []
    def walk(proc, parent):
        body, first_line = definitions[proc]
        settings = {}
        for entry in re.finditer(r"set_property -dict \[\s*list\s+([\s\S]*?)\]\s+\$(\w+)", body):
            settings[entry.group(2)] = dict(re.findall(r"CONFIG\.([\w.]+)\s+\{([^}]*)\}", entry.group(1)))
        for entry in re.finditer(r"set_property CONFIG\.([\w.]+) \{([^}]*)\} \$(\w+)", body):
            key, value, variable = entry.groups()
            settings.setdefault(variable, {})[key] = value
        for match in re.finditer(r"set (\w+) \[\s*create_bd_cell -type ip -vlnv ([^\s]+) ([^\s\]]+)\s*\]", body):
            var, vlnv, name = match.groups()
            interface_ports, signal_ports, clocks = set(), set(), {}
            for line in body.splitlines():
                if line.strip().startswith("connect_bd_intf_net"):
                    for port in re.findall(r"\[get_bd_intf_pins ([^\]]+)\]", line):
                        if port.startswith(name + "/"):
                            interface_ports.add(port.split("/", 1)[1])
                if line.strip().startswith("connect_bd_net"):
                    pins = re.findall(r"\[get_bd_pins ([^\]]+)\]", line)
                    signal_ports.update(pin.split("/", 1)[1] for pin in pins if pin.startswith(name + "/"))
                    net_match = re.search(r"-net (\S+)", line)
                    for pin in pins:
                        if pin.startswith(name + "/") and re.search(r"clk|aclk", pin, re.I):
                            peers = [p for p in pins if "/" not in p or p.startswith("ps7_0/FCLK")]
                            clocks[pin.split("/", 1)[1]] = peers or ([net_match.group(1)] if net_match else [])
            cells.append({"instance": "/".join(p for p in (parent, name) if p), "vlnv": vlnv,
                          "properties": settings.get(var, {}), "interfaces": sorted(interface_ports), "signal_ports": sorted(signal_ports),
                          "clock_connections": clocks, "source_line": first_line + body[:match.start()].count("\n")})
        for child in re.finditer(r"(?m)^\s*(create_hier_cell_\w+) (?:\$(?:hier_obj|parentObj)|\[current_bd_instance \.\]) (\w+)\s*$", body):
            walk(child.group(1), "/".join(p for p in (parent, child.group(2)) if p))
    walk("create_root_design", "")
    assert len({c["instance"] for c in cells}) == len(cells), "Duplicate scoped IP"
    addresses = []
    for match in re.finditer(r"create_bd_addr_seg -range (\S+) -offset (\S+) \[get_bd_addr_spaces ([^\]]+)\] \[get_bd_addr_segs ([^\]]+)\] (\S+)", source):
        span, offset, master, slave, segment = match.groups()
        addresses.append(dict(range=span, offset=offset, master=master, slave=slave, segment=segment))
    for match in re.finditer(r"assign_bd_address -offset (\S+) -range (\S+) (?:-with_name (\S+) )?-target_address_space \[get_bd_addr_spaces ([^\]]+)\] \[get_bd_addr_segs ([^\]]+)\]", source):
        offset, span, segment, master, slave = match.groups()
        addresses.append(dict(range=span, offset=offset, master=master, slave=slave, segment=segment))
    version = re.search(r"set scripts_vivado_version ([\w.]+)", source)
    return {"tag": tag, "vivado_version": version.group(1), "source": relative,
            "scope": "static Tcl structure, no executed or measured overlay claim", "ips": sorted(cells, key=lambda c:c["instance"]),
            "address_segments": addresses}

def disposition(cell):
    name = cell["instance"]
    if name.startswith(("iop_", "trace_", "concat_subblock_for_analyzers", "mb_iop_")) or "audio" in name or name in {"clk_wiz_10MHz", "mdm_1", "iop_interrupts", "pmoda_rp_pin_sel", "concat_pmodb", "concat_rp", "slice_pmodb_gpio", "constant_8bit_0"}:
        return "拟删除", "本项目不用扩展IO/Trace/音频；先通过原始Base验证再删除"
    if name.startswith("video/hdmi_in/") or name == "video/proc_sys_reset_pixelclk":
        return "首版保留，后评估删除", "保持原驱动与复位依赖；RX不是医学文件输入所必需"
    if name in {"ps7_0", "leds_gpio", "btns_gpio", "switches_gpio", "rgbleds_gpio"}:
        return "保留", "复用板级配置或交互控制；PS新增算法HP通路时只作必要修改"
    return "保留或缩减连接", "维持官方视频/AXI/时钟复位；按删除分支调整端口与中断"

def write_inventory(designs):
    lines = ["# 官方Base Overlay逐IP审查清单", "", "由 `scripts/analyze_references.py` 从固定Commit的Tcl生成。这里列出每个实例的来源/版本、接口、时钟网络和处置理由；接口为源码连接中实际出现的端口，未连接的IP内部端口不据此推定。时钟栏是本层连接，频率由 `base_overlay_analysis.md` 的跨层映射解释。", "", "资源成本未取得完整综合报告的实例统一标为‘待综合’，不能用此清单计算真实节省量。HLS局部估计见结构分析，不能相加后冒充最终布局布线占用。", ""]
    for design in designs:
        if design["tag"] == "v3.0.1":
            continue
        lines += [f"## {design['tag']} / Vivado {design['vivado_version']}（{len(design['ips'])}个IP实例）", "", "|实例|来源和版本 / 功能|输入输出接口|时钟连接|资源成本|处置及理由|", "|---|---|---|---|---|---|"]
        for cell in design["ips"]:
            kind = cell["vlnv"].split(":")[2]
            function = FUNCTIONS.get(kind, "官方IO辅助/布线逻辑；参数与端口见JSON清单")
            keep, reason = disposition(cell)
            clock = "; ".join(f"{pin}←{','.join(peers)}" for pin,peers in cell["clock_connections"].items()) or "无独立时钟或未在本层连接"
            interfaces = ', '.join(cell['interfaces']) or '无总线接口连接'
            signals = ', '.join(cell['signal_ports']) or '无逐引脚连接'
            lines.append(f"|`{cell['instance']}`|`{cell['vlnv']}`<br>{function}|总线：{interfaces}<br>引脚：{signals}|{clock}|待完整综合|{keep}：{reason}|")
        lines.append("")
    (ROOT / "docs/base_ip_inventory.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

def notebooks():
    records = []
    for tag in TAGS:
        folder = ROOT / "references/PYNQ" / tag
        for path in sorted((folder / "boards/Pynq-Z2/base/notebooks").rglob("*.ipynb")):
            if not ("/video/" in path.as_posix() or path.name == "board_btns_leds.ipynb"):
                continue
            actual = path
            text = actual.read_text(encoding="utf-8").strip()
            if not text.startswith("{"):
                actual = (path.parent / text).resolve()
                if not actual.is_relative_to(folder.resolve()):
                    raise ValueError("Notebook link escapes snapshot")
                text = actual.read_text(encoding="utf-8")
            nb = json.loads(text)
            code = "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []) if c["cell_type"] == "code")
            records.append({"tag": tag, "path": path.relative_to(folder).as_posix(),
                            "canonical_source": actual.relative_to(folder).as_posix(),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "opencv_cpu_functions": sorted(set(re.findall(r"cv2\.(\w+)\(", code))),
                            "status": "Preserved original only; NOT executed locally; waiting for board"})
    return records

def main():
    verified = verify_sources()
    designs = [parse_design(tag) for tag in TAGS]
    output = ROOT / "results/audit"
    for name, data in (("source_verification.json", verified), ("base_inventory.json", designs), ("notebook_inventory.json", notebooks())):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_inventory(designs)
    for design in designs:
        print(f"{design['tag']}: Vivado {design['vivado_version']}, {len(design['ips'])} IPs, {len(design['address_segments'])} address segments")
    print(f"Hash verification passed for {sum(v['verified_files'] for v in verified)} upstream files")

if __name__ == "__main__":
    main()
