"""Frozen image-only CLI. Import/help never access hardware or label data."""
from pathlib import Path
import argparse,json,numpy as np
from candidates import decide_cached
from identify import OUT,IDS,sha
def execute(input_path,profile,output_path,protocol_path=OUT/'frozen_algorithm.json'):
    p=Path(protocol_path);protocol=json.loads(p.read_text())
    assert protocol['schema']=='three-image-vessel-completion-v1' and profile in (0,1,2)
    inp=np.load(input_path,allow_pickle=False)
    assert inp.dtype==np.uint32 and inp.shape==(512,512) and np.all((inp>>26)==0)
    rgb=np.stack([(inp>>s).astype('uint8') for s in (16,8,0)],-1)
    fov=((inp>>24)&1)!=0;old=((inp>>25)&1)!=0
    cfg=protocol['config']['profiles'][IDS[profile]] # explicit register profile, no filename matching
    result=decide_cached(rgb,old,fov,cfg)
    dest=Path(output_path)
    with dest.open('xb') as f:np.savez_compressed(f,**result)
    return dict(output=str(dest),sha256=sha(dest),profile=profile,old_preserved=bool(np.all(result['final'][old])))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--profile',required=True,type=int,choices=[0,1,2]);p.add_argument('--output',required=True)
    args=p.parse_args();print(json.dumps(execute(args.input,args.profile,args.output)))
