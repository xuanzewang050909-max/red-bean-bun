"""Host-only I/O and invocation guard tests. Never imports pynq."""
from software import *
import tempfile, importlib, shutil
sys.path.insert(0,str(Path(__file__).parent/'board'))
import board_run as b
def main():
    dst=OUT/'board_unit_r2';dst.mkdir(exist_ok=False)
    ctx=dict(dest=dst,start=time.perf_counter(),phase='HOST_UNIT_FIXTURE',buffers=[])
    a=np.arange(128,dtype='uint32').reshape(8,16);before=a.copy()
    rec=b.persist(ctx,'host_only',a);assert np.array_equal(a,before)
    assert np.array_equal(np.load(dst/'host_only.npy'),a)
    try:b.persist(ctx,'host_only',a)
    except AssertionError:pass
    else:raise AssertionError('OVERWRITE_NOT_REJECTED')
    calls=[]
    assert b.call(ctx,'event',lambda:calls.append(1) or 7,event='payload',elapsed_seconds=9)==7
    try:b.call(ctx,'raises',lambda:(_ for _ in ()).throw(ValueError('synthetic')),schema='payload')
    except ValueError:pass
    else:raise AssertionError('SWALLOWED_ERROR')
    lines=[json.loads(s) for s in (dst/'events.jsonl').read_text().splitlines()]
    assert len(calls)==1 and [x['event'] for x in lines]==['ACCESS_INTENT','ACCESS_RETURNED','ACCESS_INTENT','ACCESS_FAILED']
    assert lines[0]['data']['details']['event']=='payload'
    try:b.start(dst,dst/'forbidden','NO_AUTHORIZATION')
    except RuntimeError as e:assert 'EXPLICIT_MANUAL' in str(e)
    else:raise AssertionError('GUARD')
    assert 'pynq' not in sys.modules and not (dst/'forbidden').exists()
    # Gate display before trying to read output: an actual failed session is never
    # rendered as successful, even if numerical files happen to exist.
    old_verify=b.verify
    b.verify=lambda root:None
    try:
        (dst/'FAULT.json').write_text('{"scope":"HOST_UNIT_FIXTURE"}')
        try:b.render_saved(dst,dst)
        except RuntimeError as e:assert 'FAILED_RUN' in str(e)
        else:raise AssertionError('FAILED_DISPLAY_ALLOWED')
    finally:b.verify=old_verify
    class IP:
        def __init__(self,fail=False):self.commands=[];self.fail=fail
        def write(self,r,v):self.commands.append((r,v))
        def read(self,r):return (7 if self.fail else 0) if r==16 else 6
    ip=IP();b.transaction(ctx,ip,2);assert ip.commands==[(32,2),(0,1)]
    failed=IP(True)
    try:b.transaction(ctx,failed,1)
    except RuntimeError:pass
    else:raise AssertionError('RETURN_ERROR')
    assert failed.commands==[(32,1),(0,1)]
    (dst/'receipt.json').write_text(json.dumps(dict(status='HOST_RECORDING_TEST_PASS',hardware_imports=0,hardware_operations=0,
        tests=['exclusive persistence and reload','input unchanged','duplicate rejected','metadata collision separated','exception retained','authorization guard before import','failed display blocked','single placeholder command','no retry on placeholder error'],persisted=rec),indent=2))
    print('HOST_RECORDING_TEST_PASS; no PYNQ import or hardware')
if __name__=='__main__':main()
