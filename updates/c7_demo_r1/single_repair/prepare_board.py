from software import *
import shutil
dest=Path(__file__).parent/'board';dest.mkdir(exist_ok=False)
parent=Path('D:/PLD/review_packages/C7_AtomicBridge_Guard50_Board_r1')
refs=[]
for name in ['transport.py','evidence_io.py','refinement_clock_contract.py']:
    shutil.copy2(parent/name,dest/name);refs.append(dict(path=str(parent/name),sha256=hashlib.sha256((parent/name).read_bytes()).hexdigest()))
shutil.copy2(Path(__file__).with_name('board_run.py'),dest/'board_run.py')
(OUT/'board_helper_sources.json').write_text(json.dumps(refs,indent=2))
for target,case in [('smoke','empty'),('native','native')]:
    with np.load(OUT/'integer'/f'{case}.npz') as a:
        np.save(dest/(target+'_input.npy'),a['input'],allow_pickle=False)
        np.save(dest/(target+'_expected.npy'),a['memory'],allow_pickle=False)
print('OFFLINE_BOARD_DRAFT_NO_HARDWARE')
