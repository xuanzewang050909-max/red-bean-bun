"""Build a separate C7 web release from pinned artifacts; never access hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def info(p):
    data = Path(p).read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def build(destination, presentation_revision=None):
    source = HERE/'c7_web'
    cfg = json.loads((source/'integration.json').read_bytes())
    base = Path(cfg['baseline_manifest']['path']).parent
    payload = Path(cfg['refinement_manifest']['path']).parent
    for ref in (cfg['baseline_manifest'], cfg['refinement_manifest'], cfg['verified_board_capture'], cfg['board_verification']):
        assert info(ref['path']) == {k: ref[k] for k in ('bytes','sha256')}, ref['path']
    manifest = json.loads((base/'browser_manifest.json').read_bytes())
    for name, ref in manifest['artifacts'].items():
        assert info(base/name) == ref, name
    repair = json.loads((payload/'manifest.json').read_bytes())
    for name, ref in repair['files'].items():
        assert info(payload/name) == {k: ref[k] for k in ('bytes','sha256')}, name
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    # Copy published files only; no historical sessions, caches or attempt markers.
    for name in manifest['artifacts']:
        p = root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base/name,p)
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            target = root/p.relative_to(source)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,target)
    (root/'refinement').mkdir()
    for name in list(repair['files'])+['manifest.json']:
        shutil.copy2(payload/name,root/'refinement'/name)
    manifest['integration_revision'] = 'c7-single-image-web-r1'
    if presentation_revision is not None:
        manifest['presentation_revision'] = presentation_revision
    manifest['integration_source_commit'] = subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=HERE.parent,text=True).strip()
    manifest['artifacts'] = {p.relative_to(root).as_posix():info(p) for p in sorted(root.rglob('*')) if p.is_file()}
    (root/'browser_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sys.path.insert(0,str(root))
    from pynq_showcase.protocol import validate_package
    validate_package(root)
    # Unchanged trusted DMA adapter, monitor, bit, HWH and thresholds.
    for name in ('pynq_showcase/hardware.py','pynq_showcase/quality_observer.py','q4d_detector.bit','q4d_detector.hwh','a0_dma_board_test.py'):
        assert info(root/name) == info(base/name),name
    print(json.dumps(dict(root=str(root),files=len(manifest['artifacts']),status='PACKAGE_OFFLINE_VERIFIED')))
    return root


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--presentation-revision')
    args=p.parse_args();build(args.output,args.presentation_revision)
