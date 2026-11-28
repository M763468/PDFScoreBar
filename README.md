# PDFScoreBar

[日本語](README.ja.md)

PDFScoreBar adds measure numbers to PDF scores and provides a browser application to
review detections, record corrections, and generate a corrected final PDF.

The supported runtime is Linux with NVIDIA GPU support and Docker. Start with the
[User guide](docs/USER_GUIDE.md) for installation, model registration, PDF processing,
review, and troubleshooting. For a first run, obtain the stable `main` distribution,
prepare the host, build the image, run preflight and process
a PDF as described there. A validated extracted distribution can also be used directly.

The production model manifests in `models/` record the selected versions, SHA-256
identities, and ownership. No operator-supplied model import is required: since #522 the
detector no longer uses the external OMR-DLN measure detector.

Use `main` for the supported stable distribution and `develop` for active integration.
Release candidates and distributions include `DISTRIBUTION_PROVENANCE.json` with the
source commit and hashes for every shipped file. Contributions target `develop`; a
candidate must pass release acceptance before it is promoted to `main`. Changes merged
to `develop`, including this guide, do not reach `main` until a separate promotion.

## License

PDFScoreBar's first-party code, scripts, configuration, correction GUI, tests,
documentation, `models/sr_x4/` weights, and the owner's rights in the
`models/mmr/mmr_classifier_best.pth` and barline CNN (`issue296-d27-v1`,
`models/barline_cnn/manifest.json`) model weights are licensed under the GNU Affero
General Public License v3.0 or later (`AGPL-3.0-or-later`); see [LICENSE](LICENSE) and
[NOTICE](NOTICE). You may use, modify, and run PDFScoreBar, including commercially and as
a network service. If you convey it, or let users interact with a modified version over a
network, the AGPL requires you to offer those recipients or users the corresponding source
under the same license. It does not require publishing changes to GitHub or sending them to
this project.

Third-party code, model weights, and data are not relicensed (including any third-party
rights in initialization weights or training datasets). Vendored inference code under
`src/third_party/realesrgan_sr/` remains under Apache-2.0 and BSD-3-Clause, and the built
runtime includes AGPL-3.0 components (HOMR, PyMuPDF) and others under their own licenses;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Development-only evaluation/GT data
and score-derived test fixtures are excluded from the repository license (`NotLicensed`)
and from the minimal distribution; [NOTICE](NOTICE) and `REUSE.toml` list them.
