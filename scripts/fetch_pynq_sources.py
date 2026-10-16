"""Preserve selected upstream files verbatim at explicit historical commits.

These are audit candidates, not a claim about the board's installed PYNQ version.
Use --tag to download one candidate. Never selects or tracks master.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import posixpath
import stat
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMITS = {
    "v2.2.1": "3d2641653c6d1a5ea55c4c41e15f9dd9a2e32ab3",
    "v3.0.1": "93ddd21ab623883590a8c8b07f0b157b2855da4b",
    "v3.1.2": "3c77124d86bab65ac7bb6beb0aa66e13c83508f2",
}
PREFIXES = (
    "boards/Pynq-Z2/", "boards/ip/", "boards/sw_repo/", "pynq/lib/",
    "pynq/pl_server/", "docs/source/overlay_design_methodology/",
    "docs/source/pynq_overlays/pynqz2/", "docs/source/pynq_libraries/dma",
    "docs/source/pynq_libraries/video", "docs/source/pynq_libraries/allocate",
)
FILES = {
    "LICENSE", "THIRD_PARTY_LIC", ".gitmodules", "README.md", "CITATION.cff",
    "sdbuild/Makefile", "pynq/lib/dma.py", "pynq/gpio.py", "pynq/buffer.py",
    "pynq/xlnk.py", "pynq/overlay.py", "pynq/mmio.py", "pynq/ps.py", "pynq/pl.py",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", choices=COMMITS, required=True)
    args = parser.parse_args()
    commit = COMMITS[args.tag]
    cache = ROOT / "references/cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"PYNQ-{commit}.zip"
    url = f"https://codeload.github.com/Xilinx/PYNQ/zip/{commit}"
    if not archive.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "RetinaFPGA-audit/1.0"})
        partial = archive.with_suffix(".partial")
        with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                size += len(chunk)
                if size % (10 * 1024 * 1024) == 0:
                    print(f"{args.tag}: downloaded {size // 1024 // 1024} MiB", flush=True)
        if not zipfile.is_zipfile(partial):
            raise ValueError("Not a GitHub source ZIP")
        partial.replace(archive)
    dest = ROOT / "references/PYNQ" / args.tag
    records = []
    with zipfile.ZipFile(archive) as z:
        entries = {item.filename.split("/", 1)[1]: item for item in z.infolist()
                   if not item.is_dir() and "/" in item.filename}
        pending = sorted(p for p in entries if p in FILES or p.startswith(PREFIXES))
        exported = set()
        while pending:
            relative = pending.pop(0)
            if relative in exported:
                continue
            exported.add(relative)
            item = entries[relative]
            target = (dest / relative).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("Unsafe archive path")
            data = z.read(item)
            if target.exists() and target.read_bytes() != data:
                raise FileExistsError(f"Refusing to overwrite changed original: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            record = {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if stat.S_ISLNK(item.external_attr >> 16):
                # Preserve the original link text as bytes on Windows, and
                # also preserve its canonical target. Shared Z1 notebooks are
                # Z2 upstream links, not substituted Z1 hardware/XDC designs.
                linked = posixpath.normpath(posixpath.join(posixpath.dirname(relative), data.decode("utf-8")))
                if linked.startswith("../") or linked.startswith("/"):
                    raise ValueError("Unsafe upstream symlink")
                record.update(kind="upstream_symlink_text", target=linked)
                if linked in entries:
                    pending.append(linked)
                else:
                    pending.extend(p for p in entries if p.startswith(linked + "/"))
            records.append(record)
    with archive.open("rb") as source:
        archive_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    metadata = {
        "repo": "https://github.com/Xilinx/PYNQ", "tag": args.tag, "commit": commit,
        "purpose": "Static reference audit; deployment baseline pending actual PYNQ image",
        "archive_url": url, "archive_sha256": archive_sha256,
        "accessed_utc": datetime.now(timezone.utc).isoformat(), "files": records,
    }
    (dest / "SOURCE_MANIFEST.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"{args.tag}: preserved {len(records)} files, {sum(r['bytes'] for r in records)/2**20:.2f} MiB", flush=True)


if __name__ == "__main__":
    main()
