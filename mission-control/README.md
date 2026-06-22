# 🛰 Mission Control — a personal operating harness

> **Optional, opinionated add-on.** Mission Control is **macOS-specific** (launchd + SwiftBar)
> and assumes an **Obsidian PARA vault**. It is independent of the core `/drive` pipeline —
> skip it entirely if you don't use Obsidian. Point it at your own vault with the `MC_VAULT`
> environment variable (see **Setup** below); it defaults to `~/Documents/Vault`.

Mission Control sits on top of an existing Obsidian task *system*. The task system (PARA
vault, per-project `Tasks/`, Bases dashboards) holds the *what*; Mission Control adds the
scheduled commands and the **session tracking** that keep it running day to day — and that
help you keep track of many parallel Claude sessions at once. Morning briefing skill:
**`harvest`**.

## The core insight (why this exists)

A task system you must remember to run decays — it accumulates unreviewed tasks and stale daily
notes until it's abandoned. Mission Control runs the scheduled commands and shows you what
needs attention, so keeping the system current doesn't depend on memory.

## Data model

Two entities, joined by **session id**:

1. **Session** (ground truth: `~/.claude/sessions/<pid>.json`, maintained by Claude Code) —
   `sessionId` (stable UUID) · `pid` · `cwd` · `status` (busy/idle/shell/waiting) · `updatedAt`.
   Liveness = pid responds to `kill -0`. **Color** (`/color`) and **name** (`/rename`) are read
   from the session transcript `~/.claude/projects/<slug>/<sid>.jsonl` (latest `agent-color` /
   `agent-name` event wins) — they match the TUI exactly.
2. **Binding** (Mission Control overlay: `~/mission-control/bindings.jsonl`, append-only event
   log) — binds a session to `project` · `task` · `tab_name` · `iterm_session`
   (auto from `$ITERM_SESSION_ID`). Latest event per session wins; `mc bind --unbind` removes it.

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

## Setup — point it at your vault

Mission Control reads tasks from an Obsidian PARA vault. Tell it where yours lives with two
optional environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `MC_VAULT` | Absolute path to your Obsidian vault | `~/Documents/Vault` |
| `MC_VAULT_NAME` | Vault name used in `obsidian://` deep links | basename of `MC_VAULT` |

Set them in your shell, then run `install.sh` — it **captures their values into
`~/mission-control/config`**. This matters because the 6:45am launchd job and the SwiftBar
plugin run with a *bare environment* and do **not** read your `~/.zshrc`; the config file is
how they learn your vault. An exported env var still wins at runtime, so interactive `mc`
commands honor it immediately; **re-run `install.sh` after changing `MC_VAULT`** so the
scheduled job and menu bar pick up the new value.

It expects the PARA layout it reads: `01 Projects/<Project>/Tasks/*.md` (one task per file,
frontmatter `status:`), `Daily/<date>.md` for the cockpit note, and optionally
`03 Resources/Templates/daily-note-template.md`. Without a matching vault, the loops simply
find no tasks — nothing breaks.

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

## How to run it (the operating model)

**You don't run Mission Control. It runs on a schedule, and you query it when you want to.**
A launchd job triggers it for you — there's no daemon you manage and no terminal to keep open.
Every `mc` command runs once and exits. Install once, then forget the plumbing.

Three things run on their own after install, with nothing open:

| Always-on (automatic) | What it does | You do |
|---|---|---|
| **SwiftBar menu bar** | Shows `☀N` + today's tasks + live sessions; refreshes every minute; auto-launches at login. | Glance at it. This is your always-visible surface — no terminal required. |
| **6:45am launchd job** | Writes today's plan (`mc standup --draft`) + session digest (`mc harvest --log --summarize`) into the daily note before you wake. | Wake up, open the daily note, read the plan. |
| **Passive hooks** | Every Claude session reports its status; a session flips to ⏸ "waiting on you" the moment it pings you. | Nothing. It just keeps the menu bar honest. |

The 6:45am job runs whether or not a terminal or Claude session is open; it reads the
session files and the vault directly. If your Mac is asleep at 6:45, it runs when the Mac
next wakes. (If the Mac is fully powered off, it's skipped — you just run `mc standup --draft`
by hand that morning.)

**Two ways to run a command.** Inside a Claude Code session, use the **`/mc` skill** —
`/mc harvest`, `/mc today`, `/mc standup`, etc. (this is the Claude-native front door; the
`harvest`/`standup`/`weekly` skills also exist standalone). Or, in any plain terminal, type the
`mc` executable — it prints and exits:

```bash
mc today        # what's on my plate + which agents are running (also: just `today`)
mc standup      # plan the day; add --draft to write it into the daily note
mc harvest      # live session status; add --log to record it
mc weekly       # the review sweep
mc bind <id> --project "<P>"   # tag a session to a task you're working
```

You never leave one of these running. Run it, read it, close the terminal (or keep the
tab for the next one — your choice). The menu bar keeps showing current state regardless.

### What a normal day looks like

1. **Wake up** → the daily note already has Today's Focus + a parallel plan (the 6:45am job wrote it). Read it.
2. **During the day** → glance at the menu bar (`☀3` = 3 due). When it shows `⏸`, a Claude session is waiting on you — go unblock it.
3. **Starting work in a new Claude session** → optionally `mc bind <id> --project "X"` so the harvest/menu bar shows what that session is for.
4. **Anytime you want the full picture** → `mc today` or `mc standup` in a terminal.
5. **Once a week** → `mc weekly` (or the `weekly` skill) to clear the review queue.

If you do nothing at all, the menu bar and the morning note still keep working. The `mc`
commands are there for when you want more than a glance.

## Commands

| Command | What it does |
|---|---|
| `mc harvest [--summarize] [--log]` | Per-session digest, each headed by its **goal** (the iTerm tab name, auto). `--summarize` adds an LLM **Progress** + **Next** per session (one `claude` call each, run in parallel). `--log` appends to today's daily note. |
| `mc standup [--draft\|--json]` | Plan the day for parallelism; `--draft` writes a self-contained `Today's Focus` + `Parallel Plan` into the daily note, while `--json` prints machine-readable output and takes precedence over `--draft` (suppresses the draft write). |
| `mc today [--swiftbar]` | Today's tasks in one glance — terminal or SwiftBar menu-bar format. |
| `mc weekly [--json]` | Weekly review agenda (clear Needs Review, sweep By Project, reset the week). `--json` prints machine-readable output. |
| `mc tasks` | Vault task buckets (overdue / due-today / due ≤7d). |
| `mc bind <id> --project "<P>" [--task <slug>] [--tab <name>]` | Bind a session ↔ task. |

Automated: SwiftBar menu bar (auto-launch at login) · 6:45am `mc standup --draft` + `mc harvest
--log --summarize` (launchd) so you wake to a per-session Goal/Progress/Next brief · passive
`waiting` capture via Claude Code hooks. Skills: `harvest`, `standup`, `weekly`.

**Per-session Goal / Progress / Next.** Harvest heads each live session with its **goal** —
the iTerm tab name, which Claude Code auto-titles with the session's task (resolved via
`pid → tty → osascript`, falling back to the transcript's `ai-title`). With `--summarize`, it
adds a **Progress** summary and a **Next** step per session, produced by `bin/session_summary.py`
reading the recent transcript tail through headless `claude`. The 6:45am job and
`mc harvest --summarize` share that one summarizer.

## Design decisions (locked)

- **Name:** Mission Control. Skill stays `harvest`.
- **Scope:** spans *code and life* projects (most projects aren't git repos; don't gate on
  worktrees). Worktree-per-session is a code-only optimization, added later.
- **Ledger:** append-only JSONL event log (gstack `timeline.jsonl` pattern), state = latest event.
- **Identity:** ID, iTerm tab, color, name all auto-resolved. Only the task binding is manual.
- **Capture:** manual `mc bind` now; passive notification-hooks layer on later.
- **Vault log:** harvests append to `Daily/<date>.md` (the operations cockpit) — no separate folder.
- **Scheduling:** `harvest` read-only now; the 6:45am run is `mc standup --draft` + `mc harvest
  --log --summarize`. The `mc standup --draft` *drafts* the day by writing the `Today's Focus` +
  `Parallel Plan` sections into the daily note (non-destructive to other sections); it does not
  touch task frontmatter or set any `needs_review` status.

## Future polish (not core)

- Richer LLM standup at 6:45am (currently a deterministic draft; the `standup` skill adds the
  two-lane "you vs. fan-out-to-agents" judgment when you're in the loop).
- Task `depends_on` adoption so the parallel plan computes a real critical path.
- Optional Apple Reminders relay for timed notifications (vault stays the only source of truth).

## Reversibility

Additive and reversible: the install copies `bin/` + `swiftbar-plugins/` into
`~/mission-control/`, symlinks `mc`/`today` onto your `PATH`, adds one launchd job, and
merges a few hooks into `settings.json`. The only vault writes are new `Daily/<date>.md`
cockpit notes — disposable by design; no existing task or doc is ever modified.

See `RELATED-WORK.md` for the prior-art scan this design draws from.
