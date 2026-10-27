from software import *
p=Path(__file__).parent/'hardware';p.mkdir(exist_ok=True)
cfg=json.loads((OUT/'frozen_algorithm.json').read_text())['config']
rows=[];normals=[];unit=[]
for dx,dy in DIRECTIONS:
    off,_=offsets(dx,dy,cfg['length'],2);rows.append(off)
    normals.append([offsets(dx,dy,cfg['length'],w)[1] for w in cfg['widths']])
    n=np.hypot(dx,dy);unit.append((int(round(dx/n)),int(round(-dy/n))))
def c(v):return '{'+','.join(c(x) if isinstance(x,(tuple,list)) else str(x) for x in v)+'}'
(p/'geometry.hpp').write_text('#pragma once\nstatic const int POS[8][13][2]='+c(rows)+';\nstatic const int NORMAL[8][3][2]='+c(normals)+';\nstatic const int UNIT[8][2]='+c(unit)+';\n')
print('FINITE_GEOMETRY_WRITTEN')
