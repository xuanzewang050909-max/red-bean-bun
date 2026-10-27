from software import *
import shutil
dst=OUT/'viewer';dst.mkdir(exist_ok=False)
for name,p in {'original':'input/rgb.png','before':'input/old_overlay.png','after':'selected/final_overlay.png','colored':'selected/old_new_colors.png','added':'selected/added_mask.png','uncertain':'selected/uncertain.png'}.items():shutil.copy2(OUT/p,dst/(name+'.png'))
for name in ['right_lower','lower_left','upper_left','right_middle']:shutil.copy2(OUT/'selected'/f'{name}.png',dst/(name+'.png'))
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>单图血管补标 · 离线结果</title>
<style>body{margin:0;background:#121b20;color:#edf5f5;font:16px system-ui}main{max-width:1160px;margin:auto;padding:24px}h1{font-size:28px;margin-bottom:8px}p{color:#c5d7d8;line-height:1.65}button{padding:10px 16px;border:1px solid #49656a;background:#253a40;color:white;border-radius:8px;cursor:pointer;margin:4px}button[aria-pressed=true]{background:#316a61;border-color:#6adcb9}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.box{background:#050807;border-radius:12px;overflow:hidden}.box img{display:block;width:100%;image-rendering:auto}.label{padding:12px}.tag{font-size:13px;background:#3a444b;padding:5px 9px;border-radius:5px}.crop{width:100%;margin:8px 0;border-radius:10px}details{margin:24px 0}summary{cursor:pointer;font-size:20px}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>
<main><span class="tag">开发电脑计算结果 · 尚未上板</span><h1>im0324 单图血管补标</h1><p>保持全部旧标注，补入图像支持的长分支。原标注 6,457 像素；新增 3,083 像素。没有使用人工描绘、标注答案或神经网络。</p>
<nav aria-label="结果选择"><button data-mode="after" aria-pressed="true">最终绿色叠加</button><button data-mode="colored">旧 / 新分色</button><button data-mode="before">原绿色叠加</button><button data-mode="added">仅新增</button><button data-mode="uncertain">不确定区域</button></nav>
<div class="grid"><section class="box"><div class="label">未覆盖的原始 RGB</div><img src="original.png" alt="原始眼底图"></section><section class="box"><div class="label" id="label">最终绿色叠加</div><img id="result" src="after.png" alt="补标结果"></section></div>
<p>分色图：绿色为原标注，青色为新增。2,441 个弱候选像素保留在不确定区域图中，未自动并入最终结果。此页展示单图目视修补，不表示独立标注验证或板上运行通过。</p>
<details open><summary>重点区域：同一位置前后对比</summary><p>每组从左到右为原图、旧标注、旧新分色。</p><img class="crop" src="right_lower.png" alt="右下长段"><img class="crop" src="lower_left.png" alt="下方分支"><img class="crop" src="upper_left.png" alt="左上分支"><img class="crop" src="right_middle.png" alt="右侧中部"></details>
<p>仍有淡小分支、交汇处内部和边缘区域未能可靠补齐。旧标注中的既有错误按本任务“只增不删”要求保留。所有计算在开发电脑完成，BOARD_NOT_RUN。</p></main>
<script>document.querySelectorAll('button[data-mode]').forEach(b=>b.onclick=()=>{document.querySelectorAll('button[data-mode]').forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));document.getElementById('result').src=b.dataset.mode+'.png';document.getElementById('label').textContent=b.textContent;});</script></html>'''
(dst/'index.html').write_text(html,encoding='utf-8')
print(dst/'index.html')
