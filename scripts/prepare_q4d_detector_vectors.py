"""C7 actual HLS/RTL vectors; independently composed frozen C5 and integer C7."""
from pathlib import Path
import json
import sys
import hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts import prepare_q4_refined_vectors as old
from software.q4d_features import integer_features,scalar_features
from software.q4d_forest import predict_integer

MODEL=ROOT/'software/models/c7_d6_r1.json'
CASES=[(256,0,'A',28,'gradient'),(256,1,'C5',27,'random'),(256,2,'C5',29,'gradient'),
 (512,3,'A',28,'stare'),(256,3,'C2',28,'stare'),(512,3,'C2',28,'stare'),
 (512,3,'C7',112,'stare'),(256,3,'C7',112,'stare'),(256,3,'C7',1,'fov_edge'),
 (512,3,'C7',112,'bright_cross'),(256,3,'C7',96,'broken_line'),(512,3,'C7',255,'random'),
 (256,0,'C7',112,'vessel_stripes'),(512,3,'C5',28,'stare'),(256,3,'C7',112,'checker'),
 (256,3,'C7',112,'impulse'),(256,3,'C7',128,'random'),(512,3,'C7',112,'black')]

def expected_words(source,stage,algorithm,threshold,candidate):
    output=old.expected_words(source,stage,'C5' if algorithm=='C7' else algorithm,threshold,candidate)
    if algorithm=='C7' and stage==3:
        names,features=integer_features(((source>>8)&255).astype(np.uint8))
        model=json.loads(MODEL.read_bytes()); assert names==model['features']
        score=predict_integer(features,model)
        mask=(score>=threshold)&((source>>24)!=0)
        output=(output&np.uint32(65535))|(mask.astype(np.uint32)*255<<16)|(score.astype(np.uint32)<<24)
    return output

def main(destination):
    assert not destination.exists() or not any(destination.iterdir()); destination.mkdir(parents=True,exist_ok=True)
    candidate=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
    from scripts.evaluate_q1_bilateral import read_training_archive
    from software.preprocessing import prepare_sample,pack_input
    p=json.loads((ROOT/'docs/q1_bilateral_protocol_r1.json').read_bytes())
    rgb=read_training_archive(ROOT/'data/raw/stare/stare-images.tar','',['im0001'],p['train_ids']+p['heldout_ids_not_decoded'])['im0001']['pixels']
    for side in (256,512):
        image,aligned,_=prepare_sample(rgb,{},side)
        np.save(destination/f'stare_im0001_{side}.npy',pack_input(image,aligned['fov']),allow_pickle=False)
    records=[];oracle=[]
    for index,(side,stage,algorithm,threshold,pattern) in enumerate(CASES,1):
        if pattern=='bright_cross':
            y,x=np.indices((side,side),dtype=np.uint32)
            g=np.where((x>=side//3)&(x<2*side//3)&(y>=side//3)&(y<2*side//3),245,120+((x*3+y*5)%30))
            g=np.where(abs(y.astype(np.int32)-side//2)<=2,60,g).astype(np.uint32)
            source=(np.uint32(1)<<24)|(np.uint32(100)<<16)|(g<<8)|37
        else:source=old.make_pattern(side,pattern,index,destination)
        output=expected_words(source,stage,algorithm,threshold,candidate)
        for name,data in (('input',source),('expected',output)):
            np.savetxt(destination/f'case_{index:02d}_{name}.hex',data.ravel(),fmt='%08x')
        flags={'A':0,'C2':8,'C5':24,'C7':56}[algorithm]
        records.append(dict(case=index,side=side,stage=stage,algorithm=algorithm,threshold=threshold,pattern=pattern,
            control_word=stage|(4 if side==256 else 0)|flags|(threshold<<8),words=source.size,
            input_sha256=old.sha(source.astype('<u4').tobytes()),expected_sha256=old.sha(output.astype('<u4').tobytes()),
            complete_frame_expected=index!=17,labels_used=False))
        green=((source>>8)&255).astype(np.uint8)
        rng=np.random.default_rng(1900+index)
        coords=[(0,0),(0,side-1),(side-1,0),(side-1,side-1),(side//2,side//2)]+[tuple(x) for x in rng.integers(0,side,(10,2))]
        _,f=integer_features(green)
        for y,x in coords:
            expected=scalar_features(green,y,x); assert np.array_equal(f[y,x],expected)
            oracle.append([index,int(y),int(x),*[int(v) for v in expected]])
        print('C7_VECTOR_READY',index,algorithm,side,flush=True)
    np.savetxt(destination/'feature_oracle.txt',np.array(oracle),fmt='%d')
    (destination/'csim_cases.txt').write_text(''.join(f'{r["case"]} {r["side"]} {r["control_word"]}\n' for r in records))
    (destination/'vector_manifest.json').write_text(json.dumps(dict(status='C7_VECTORS_NOT_BOARD',cases=records,
        model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),complete_frames=17,
        full_words=sum(r['words'] for r in records if r['complete_frame_expected']),
        hex_sha256={p.name:old.sha(p.read_bytes()) for p in destination.glob('*.hex')},board_status='NOT_RUN'),indent=2)+'\n')

if __name__=='__main__':main(Path(sys.argv[1]))
