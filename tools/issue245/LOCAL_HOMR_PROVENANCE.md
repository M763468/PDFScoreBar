# Local HOMR provenance inventory

## Boundary

The canonical page-001 source-ref probe completed for the PDFScoreBar commit immediately preceding the retained artifact run:

```text
bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7
2026-01-31T02:09:44+09:00
```

With HOMR `2c6c65b00c836feb167d08c2553acec36ef68401`, SegNet 308, ONNX Runtime GPU 1.22.0, the canonical image, and evaluator/default-thin fixed, current PDFScoreBar source and `bd6ae56` produced identical output:

```text
count=101
thin=21
historical match=85
historical-only=2
candidate-only=16
```

The generated detection JSON SHA-256 was identical for both variants:

```text
bae0f24ef9bd21a5c72ca1c37a1b29e39840f1e555f63835a1d8f9dfd0049ad7
```

Tracked PDFScoreBar evaluator/preprocessing source at artifact time is therefore excluded as the core HOMR drift source.

The remaining provenance boundary is the ignored local HOMR clone installed by historical `Dockerfile.sr_eval`:

```text
uv pip install ./external/homr
```

## Inventory scope

`collect_local_homr_provenance.py` performs a read-only inventory of:

- Issue #245 and main-clone `external/homr` and historical `homr` layout candidates;
- Git HEAD, branch, status, remotes, refs, reflogs, and unreachable commits;
- candidate commits dated around the January 2026 artifact run;
- HOMR source lines that identify SegNet/ONNX/checkpoint provenance;
- SegNet/HOMR model artifacts under those repositories and known HOMR/cache roots.

It does not inspect shell history or unrelated personal files. It does not check out a candidate, modify a repository, start inference, or select an artifact as a production input.

## Run

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/collect_local_homr_provenance.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_local_homr_provenance.py

python3 tools/issue245/collect_local_homr_provenance.py
```

The default output is:

```text
/home/masaki_muramatsu/ws_PDFScoreBar/logs/
  issue245_local_homr_provenance/
    local_homr_provenance.json
```

`git fsck --unreachable --no-reflogs` is included because deleted branch tips may still exist in the local object database. Skip it only if the repository is unexpectedly expensive to inspect:

```bash
python3 tools/issue245/collect_local_homr_provenance.py --skip-fsck
```

Additional known clone or cache roots can be supplied explicitly:

```bash
python3 tools/issue245/collect_local_homr_provenance.py \
  --root /path/to/another/homr \
  --cache-root /path/to/model/cache
```

## Decision gate

- If a January 2026 reflog/unreachable commit or model 301/303 file is found, preserve it first and compare its source/model hashes with the known revision matrix before inference.
- If only model 155 and 308 provenance remains, exact historical HOMR reconstruction is not recoverable from the current local Git/cache state; record that boundary and stop source archaeology.
- Do not run full-68 or change production defaults from inventory evidence.
