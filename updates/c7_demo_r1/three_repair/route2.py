from candidates import run
base=dict(mode='valley',length=6,widths=[2,4,6],fraction=True,low=1.5,high=3,ridge_tolerance=2,grow_steps=16,min_support=8,anisotropy=0.75)
for name,coh in [('v05',10),('v06',12),('v07',14),('v08',15)]:
    cfg=base.copy();cfg['coherence']=coh
    run(name,cfg,'Reject non-aligned short texture: require evidence along a bounded 17-position, 3-wide line corridor, directions within one bin; preserve independent seeds.','route2_initial')
