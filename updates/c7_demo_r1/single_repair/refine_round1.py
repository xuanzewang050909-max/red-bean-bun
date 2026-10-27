from software import *
base=dict(mode='valley',length=6,widths=[2,4,6],low=2,high=4,ridge_tolerance=2,grow_steps=16,min_support=8,fraction=True)
for name,change in [('v04',{}),('v05',{'length':8,'widths':[2,4,6],'high':4}),('v06',{'length':6,'high':5,'ridge_tolerance':4}),('v07',{'length':8,'widths':[3,5,7],'high':5})]:
    run(name,dict(base,**change))
