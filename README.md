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

Not used: wshobson `agent-teams` (it solves parallelism with file ownership, not
sequential stage-autonomy). Generic `Agent` subagents fill the roles.

## Workflow

    /drive <task>   -> runs the whole pipeline below, autonomously

    PLAN (gstack brain)                     EXECUTE (harness-owned)
    0. Premises (human)                     2. /implement  subagent + STATUS contract
    1. /plan: author rough design           3. /review     reviewer + codex CLI (loop ≤2)
       -> autoplan reviews -> [Gate A]      4. verify      qa-only / browse (optional)
                                            5. /ship       thin stage -> [Gate B] -> push

Two human gates: **Gate A** (approve direction, = autoplan's terminal gate) and
**Gate B** (approve diff before push). Plus dynamic Taste/User-Challenge
surfacing. Everything else is auto-decided and logged.

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
- `workflows/gstack-pipeline.md` -- the opt-in gstack review pipeline (alternative to /drive)
- `.harness/decisions.md` -- append-only autonomous-decision ledger
- `.harness/followups.md` -- append-only out-of-scope discoveries

## Generated artifacts (gitignored)

`.harness/design.md`, `.harness/task.md`, `.harness/review-*.md`,
`.harness/codex-review.md`, `.harness/codex-raw.log`, `.harness/verify.md`,
`.harness/state.json` are produced per task and not committed.
