# Agent Skill Lightweight Evaluation

Use this small repeatable protocol when adding or materially changing a repository Skill that is
intended to improve task outcomes. It is a manual comparison protocol; do not run it for every
ordinary code change.

## Cases

| Capability | Representative task | Negative control |
| --- | --- | --- |
| Issue implementation (`issue-solver`) | Given an Issue number, implement its scoped acceptance criteria and report policy-aligned validation. | Given a local coding request with all requirements supplied, make the change without fetching or commenting on any Issue. |
| PR feedback (`pr-refinement`) | Given a PR with one concrete requested change and one ambiguous suggestion, fetch context and implement only the concrete request. | Given a request to explain a PR, summarize it without changing files or posting a comment. |
| Backlog triage (`issue-triage`) | Rank a fixed set of open Issues with stated dependencies and explain the evidence for the order. | Given one specific Issue to implement, avoid running backlog triage. |
| Issue creation (`issue-creation`) | Given a request to create an Issue, use the repository template and branch policy to create it. | Given a request to draft an Issue, return a draft without writing to GitHub. |
| Issue post-mortem (`issue-post-mortem`) | Compare completed work against a fixed Issue's acceptance criteria and report gaps. | Given an implementation task, avoid post-mortem workflow. |
| OMR visual review (`visual-diff-viewer`) | From a fixed debug image directory, identify recent images and inspect them for the stated visual defect. | For a text-only code review with no visual evidence request, do not scan or copy images. |

## Modes and scoring

For each case, use the same prompt, repository snapshot, and available tools in three runs:

1. No Skill selected.
2. Skill explicitly selected and its `SKILL.md` provided.
3. Skill installed and only its description available for implicit selection.

Also run the listed negative control with Skills installed. Record task success, unnecessary commands
or file changes, validation coverage, turn/token use when available, and any external write or
sandbox-boundary error. Count a run as successful only when it meets the task's stated outcome and
does not violate repository policy. Compare results in a short table; retain the prompt, commit,
model/runtime, and result notes with the relevant Skill change or PR. A Skill that does not improve
success or reduce material errors should be narrowed or removed.
