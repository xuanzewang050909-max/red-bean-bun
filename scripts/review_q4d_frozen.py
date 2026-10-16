"""Fixed-model visual/metric audit. CPU evidence only; no parameter selection."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.prepare_q4d_detector_vectors import expected_words
from pynq_q4d.protocol import rgb_from_input


def main():
    source=ROOT/'build/deploy/q3_full_quality_r1'
    run=ROOT/'build/q4d_board_references_01'
    out=ROOT/'build/q4d_frozen_visual_02'
    out.mkdir(exist_ok=False)
    catalog=json.loads((source/'browser_manifest.json').read_bytes())
    report=json.loads((run/'frozen_evaluation.json').read_bytes())
    candidate=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
    text=['# C7冻结后CPU评价与视觉核查\n',
          '仅CPU参考，不是板测；所有参数在本评价之前冻结，未据留出/VK调参。训练图结果是重新拟合后的重代入，留出图已在旧研究中使用，不是新外部验证。\n',
          '|分组|标注|尺寸|Dice C5→C7|细代理Recall|亮带FP|亮带Recall|clDice|',
          '|---|---|---|---|---|---|---|---|']
    for split,observers in report['groups'].items():
        for observer,sizes in observers.items():
            for side,algorithms in sizes.items():
                summaries=[algorithms[a]['summary'] for a in ('C5','C7')]
                functions=[lambda s:s['macro_fov']['dice'],lambda s:s['pooled']['thin_label_proxy']['recall'],
                           lambda s:s['pooled']['bright_band']['fp'],lambda s:s['pooled']['bright_band']['recall'],
                           lambda s:s['continuity']['cldice']]
                vals=[' → '.join(str(fn(s)) if i==2 else f'{fn(s):.4f}' for s in summaries) for i,fn in enumerate(functions)]
                text.append('|'+ '|'.join([split,observer,side,*vals])+'|')
                losses=[]
                for image,c in algorithms['C7']['per_image'].items():
                    b=algorithms['C5']['per_image'][image]
                    if c['fov']['dice']<b['fov']['dice']:
                        losses.append(dict(image=image,c5=b['fov']['dice'],c7=c['fov']['dice']))
                (out/f'{split}_{observer}_{side}_dice_losses.json').write_text(json.dumps(losses,indent=2)+'\n',encoding='utf-8')
    text += ['\n逐图Dice下降名单一并保存，不能只报告分组平均改善。原分组OOF的512亮带召回损失仍是未通过项，最终模型重代入或复用留出结果不能抹去它。',
             '\n以下固定三图、固定裁剪用于检查残余误检和漏检。绿色TP，红色FP，蓝色FN；参考AH，VK另计表。无掩膜美化、连接后处理或挑选像素。']
    for image in ('im0001','im0002','im0324'):
        entry=catalog['images'][image]['512']
        words=np.load(source/entry['input'],allow_pickle=False)
        rgb=rgb_from_input(words)
        truth=np.load(source/entry['evaluation_only']['AH']['path'],allow_pickle=False).astype(bool)
        c5=expected_words(words,3,'C5',28,candidate)
        c7=np.load(run/f'{image}_512_C7_words.npy',allow_pickle=False)
        masks=[((w>>16)&255)!=0 for w in (c5,c7)]
        fig,axes=plt.subplots(3,5,figsize=(15,10))
        for row,sl in enumerate(((slice(None),slice(None)),(slice(145,385),slice(180,340)),(slice(270,430),slice(40,220)))):
            axes[row,0].imshow(rgb[sl],interpolation='nearest');axes[row,0].set_title(image+' input')
            for k,(m,name) in enumerate(zip(masks,('C5 / T28','C7 / T112'))):
                axes[row,1+k].imshow(m[sl],cmap='gray',vmin=0,vmax=1,interpolation='nearest');axes[row,1+k].set_title(name+' mask')
                canvas=rgb.astype(float)*.25
                canvas[m&truth]=[0,240,80];canvas[m&~truth]=[255,30,40];canvas[~m&truth]=[40,130,255]
                axes[row,3+k].imshow(canvas[sl].astype(np.uint8),interpolation='nearest');axes[row,3+k].set_title(name+' errors')
            for ax in axes[row]:ax.axis('off')
        label='TRAIN resubstitution' if image=='im0001' else 'REUSED heldout'
        fig.suptitle(label+' / CPU reference only / fixed model / Green TP, red FP, blue FN')
        fig.tight_layout();fig.savefig(out/f'{image}_comparison.png',dpi=130);plt.close(fig)
        text.append(f'\n![{image} CPU comparison]({image}_comparison.png)')
    (out/'review.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print('C7_FROZEN_VISUAL_READY_CPU_ONLY',out)

if __name__=='__main__':main()
