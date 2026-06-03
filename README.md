# Claude Harness

Autonomous engineering pipeline for Claude Code. `/drive` runs the task lifecycle
with **gstack for planning** and **harness-owned stages for execution**.

- gstack `autoplan` + `plan-*-review` — autonomous planning/review brain
- `codex` — cross-model second opinion (run via the codex CLI directly)
- Slash commands: `/drive`, `/drive-plan`, `/drive-implement`, `/drive-review`, `/drive-harden`, `/drive-ship`
- Decision policy: autoplan's 6 principles + Mechanical/Taste/User-Challenge
  classification (auto-decides; pauses only at the gates)

Roles are generic `Agent` subagents (no parallel-team framework — see
`.harness/decisions.md` D1).

This repo also houses a second, separate harness: **[Mission Control](mission-control/README.md)**
— a personal operating layer that tracks Claude agent sessions as first-class
objects bound to vault tasks, with a morning standup and a glanceable single
surface. Independent of `/drive`; see `mission-control/README.md`.

## Workflow

    /drive <task>   -> runs the whole pipeline below, autonomously

    PLAN (gstack brain)
    0. Premises (human) + set the session goal (native /goal, you paste it)
    1. /drive-plan: author design + a ## Phases & Slices breakdown
       -> autoplan -> dual-voice design review converges -> [Gate A]

    EXECUTE (harness-owned) - for each PHASE in order:
    2. /drive-implement per slice   (independent slices run in PARALLEL)
    3. /drive-review per slice + phase-integration  (Claude subagent + codex; cap 8)
    4. /drive-harden phase          (after review converges: reduce AI slop, add
                                     missing tests, fix logic bugs; own cap 3)
    5. verify (optional)      (qa-only / browse)
    6. /drive-ship ONCE             -> [Gate B] -> push

Two human gates (A: direction, B: diff before push); every review is dual-voice
(Claude + codex), converging when neither flags a P1. Full annotated diagram +
decision policy: **[`docs/flow.md`](docs/flow.md)** and `CLAUDE.md`.

### Review enforcement (a run cannot skip review by omission)

A `/drive` run **cannot skip plan/design review or code review by omission**: a
git-truth conformance checker plus a PreToolUse gate chain (`plan → slice → phase →
ship`) blocks each transition until its scope has a SHA-bound CONVERGED review, with a
Stop hook as backstop. It is omission-proof, not forgery-proof. Install once per
machine:

    bin/install-drive-hooks.sh

Full reference (mechanism, gate chain, limitations): **[`docs/drive-enforcement.md`](docs/drive-enforcement.md)**.

## Portable config — reproduce this Claude on a new machine

This repo is the canonical home of the operating rules (`OPERATING.md`). To make a
fresh machine behave the same:

1. Clone the repo:

       git clone https://github.com/jiazou/claude-harness ~/workspace/claude-harness

2. Point your global `~/CLAUDE.md` at the rules — one command, path auto-detected:

       ~/workspace/claude-harness/bin/install-operating-rules.sh

   It backs up any existing `~/CLAUDE.md`, writes an `@import` of this repo's
   `OPERATING.md`, symlinks bundled skills (e.g. `/decant`) into `~/.claude/skills/`
   so `OPERATING.md`'s references resolve, and symlinks the pipeline commands
   (`/drive` `/drive-plan` `/drive-implement` `/drive-review` `/drive-harden` `/drive-ship`) into `~/.claude/commands/` so
   they're discoverable from any directory. Operating rules and the `/drive`
   pipeline both apply machine-wide; the pipeline stays *opt-in per task* (it only
   acts when you invoke `/drive`, and STOPs unless run from a clean git repo).
   Manual alternative: put `@<clone-path>/OPERATING.md` in `~/CLAUDE.md`.

3. Install gstack + codex so `/drive` can run — see Setup below.

## Setup

1. Install gstack:

       git clone --single-branch --depth 1 \
         https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
         && cd ~/.claude/skills/gstack && ./setup

   (Provides `autoplan`, `plan-*-review`, `qa-only`, `browse`. The codex CLI is
   used directly by the review stage; install it separately if you want the
   cross-model pass — it degrades gracefully if absent.)

2. Start a session in whatever repo you want to drive (the commands are global,
   so any directory works):

       claude

3. Run the pipeline:

       /drive <your task>

See `CLAUDE.md` for the full decision policy and invariants.

## Files

- `OPERATING.md` -- canonical, portable operating rules (imported by CLAUDE.md + global)
- `bin/install-operating-rules.sh` -- link global ~/CLAUDE.md at OPERATING.md + bundled skills
- `bin/install-drive-hooks.sh` -- wire the /drive review-enforcement hooks into ~/.claude/settings.json
- `bin/{drive-conformance,drive-hook-lib,drive-merge-gate,drive-stop-guard}.sh` -- review-enforcement checker, ref→run lib, PreToolUse gate, Stop backstop
- `docs/drive-enforcement.md` -- review-enforcement reference (git-truth mechanism, gate chain, limitations)
- `skills/decant/` -- bundled `/decant` skill (symlinked into ~/.claude/skills by the installer)
- `CLAUDE.md` -- imports OPERATING.md, plus the coordinator pipeline + decision policy
- `.claude/commands/drive.md` -- the autonomous lifecycle orchestrator
- `.claude/commands/{drive-plan,drive-implement,drive-review,drive-harden,drive-ship}.md` -- single-sourced stage runners
- `docs/flow.md` -- annotated execution-flow diagram (phases, slices, every command)
- `.harness/decisions.md` -- append-only autonomous-decision ledger
- `.harness/followups.md` -- append-only out-of-scope discoveries
- `mission-control/` -- separate personal operating harness (session tracking +
  daily standup); self-contained, see `mission-control/README.md`

## Run artifacts (not committed)

Per-run state — design, `state.json`, review files, worktrees — lives in an
external run dir `~/.claude/harness-runs/<run-id>/`. The committed `.harness/`
holds only the cross-task ledgers (`decisions.md`, `followups.md`).
