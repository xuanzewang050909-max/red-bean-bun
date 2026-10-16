"""Read-only PYNQ-board inventory; never loads an overlay or reports a demo pass.

Copy to the board after it arrives. Run with its Python, not Windows Python.
PCB revision still requires checking the physical silkscreen.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import platform
import sys
from datetime import datetime, timezone

def read_text(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace").strip().strip("\x00")
    except OSError:
        return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("board_environment.json"))
    args = parser.parse_args()
    if sys.platform != "linux":
        raise SystemExit("This script must run on the Linux PYNQ board; it does not emulate board results on Windows")
    import pynq
    from pynq import PL
    spec = importlib.util.find_spec("pynq.overlays.base")
    base_files = []
    if spec is not None and spec.origin:
        folder = pathlib.Path(spec.origin).parent
        for suffix in ("*.bit", "*.hwh", "*.tcl"):
            for path in sorted(folder.glob(suffix)):
                with path.open("rb") as source:
                    digest = hashlib.sha256(source.read()).hexdigest()
                base_files.append({"path": str(path), "bytes": path.stat().st_size, "sha256": digest})
    current_ips = {}
    for name, description in PL.ip_dict.items():
        current_ips[name] = {key: description.get(key) for key in ("type", "phys_addr", "addr_range", "parameters")}
    memory_lines = read_text("/proc/meminfo") or ""
    report = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only metadata; no overlay load, GPIO toggle, HDMI or DMA test",
        "python_version": sys.version, "pynq_version": getattr(pynq, "__version__", None),
        "uname": platform.uname()._asdict(), "board_env": os.environ.get("BOARD"),
        "device_tree_model": read_text("/proc/device-tree/model"),
        "device_tree_compatible": read_text("/proc/device-tree/compatible"),
        "os_release": read_text("/etc/os-release"),
        "memtotal": next((line for line in memory_lines.splitlines() if line.startswith("MemTotal:")), None),
        "pcb_revision": None, "pcb_revision_status": "Check physical silkscreen; not inferred from Board Files",
        "installed_base_files": base_files, "currently_loaded_bitfile": getattr(PL, "bitfile_name", None),
        "currently_loaded_ip_dict": current_ips,
        "demo_status": "NOT_TESTED: environment collection does not prove a demo passed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(str(args.output))

if __name__ == "__main__":
    main()
