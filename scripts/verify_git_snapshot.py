"""Verify that the Git index retains every original reference with exact bytes."""
from __future__ import annotations
import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]

def main():
    entries = subprocess.check_output(["git", "ls-files", "-s", "-z"], cwd=ROOT).split(b"\0")
    index = {}
    for entry in entries:
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, object_id, stage = metadata.split()
        assert stage == b"0", "Unmerged index"
        index[path.decode("utf-8")] = object_id.decode("ascii")
    targets = {}
    for manifest in [*ROOT.glob("references/PYNQ/*/SOURCE_MANIFEST.json"), *ROOT.glob("references/xfopencv/*/SOURCE_MANIFEST.json")]:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for item in data["files"]:
            relative = (manifest.parent / item["path"]).relative_to(ROOT).as_posix()
            targets[relative] = item["sha256"]
    for item in json.loads((ROOT / "references/board/download_manifest.json").read_text(encoding="utf-8")):
        if item["result"] == "downloaded":
            targets[f"references/board/{item['file']}"] = item["sha256"]
    taskbook = ROOT / "docs/original_development_task.md"
    targets[taskbook.relative_to(ROOT).as_posix()] = hashlib.sha256(taskbook.read_bytes()).hexdigest()
    wanted = {}
    for relative, digest in targets.items():
        assert relative in index, f"Original missing from Git: {relative}"
        object_id = index[relative]
        if object_id in wanted:
            assert wanted[object_id] == digest, f"Different originals normalized into the same Git object: {relative}"
        wanted[object_id] = digest
    object_ids = list(wanted)
    result = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                            input=("\n".join(object_ids) + "\n").encode("ascii"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    output = result.stdout
    offset = 0
    for object_id in object_ids:
        end = output.index(b"\n", offset)
        actual_id, kind, size = output[offset:end].decode("ascii").split()
        assert actual_id == object_id and kind == "blob"
        start = end + 1
        finish = start + int(size)
        assert hashlib.sha256(memoryview(output)[start:finish]).hexdigest() == wanted[object_id], f"Git changed original: {object_id}"
        assert output[finish:finish + 1] == b"\n"
        offset = finish + 1
    assert offset == len(output)
    report = {"captured_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS_GIT_INDEX_EXACT_BYTES",
              "original_files_checked": len(targets), "unique_blobs_checked": len(wanted),
              "scope": "Pinned reference files, manufacturer archives/PDFs and original user taskbook; no hardware claim"}
    (ROOT / "results/audit/git_snapshot_verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
