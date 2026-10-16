"""Verify A3 release sources and inherited helpers against the Git index."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve earlier attestation")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    targets = dict(manifest["source_files"])
    for name, item in manifest["artifacts"].items():
        if name.endswith(".py"):
            targets["scripts/" + name] = item
    targets["notebooks/a3_background_check.ipynb"] = manifest["artifacts"]["a3_background_check.ipynb"]
    targets["docs/a3_background_validation_steps.md"] = manifest["artifacts"]["使用说明.txt"]
    files = {}
    for path, recorded in targets.items():
        working = (ROOT / path).read_bytes()
        if sha(working) != recorded["sha256"] or len(working) != recorded["bytes"]:
            raise ValueError("Changed released source: " + path)
        blob = subprocess.check_output(["git", "rev-parse", ":" + path], cwd=ROOT).decode().strip()
        indexed = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        comparison = "EXACT_BYTES"
        if indexed != working:
            if path != "scripts/a0_dma_board_test.py" or indexed != working.replace(b"\r\n", b"\n"):
                raise ValueError("Git index differs from released source: " + path)
            attrs = subprocess.check_output(["git", "check-attr", "text", "eol", "--", path], cwd=ROOT).decode()
            if "text: set" not in attrs or "eol: lf" not in attrs:
                raise ValueError("Inherited A0 line-ending transformation is not declared")
            comparison = "INHERITED_A0_CRLF_TO_DECLARED_LF_ONLY"
        files[path] = {"released_source_sha256": recorded["sha256"], "git_sha256": sha(indexed),
                       "comparison": comparison, "git_blob": blob}
    result = {"status": "PASS_GIT_RELEASE_SOURCE_AND_DECLARED_LINE_ENDINGS", "board_status": "NOT_RUN",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "parent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
              "release_manifest_sha256": sha(args.manifest.read_bytes()), "files": files}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A3_GIT_RELEASE_SOURCE_ATTESTATION_PASS", len(files), "files; board NOT_RUN")


if __name__ == "__main__":
    main()
