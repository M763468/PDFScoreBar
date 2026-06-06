# MMR RapidOCR provider mode

MMR OCR uses RapidOCR only in the MMR numbering path.

The default provider mode is `auto`:

- If ONNX Runtime exposes `CUDAExecutionProvider`, MMR RapidOCR is constructed with `det_use_cuda=True`, `cls_use_cuda=True`, and `rec_use_cuda=True`.
- Otherwise, MMR RapidOCR falls back to the default `RapidOCR()` constructor.

The helper also supports explicit modes for local checks:

- `auto`: default CUDA-if-available behavior.
- `cpu`: force the default `RapidOCR()` constructor.
- `cuda`: request CUDA kwargs and warn if `CUDAExecutionProvider` is not confirmed after construction.

This is limited to MMR OCR construction. It does not change HOMR title detection, SR, CNN scoring, or barline detection. The relevant validation scope is therefore local MMR construction and numbering-step tests rather than a full detector contract run.
