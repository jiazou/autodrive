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
out DETACHED at the `featureBranch` tip (the coordinator creates it with `git worktree add
--detach` and passes the frozen 40-hex tip SHA; the worktree is the subagent's cwd — it
holds phases 1..P-1's actual hardened code; for phase 1 it is `baseRef`). No code is
written here — design only.

## Step 1 — Author the phase's detailed design (design subagent)

Spawn a generic design subagent (the Agent tool) with **cwd = the detached
featureBranch-tip worktree** — the Agent tool does NOT set the subagent's cwd, so include
that ABSOLUTE worktree path AND the frozen 40-hex `featureBranch` tip SHA IN the prompt
(the subagent `cd`s to it as its FIRST ACTION so "the actual code in this worktree" it
reads is the REAL prior-phase code, not the main repo's tree). Pass file PATHS, never contents.

----- BEGIN SUBAGENT SCOPE -----
Produce the detailed design for phase `<P>`. Do NOT implement anything.

**FIRST ACTION: `cd` into the absolute worktree path you were given, then confirm
`git rev-parse HEAD` equals the frozen tip SHA you were passed. If the path is missing/wrong or the
`cd` fails or HEAD is not that SHA, STOP with `STATUS: BLOCKED — wrong cwd` instead of reading —
do NOT design against the wrong tree.** (The worktree is DETACHED at the `featureBranch` tip by
design, so there is no branch name to check — compare the SHA.) The Agent tool does NOT set your
cwd, so you begin in the
MAIN repo, and "the actual code in this worktree" below would otherwise read the wrong tree (the
main repo's `main`, not the run's real prior-phase code). You author only design docs into the
absolute `$RUN_DIR` (never edit repo code), so this is a READ-correctness guard, not a commit guard.

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
- **Pin depth per AC** (REQUIRED section): for each AC, fix at design time whether its
  test pin is **mutation-verified** (must red on deletion/partial-revert of the exact
  clause it guards — REQUIRED for gate-adjacent / fail-closed surfaces) or **smoke**
  (presence/shape). When the phase retires or moves pinned text, name token-sweep +
  green-full-suite as the default spec-pin-migration pattern (never per-line pin
  enumeration).
- ALSO write `$RUN_DIR/verify-design-claims-phase<P>.md` (a separate file, ALWAYS
  written — even when there is nothing to verify — and rewritten in place on revision
  legs): an ARTIFACT-shaped transcript (the commands run + their outputs) verifying
  EVERY citation, quoted snippet, and empirical claim this design makes; if it makes
  none, state that explicitly ("no citations / no quoted snippets / no empirical
  claims"). A classifier/matcher rule proposed by the design requires a runnable
  calibration script + its corpus + a stated imprecision budget shipped as design INPUT
  (paths named in the design). Never a prose "verified" attestation.
- **Slices** — **default to ONE slice for the phase.** A second slice is justified ONLY by
  (a) **fan-out** (built independently/in parallel, disjoint files) or (b) **staged risk** (a
  foundation whose correctness must verify before the next is safe to build on it). A linear
  chain is one slice unless it contains such a foundation. **Shared-contract rule:** if two
  candidate slices share a contract that is **new in this phase and co-authored by both** — a
  helper emitted/mirrored in both, a writer/reader pair, a value produced by one and consumed
  by another — they MUST be the **same slice** (a split here is where the contract fails to
  transfer). This does NOT apply to consuming an already-fixed interface from a prior
  slice/phase — that is a normal `deps:` edge and fan-out-eligible. Tests ride with the code
  they cover — never a slice of their own. For each slice give `acceptance:`
  (which criteria it satisfies), `owns:` (the files/dirs it will write — parallel slices MUST
  own DISJOINT files), and `deps:` (slice ids it needs first); for each slice beyond the first,
  `why:` names its justification (`fan-out` | `staged-risk: <what verifies first>`):
      - Slice <P>.1 <name> — acceptance: <criteria>; owns: <files>; deps: none
      - Slice <P>.2 <name> — acceptance: ...; owns: <disjoint files>; deps: <P>.1; why: fan-out

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision Principles
(see the harness `CLAUDE.md`). Record choices under a "Decisions" section + append to
`$RUN_DIR/decisions.md` with a Classification field. Out-of-scope discoveries →
`$RUN_DIR/followups.md`. Return the design path + a 3-line summary.
----- END SUBAGENT SCOPE -----

## Step 2 — Dual-voice review (converge; no human gate)

BEFORE dispatching round 1 (and again before every later round), CHECK
`$RUN_DIR/verify-design-claims-phase<P>.md` exists non-empty AND — on every round after
a revision leg — that its coverage statement is re-affirmed at the CURRENT revision
(the rewritten-in-place transcript re-affirms coverage against the revised design);
missing, empty, or coverage not re-affirmed at the current revision ⇒ send the author
back first (a pre-round-1 gate, not a review round — it consumes no counter).
Then run `/drive-review` scoped `phase <P> design` (`~/.claude/commands/drive-review.md`): a
Claude reviewer subagent AND `codex exec` both audit `$RUN_DIR/design-phase<P>.md` for P1s
(BLOCKING/MAJOR — an unbuildable interface, a slice dependency cycle, overlapping slice
ownership, or a slice contract that contradicts the real prior-phase code). If either flags
a P1, the design subagent revises and you re-run — loop until **converged** (neither voice
has an open P1), capped at 8 rounds (counter `phaseDesign[<P>].round`). A new-machinery P1
may exit to a revision leg that whole-chain-traces before re-entering, but the leg
CONSUMES a `phaseDesign[<P>].round` tick, mints NO new artifact family, and re-enters as a
FULL fresh dual-voice round (the revision leg also rewrites
`verify-design-claims-phase<P>.md` in place — no epoch suffix — and the pre-round check
re-fires). This is autonomous:
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
