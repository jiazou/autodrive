# Claude Harness

Autonomous engineering pipeline for Claude Code. `/drive` runs the task lifecycle
with **gstack for planning** and **harness-owned stages for execution**.

- gstack `autoplan` + `plan-*-review` — autonomous planning/review brain
- `codex` — cross-model second opinion (run via the codex CLI directly)
- Slash commands: `/drive`, `/plan`, `/implement`, `/review`, `/ship`
- Decision policy: autoplan's 6 principles + Mechanical/Taste/User-Challenge
  classification (auto-decides; pauses only at the gates)

Roles are generic `Agent` subagents (no parallel-team framework — see
`.harness/decisions.md` D1).

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

Two human gates (A: direction, B: diff before push); every review is dual-voice
(Claude + codex), converging when neither flags a P1. Full annotated diagram +
decision policy: **[`docs/flow.md`](docs/flow.md)** and `CLAUDE.md`.

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

## Run artifacts (not committed)

Per-run state — design, `state.json`, review files, worktrees — lives in an
external run dir `~/.claude/harness-runs/<run-id>/`. The committed `.harness/`
holds only the cross-task ledgers (`decisions.md`, `followups.md`).
