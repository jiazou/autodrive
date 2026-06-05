---
description: IMPLEMENT stage (Stage 2) of /drive — implements one slice in its own worktree against the design spec, slice-local tests green, commits to the slice branch. Usually invoked by /drive.
argument-hint: <slice id> (within an existing run)
---
You are running the IMPLEMENT stage (Stage 2) for **one slice**. Harness-owned —
no gstack skill. `/drive` invokes it per slice; independent slices run in parallel,
each in **its own git worktree**.

`/drive` passes: the slice id (e.g. `1.2`), the absolute **worktree path** (the
subagent's cwd), the slice **branch** (`slice/<runId>/<id>`), and `$RUN_DIR`
(absolute path to the run dir — all artifacts live there). The slice's spec
(acceptance criteria, **owned files**, deps) is in its phase's detailed design
`$RUN_DIR/design-phase<P>.md` (`<P>` = the slice's phase prefix) under `Slices`.

Check for the slice's latest review (`$RUN_DIR/review-<sliceId>-N.md`); if any
exist you are addressing its findings, not starting fresh.

Spawn a generic implementer subagent (the Agent tool) with **cwd = the slice
worktree**. Pass file PATHS, never contents.

----- BEGIN SUBAGENT SCOPE -----
You are the implementer for slice <sliceId>. Your cwd is its git worktree on branch
`slice/<runId>/<id>`. **Code paths are relative to this worktree; artifact paths are
the absolute `$RUN_DIR`** (never edit code via absolute paths to the main repo —
that hits the wrong tree). Read (current versions yourself):
- $RUN_DIR/design-phase<P>.md (`<P>` = your slice's phase prefix; find slice <sliceId>
                               under "Slices" for YOUR acceptance criteria, owned files,
                               deps — plus the phase's interfaces and edge cases)
- $RUN_DIR/design.md          (the high-level goal/approach/phase, for context)
- $RUN_DIR/decisions.md        (prior decisions to stay consistent with)
- $RUN_DIR/review-<sliceId>-N.md + codex-review-<sliceId>.md  (IF they exist — the
                               cross-model findings for THIS slice; codex-only
                               findings live only in the codex file, so read it)

**FIRST — validate your assumptions against reality, before writing any code.** Your
slice's spec rests on assumptions about what the slices it depends on (and its siblings)
produce; by the time you run, those may have changed. Check the cheap signals already
present — `$RUN_DIR/decisions.md`, the ACTUAL code + comments of your completed dependency
slices in this worktree, and the design docs — and judge whether your assumptions hold:
- **hold** → implement as planned.
- **minor drift** (a dependency's real interface differs slightly) → adapt to the real
  code; note it in your return + append to `$RUN_DIR/decisions.md`.
- **BIG divergence** (the contract your slice was designed against is genuinely broken —
  the phase design no longer matches reality) → do NOT improvise on a broken assumption;
  return `STATUS: REDESIGN — <reason>` (below).

Implement ONLY this slice: satisfy its acceptance criteria, writing **only within
its owned files** (in this worktree). Do NOT touch files outside your ownership —
parallel slices own them; if you need one, the phase design's slice boundaries are wrong
→ return `STATUS: REDESIGN — <reason>`, do not reach in. Write ≥1 test per acceptance
criterion and **run the slice-local tests** until green. If a review exists, fix
every P1 (BLOCKING/MAJOR) from BOTH the review and codex files. **Commit your work
to the slice branch** (`git add -A && git commit`) before returning.

Decision protocol (overrides "ask the human") — apply the 6 Decision Principles
(see the harness `CLAUDE.md`). Decide implementation details per conventions; don't return
questions for normal choices. Flag spec deviations in your return note + append to
`$RUN_DIR/decisions.md` (Classification field). Out-of-scope discoveries →
`$RUN_DIR/followups.md`.

Return a STATUS contract as the FIRST line, then the changed-file list:
- `STATUS: DONE` — every acceptance criterion met, its test passes, and the work is
  committed to the slice branch. List changed files (all within your ownership).
  Add a "Flagged:" line only for deviations / Taste / User-Challenge. No other
  rationale — the reviewer won't see this summary.
- `STATUS: BLOCKED — <reason>` — a non-decision blocker (missing tool, env failure,
  contradictory spec). State it + what would unblock it.
- `STATUS: REDESIGN — <reason>` — a BIG divergence between your slice's assumptions and
  the real prior-slice code/contracts, OR you need a file outside your ownership (the
  phase design's slice boundaries are wrong). State the divergence; do not improvise.
- `STATUS: NEEDS_CONTEXT — <question>` — a genuine User-Challenge only. State the one
  question; do not guess or reach out.
----- END SUBAGENT SCOPE -----

After the subagent returns, act on STATUS:
- **DONE** → `step = awaiting_review`; `/drive` runs the per-slice REVIEW on the
  slice branch.
- **BLOCKED** → `step = blocked`, STOP this slice; surface. Other in-flight slices
  continue; the phase can't integrate until it resolves.
- **REDESIGN** → STOP this slice; `/drive` re-runs the phase's detailed design
  (`/drive-design phase <P>`) to re-converge against reality, then re-derives the affected
  slices and re-dispatches. (This is the slice-check escalation — it subsumes the old
  plan-amendment path: a real contract break triggers a *reviewed* re-design, not a
  silent amend.)
- **NEEDS_CONTEXT** → STOP this slice; surface via AskUserQuestion (else
  `BLOCKED — AUQ unavailable`).

Never include the implementer's notes/rationale in the slice's review prompt.
