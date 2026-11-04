# MMR RapidOCR provider mode

[日本語](MMR_RAPIDOCR_PROVIDER.ja.md)

MMR OCR uses RapidOCR only in the MMR numbering path.

The default provider mode is `auto`:

- If ONNX Runtime exposes `CUDAExecutionProvider`, MMR RapidOCR is constructed with `det_use_cuda=True`, `cls_use_cuda=True`, and `rec_use_cuda=True`.
- Otherwise, MMR RapidOCR falls back to the default `RapidOCR()` constructor.

The helper also supports explicit modes for local checks:

- `auto`: default CUDA-if-available behavior.
- `cpu`: force the default `RapidOCR()` constructor.
- `cuda`: request CUDA kwargs and warn if `CUDAExecutionProvider` is not confirmed after construction.

Unknown mode values are rejected. The helper is `src/measure_numbering/rapidocr_provider.py`.

## Where the mode is selected

- The main pipeline's MMR batch (`src/pipeline/steps/numbering_phases.py`) reads `mmr.rapidocr_provider`, defaulting to `auto`.
- The selective MMR rerun used when applying corrections (`src/pipeline/review/apply_corrections.py`) reads `mmr.rapidocr_provider` from the source run's config, defaulting to `auto`.

This is limited to MMR OCR construction. It does not change HOMR title detection, SR, CNN scoring, or barline detection. The relevant validation scope is therefore local MMR construction and numbering-step tests rather than a full detector contract run.
