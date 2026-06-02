# Claude Harness

Autonomous engineering pipeline for Claude Code. `/drive` carries a task through
the full lifecycle, using **gstack skills as the planning brain** and
**harness-owned stages for execution**, occupying the coordinator seat that
gstack skills normally reserve for the human.

- gstack `autoplan` + `plan-*-review` — autonomous planning/review brain
- gstack `codex` — cross-model second opinion (run via the codex CLI directly)
- Custom slash commands: `/drive`, `/plan`, `/implement`, `/review`, `/ship`
- autoplan's 6 Decision Principles + Mechanical/Taste/User-Challenge
  classification as the decision policy — overrides the default "ask the human"
  reflex, pausing only at genuine checkpoints

Roles (planner / implementer / reviewer) are generic `Agent` subagents — a
sequential single-coordinator pipeline, not a parallel-team framework. (Why not a
parallel-team framework: see `.harness/decisions.md` D1.)

## Workflow

    /drive <task>   -> runs the whole pipeline below, autonomously

    PLAN (gstack brain)
    0. Premises (human)
    1. /plan: author design + a ## Phases & Slices breakdown
       -> autoplan -> dual-voice design review converges -> [Gate A]

    EXECUTE (harness-owned) - for each PHASE in order:
    2. /implement per slice   (independent slices run in PARALLEL)
    3. /review per slice + phase-integration  (Claude subagent + codex; cap 8)
    4. verify (optional)      (qa-only / browse)
    5. /ship ONCE             -> [Gate B] -> push

Every review (design + code) runs a Claude reviewer subagent AND codex; a review
**converges** when neither flags a P1 (BLOCKING/MAJOR). Two human gates: **Gate A**
(direction) and **Gate B** (diff before push) — everything else is auto-decided
and logged. **See [`docs/flow.md`](docs/flow.md) for the full annotated diagram**
(phases, slices, every command invocation).

## Portable config — reproduce this Claude on a new machine

This repo is the canonical home of the operating rules (`OPERATING.md`). To make a
fresh machine behave the same:

1. Clone the repo:

       git clone https://github.com/jiazou/claude-harness ~/workspace/claude-harness

2. Point your global `~/CLAUDE.md` at the rules — one command, path auto-detected:

       ~/workspace/claude-harness/bin/install-operating-rules.sh

   It backs up any existing `~/CLAUDE.md`, then writes an `@import` of this repo's
   `OPERATING.md`. Operating rules now apply machine-wide; the `/drive` pipeline
   stays opt-in (active only inside this repo). Manual alternative: put
   `@<clone-path>/OPERATING.md` in `~/CLAUDE.md` yourself.

3. Install gstack + codex so `/drive` can run — see Setup below.

## Setup

1. Install gstack:

       git clone --single-branch --depth 1 \
         https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
         && cd ~/.claude/skills/gstack && ./setup

   (Provides `autoplan`, `plan-*-review`, `qa-only`, `browse`. The codex CLI is
   used directly by the review stage; install it separately if you want the
   cross-model pass — it degrades gracefully if absent.)

2. Start a session in this directory:

       claude

3. Run the pipeline:

       /drive <your task>

See `CLAUDE.md` for the full decision policy and invariants.

## Files

- `OPERATING.md` -- canonical, portable operating rules (imported by CLAUDE.md + global)
- `bin/install-operating-rules.sh` -- point a machine's global ~/CLAUDE.md at OPERATING.md
- `CLAUDE.md` -- imports OPERATING.md, plus the coordinator pipeline + decision policy
- `.claude/commands/drive.md` -- the autonomous lifecycle orchestrator
- `.claude/commands/{plan,implement,review,ship}.md` -- single-sourced stage runners
- `docs/flow.md` -- annotated execution-flow diagram (phases, slices, every command)
- `workflows/gstack-pipeline.md` -- the opt-in gstack review pipeline (alternative to /drive)
- `.harness/decisions.md` -- append-only autonomous-decision ledger
- `.harness/followups.md` -- append-only out-of-scope discoveries

## Generated artifacts (gitignored)

`.harness/design.md`, `.harness/task.md`, `.harness/review-*.md`,
`.harness/codex-review.md`, `.harness/codex-raw.log`, `.harness/verify.md`,
`.harness/state.json` are produced per task and not committed.
