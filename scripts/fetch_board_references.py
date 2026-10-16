"""Download unmodified manufacturer resources; retain provenance and SHA256."""
from __future__ import annotations

import hashlib
import json
import pathlib
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "references" / "board"
SOURCES = {
    "TUL_PYNQ_Schematic_R12.pdf": "https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf",
    "TUL_PYNQ_Schematic_R12_space.pdf": "https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ%20Schematic_R12.pdf",
    "pynqz2_user_manual_v1_0.pdf": "https://dpoauwgwqsy2x.cloudfront.net/Download/pynqz2_user_manual_v1_0.pdf",
    "pynq-z2_v1.0.xdc.zip": "https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2_v1.0.xdc.zip",
    "pynq-z2.zip": "https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2.zip",
}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for name, url in SOURCES.items():
        record = {"file": name, "source_url": url, "accessed_utc": datetime.now(timezone.utc).isoformat()}
        path = DEST / name
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "RetinaFPGA-reference-audit/1.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
                record.update(final_url=response.url, status=response.status)
            expected_magic = b"%PDF-" if name.endswith(".pdf") else b"PK"
            if not data.startswith(expected_magic):
                raise ValueError("Response is not the requested PDF/ZIP format")
            if path.exists() and path.read_bytes() != data:
                raise FileExistsError("Existing resource differs; refusing to overwrite original")
            path.write_bytes(data)
            if name.endswith(".zip"):
                folder = DEST / path.stem
                with zipfile.ZipFile(path) as archive:
                    for item in archive.infolist():
                        if item.is_dir():
                            continue
                        target = (folder / item.filename).resolve()
                        if not target.is_relative_to(folder.resolve()):
                            raise ValueError("Unsafe manufacturer archive path")
                        contents = archive.read(item)
                        if target.exists() and target.read_bytes() != contents:
                            raise FileExistsError("Extracted original differs; refusing overwrite")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(contents)
            record.update(result="downloaded", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        except Exception as exc:
            record.update(result="unavailable", error=f"{type(exc).__name__}: {exc}")
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
    (DEST / "download_manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
