"""Reject falsely labelled host data before any board-result acceptance."""
from identify import *
import zipfile, tempfile
from verify_download import verify

def check(package):
    package=Path(package);m=json.loads((package/'payload/manifest.json').read_bytes())
    target=OUT/'host_verifier_test';target.mkdir(exist_ok=False)
    zpath=target/'HOST_ONLY_REJECT_FIXTURE.zip'
    with zipfile.ZipFile(zpath,'x') as z:
        z.writestr('session.json',json.dumps(dict(manifest_sha256=sha(package/'payload/manifest.json'),algorithm=m['algorithm'],board='PYNQ-Z2',confirmation='I_AUTHORIZE_THREE_IMAGE_BOARD_TEST_ONCE')))
        z.writestr('summary.json',json.dumps(dict(status='BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW',source='HOST_UNIT_FIXTURE')))
    rejected=False
    try:verify(zpath,package)
    except AssertionError:rejected=True
    assert rejected
    result=dict(status='HOST_FIXTURE_REJECTED',fixture=ref(zpath),scope='Negative source test only; no real PL capture exists for this release',board_operations=0)
    (target/'receipt.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--package',required=True)
    print(check(p.parse_args().package)['status'])
