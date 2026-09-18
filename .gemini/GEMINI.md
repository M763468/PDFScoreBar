# Gemini project guidance

Follow the repository root `AGENTS.md` as the project-specific instruction source.

- Do not add a second confirmation loop, mandatory planning mode, mandatory sub-agent delegation,
  or mandatory artifact logging on top of `AGENTS.md`.
- Use multimodal inspection when geometric/OMR work has relevant visual evidence and the evidence
  can materially test a hypothesis.
- Use current source, tests, Issues/PRs, `docs/ENVIRONMENTS.md`, and
  `docs/dev/VALIDATION_POLICY.md` as appropriate to the task.
- Do not treat this file as a project-status or roadmap record. Revalidate current branch, Issue/PR,
  environment, runtime, model, and evaluation state before relying on them.
- Cross-model consultation is optional and should be used only when the user requests it or when it
  clearly adds value to a difficult task. Local evidence remains authoritative.
