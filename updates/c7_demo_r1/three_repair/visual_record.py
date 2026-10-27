"""Record completed visual inspection; no image recomputation or quality metrics."""
from identify import *
def main():
    notes={
      'v01':['Long right lower / left central branches recovered; weaker upper pieces absent.','Some upper/right extensions; central short texture appears.','Right lower distant continuation largely absent.'],
      'v02':['More faint branch seeds, useful upper middle.','More unsupported-looking central fragments than v01.','Right lower segment appears but central speckle increases.'],
      'v03':['Substantial visible long segments, no area fill; selected profile0.','Central irregular texture too prominent; not selected.','Useful right lower segment but central short fragments.'],
      'v04':['Extra short twigs versus v03; no clear benefit.','More connected central texture; rejected.','More fuzzy short branches; rejected.'],
      'v05':['Long branches retained but some bends broken.','Central fragments reduced, some still remain.','Right lower visible segment retained, central texture reduced; selected profile2.'],
      'v06':['Too many breaks in curved long branches.','Suppresses texture but loses upper branch continuation.','Right lower path fragmented.'],
      'v07':['Long paths break into fragments.','Mostly tip changes; insufficient relative to alternatives.','Little new right lower continuity.'],
      'v08':['Overly sparse and disconnected.','Overly sparse.','Right lower path largely removed.'],
      'v09':['Seed-only restores long paths with some faint bends omitted.','Several irregular central clusters return.','Central fragments return.'],
      'v10':['Similar useful long paths to v09 but no advantage over v03.','Central clusters reduced but still visible.','More useful right path; more central fragments than v05.'],
      'v11':['Higher seed floor drops faint long branches.','Conservative continuation; less central texture.','Drops distant right lower continuation.'],
      'v12':['Slightly fewer faint branches than v11.','Conservative upper/right and lower-left extensions, little central texture; selected profile1.','Too little right lower recovery.'],
      'v13':['Same exact arrays as v03 profile0.','Same exact arrays as v12 profile1.','Same exact arrays as v05 profile2.']}
    rows=json.loads((OUT/'candidate_ledger.json').read_text());reviews=[]
    for row in rows:
        for n,frame in enumerate(row['frames']):
            reviews.append(dict(candidate=row['name'],image=frame['id'],array_sha256=frame['array_sha256'],whole_image_viewed=True,
                finding=notes[row['name']][n],representative_crops_viewed=(row['name']=='v13')))
    report=dict(method='Actual tool image viewing of native whole overlays for all configurations; all nine pre-registered zoom panels for selected configuration. No GT metrics claimed.',
      reviews=reviews,selected='v13',selected_crops=json.loads((ROOT/'three_repair/roi_views.json').read_text()),
      limits={'im0004':'Low-contrast upper-central ends and intersections remain incomplete; image blur limits judgement.',
              'im0291':'Large inferior radial bright/dark fan is not assumed to be retinal vessels. Kept conservative; faint central lines remain uncertain.',
              'im0319':'Central horizontal faint vessel and tiny side branches remain incomplete. Some short candidate fragments are uncertain; no claim of perfect topology.'},
      all_images_improved=True,uniform_dilation_used=False,area_fill_observed=False,clinical_or_GT_accuracy='NOT_CLAIMED',
      old_labels='All preserved, including pre-existing artifacts; display-only fixes=0')
    (OUT/'visual_review.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
