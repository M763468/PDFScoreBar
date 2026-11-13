# Issue #506 Windows-native PoC tooling (experiment only)

Not production code. Reproduces the isolated Windows-native PoC described in
Issue #506: an isolated uv/Python 3.12 runtime (`env.sh`, `install_runtime.sh`),
native runs of the PoC source (`run_native.sh`), runtime probes (`probe_*.py`),
Docker baseline helpers for WSL (`wsl_*.sh`), and semantic/PDF comparison
(`compare_semantic.py`, `compare_pdf_render.py`, `pdf_diff_regions.py`).

`shim/` holds PoC-only `fcntl`/`os.O_NOFOLLOW` emulation for the review
application on Windows; it is injected through `PYTHONPATH` and is not a
production lock implementation.

Paths are fixed to the PoC machine (`S:\workspace\ws_PDFScoreBar\issue506_poc`).
