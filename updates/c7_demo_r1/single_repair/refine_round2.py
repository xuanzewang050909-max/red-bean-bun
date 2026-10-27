from software import *
base=dict(mode='valley',length=6,widths=[2,4,6],low=2,high=4,ridge_tolerance=2,grow_steps=16,min_support=8,fraction=True,anisotropy=1)
for name,change in [('v08',{}),('v09',{'anisotropy':2}),('v10',{'high':5,'ridge_tolerance':4}),('v11',{'high':4,'anisotropy':1,'min_support':12})]:
    run(name,dict(base,**change))
