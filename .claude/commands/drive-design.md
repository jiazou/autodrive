---
description: DESIGN stage (Stage 1.5) of /drive — per-phase detailed design, authored just before a phase implements, against the REAL code earlier phases produced: interfaces, edge cases, and the phase's slice breakdown. Dual-voice reviewed; no human gate. Usually invoked by /drive.
argument-hint: phase <P> (within an existing run)
---
You are running the per-phase DESIGN stage (Stage 1.5) for **one phase**. The whole-run
`design.md` is high-level (goal · approach · phases); this stage produces the **detailed
design for phase `<P>`** — its interfaces, edge cases, and slice breakdown — just before
the phase implements, so the detail is drafted against the **real code earlier phases
produced**, not a speculative up-front guess.

`/drive` passes: the phase `<P>`, `$RUN_DIR`, and the absolute path of a worktree checked
out on `featureBranch` (the subagent's cwd — it holds phases 1..P-1's actual hardened
code; for phase 1 it is `baseRef`). No code is written here — design only.

## Step 1 — Author the phase's detailed design (design subagent)

Spawn a generic design subagent (the Agent tool) with **cwd = the featureBranch worktree**.
Pass file PATHS, never contents.

----- BEGIN SUBAGENT SCOPE -----
Produce the detailed design for phase `<P>`. Do NOT implement anything.

Read (current versions yourself):
- $RUN_DIR/design.md       (the high-level design — find phase `<P>`'s scope/boundary/goal)
- $RUN_DIR/decisions.md    (prior decisions to stay consistent with)
- the actual code in this worktree (`featureBranch`) — the REAL interfaces, contracts, and
  comments earlier phases produced. Design phase `<P>` AGAINST this reality; where it
  differs from the high-level design's assumptions, the real code wins — note the divergence.

Write `$RUN_DIR/design-phase<P>.md` covering, for phase `<P>` ONLY:
- Interfaces (exact signatures, types, endpoints this phase adds or changes)
- Edge cases and failure modes (at least 5, with intended behavior)
- Acceptance criteria (numbered, testable)
- **Slices** — the independent units within this phase. For each slice give `acceptance:`
  (which criteria it satisfies), `owns:` (the files/dirs it will write — slices intended to
  run in parallel MUST own DISJOINT files), and `deps:` (other slice ids it needs first):
      - Slice <P>.1 <name> — acceptance: <criteria>; owns: <files>; deps: none
      - Slice <P>.2 <name> — acceptance: ...; owns: <disjoint files>; deps: <P>.1

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision Principles
(see the harness `CLAUDE.md`). Record choices under a "Decisions" section + append to
`$RUN_DIR/decisions.md` with a Classification field. Out-of-scope discoveries →
`$RUN_DIR/followups.md`. Return the design path + a 3-line summary.
----- END SUBAGENT SCOPE -----

## Step 2 — Dual-voice review (converge; no human gate)

Run `/drive-review` scoped `phase <P> design` (`~/.claude/commands/drive-review.md`): a
Claude reviewer subagent AND `codex exec` both audit `$RUN_DIR/design-phase<P>.md` for P1s
(BLOCKING/MAJOR — an unbuildable interface, a slice dependency cycle, overlapping slice
ownership, or a slice contract that contradicts the real prior-phase code). If either flags
a P1, the design subagent revises and you re-run — loop until **converged** (neither voice
has an open P1), capped at 8 rounds (counter `phaseDesign[<P>].round`). This is autonomous:
there is **no new human gate** — Gate A already approved the shape.

## After this stage

- **Converged** → **merge** the `Slices` breakdown into `state.slices` for phase `<P>`'s
  ids (a re-design after a `REDESIGN` must NOT clobber slices already built this phase, but
  MUST re-build any slice whose design changed). A slice is built against BOTH its own bullet
  AND the phase's `Interfaces`/`Edge cases` sections, so:
  - If this re-design changed the phase's `Interfaces` or `Edge cases` sections vs the prior
    `design-phase<P>.md`, **re-queue every not-yet-assembled slice** of the phase (any may
    depend on the changed contract) → `{step:"queued", reviewCount:0, owns, deps}`.
  - Otherwise, per id: an **unchanged bullet** (`owns`/`deps`/`acceptance`) → KEEP as-is
    (preserve `step`/`reviewCount`; an already-`converged` slice stays converged); a **new or
    bullet-changed** id → re-queue; an id **no longer in the breakdown** → drop it (its
    worktree/branch cleanup is `/drive`'s job).
  Then set `state.phaseDesign[<P>].status = "converged"` (the `round` counter is owned by
  `/drive-review`, not written here). `/drive` proceeds to freeze + dispatch phase `<P>`.
- **Cannot converge in 8 rounds** → STOP (surface what each voice asserts) via the Present
  human pause routine.

Do not begin implementation on this command.
