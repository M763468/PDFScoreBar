# PDFScoreBar

PDFScoreBar adds measure numbers to PDF scores and provides a browser application to
review detections, record corrections, and generate a corrected final PDF.

The supported runtime is Linux with NVIDIA GPU support and Docker. Start with the
[User guide](docs/USER_GUIDE.md) for installation, model registration, PDF processing,
review, and troubleshooting.

The production model manifests in `models/` record the selected versions, SHA-256
identities, and ownership. OMR-DLN weights require a separate operator import.

Extracted release candidates and distributions include `DISTRIBUTION_PROVENANCE.json`
with the exact source commit and shipped file hashes. Until the first accepted
[minimal-distribution promotion](https://github.com/M763468/PDFScoreBar/issues/410),
repository `main` is historical; use `develop` for the maintained implementation.
Contributions target `develop`. A generated candidate still requires release acceptance.
