# Issue #245 baseline HOMR reconstruction result

The recovered local HOMR snapshot probe completed successfully on the canonical page-001 image.

## Exact focused result

```text
retained historical baseline: 87
reconstructed candidate:      87
matched:                      87
historical-only:               0
candidate-only:                0
semantic_equal:             true
```

All 21 thin-barline-tagged records were preserved. The comparison uses the established x-distance and vertical-overlap matching contract.

## Reproducing condition

```text
PDFScoreBar source: bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7
HOMR source:        864e2882f7a41afcf8f16654728a473ae56826d6
SegNet:             155 fp32
Transformer:        encoder/decoder 220 epoch 55
NumPy:              2.2.6
OpenCV headless:    4.12.0.88
ONNX Runtime GPU:   1.22.0
ORT provider:       CUDAExecutionProvider, CPUExecutionProvider
```

The reconstructed source and three model hashes were recorded and verified. The source was a clean Git archive; post-artifact dirty changes in the recovered checkout were excluded.

## Interpretation

The retained 87-record baseline is not dependent on a hidden PDFScoreBar source revision, consensus change, or retained detection JSON as a runtime input. Its page-001 geometry is explained by the older HOMR 864e288 / SegNet 155 route and its dependency layer.

The successful probe still copied model binaries from the recovered local HOMR checkout. Therefore it is exact reconstruction evidence, but not yet the final fresh public-upstream route required by Issue #245.

The next probe clones HOMR 864e288 from the public repository, calls that revision's public `download_weights()` implementation, verifies the downloaded model hashes, and repeats the 87/87 page-001 comparison. No local recovered source or model file is copied into that image.

Production defaults remain unchanged. Full-68 is not started until the public-upstream page-001 gate and a representative focused-page gate pass.
