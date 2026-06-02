You are running the IMPLEMENT stage (Stage 2) for **one slice**. This stage is
harness-owned — it does NOT call any gstack skill. `/drive` invokes it per slice
and runs independent slices (disjoint owned files) in parallel.

`/drive` tells you which slice — its id (e.g. `1.2`). The slice's spec —
acceptance criteria, **owned files**, deps — lives in the `## Phases & Slices`
section of .harness/design.md. The design must exist; if not, stop and say to run
/plan first.

Read .harness/decisions.md for prior decisions. Check for the slice's latest
review (`.harness/review-<sliceId>-N.md`); if any exist you are addressing its
findings, not starting fresh.

Spawn a generic implementer subagent (the Agent tool) for this slice. Pass file
PATHS, never contents.

----- BEGIN SUBAGENT SCOPE -----
You are the implementer for slice <sliceId>. Read (current versions yourself):
- .harness/design.md          (the spec; find slice <sliceId> under "Phases &
                               Slices" for YOUR acceptance criteria, owned files,
                               and deps)
- .harness/decisions.md        (prior decisions to stay consistent with)
- .harness/review-<sliceId>-N.md + codex-review-<sliceId>.md  (IF they exist —
                               the cross-model findings for THIS slice; codex-only
                               findings live only in the codex file, so read it)

Implement ONLY this slice: satisfy its acceptance criteria, writing **only within
its owned files**. Do NOT touch files outside your ownership — other slices may be
running in parallel and own them. If you think you need a file you don't own, that
is a missing dependency or a shared interface → return NEEDS_CONTEXT; do not reach
in. Write at least one test per acceptance criterion. If a review exists, fix
every P1 (BLOCKING/MAJOR) from BOTH the review and codex files.

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision
Principles (see CLAUDE.md). Decide implementation details per codebase
conventions; don't return questions for normal choices. Flag spec deviations in
your return note + append to .harness/decisions.md (Classification field).
Out-of-scope discoveries → .harness/followups.md.

Return a STATUS contract as the FIRST line, then the changed-file list:
- `STATUS: DONE` — every acceptance criterion for this slice is met and its test
  passes. List changed files (all within your ownership). Add a "Flagged:" line
  only for deviations / Taste / User-Challenge decisions. No other rationale —
  the reviewer will not see this summary.
- `STATUS: BLOCKED — <reason>` — a non-decision blocker (missing tool, env
  failure, contradictory spec). State it + what would unblock it. Include any
  partial changes.
- `STATUS: NEEDS_CONTEXT — <question>` — a User-Challenge, OR you need a file
  outside your ownership (name it). State the one question; do not guess or reach
  outside your files.
----- END SUBAGENT SCOPE -----

After the subagent returns, act on STATUS:
- **DONE** → record the slice's changed files; `/drive` proceeds to the per-slice
  review for this slice.
- **BLOCKED** → STOP this slice (non-decision STOP); surface the blocker. Other
  independent slices in the phase keep running; the phase can't integrate until
  this resolves.
- **NEEDS_CONTEXT** → STOP this slice; surface via AskUserQuestion (if
  unavailable, report `BLOCKED — AUQ unavailable`).

Pass file paths only — never include the implementer's notes or rationale in the
slice's review prompt.
