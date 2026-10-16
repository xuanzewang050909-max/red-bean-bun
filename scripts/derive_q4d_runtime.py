"""Derive optional C7 runtime from actual board-verified Q4, keeping old release intact."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def converted(text):
    for old,new in [('q4_c5_experimental_r1','q4d_c7_experimental_r1'),('q4_rq51_c5_experimental_r1','q4d_rq71_c7_experimental_r1'),
        ('pynq_q4','pynq_q4d'),('q4_refined','q4d_detector'),('q4_hardware','q4d_hardware'),('RQ51','RQ71'),('52513531','52513731'),
        ("'A', 'C2', 'C5'","'A', 'C2', 'C5', 'C7'"),('A/C2/C5','A/C2/C5/C7'),('Q4 ','Q4d ')]:
        text=text.replace(old,new)
    return text

def main():
    for src,dst in [('pynq_q4','pynq_q4d'),('ui_q4','ui_q4d')]:
        target=ROOT/dst
        if target.exists():raise ValueError('Preserve previous runtime')
        target.mkdir()
        for file in (ROOT/src).iterdir():
            if file.suffix in ('.py','.html','.css','.js'):
                (target/file.name).write_text(converted(file.read_text(encoding='utf-8')),encoding='utf-8',newline='\n')
    for src,dst in [('scripts/q4_board.py','scripts/q4d_board.py'),('scripts/verify_q4_run.py','scripts/verify_q4d_run.py')]:
        target=ROOT/dst;assert not target.exists()
        text=converted((ROOT/src).read_text())
        text=text.replace('q4_','q4d_') if 'board.py' in dst else text.replace('prepare_q4_refined_vectors','prepare_q4d_detector_vectors')
        # converted() has already changed package prefix: do not create q4dd.
        text=text.replace('q4dd','q4d')
        target.write_text(text,encoding='utf-8',newline='\n')
    print('C7_RUNTIME_DERIVED_REQUIRES_ABI_EDITS_AND_TESTS')

if __name__=='__main__':main()
