# `realesrgan_sr` — vendored Real-ESRGAN inference subset

PDFScoreBar uses Real-ESRGAN only for inference with the released
`RealESRGAN_x4plus` / `RealESRGAN_x2plus` weights. Installing the upstream
`realesrgan` distribution also installed `basicsr`, `gfpgan` and `facexlib`.
Importing `basicsr.archs.rrdbnet_arch` loads the whole `basicsr.archs` package,
including `stylegan2_arch` and `basicsr.ops` (`fused_act`, `upfirdn2d`), whose
StyleGAN2-derived code is covered by the **NVIDIA Source Code License-NC**
(non-commercial). `gfpgan` also contains NVIDIA-NC and CC BY-NC-SA 4.0 parts.

Issue #533 replaces those distributions with the two pieces PDFScoreBar runs:

| File | Upstream source | Upstream license | License text |
| --- | --- | --- | --- |
| `rrdbnet.py` | BasicSR 1.4.2 `basicsr/archs/rrdbnet_arch.py` and three helpers from `basicsr/archs/arch_util.py` | Apache-2.0 | `LICENSE-BasicSR.txt` |
| `upsampler.py` | Real-ESRGAN `a4abfb2979a7bbff3f69f58f58ae324608821e27` `realesrgan/utils.py` (`RealESRGANer`) | BSD-3-Clause | `LICENSE-Real-ESRGAN.txt` |

`LICENSE-BasicSR.txt` is the Apache-2.0 text shipped in the BasicSR 1.4.2 wheel;
`LICENSE-Real-ESRGAN.txt` is the BSD-3-Clause text shipped in the pinned
Real-ESRGAN distribution. No file from `basicsr/ops`, `stylegan2_arch`, GFPGAN or
facexlib is copied. Each vendored file states its modifications in its header.

## Equivalence contract

The layer structure, parameter names and forward operations are unchanged, so
the released state dicts load with `strict=True`. Issue #533 validated byte-identical
SR outputs against the upstream packages on the same GPU/image before removing
them; see `docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md` §0.10.

## Weights

The Real-ESRGAN release weights are not used. The network runs the first-party
`models/sr_x4` checkpoint, trained from random initialization on procedural synthetic
notation (Issue #533; see `models/sr_x4/manifest.json` and
`docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md` §0.11). The vendored code above remains under
its upstream Apache-2.0 / BSD-3-Clause licenses.
