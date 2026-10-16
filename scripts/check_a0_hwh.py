"""Host-only metadata check with pinned official PYNQ 3.0.1 HWH parser.

Stub only pynq.ps architecture constants (no hardware access). The actual
parser source remains unchanged. Board Overlay/driver compatibility still
requires the real notebook run.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Import the frozen reference without generating files inside references/.
    sys.dont_write_bytecode = True
    argp = argparse.ArgumentParser()
    argp.add_argument("hwh", type=Path)
    argp.add_argument("--output", type=Path, required=True)
    args = argp.parse_args()
    architecture = types.ModuleType("pynq.ps")
    architecture.CPU_ARCH = architecture.ZYNQ_ARCH = "armv7l"
    architecture.ZU_ARCH = "aarch64"
    architecture.CPU_ARCH_IS_SUPPORTED = True
    sys.modules["pynq.ps"] = architecture
    parser_source = ROOT / "references/PYNQ/v3.0.1/pynq/pl_server/hwh_parser.py"
    spec = importlib.util.spec_from_file_location("official_hwh_parser", parser_source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parsed = module.HWH(hwh_name=str(args.hwh.resolve()))
    description = parsed.ip_dict["axi_dma_0"]
    expected = {"c_include_sg": 0, "c_micro_dma": 0, "c_include_mm2s": 1,
                "c_include_s2mm": 1, "c_sg_length_width": 23,
                "c_m_axi_mm2s_data_width": 64, "c_m_axi_s2mm_data_width": 32,
                "c_m_axis_mm2s_tdata_width": 32, "c_s_axis_s2mm_tdata_width": 32}
    assert description["type"] == "xilinx.com:ip:axi_dma:7.1"
    assert description["phys_addr"] == 0x40400000
    assert description["addr_range"] == 0x10000
    assert not description["interrupts"]
    for key, value in expected.items():
        assert int(description["parameters"][key]) == value, key
    tree = ET.parse(args.hwh)
    ps = tree.find(".//MODULE[@INSTANCE='ps7_0']")
    ps_params = {p.get("NAME"): p.get("VALUE") for p in ps.findall("./PARAMETERS/PARAMETER")}
    assert int(ps_params["PCW_DDR_RAM_HIGHADDR"], 0) == 0x1FFFFFFF
    assert float(ps_params["PCW_FPGA0_PERIPHERAL_FREQMHZ"]) == 100
    assert float(ps_params["PCW_M_AXI_GP0_FREQMHZ"]) == 100
    assert float(ps_params["PCW_S_AXI_HP0_FREQMHZ"]) == 100
    fifo = tree.find(".//MODULE[@INSTANCE='loopback_fifo']")
    fifo_params = {p.get("NAME"): p.get("VALUE") for p in fifo.findall("./PARAMETERS/PARAMETER")}
    assert int(fifo_params["HAS_TKEEP"]) == 1
    assert int(fifo_params["HAS_TLAST"]) == 1
    reset = tree.find(".//MODULE[@INSTANCE='reset_100m']")
    assert reset.find("./PARAMETERS/PARAMETER[@NAME='C_EXT_RESET_HIGH']").get("VALUE") == "0"
    assert reset.find("./PARAMETERS/PARAMETER[@NAME='C_AUX_RESET_HIGH']").get("VALUE") == "0"
    aux_port = reset.find("./PORTS/PORT[@NAME='aux_reset_in']")
    aux_connections = {(p.get('INSTANCE'), p.get('PORT')) for p in aux_port.findall('./CONNECTIONS/CONNECTION')}
    assert ('const_one', 'dout') in aux_connections, 'ACTIVE_LOW auxiliary reset must be tied HIGH'
    assert ('const_zero', 'dout') not in aux_connections, 'Auxiliary reset permanently asserted'
    result = {"status": "PASS_HOST_METADATA_ONLY", "board_test": "NOT_RUN",
              "hwh_sha256": hashlib.sha256(args.hwh.read_bytes()).hexdigest(),
              "parser_source": str(parser_source.relative_to(ROOT)),
              "parser_sha256": hashlib.sha256(parser_source.read_bytes()).hexdigest(),
              "architecture_stub": "pynq.ps constants only; original parser unchanged",
              "clock_dict": parsed.clock_dict, "ip_dict": parsed.ip_dict,
              "dma_parameters_checked": expected,
              "fifo_keep_last": True, "reset_active_low": True,
              "auxiliary_reset_active_low_tied_high": True,
              "ddr_high_address": "0x1FFFFFFF", "axi_frequency_mhz": 100}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PASS_HOST_METADATA_ONLY: PYNQ 3.0.1 HWH parser, DMA/clock/reset checks")


if __name__ == "__main__":
    main()
