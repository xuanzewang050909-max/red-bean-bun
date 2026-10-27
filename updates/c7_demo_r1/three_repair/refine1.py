from candidates import run
base=dict(mode='valley',length=6,widths=[2,4,6],fraction=True,low=1.5,high=3,ridge_tolerance=2,grow_steps=16,min_support=8,anisotropy=0.75,coherence_seed_only=True)
for name,coh,high in [('v09',12,3),('v10',14,3),('v11',14,4),('v12',15,4)]:
    cfg=base.copy();cfg.update(coherence=coh,high=high)
    run(name,cfg,'Pixelwise coherence broke curved branches. Apply alignment requirement only to image-derived independent seeds, then retain bounded growth through original evidence. Compare removal of short texture.','route2_refinement1')
