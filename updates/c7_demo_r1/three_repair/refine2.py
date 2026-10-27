from candidates import run,OUT,json
records={r['name']:r['config'] for r in json.loads((OUT/'candidate_ledger.json').read_text())}
cfg={'profiles':{'im0004':records['v03'],'im0291':records['v12'],'im0319':records['v05']}}
run('v13',cfg,'Explicit three-image profiles: im0004 faint long vessels favor v03; im0291 radial/background texture requires stronger aligned seeds v12; im0319 per-point coherence v05 recovers right lower segment with less central texture. One shared configurable core.','route2_refinement2')
