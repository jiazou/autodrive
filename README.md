# autodrive

**AI coding agents skip code review, claim "done" on work they didn't finish, and quietly
drop steps. `/drive` makes that structurally impossible.** It drives one task through the whole
lifecycle — plan → implement → review → harden → ship — as an autonomous pipeline for Claude
Code, and it **cannot skip review by omission**: the merge and ship gates are computed from git
truth (SHA-bound review artifacts), so a coordinator that forgets or hallucinates a review is
blocked before it can act on the result.

You approve two things — the direction (Gate A) and the final diff (Gate B). The pipeline drives
everything in between: **gstack** plans, **harness-owned stages** execute, and every review runs
two independent voices (a Claude reviewer + `codex`) that must both sign off.

- gstack `autoplan` + `plan-*-review` — autonomous planning/review brain
- `codex` — cross-model second opinion (run via the codex CLI directly)
- Slash commands: `/drive`, `/drive-plan`, `/drive-design`, `/drive-implement`, `/drive-review`, `/drive-harden`, `/drive-finalize`, `/drive-ship`
- Decision policy: autoplan's 6 principles + Mechanical/Taste/User-Challenge
  classification (auto-decides; pauses only at the gates)

Roles are generic `Agent` subagents (no parallel-team framework — see
`.harness/decisions.md` D1).

This repo also houses a second, separate harness: **[Mission Control](mission-control/README.md)**
— an *optional* add-on that tracks your Claude agent sessions, binds each to an Obsidian
task, and gives you a morning standup plus a single status view. It is **macOS-specific**
(launchd + SwiftBar) and assumes an **Obsidian PARA vault**
(configurable via `MC_VAULT`). Fully independent of `/drive` — skip it if you don't use Obsidian.
See `mission-control/README.md`.

## Workflow

    /drive <task>   -> runs the whole pipeline below, autonomously

    PLAN (gstack brain)
    0. Premises (human)
    1. /drive-plan: author a HIGH-LEVEL design — goal, approach, ordered ## Phases
       (no slices/interfaces) -> autoplan -> dual-voice review converges -> [Gate A]

    EXECUTE (harness-owned) - for each PHASE in order:
    2. /drive-design phase: detailed design for THIS phase (interfaces, edge cases,
                                     slices) against the real prior-phase code;
                                     dual-voice review converges (cap 8); no gate
    3. /drive-implement per slice   (independent slices run in PARALLEL; each first
                                     checks its assumptions vs reality -> REDESIGN
                                     re-runs step 2 on a big divergence)
    4. /drive-review per slice + phase-integration  (Claude subagent + codex; cap 8)
    5. /drive-harden phase          (after review converges: add missing tests,
                                     fix logic bugs; de-slop deferred to finalize;
                                     own cap 3)
    (after ALL phases hardened, before verify)
    6. /drive-finalize ONCE         (aggregate whole-run pass over baseRef..featureBranch:
                                     LEADS with de-slop + logic-bug/missing-test sweep;
                                     appends architectural findings to
                                     $RUN_DIR/finalize-todo.md (ship promotes it to the
                                     project's TODO.md); emits the ship gate's terminal SHA-bound
                                     review artifact; own cap 3)
    7. verify (optional)      (qa-only / browse)
    8. /drive-ship ONCE             -> [Gate B] -> push

Two human gates (A: direction, B: diff before push); every review is dual-voice
(Claude + codex), converging when neither flags a P1. Every pause — and every
fresh-session handoff/resume — prints a run-graph chart plus a short
context-of-execution summary (problem · where we are · done · next). Design is refined in three
tiers — high-level whole-run plan (Gate A), a detailed per-phase design against the
real prior-phase code, then a per-slice assumption check. Full annotated diagram +
decision policy: **[`docs/flow.md`](docs/flow.md)** and `CLAUDE.md`.

### Review enforcement (a run cannot skip review by omission)

A `/drive` run **cannot skip plan/design review or code review by omission**: a
git-truth conformance checker plus a PreToolUse gate chain (`plan → phasedesign → slice
→ phase → ship`) blocks each transition until its scope has a CONVERGED review — including
each phase's detailed-design review before that phase's slices can be built — with a
Stop hook (`bin/drive-stop-guard.sh`) as backstop. It is omission-proof, not
forgery-proof. Install once per machine:

    bin/install-drive-hooks.sh

Full reference (mechanism, gate chain, limitations): **[`docs/drive-enforcement.md`](docs/drive-enforcement.md)**.

> `/drive` installs **two distinct Stop hooks** that coexist: this **review-omission
> backstop** (`drive-stop-guard.sh`, installed by `bin/install-drive-hooks.sh`) blocks a
> stop when merged work lacks a review; the **autonomous-continuation hook**
> (`drive-stop-hook.py`, installed by `bin/install-operating-rules.sh`) blocks a stop while
> a run still has autonomous work, so the pipeline keeps driving across turns. Both fail
> open and are no-ops outside an active `/drive` run.

## Requirements

This repo has **two independent parts** with different requirements. The core
`/drive` pipeline is the main product; Mission Control is an optional add-on.

### Platform support at a glance

| Platform | Core `/drive` pipeline | Mission Control |
| --- | --- | --- |
| **macOS** | ✅ Fully supported | ✅ Fully supported |
| **Linux** | ✅ Fully supported | ⚠️ CLI only (`mc harvest/today/tasks` work; no menu bar or scheduled job) |
| **Windows** | ⚠️ Via [WSL](https://learn.microsoft.com/windows/wsl/) only | ❌ Not supported |

The scripts are `bash` + `python3`; there is no native Windows support — use WSL.

### Core `/drive` pipeline

| Dependency | Required? | Purpose | Install |
| --- | --- | --- | --- |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | **Required** | Runs the slash commands | Per Anthropic docs |
| `git` + `bash` (3.2+) | **Required** | Clone + the installer script | Preinstalled on macOS/Linux |
| [gstack](https://github.com/garrytan/gstack) | **Required to run `/drive`** | Provides the planning/review brain: `autoplan`, `plan-*-review`, `qa-only`, `browse` | Step 3 below |
| [codex CLI](https://github.com/openai/codex) | *Optional* | Cross-model second opinion in the review stage (supervised by `bin/drive-codex.sh`). **Degrades gracefully if absent, down, or stalled** — the pipeline still completes (an honest `CODEX_UNAVAILABLE` / `CODEX_KILLED_TIMEOUT` tier) | Per OpenAI docs |

No third-party libraries are bundled or required for the core pipeline beyond the above.

### Mission Control (optional — skip entirely if you don't use Obsidian)

| Dependency | Required? | Purpose |
| --- | --- | --- |
| **macOS** | **Required** | Uses `launchd` (scheduled job), SwiftBar (menu bar), `osascript` (iTerm tab names) |
| `python3` (3.8+) | **Required** | All `mc` commands. **Standard library only** — no `pip install` needed |
| An **Obsidian PARA vault** | **Required** | Source of tasks; point at it with `MC_VAULT` (see `mission-control/README.md`) |
| [SwiftBar](https://github.com/swiftbar/SwiftBar) | *Optional* | The always-visible menu-bar surface |

See **[`mission-control/README.md`](mission-control/README.md)** for its full setup.

## Installation

### Core pipeline (everyone)

**1. Clone the repo** (anywhere; the path is remembered by the installer):

```bash
git clone https://github.com/jiazou/autodrive ~/workspace/autodrive
```

**2. Register the rules + commands machine-wide** — one command, path auto-detected:

```bash
~/workspace/autodrive/bin/install-operating-rules.sh
```

This is **idempotent** — safe to re-run. Note that it configures Claude Code **machine-wide,
for every session in every directory** (full details in [SECURITY.md](SECURITY.md)). It:
- backs up any existing `~/CLAUDE.md`, then writes a new one that `@import`s this repo's `OPERATING.md`;
- symlinks bundled skills (e.g. `/decant`) into `~/.claude/skills/` so `OPERATING.md`'s references resolve;
- symlinks the pipeline commands (`/drive`, `/drive-plan`, `/drive-design`, `/drive-implement`, `/drive-review`, `/drive-harden`, `/drive-finalize`, `/drive-ship`) into `~/.claude/commands/` so they work from **any** directory;
- registers the `/drive` **autonomous-continuation** Stop hook (`bin/drive-stop-hook.py`) in `~/.claude/settings.json` — it keeps a run driving across turns and is a no-op outside an active `/drive` run owned by the firing session. Disable it per-run with `autoContinue: false` in that run's `state.json`, or remove it globally by deleting the `drive-stop-hook.py` entry from `~/.claude/settings.json` under `hooks.Stop`.

> This is a **separate** Stop hook from the review-enforcement backstop (`bin/drive-stop-guard.sh`) installed by `bin/install-drive-hooks.sh`; the two coexist. See [Review enforcement](#review-enforcement-a-run-cannot-skip-review-by-omission).

> ⚠️ It uses **symlinks back into the clone**, so don't move or delete the clone after installing. If you move it, just re-run the script. (Manual alternative: add `@<clone-path>/OPERATING.md` to `~/CLAUDE.md` yourself.)

**3. Install gstack** (required to run `/drive`):

```bash
git clone --single-branch --depth 1 \
  https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
  && cd ~/.claude/skills/gstack && ./setup
```

Optionally install the [codex CLI](https://github.com/openai/codex) for the
cross-model review pass — the pipeline runs fine without it.

**4. Verify** the commands registered:

```bash
ls ~/.claude/commands/drive.md && echo "OK: /drive is installed"
```

**5. Use it** — start Claude Code in *any* repo you want to drive and run the pipeline:

```bash
cd ~/some/project
claude
# then, inside the session:
/drive <your task>
```

`/drive` is **opt-in per task**: it only acts when you invoke it, and it stops
unless run from a clean git repo. See `CLAUDE.md` for the full decision policy.

### Mission Control (optional, macOS + Obsidian)

Only if you want the session-tracking / daily-standup layer:

```bash
export MC_VAULT="$HOME/Documents/YourVault"   # add to your shell profile
~/workspace/autodrive/mission-control/install.sh
mc today                                        # verify
```

Full details, the expected vault layout, and `MC_VAULT_NAME` are in
**[`mission-control/README.md`](mission-control/README.md)**.

## Files

- `OPERATING.md` -- canonical, portable operating rules (imported by CLAUDE.md + global)
- `bin/install-operating-rules.sh` -- link global ~/CLAUDE.md at OPERATING.md + bundled skills + /drive commands; register the autonomous-continuation Stop hook
- `bin/install-drive-hooks.sh` -- wire the /drive review-enforcement hooks into ~/.claude/settings.json
- `bin/{drive-conformance,drive-hook-lib,drive-merge-gate,drive-stop-guard}.sh` -- review-enforcement checker, ref→run lib, PreToolUse gate, Stop backstop
- `bin/drive-codex.sh` -- supervised codex-dispatch helper for the dual-voice review leg (watchdog + honest `CODEX_UNAVAILABLE`/`CODEX_KILLED_TIMEOUT` degradation)
- `bin/drive-stop-hook.py` -- /drive autonomous-continuation Stop hook (keeps a run driving across turns; registered by install-operating-rules.sh)
- `docs/drive-enforcement.md` -- review-enforcement reference (git-truth mechanism, gate chain, limitations)
- `skills/decant/` -- bundled `/decant` skill (symlinked into ~/.claude/skills by the installer)
- `CLAUDE.md` -- imports OPERATING.md, plus the coordinator pipeline + decision policy
- `.claude/commands/drive.md` -- the autonomous lifecycle orchestrator
- `.claude/commands/{drive-plan,drive-design,drive-implement,drive-review,drive-harden,drive-finalize,drive-ship}.md` -- single-sourced stage runners
- `docs/flow.md` -- annotated execution-flow diagram (design tiers, phases, slices, every command)
- `.harness/decisions.md` -- append-only autonomous-decision ledger
- `.harness/followups.md` -- append-only out-of-scope discoveries
- `.harness/codex-refutations.md` -- append-only durable codex-refutation ledger (hermetic cross-run adjudications)
- `mission-control/` -- separate, optional personal operating harness (session tracking +
  daily standup); macOS + Obsidian-specific, see `mission-control/README.md`
- `LICENSE` -- MIT

## Run artifacts (not committed)

Per-run state — design, `state.json`, review files, worktrees — lives in an
external run dir `~/.claude/harness-runs/<run-id>/`. The committed `.harness/`
holds only the cross-task ledgers (`decisions.md`, `followups.md`,
`codex-refutations.md`).

## Testing

The repo has **two test suites**, split by language: the `/drive` coordinator gates are
shell, while Mission Control and the hooks are Python, so each is tested by its native
runner.

| Suite | Dir | Language / runner | Covers |
| --- | --- | --- | --- |
| Bash | `test/` (singular) | `bash` per `*.test.sh` | The `/drive` coordinator gates (`drive-conformance.sh`, `drive-merge-gate.sh`, `drive-hook-lib.sh`, `drive-stop-guard.sh`, the hooks installer `install-drive-hooks.sh`, and the e2e enforcement test) |
| Pytest | `tests/` (plural) | `python3 -m pytest` (`testpaths = ["tests"]` in `pyproject.toml`) | Mission Control, Python hooks, installers, and contract tests |

**Run the pytest suite:**

```bash
python3 -m pytest -q
```

**Run the bash suite** — loop over each file so one script's failure stops the run
(do **not** `bash test/*.test.sh`, which runs the first file with the rest as argv):

```bash
for f in test/*.test.sh; do bash "$f" || exit 1; done
```

CI (`.github/workflows/test.yml`) now runs **both** suites as separate jobs
(`pytest` and `bash-suite`) for independent red/green signal.

## License

MIT — see [LICENSE](LICENSE). Builds on third-party tools installed separately:
[gstack](https://github.com/garrytan/gstack) (MIT) and the
[codex CLI](https://github.com/openai/codex).
