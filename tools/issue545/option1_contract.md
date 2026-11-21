# Issue #545 option-1 evaluation contract (fixed 2026-11-21 before any candidate result)

Inputs (production route, retained jobs; each job's own numbering_base + current-x4 HOMR staff mask + page PNG):
- E2-new : logs/issue535/develop_f49a34e8_25 (3 eval2 scores, 25 pages, first-party SR)
- E2-old : logs/issue535/linux_eval2_d0d09be0 (same 25 pages, Real-ESRGAN SR)
- F43-new: logs/issue535/linux_e2e_b38b81bf (Sym5 + Prok5, first-party SR; pages scored only where reviewed GT exists)
- P5-old : logs/issue535/linux_e2e_f5e3dbf8 (Prok5, Real-ESRGAN SR)
GT/scorer: tools/issue415/reviewed_gt.json, tools/issue264 score_overrides. MMR: production MMRProcessor, CUDA,
defaults (threshold 0.5, rescue 0.1). No classifier/OCR/rescue/veto threshold changes.

Candidates (fixed):
- P0  production (x4 staff y)
- C1  phase_a_y: MMR staff y from Phase-A numbering_base (SR-independent)
- C2  union_y: staff y = union(Phase-A, x4)
- C3u dual-view merge of P0 and C1: agree -> keep; disagree -> higher OCR score (tie -> P0); singleton -> keep
- C3i dual-view merge of P0 and C1: agree -> keep; disagree -> higher OCR score (tie -> P0); singleton -> drop
- F   (option 2, report only / contract change) P0 without overrides whose OCR score <= 0

Pass (option 1):
1. E2-new: TP >= 48, FN <= 7, wrong <= 5, FP <= 0 (#545 acceptance: baseline d0d09be0 or better).
2. E2-old: not worse than P0 on E2-old in any of TP/FN/wrong/FP (robust across SR).
3. F43-new: TP >= P0, FP <= P0, wrong <= P0, FN <= P0 on the same input.
4. P5-old : TP >= P0, FP <= P0, wrong <= P0, FN <= P0.
5. No accepted negative-score override on E2-new (#545 acceptance 3) - reported for every candidate.
