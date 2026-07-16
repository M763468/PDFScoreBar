# Accuracy-first mixed upstream route

## Purpose

Issue #245 is evaluated by final recovered accuracy, not by reproducing every historical
SR dependency before measuring the result.

This gate therefore keeps the already verified fresh public-upstream baseline HOMR and
combines it with the existing current full-68 artifacts for:

- SR-side HOMR;
- OMR-DLN;
- staff-mask selection;
- current hybrid consensus.

The resulting hybrid geometry is compared with the accepted historical hybrid geometry
before dense reconstruction or CNN evaluation is run.

## Inputs and safety checks

The preparation tool requires:

- the completed exact-match baseline report under
  `logs/issue245_fresh_upstream_full68_probe/`;
- the accepted historical inventory
  `logs/issue36_prep/20260208_bench_inventory.json`;
- one current full-68 inventory whose source totals exactly match the #244 run:

```text
baseline=10229
sr=4635
omr=5984
hybrid=4064
```

The accepted historical source totals are also checked:

```text
baseline=4381
sr=3356
omr=5820
hybrid=3312
```

A retained historical hybrid is comparison evidence only. It is not used as a mixed
route production input.

## Run the inexpensive source-level gate

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/prepare_accuracy_first_mixed_route.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_accuracy_first_mixed_route.py

bash tools/issue245/run_accuracy_first_mixed_route.sh \
  --force
```

If automatic discovery finds zero or multiple current inventories, rerun with the exact
path reported by the tool:

```bash
bash tools/issue245/run_accuracy_first_mixed_route.sh \
  --force \
  --current-inventory logs/<path-to-current-inventory>.json
```

## Outputs

```text
logs/issue245_accuracy_first_mixed_route/
  accuracy_first_mixed_route_report.json
  mixed_inventory.json
  mixed_hybrid/<score>/<page>_hybrid.json
```

## Decision gate

Review the aggregate hybrid comparison and the `Va_Prokofiev_Symphony1/page_001`
comparison first.

- Strong recovery: run the maintained Stage E dense/CNN pipeline with
  `mixed_inventory.json`, then evaluate against current GT.
- Weak recovery: use the page-level residuals to choose the minimum SR, OMR, or
  staff-mask ablation. Do not continue historical SR archaeology without a demonstrated
  accuracy need.

No production default is changed by this preparation tool.
