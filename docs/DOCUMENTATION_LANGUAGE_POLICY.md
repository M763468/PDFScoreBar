# Documentation language and maintenance policy

[日本語](DOCUMENTATION_LANGUAGE_POLICY.ja.md)

This policy supports Epic #446. The [documentation inventory](DOCUMENTATION_INVENTORY.md)
tracks scope and missing translations; the [documentation guide](README.md) remains the
navigation entry. This policy does not promote future designs or historical evidence into
current runtime contracts.

## Authority and original language

Current source/tests/config and the latest accepted Issue/PR contract determine behavior.
A translation is a faithful reading path to the same contract, not an independent specification.
For an existing English document, keep its current path and English original authoritative
for translation. For an existing Japanese guide, keep the Japanese original authoritative
until an explicit editorial decision changes that designation. Mixed documents require a
content review and an explicitly designated original before a full counterpart is certified.
Do not select the original language from character counts alone.

When source and prose disagree, record the disputed section, relevant source/test, and
Issue/PR decision needed. Preserve the original acceptance contract; correct the original
through review and then synchronize the translation. Never resolve the difference by
silently changing production behavior or publishing a translated guarantee absent from
the original. `AGENTS.md` remains the single English operational instruction entry and
is excluded from the translation backlog (agent-only). Reconsider a human reading aid
only when a concrete future need arises; do not create another instruction hierarchy.

## Paths and navigation

Preserve existing original paths. Place translations beside the original using `.ja.md`
for Japanese or `.en.md` for English: `PIPELINE_ARCHITECTURE.md` pairs with
`PIPELINE_ARCHITECTURE.ja.md`; `dev/EXPERIMENT_MODEL_SELECTION.md` pairs with
`dev/EXPERIMENT_MODEL_SELECTION.en.md`. This also applies to root documents, except
the excluded `AGENTS.md`.
Do not move originals into a new directory hierarchy merely to translate them.

Add reciprocal language links once both files exist. Link to the matching-language target
when available; otherwise link to the original and label its language and untranslated
status. Never link to a planned, nonexistent counterpart. Translate headings and link
labels while preserving valid anchors; check fragment links after translating headings.
Keep identifiers, schema keys, flags, paths, hashes and command semantics unchanged.

## Translation record and completeness

Put a small record at the top of each counterpart:

- Original document: relative link and designated original language.
- Translation source: full Git commit containing the reviewed original. For a new pair
  in the same PR, use `same PR` plus the SHA-256 of the original file bytes; replace it
  with a committed source identity on a later synchronization.
- State: `draft`, `reviewed`, or `update required`; state who reviewed it in the PR.

A reviewed translation covers the entire document, including constraints, warnings,
exceptions, tables and examples. Summaries and partial translations must say what is
missing and remain draft. Machine-produced text requires the same completeness and
technical review. Evaluate (1) meaning, constraints and exceptions against the original
and (2) Japanese readability separately. Optional model-assisted language review, including
Gemini through Antigravity, is advisory; the primary author checks the technical meaning
of proposed edits against the original and source/tests. No particular model is a required
gate. A Japanese example or UI label in an English guide is not a Japanese
edition. Frozen experiment results retain their revision, scope and historical status.

## Update and review responsibility

The author changing an original owns checking every existing counterpart and its links
in the same PR. The reviewer checks meaning, completeness, source identity and links,
including the scope/authority labels. Prefer updating both languages together. If a
counterpart cannot be synchronized, mark it `update required`, identify affected sections,
link the tracking Issue/PR, and update the inventory; do not leave it labelled reviewed.

The source revision or digest records what was actually translated, not the repository's
latest commit. Compare changes to the original since that identity; an unrelated repository
commit does not make a translation stale. Update the identity after reviewing affected
sections. Missing counterparts remain explicit inventory backlog, not claimed coverage.

## Validation and distribution

For documentation-only work, run `git diff --check` and inspect changed local links,
anchors and command references. Follow [validation policy](dev/VALIDATION_POLICY.md)
when a change also affects executable behavior. Translation alone needs no GPU run or
full evaluation. A link check does not establish command execution or runtime correctness.

Preserve machine-readable contracts and the exact distribution manifest. Adding a
translation to `develop` does not include it in `main` or a minimal release. Distribution
changes require a separate scoped decision and relevant validation. Bulk historical
translation, physical reorganization and new design layers are separate Epic decisions.

## Repeatable static check

Run `python3 tools/verification/check_doc_translations.py` locally; the existing PR validation
workflow runs the same command and its dependency-free regression tests. It scans existing
root and `docs/**` files ending in `.ja.md` or `.en.md`. Missing planned counterparts stay
in the inventory; they are not required to exist by this check.

Each counterpart carries exactly one JSON comment (paths are relative to that file):

```text
<!-- translation: {"original":"guide.md","source":{"sha256":"<64 lowercase hex>"},"state":"draft"} -->
```

`source.sha256` represents the `same PR` form. Alternatively use
`"source":{"commit":"<40 lowercase hex>"}`. Keep the human-readable source record consistent
with this machine-readable record. Valid states are `draft`, `reviewed`, and `update required`.
The check validates metadata, the original file's existence and reciprocal Markdown links.
SHA-256 must match current original bytes. A commit identity compares that file's bytes at
the specified commit with the current original, not with HEAD's commit identity. Changed
originals require `update required`. Unavailable commit/path history reports `UNKNOWN`,
never synchronized; obtain the original revision before making a synchronization claim.
A shallow CI checkout may therefore report unknown provenance until history is available.

This tool checks syntax, references and provenance, not translation fidelity, naturalness,
or consistency with implementation. It does not duplicate general Markdown anchor checking.
