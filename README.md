# PDFScoreBar

PDFScoreBar adds measure numbers to PDF scores and provides a browser application to
review detections, record corrections, and generate a corrected final PDF.

The supported runtime is Linux with NVIDIA GPU support and Docker. Start with the
[User guide](docs/USER_GUIDE.md) for installation, model registration, PDF processing,
review, and troubleshooting.

The production model manifests in `models/` record the selected versions, SHA-256
identities, and ownership. OMR-DLN weights require a separate operator import.

Use `main` for the supported stable distribution and `develop` for active integration.
Release candidates and distributions include `DISTRIBUTION_PROVENANCE.json` with the
source commit and hashes for every shipped file. Contributions target `develop`; a
candidate must pass release acceptance before it is promoted to `main`.
