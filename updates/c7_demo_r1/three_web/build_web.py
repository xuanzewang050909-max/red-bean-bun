"""Build fresh C7 web package from verified published bytes; no hardware access."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys,zipfile,subprocess
HERE=Path(__file__).resolve().parent
def info(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def build(destination):
    source=HERE/'c7_web';cfg=json.loads((source/'integration.json').read_bytes())
    for r in [cfg['baseline_web'],cfg['verified_board_capture'],cfg['board_verification'],cfg['preserved_im0324_capture'],*cfg['payload_manifests'].values()]:
        assert info(r['path'])=={k:r[k] for k in ('bytes','sha256')},r['path']
    assert json.loads(Path(cfg['board_verification']['path']).read_bytes())['status']=='THREE_IMAGE_BOARD_NUMERIC_VERIFIED'
    root=Path(destination).resolve();root.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(cfg['baseline_web']['path']) as z:
        m=json.loads(z.read('browser_manifest.json'))
        assert set(z.namelist())==set(m['artifacts'])|{'browser_manifest.json'}
        for name,r in m['artifacts'].items():
            b=z.read(name);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],name
            target=root/(name.replace('refinement/','refinement_single/',1) if name.startswith('refinement/') else name)
            assert root in target.resolve().parents;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            target=root/p.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    payload=Path(cfg['payload_manifests']['refinement']['path']).parent
    pm=json.loads((payload/'manifest.json').read_bytes())
    for name in list(pm['files'])+['manifest.json']:
        if name!='manifest.json':assert info(payload/name)=={k:pm['files'][name][k] for k in ('bytes','sha256')}
        target=root/'refinement'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(payload/name,target)
    m['integration_revision']='c7-four-image-web-r4-staged';m['presentation_revision']='c7-four-panels-original-then-improved'
    m['integration_source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE.parent,text=True).strip()
    original=m['artifacts'].copy()
    m['artifacts']={p.relative_to(root).as_posix():info(p) for p in sorted(root.rglob('*')) if p.is_file()}
    (root/'browser_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sys.path.insert(0,str(root))
    from pynq_showcase.protocol import validate_package
    validate_package(root)
    for name in ('pynq_showcase/hardware.py','pynq_showcase/quality_observer.py','q4d_detector.bit','q4d_detector.hwh','a0_dma_board_test.py'):
        assert info(root/name)==original[name],name
    print(json.dumps(dict(status='PACKAGE_OFFLINE_VERIFIED',root=str(root),files=len(m['artifacts']),board_operations=0)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);build(p.parse_args().output)
