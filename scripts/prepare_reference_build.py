"""Make a disposable build copy; verify and leave pinned originals untouched."""
from __future__ import annotations
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "references/PYNQ/v2.2.1"
DEST = ROOT / "build/official_v2.2.1"

def main():
    manifest = json.loads((SOURCE / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        data = (SOURCE / item["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Original modified: {item['path']}")
    if DEST.exists():
        raise FileExistsError(f"Build copy already exists: {DEST}; reuse it or archive it explicitly")
    for relative in ("boards/ip", "boards/Pynq-Z2/base"):
        shutil.copytree(SOURCE / relative, DEST / relative)
    (DEST / "BUILD_ORIGIN.json").write_text(json.dumps({
        "tag": manifest["tag"], "commit": manifest["commit"],
        "source_files_verified": len(manifest["files"]),
        "scope": "Original HLS IP rebuild and BD validation; no full overlay implementation or board test"
    }, indent=2) + "\n", encoding="utf-8")
    print(DEST)

if __name__ == "__main__":
    main()
