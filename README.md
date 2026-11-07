# PDFScoreBar

[日本語](README.ja.md)

PDFScoreBar adds measure numbers to PDF scores and provides a browser application to
review detections, record corrections, and generate a corrected final PDF.

The supported runtime is Linux with NVIDIA GPU support and Docker. Start with the
[User guide](docs/USER_GUIDE.md) for installation, model registration, PDF processing,
review, and troubleshooting. For a first run, obtain the stable `main` distribution,
prepare the host, build the image, import the external model, run preflight and process
a PDF as described there. A validated extracted distribution can also be used directly.

The production model manifests in `models/` record the selected versions, SHA-256
identities, and ownership. OMR-DLN weights require a separate operator import.

Use `main` for the supported stable distribution and `develop` for active integration.
Release candidates and distributions include `DISTRIBUTION_PROVENANCE.json` with the
source commit and hashes for every shipped file. Contributions target `develop`; a
candidate must pass release acceptance before it is promoted to `main`. Changes merged
to `develop`, including this guide, do not reach `main` until a separate promotion.

## License

PDFScoreBar's first-party code, scripts, configuration, correction GUI, tests, and
documentation are licensed under the GNU Affero General Public License v3.0 or later
(`AGPL-3.0-or-later`); see [LICENSE](LICENSE) and [NOTICE](NOTICE). You may use, modify,
and run PDFScoreBar, including commercially and as a network service. If you convey it, or
let users interact with a modified version over a network, the AGPL requires you to offer
those recipients or users the corresponding source under the same license. It does not
require publishing changes to GitHub or sending them to this project.

Third-party code, model weights, and data are not relicensed. The built runtime includes
AGPL-3.0 components (HOMR, Ultralytics, PyMuPDF) and others under their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The MMR model weight, evaluation/GT data,
and score-derived test fixtures are excluded from the repository license until their rights
are confirmed; [NOTICE](NOTICE) and `REUSE.toml` list them.
