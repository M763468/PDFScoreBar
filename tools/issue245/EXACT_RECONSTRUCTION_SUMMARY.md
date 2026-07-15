# Exact reconstruction summary

The canonical page-001 baseline HOMR output has been reproduced exactly from fresh image input with a reconstructed source/model/runtime stack.

```text
retained historical records: 87
reconstructed records:       87
matched records:             87
retained-only:                0
reconstructed-only:           0
semantic_equal:            true
```

The exact reproducing stack is:

```text
PDFScoreBar bd6ae56
HOMR 864e288
SegNet 155 fp32
Transformer encoder/decoder 220 epoch 55
NumPy 2.2.6
OpenCV headless 4.12.0.88
ONNX Runtime GPU 1.22.0
CUDAExecutionProvider selected
```

This result isolates the historical/current baseline drift to the HOMR source/model/runtime boundary. It excludes current versus historical tracked PDFScoreBar evaluator/preprocessing source as the primary cause.

The successful reconstruction used recovered local model files only as model inputs to the experimental image. A separate fresh-upstream probe now downloads the same models from HOMR's public release route and verifies their hashes before inference. Passing that probe is required before representative-page or full-68 work.
