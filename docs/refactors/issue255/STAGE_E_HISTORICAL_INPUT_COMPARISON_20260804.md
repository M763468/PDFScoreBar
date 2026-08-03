# Issue #255 Stage E historical-input comparison

## Scope

This note records an offline comparison between the historical Stage E inventory inputs and the same-run fresh inputs used by `issue255_stage_e_focused_03`.

This remains a restoration-only investigation. It does not propose a new detector route, rescue rule, threshold, NMS policy, or bbox correction.

## Result

Both focused pages first diverge exactly at the dense raw candidate layer.

### Prokofiev page_004

```text
historical hybrid predictions: 107
fresh hybrid predictions:      155
exact shared boxes:               7

historical dense raw:           765
fresh dense raw:                956
exact shared boxes:             242
extra in fresh:                 714
missing from fresh:             523

historical clef-filtered:       659
fresh clef-filtered:            637
exact shared boxes:             202
extra in fresh:                 435
missing from fresh:             457
```

The two remaining historical false-negative boxes are absent from the fresh dense raw candidate layer:

```text
[2822, 621, 2826, 704]
[3187, 621, 3191, 704]
```

Fresh hybrid/raw instead contains differently shaped boxes at the same x positions, such as:

```text
[2821, 652, 2827, 753]
[3185, 647, 3194, 753]
```

### Shostakovich page_014

```text
historical hybrid predictions: 48
fresh hybrid predictions:      44
exact shared boxes:              0

historical dense raw:          291
fresh dense raw:               294
exact shared boxes:              0

historical clef-filtered:      169
fresh clef-filtered:           163
exact shared boxes:              0
```

Despite the complete exact-coordinate drift, the later reconstructed detector output still matches the historical accepted result at TP=48/FP=0/FN=0. This means exact candidate identity is not itself the final acceptance criterion, but it confirms that the same-run fresh upstream is not reproducing the historical inventory inputs.

## Boundary interpretation

The Issue #36 dense raw generator uses `band_source=row_stats`; in this mode it builds scan bands from `existing_boxes` and does not use the staff mask for raw generation. The image path is the same and the historical generation parameters, including `band_cluster_max_dist=25.0`, are already pinned in the reconstructed route.

Therefore the dense raw divergence is attributable to the different hybrid prediction inputs, not to a new Stage E filter/CNN problem.

The staff and clef masks also differ in dimensions and content and can affect the later filter layer, but they cannot explain the first dense raw divergence.

## Next restoration step

Inspect the retained historical run directories and the fresh source snapshot for the baseline, SR, OMR-DLN, hybrid, staff-mask, and clef-mask artifacts. The purpose is to identify the earliest upstream component that differs from the historical run.

No GPU inference is required for this inventory step. No alternative detection logic is added.
