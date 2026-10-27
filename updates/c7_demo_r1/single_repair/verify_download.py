"""Future host-only verification of the manually returned board capture."""
from pathlib import Path
import argparse,zipfile,json,hashlib,io
import numpy as np
def main():
    p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('--payload',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    manifest=json.loads((a.payload/'manifest.json').read_text())
    for name,ref in manifest['files'].items():
        path=(a.payload/name).resolve();assert a.payload.resolve() in path.parents
        assert path.stat().st_size==ref['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==ref['sha256']
    with zipfile.ZipFile(a.zip) as z:
        assert len(z.namelist())==len(set(z.namelist())) and not any('..' in Path(n).parts for n in z.namelist())
        assert 'FAULT.json' not in z.namelist()
        session=json.loads(z.read('session.json'));assert session['manifest_sha256']==hashlib.sha256((a.payload/'manifest.json').read_bytes()).hexdigest()
        summary=json.loads(z.read('summary.json'));assert summary['source']=='REAL_PYNQ_PL' and summary['status']=='BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW'
        runtime=json.loads(z.read('runtime_identity.json'));assert runtime['pynq']=='3.0.1' and runtime['machine'] in ('armv7l','armv7')
        contract=json.loads((a.payload/'runtime_contract.json').read_text())
        for name in ['Overlay','allocate']:
            for key in ['bytes','sha256']:assert runtime['sources'][name][key]==contract[name][key]
        clock=json.loads(z.read('clock.json'))
        assert 49.9<=clock['actual_register_derived_mhz']<=50.000001 and clock['sta_period_ns']==20
        assert clock['metadata_divisor0']*clock['metadata_divisor1']==20 and not clock['set_clock_performed']
        boot=json.loads(z.read('boot_context.json'));assert boot['boot_id'] and boot['pid']>0
        events=[json.loads(x) for x in z.read('events.jsonl').decode().splitlines()]
        assert not any(x['event']=='ACCESS_FAILED' for x in events)
        ops=[x['data']['op'] for x in events if x['event']=='OP_DONE'];assert ops==([0,1,2]+[3]*16+[4])*2
        for case in ['smoke','native']:
            ref=json.loads(z.read(case+'_record.json'));assert ref['source']=='REAL_PYNQ_PL' and ref['differences']==0 and ref['guard_ok']
            assert ref['input_sha256']==hashlib.sha256((a.payload/(case+'_input.npy')).read_bytes()).hexdigest()
            assert ref['shape']==([32,32] if case=='smoke' else [512,512]) and ref['words']==6*ref['shape'][0]*ref['shape'][1] and ref['guard_words']==32
            assert ref['physical_address']%4==0 and 0<=ref['physical_address'] and ref['physical_address']+(ref['words']+32)*4<=0x20000000
            data=z.read(case+'_actual.npy');assert hashlib.sha256(data).hexdigest()==ref['actual']['sha256']
            got=np.load(io.BytesIO(data),allow_pickle=False);expected=np.load(a.payload/(case+'_expected.npy'),allow_pickle=False)
            assert got.dtype==expected.dtype==np.uint32 and got.size==expected.size+32 and np.array_equal(got[:expected.size],expected) and np.all(got[expected.size:]==0xdeadbeef)
            assert hashlib.sha256(got.tobytes()).hexdigest()==ref['actual']['raw_sha256']
    result=dict(status='SINGLE_IMAGE_BOARD_NUMERIC_VERIFIED',capture_zip_sha256=hashlib.sha256(a.zip.read_bytes()).hexdigest(),quality='Single-image visual review only; no independent GT accuracy claim')
    if a.output:
        with a.output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
if __name__=='__main__':main()
