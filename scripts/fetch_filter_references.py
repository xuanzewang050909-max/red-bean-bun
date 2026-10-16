"""Pinned vendor filter candidates for static reuse review, not a board platform."""
from __future__ import annotations
import hashlib
import json
import pathlib
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = "6e6953c20dc12de828693d6ae34bbb9a9a55ac37"
TAG = "2017.4_release"
EXAMPLES = ("gaussianfilter", "boxfilter", "dilation", "erosion", "lut", "threshold", "customconv")

def main():
    archive = ROOT / "references/cache" / f"xfopencv-{COMMIT}.zip"
    url = f"https://codeload.github.com/Xilinx/xfopencv/zip/{COMMIT}"
    if not archive.exists():
        with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    destination = ROOT / "references/xfopencv" / TAG
    records = []
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if item.is_dir() or "/" not in item.filename:
                continue
            relative = item.filename.split("/", 1)[1]
            example = relative.startswith(tuple(f"examples/{name}/" for name in EXAMPLES)) and relative.endswith((".cpp", ".h", ".hpp", ".json", "Makefile"))
            if relative not in ("README.md", "LICENSE.txt", "include/README.md") and not relative.startswith("include/") and not example:
                continue
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive path")
            data = z.read(item)
            if target.exists() and target.read_bytes() != data:
                raise FileExistsError(f"Modified reference: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            records.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    manifest = {"repo": "https://github.com/Xilinx/xfopencv", "tag": TAG, "commit": COMMIT,
                "archive_url": url, "archive_sha256": digest, "accessed_utc": datetime.now(timezone.utc).isoformat(),
                "purpose": "Vendor filter candidate audit only; not synthesized or board-validated", "files": records}
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"xfOpenCV {TAG}: {len(records)} files preserved")

if __name__ == "__main__":
    main()
