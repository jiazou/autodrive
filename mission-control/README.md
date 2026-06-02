# 🛰 Mission Control — Jia's personal operating harness

Mission Control is the **operating layer** on top of the existing Obsidian task *system*. The
task system (PARA vault, per-project `Tasks/`, Bases dashboards) holds the *what*; Mission
Control adds the recurring *loops* and the **session tracking** that make the system actually
get operated — and that let Jia context-switch across many parallel Claude sessions without
losing the thread. Morning briefing skill: **`harvest`**.

## The core insight (why this exists)

The task system was bootstrapped 2026-05-21 and then *never operated* — exactly one daily note
ever, 29 seed tasks left unreviewed. A system you must remember to run decays. Mission Control is
the harness that runs the loops and surfaces what needs you, so operation doesn't depend on memory.

## Data model

Two entities, joined by **session id**:

1. **Session** (ground truth: `~/.claude/sessions/<pid>.json`, maintained by Claude Code) —
   `sessionId` (stable UUID) · `pid` · `cwd` · `status` (busy/idle/shell/waiting) · `updatedAt`.
   Liveness = pid responds to `kill -0`. **Color** (`/color`) and **name** (`/rename`) are read
   from the session transcript `~/.claude/projects/<slug>/<sid>.jsonl` (latest `agent-color` /
   `agent-name` event wins) — they match the TUI exactly.
2. **Binding** (Mission Control overlay: `~/mission-control/bindings.jsonl`, append-only event
   log) — binds a session to `project` · `task` · `tab_name` · `iterm_session`
   (auto from `$ITERM_SESSION_ID`). Latest event per session wins; `--unbind` removes it.

A **task → sessions** relationship is 1:n and derived: all bindings pointing at the same task.
Task status should **roll up** from its sessions (blocked if any bound session is `waiting`) —
never tracked independently (a "done" task with a stuck agent is the trap).

### Identity discovery (verified 2026-06-02) — all three are automatic

| Piece | Source | Auto? |
|---|---|---|
| Session ID | `$CLAUDE_CODE_SESSION_ID` | ✅ |
| iTerm session/tab | `$ITERM_SESSION_ID` (`wNtMpK:UUID` = window/tab/pane) | ✅ |
| Session **color** | latest `agent-color` in `~/.claude/projects/<slug>/<sid>.jsonl` (set by `/color`) | ✅ |
| Session **name** | latest `agent-name` in same transcript (set by `/rename`) | ✅ |

Only the **binding** (which task a session is working) is a human decision.

## Install

This repo is the **source**; `install.sh` **deploys** it (real copies, not symlinks) into
`~/mission-control/`, so the live harness keeps working no matter which branch the repo is on.
Runtime data also lives in `~/mission-control/` and is never committed. Re-run after editing.

```bash
./install.sh
```

It deploys `bin/` + `swiftbar-plugins/` into `~/mission-control/`, copies the three skills into
`~/.claude/skills/`, links `mc`/`today` onto your `PATH`, installs the 6:45am launchd job, points
SwiftBar at the plugin, and merges the passive-capture hooks into `~/.claude/settings.json`.

## Commands

| Command | What it does |
|---|---|
| `mc harvest [--log]` | Live session digest (waiting-on-you first); `--log` appends it to today's daily note. |
| `mc standup [--draft\|--json]` | Plan the day for parallelism; `--draft` writes a self-contained `Today's Focus` + `Parallel Plan` into the daily note. |
| `mc today [--swiftbar]` | Today's tasks in one glance — terminal or SwiftBar menu-bar format. |
| `mc weekly` | Weekly review agenda (clear Needs Review, sweep By Project, reset the week). |
| `mc tasks` | Vault task buckets (overdue / due / waiting). |
| `mc bind <id> --project "<P>" [--task <slug>] [--tab <name>]` | Bind a session ↔ task. |

Automated: SwiftBar menu bar (auto-launch at login) · 6:45am `standup --draft` + `harvest
--log` (launchd) · passive `waiting` capture via Claude Code hooks. Skills: `harvest`,
`standup`, `weekly`.

## Design decisions (locked)

- **Name:** Mission Control. Skill stays `harvest`.
- **Scope:** spans *code and life* projects (most projects aren't git repos; don't gate on
  worktrees). Worktree-per-session is a code-only optimization, added later.
- **Ledger:** append-only JSONL event log (gstack `timeline.jsonl` pattern), state = latest event.
- **Identity:** ID, iTerm tab, color, name all auto-resolved. Only the task binding is manual.
- **Capture:** manual `mc bind` now; passive notification-hooks layer on later.
- **Vault log:** harvests append to `Daily/<date>.md` (the operations cockpit) — no separate folder.
- **Scheduling:** `harvest` read-only now; 7am run is `harvest --log` (digest only). The
  `--prep` standup that *drafts* the day lands everything as `needs_review`.

## Future polish (not core)

- Richer LLM standup at 6:45am (currently a deterministic draft; the `standup` skill adds the
  two-lane "you vs. fan-out-to-agents" judgment when Jia is in the loop).
- Task `depends_on` adoption so the parallel plan computes a real critical path.
- Optional Apple Reminders relay for timed notifications (vault stays the only source of truth).

## Reversibility

Additive and reversible: the install is all symlinks + one launchd job + a hooks merge.
The only vault writes are new `Daily/<date>.md` cockpit notes — disposable by design; no
existing task or doc is ever modified.

See `RELATED-WORK.md` for the prior-art scan this design draws from.
