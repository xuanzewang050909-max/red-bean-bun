"""Pair a demonstration notebook with the unchanged, board-verified W5b ZIP."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(release, destination):
    destination.mkdir(parents=True, exist_ok=False)
    old=json.loads((release/'upload/c7_w5b_interaction.ipynb').read_bytes())
    extract=next(c for c in old['cells'] if c['cell_type']=='code')['source']
    helper=(ROOT/'scripts/c7_demo_board.py').read_text(encoding='utf-8')
    steps=[('1. 校验原配对包', '使用全新 retina_c7_demo_r1 目录；原 W5b ZIP 字节不变。', ''.join(extract)),
           ('2. 记录本次启动并检查环境', '重启后运行；记录 boot_id/uptime，仍须真实视频确认重启动作。此框不加载FPGA。', helper+"\nif 'browser_context' in globals():\n    raise RuntimeError('Already prepared; do not repeat')\nbrowser_context = prepare_demo(w4_root)\n"),
           ('3. 加载一次并启动网页', '沿用已验 C7；不运行 W5b 自动35帧。', 'print(await start(browser_context))\n'),
           ('4. 七次演示操作', '打开8090并Ctrl+F5，沿用W5b界面。本轮仅七次、全部512/快速PNG：①im0001 C7最终112；②im0324_nogt C7最终112；③im0324 C7旁路112；④im0001 C2模式1/28；⑤同图C2模式2/28；⑥同图C2最终3/28。每次等图和延迟显示后截图。第六次后Ctrl+F5；⑦im0001 C7最终112。建议从启动到结束录制真实视频；不要运行旧35帧自动流程。', "print('DEMO_MANUAL_READY: exactly seven manual frames; reload after sixth')\n"),
           ('5. 核对并安全关闭', '仅七次全部完成后运行；异常停止并保留现场，不重载或自动重试。', 'await close_demo(browser_context)\n'),
           ('6. 导出完整证据', '原始会话导出含真实输入输出、PNG、回读、时序、CSV；本轮不是正式FPS复测。', 'demo_bundle = await export_demo(browser_context)\n'),
           ('7. 保存与下载', 'Ctrl+S，下载c7_delivery_demo.ipynb和c7_demo_results.zip；同时保留视频及截图。确认此框正常后可在Running关闭本内核。', "print('DEMO_FINISHED:', browser_context['manager'].status())\n")]
    cells=[dict(cell_type='markdown',metadata={},source=['# C7交付演示与重启后启动检查\n\n新演示板测状态BOARD_NOT_RUN。算法、bit/HWH、服务和网页复用已验W5b原字节；仅更换Notebook调度。正常重启后启动不等于在途断电恢复。失败保留现场。\n'])]
    for title,desc,code in steps:
        cells += [dict(cell_type='markdown',metadata={},source=[f'## {title}\n\n{desc}\n']), dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=code.splitlines(True))]
    nb=dict(old,cells=cells)
    (destination/'c7_delivery_demo.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
    shutil.copy2(release/'upload/c7_w5b_interaction_r1.zip',destination/'c7_w5b_interaction_r1.zip')
    return {p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in destination.iterdir()}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('release',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    print(json.dumps(build(a.release,a.destination),indent=2))
