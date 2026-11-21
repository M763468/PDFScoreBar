# Issue #545 MMR regression evaluation tools

Evaluation-only MMR replays for the #533 SR-replacement regression. Production code is unchanged;
candidate C1 (Phase-A staff y for MMR) is recorded here as an evaluated, not adopted, option.

| Tool | Purpose |
| --- | --- |
| `replay_mmr_swap.py` | Swap Phase-A `numbering_base` and current-x4 HOMR staff mask between two retained jobs, rerun production MMR, score against `tools/issue415/reviewed_gt.json` |
| `replay_mmr_variants.py` | Replay staff-y candidates (P0 production, C1 Phase-A y, C2 union y, C3u/C3i dual-view merges, F score>0 floor) on retained production jobs |
| `downstream_numbering.py` | Rebuild final measure numbers per candidate from a variant report and the retained jobs; compare with GT-implied numbers and #415 row-start samples; report local errors, propagation spans and recovery points |
| `option1_contract.md` | Evaluation contract fixed before candidate results |

Run inside the image the jobs were evaluated with, with the manager checkout and this worktree mounted
at their host paths and `--gpus all`, for example:

```bash
docker run --rm --gpus all --user 1000:1000 -e HOME=/tmp -v "$WT:$WT" -v "$M/logs:$M/logs" -w "$WT" \
  pdfscore_issue535_develop:f49a34e8 python3 tools/issue545/replay_mmr_variants.py \
  --set E2-new=$M/logs/issue535/develop_f49a34e8_25/out:Shostakovich-Festival_Overture_Va,Sibelius-Violin_Concerto-Viola,Va_Prokofiev_Symphony1 \
  --out $M/logs/issue545/mmr_robust/<run>/report.json
```

## Results (2026-11-21, code `f49a34e8`, TP/FN/wrong/FP)

- Attribution (`replay_mmr_swap.py`): the regression follows the staff mask only
  (baseline mask 48/7/5/0, develop mask 46/7/7/1, independent of `numbering_base`).
- Option 1 (`replay_mmr_variants.py`): no candidate passes the contract. C1 is SR-invariant on eval2
  (48/9/3/0 with both SRs, no negative-score acceptance) but trades wrong for FN and adds one FP on
  Sym5/Prok5 (115/0/2/3 vs P0 114/0/3/2). Adoption is an owner decision.

The committed harnesses are the evaluated scripts after import formatting (Ruff) and, for
`replay_mmr_variants.py`, resolving the code root from the file path instead of `PDFSCORE_CODE`; the
`runner_sha256` values in the round-1 reports refer to the pre-format bytes copied under `logs/issue545/mmr_robust/`.
Round-2 reports were produced by the committed `replay_mmr_variants.py` (`logs/issue545/mmr_round2/runner_sha256.txt`).

## Round 2 (review follow-up, 2026-11-21)

Same inputs, P0/C1 re-run on origin/develop `11efed71` and PR #538 head `480d7bc7`
(`PDFSCORE_CODE` selects the code tree). With PR #538 code (#535 narrow-measure guard), new-SR
measures whose final number differs from the GT-implied number drop from 1983 to 906 of 3288
(P0 vs C1). The largest offset drops from 1106 to 11. Without the guard (develop), C1 regresses
Prok5. Round-1 C1 FAIL stays. Evidence and contract: `logs/issue545/mmr_round2/`.

Retained evidence (git-ignored): `logs/issue545/mmr_swap_replay/`, `logs/issue545/mmr_robust/`.
Discussion: Issue #545 comments.
