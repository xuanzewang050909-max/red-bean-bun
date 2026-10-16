"""Prepared RGB/FOV input only; no vessel annotation enters A2 test vectors."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.preprocessing import read_archive, prepare_sample, pack_input
from software.reference import gaussian3, LUT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    rgb = read_archive(ROOT / "data/raw/stare/stare-images.tar", "")["im0001"]
    records = []
    for side, mode in ((256,2),(512,3)):
        prepared, aligned, geometry = prepare_sample(rgb["pixels"], {}, side)
        packed = pack_input(prepared, aligned["fov"])
        smooth = gaussian3(prepared[:,:,1])
        value = smooth if mode==2 else LUT[smooth]
        expected = prepared[:,:,1].astype(np.uint32) | (value.astype(np.uint32)<<8) | (aligned["fov"].astype(np.uint32)<<24)
        np.savetxt(args.destination / f"stare_{side}_input.hex", packed.reshape(-1), fmt="%08x")
        np.savetxt(args.destination / f"stare_{side}_expected.hex", expected.reshape(-1), fmt="%08x")
        np.save(args.destination / f"stare_im0001_{side}.npy", packed)
        records.append({"side":side,"mode":mode,"geometry":geometry,
                        "raw_rgb_member":rgb["member"],"raw_rgb_member_sha256":rgb["member_sha256"],
                        "input_sha256":hashlib.sha256(packed.astype("<u4").tobytes()).hexdigest(),
                        "expected_sha256":hashlib.sha256(expected.astype("<u4").tobytes()).hexdigest(),
                        "labels_used":False})
    (args.destination / "vector_manifest.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    print("A2_STARE_RGB_ONLY_VECTORS_PREPARED")


if __name__=="__main__": main()
