"""Fixed host reference hashes; no labels decoded or scores tuned."""
import json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_q4_refined_vectors import expected_words, sha

def main():
    out=ROOT/'build/q4_board_hashes_01.json'
    if out.exists():raise ValueError('Preserve existing hashes')
    p=json.loads((ROOT/'docs/q4_board_protocol_r1.json').read_bytes())
    old=json.loads((ROOT/'build/deploy/q3_full_quality_r1/browser_manifest.json').read_bytes())
    c=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
    hashes={}
    for name in sorted(p['split']['train']+p['split']['heldout']):
        for side in p['sizes']:
            e=old['images'][name][str(side)]
            words=np.load(ROOT/'build/deploy/q3_full_quality_r1'/e['input'],allow_pickle=False)
            assert sha(words.tobytes())==e['input_word_sha256']
            for alg in p['algorithms']:
                result=expected_words(words,3,alg,28,c)
                hashes[f'{name}_{side}_{alg}']=sha(result.astype('<u4').tobytes())
        print('Q4_REFERENCE_HASHED',name,flush=True)
    out.write_text(json.dumps(dict(status='HOST_REFERENCE_HASHES_NOT_BOARD',protocol_sha256=sha((ROOT/'docs/q4_board_protocol_r1.json').read_bytes()),expected_output_sha256=hashes,labels_loaded=False),indent=2)+'\n')
if __name__=='__main__':main()
