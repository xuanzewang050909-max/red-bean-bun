"""Check recorded A3 derivations against current sources without overwriting them."""
import argparse
import hashlib
import importlib
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve earlier verification")
    checks = []
    jobs = [("derive_a3_runner", ["scripts/a2_gaussian_board_test.py"], ["scripts/a3_background_board_test.py", "results/a3_background_2017_4/a2_to_a3_runner.diff"]),
            ("derive_a3_package", ["scripts/package_a2.py"], ["scripts/package_a3.py", "results/a3_background_2017_4/a2_to_a3_package.diff"]),
            ("derive_a3_tcl", ["vivado/scripts/build_a2_gaussian.tcl", "vivado/scripts/simulate_a2_reset.tcl"],
             ["vivado/scripts/build_a3_background.tcl", "vivado/scripts/simulate_a3_reset.tcl", "results/a3_background_2017_4/a2_to_a3.diff"])]
    for module_name, sources, targets in jobs:
        module = importlib.import_module(module_name)
        with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="a3_derive_check_") as temporary:
            staging = Path(temporary)
            (staging / "scripts").mkdir()
            (staging / "results/a3_background_2017_4").mkdir(parents=True)
            for source in sources:
                (staging / source).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, staging / source)
            saved_root = module.ROOT
            try:
                module.ROOT = staging
                module.main()
            finally:
                module.ROOT = saved_root
            for target in targets:
                actual = (ROOT / target).read_bytes()
                if actual != (staging / target).read_bytes():
                    raise ValueError("Derivation is not reproducible: " + target)
                checks.append({"file": target, "sha256": hashlib.sha256(actual).hexdigest(), "status": "PASS_EXACT_REPRODUCTION"})
    args.output.write_text(json.dumps({"status": "PASS_A3_DERIVATION_REPRODUCTION", "board_status": "NOT_RUN", "checks": checks}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A3_DERIVATION_REPRODUCTION_PASS", len(checks))


if __name__ == "__main__":
    main()
