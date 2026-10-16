"""Change only the computation IP in the board-verified A2 DMA design."""
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = (ROOT / "vivado/scripts/build_a2_gaussian.tcl").read_text(encoding="utf-8")
    new = original
    for before, after in (("a2_gaussian", "a3_background"), ("A2", "A3"),
                          ("a2_hls_01", "a3_hls_01"), ("retina_gaussian_hls", "retina_background_hls"),
                          ("gaussian_filter", "background_filter"), ("derive_a2_tcl.py", "derive_a3_tcl.py")):
        new = new.replace(before, after)
    new = new.replace("# Reused vendor Gaussian + frame guard; no segmentation/HDMI/programming.",
                      "# Reused Gaussian/BoxFilter and unchanged A2 guard; background/response only.")
    new = new.replace("A0/A1 baselines remain unchanged.", "A0/A1/A2 baselines remain unchanged.")
    new = new.replace("not board Gaussian PASS", "not board background/response PASS")
    for marker in ("retina_gaussian_guard", "background_filter/source_V_V", "background_filter/result_V_V",
                   "background_filter/ap_rst_n", "point_stage/hls_start", "offset 0x40400000", "offset 0x41200000"):
        if marker not in new:
            raise ValueError("Missing inherited connection: " + marker)
    target = ROOT / "vivado/scripts/build_a3_background.tcl"
    if target.exists():
        raise ValueError("Preserve the earlier derived script")
    target.write_text(new, encoding="utf-8", newline="\n")
    (ROOT / "results/a3_background_2017_4/a2_to_a3.diff").write_text("".join(difflib.unified_diff(
        original.splitlines(True), new.splitlines(True), fromfile="build_a2_gaussian.tcl", tofile=target.name)),
        encoding="utf-8", newline="\n")
    reset = (ROOT / "vivado/scripts/simulate_a2_reset.tcl").read_text(encoding="utf-8")
    (ROOT / "vivado/scripts/simulate_a3_reset.tcl").write_text(
        reset.replace("a2_gaussian", "a3_background").replace("A2", "A3"), encoding="utf-8", newline="\n")
    print("A3_DERIVED_FROM_BOARD_VERIFIED_A2; guard/PS/DDR/DMA/GPIO/FIFO/reset unchanged")


if __name__ == "__main__":
    main()
