"""Independent host audit of a future returned ZIP; no model or board access."""
import argparse,hashlib,io,json,zipfile
from pathlib import Path
import numpy as np
def digest(data):return hashlib.sha256(data).hexdigest()
def verify(archive,package):
    package=Path(package);mraw=(package/'payload/manifest.json').read_bytes();m=json.loads(mraw)
    for name,r in m['files'].items():
        path=(package/'payload'/name).resolve();assert (package/'payload').resolve() in path.parents
        data=path.read_bytes();assert len(data)==r['bytes'] and digest(data)==r['sha256'],name
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();assert len(names)==len(set(names)) and 'FAULT.json' not in names
        session=json.loads(z.read('session.json'));assert session['manifest_sha256']==digest(mraw)
        assert session['algorithm']==m['algorithm'] and session['board']=='PYNQ-Z2'
        assert session['confirmation']=='I_AUTHORIZE_THREE_IMAGE_BOARD_TEST_ONCE'
        summary=json.loads(z.read('summary.json'));assert summary['status']=='BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW' and summary['source']=='REAL_PYNQ_PL'
        assert [r['case'] for r in summary['records']]==m['case_order']
        results=[]
        for case in m['case_order']:
            rec=json.loads(z.read(case+'_record.json'));assert rec['source']=='REAL_PYNQ_PL' and rec['case']==case
            raw=z.read(rec['actual']['path']);assert len(raw)==rec['actual']['bytes'] and digest(raw)==rec['actual']['sha256']
            a=np.load(io.BytesIO(raw),allow_pickle=False)
            expected=np.load(package/'payload'/(case+'_expected.npy'),allow_pickle=False)
            inp=np.load(package/'payload'/(case+'_input.npy'),allow_pickle=False);n=inp.size
            assert a.dtype==expected.dtype==np.uint32 and a.shape==(6*n+32,) and expected.size==6*n
            assert rec['shape']==list(inp.shape) and rec['words']==6*n and rec['guard_words']==32
            assert rec['differences']==0 and rec['guard_ok'] is True and rec==summary['records'][len(results)]
            assert digest(a.tobytes())==rec['actual']['raw_sha256']
            assert rec['input_sha256']==digest((package/'payload'/(case+'_input.npy')).read_bytes())
            assert np.array_equal(a[:6*n],expected) and np.all(a[6*n:]==0xdeadbeef)
            old=((inp>>25)&1)!=0;out=a[5*n:6*n].reshape(inp.shape);final=(out&1)!=0;added=((out>>1)&1)!=0
            assert np.array_equal(final,old|added) and not np.any(added&old)
            results.append(dict(case=case,profile=m['cases'][case]['profile'],words=6*n,differences=0,old_preserved=True,added=int(added.sum()),actual_sha256=digest(raw)))
        # Persisted access ledger proves the configured profile and 20-stage sequence per frame.
        events=[json.loads(x) for x in z.read('events.jsonl').decode().splitlines()]
        done=[x for x in events if x['event']=='OP_DONE']
        assert [x['data']['op'] for x in done]==([0,1,2]+[3]*16+[4])*len(m['case_order'])
        assert not any(x['event']=='ACCESS_FAILED' for x in events)
        # Every attempted access must have its matching return; no inferred completion.
        pending=None
        for e in events:
            if e['event']=='ACCESS_INTENT':
                assert pending is None;pending=e['data']
            elif e['event']=='ACCESS_RETURNED':
                assert pending is not None
                assert e['data']['label']==pending['label'] and e['data']['details']==pending['details']
                pending=None
        assert pending is None
        writes=[x['data']['details'] for x in events if x['event']=='ACCESS_INTENT' and x['data']['label']=='CONTROL_WRITE']
        assert len(writes)==5*len(results)
        for i,case in enumerate(m['case_order']):
            rec=summary['records'][i];h,w=rec['shape']
            assert writes[5*i:5*i+5]==[dict(offset=off,value=val) for off,val in
              [(0x18,rec['physical_address']),(0x28,h),(0x30,w),(0x38,6*h*w),(0x40,m['cases'][case]['profile'])]]
        clock=json.loads(z.read('clock.json'))
        assert 49.9<=clock['actual_register_derived_mhz']<=50.000001
        assert clock['metadata_divisor0']*clock['metadata_divisor1']==20
        assert clock['sta_period_ns']==20 and clock['set_clock_performed'] is False
        runtime=json.loads(z.read('runtime_identity.json'));contract=json.loads((package/'payload/runtime_contract.json').read_bytes())
        assert runtime['pynq']=='3.0.1' and runtime['machine'] in ('armv7','armv7l')
        for key in ('Overlay','allocate'):
            assert all(runtime['sources'][key][field]==contract[key][field] for field in ('bytes','sha256'))
    return dict(status='THREE_IMAGE_BOARD_NUMERIC_VERIFIED',archive_sha256=digest(Path(archive).read_bytes()),manifest_sha256=digest(mraw),frames=results,
      scope='Captured numerical outputs and identity verified; visual quality separate; no independent GT accuracy claimed')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--zip',required=True);p.add_argument('--package',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=verify(a.zip,a.package)
    with Path(a.output).open('x',encoding='utf8') as f:json.dump(r,f,indent=2)
    print(r['status'])
