"""Make a clearly labeled diagnostic from verified REAL Q3 DMA arrays (A and C2)."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image,ImageDraw,ImageFont


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'build/q3_residual_audit_2026-10-14'
    if out.exists():raise RuntimeError('Preserve prior audit')
    out.mkdir()
    report=json.loads((root/'results/q3_quality_r1/board_execution_2026-10-14/verification.json').read_text())
    records={a:next(r for r in report['runs'] if r['request']['image_id']=='im0001'
                   and r['request']['side']==512 and r['request']['algorithm']==a) for a in ('A','C2')}
    source=root/'build/board_results/q3_quality_2026-10-14/q3_results_bundle.zip'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==report['archive']['sha256']
    with zipfile.ZipFile(source) as z:
        masks={}
        for a,r in records.items():
            words=np.load(io.BytesIO(z.read(r['run_id']+'/output_packed.npy')),allow_pickle=False).reshape(512,512)
            assert hashlib.sha256(words.astype('<u4').tobytes()).hexdigest()==r['output_sha256']
            masks[a]=((words>>16)&255)!=0
        words=np.load(io.BytesIO(z.read(records['A']['run_id']+'/input_packed.npy')),allow_pickle=False).reshape(512,512)
    rgb=np.stack([(words>>16)&255,(words>>8)&255,words&255],axis=-1).astype(np.uint8)
    fov=((words>>24)&255)!=0
    with np.load(root/'build/q4_refinement_2026-10-14_r1/im0001_512_offline_masks.npz',allow_pickle=False) as z:
        assert np.array_equal(z['rgb'],rgb) and np.array_equal(z['fov'],fov)
        truth=z['truth_AH']
    crop=np.s_[145:385,180:340]
    base=rgb[crop];t=truth[crop];area=fov[crop]
    plots=[('Input RGB - central example',base)]
    plots += [(f'Real Q3 PL: {a}',np.repeat(masks[a][crop][...,None]*255,3,axis=2).astype(np.uint8)) for a in ('A','C2')]
    plots.append(('AH manual vessels',np.repeat(t[...,None]*255,3,axis=2).astype(np.uint8)))
    counts={}
    for a in ('A','C2'):
        p=masks[a][crop]
        im=(base.astype(np.uint16)//5).astype(np.uint8)
        im[p&t&area]=[0,230,110];im[p&~t&area]=[255,40,55];im[~p&t&area]=[30,120,255]
        plots.append((f'{a}: green TP / red FP / blue FN',im))
        counts[a]={'tp':int((p&t&area).sum()),'fp':int((p&~t&area).sum()),'fn':int((~p&t&area).sum())}
    canvas=Image.new('RGB',(1016,1136),'white');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    for i,(title,im) in enumerate(plots):
        x=16+(i%3)*336;y=16+(i//3)*520
        draw.text((x,y),title,font=font,fill='black')
        canvas.paste(Image.fromarray(im).resize((320,480),Image.Resampling.NEAREST),(x,y+30))
    draw.text((16,1060),'im0001 / real DMA / 512 / mode 3 / T28. Same diagnostic crop; AH only.',font=font,fill='black')
    draw.text((16,1088),'C2 reduces some red pixels; substantial false positives and missing vessels remain.',font=font,fill='black')
    canvas.save(out/'actual_a_c2_comparison.png')
    metadata={'source_archive_sha256':report['archive']['sha256'],'runs':{a:r['run_id'] for a,r in records.items()},
              'output_sha256':{a:r['output_sha256'] for a,r in records.items()},'crop':[180,145,340,385],
              'annotation':'AH','scope':'ILLUSTRATIVE_CROP_NOT_FULL_BRIGHT_REGION_OR_QUALITY_ACCEPTANCE',
              'confusion_counts':counts,'image_sha256':hashlib.sha256((out/'actual_a_c2_comparison.png').read_bytes()).hexdigest()}
    (out/'audit.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    print(out/'actual_a_c2_comparison.png');print(counts)


if __name__=='__main__':main()
