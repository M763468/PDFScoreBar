# 2025-10-06 PDF→PNG Parameter Sweep (page_3)

This experiment renders `data/evaluation/pdfs/おもちゃの交響曲_bass.pdf` page 3 with varying DPI and interpolation settings via the new `src/pdf_to_images.py` helper. All images are resized back to the baseline height 792 px (width 593 px) to keep detector input resolutions consistent. Rendered assets live under `data/workbench/pdf_render/20251006T2038/`.

Homr and oemer were re-evaluated against `data/evaluation/annotations/page_003/boxes_sorted.json` using the generated images. Runs were executed on CPU (no CUDA providers available), so timings are not comparable to container GPU runs.

## Image Variants

| Variant | Render Params | Image Path |
| --- | --- | --- |
| Baseline | legacy image (`data/evaluation/images/page_3.png`) | — |
| dpi144_area | `dpi=144`, resize→792 px, `cv2.INTER_AREA` | `data/workbench/pdf_render/20251006T2038/dpi144_area/page_003.png` |
| dpi200_area | `dpi=200`, resize→792 px, `cv2.INTER_AREA` | `data/workbench/pdf_render/20251006T2038/dpi200_area/page_003.png` |
| dpi288_area | `dpi=288`, resize→792 px, `cv2.INTER_AREA` | `data/workbench/pdf_render/20251006T2038/dpi288_area/page_003.png` |
| dpi288_linear | `dpi=288`, resize→792 px, `cv2.INTER_LINEAR` | `data/workbench/pdf_render/20251006T2038/dpi288_linear/page_003.png` |
| dpi288_lanczos | `dpi=288`, resize→792 px, `cv2.INTER_LANCZOS4` | `data/workbench/pdf_render/20251006T2038/dpi288_lanczos/page_003.png` |

## homr Metrics

| Variant | Run ID | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | `20251006T015717JST_official-gpu` | 95 | 2 | 57 | 0.9794 | 0.6250 | 0.7631 |
| dpi144_area | `20251006T212333JST_pdfdpi144-area` | 91 | 4 | 61 | 0.9579 | 0.5987 | 0.7368 |
| dpi200_area | `20251006T212518JST_pdfdpi200-area` | **101** | 4 | 51 | 0.9619 | **0.6645** | **0.7860** |
| dpi288_area | `20251006T212701JST_pdfdpi288-area` | 94 | 6 | 58 | 0.9400 | 0.6184 | 0.7460 |
| dpi288_linear | `20251006T212841JST_pdfdpi288-linear` | 94 | 4 | 58 | 0.9592 | 0.6184 | 0.7520 |
| dpi288_lanczos | `20251006T212930JST_pdfdpi288-lanczos` | 83 | 4 | 69 | 0.9540 | 0.5461 | 0.6946 |

## oemer Metrics

| Variant | Run ID (output stored under `output/oemer_eval_tests/`) | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | `20251006T013456JST_baseline` | 120 | 2 | 32 | 0.9836 | 0.7895 | 0.8759 |
| dpi144_area | `20251006T213809JST_pdfdpi144-area` | 124 | 5 | 28 | 0.9612 | 0.8158 | 0.8826 |
| dpi200_area | `20251006T214400JST_pdfdpi200-area` | **128** | 2 | **24** | **0.9846** | **0.8421** | **0.9078** |
| dpi288_area | `20251006T214947JST_pdfdpi288-area` | 126 | 3 | 26 | 0.9767 | 0.8289 | 0.8968 |
| dpi288_linear | `20251006T215532JST_pdfdpi288-linear` | 104 | 1 | 48 | 0.9905 | 0.6842 | 0.8093 |
| dpi288_lanczos | `20251006T220803JST_pdfdpi288-lanczos` | 86 | 1 | 66 | 0.9885 | 0.5658 | 0.7197 |

## Observations

- Rendering at 200 DPI and downsampling with area interpolation provided the best overall gains: homr F1 +0.023 (0.786 vs. 0.763) and oemer F1 +0.032 (0.908 vs. 0.876) with modest FP changes.
- Higher DPI with the same interpolation (`dpi288_area`) still improves oemer performance but homr recall regresses slightly compared to the 200 DPI setting, suggesting diminishing returns beyond ~200 DPI for the current pipeline.
- Interpolation choice matters: linear/lanczos at 288 DPI kept precision high but significantly reduced recall, likely due to over-sharpened staff lines triggering oemer symbol failures and homr staff grouping collapse.
- The lanczos variant also triggered repeated MusicXML build failures (now caught and logged) and produced the weakest metrics for both detectors.
- CPU execution (no CUDA providers) is markedly slower; each oemer run took ~5 minutes. Profiles and provider dumps remain under the run directories for reproducibility.

## Artifacts

- homr outputs: `logs/homr_eval/20251006T21*JST_pdfdpi*/`
- oemer outputs: `output/oemer_eval_tests/20251006T21*JST_pdfdpi*/`
- Rendered PNGs: `data/workbench/pdf_render/20251006T2038/`

