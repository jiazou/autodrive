# Security

This document describes what autodrive installs on your machine, the threat model of
the `/drive` review-enforcement system, the residuals it knowingly does **not** defend
against, and how to report a vulnerability.

## What the installers touch

Two installers configure Claude Code on your machine. **Both print a disclosure banner
and, when run interactively, ask for confirmation before changing anything.** Run them
non-interactively with `DRIVE_INSTALL_ASSUME_YES=1` — and `install-drive-hooks.sh` also
skips the prompt when given an explicit `$1` target path (scripted installs / tests).

### `bin/install-drive-hooks.sh` — review-enforcement hooks

Writes to **`~/.claude/settings.json`** (a timestamped backup is made first; existing
hooks are preserved — except a pre-existing *lone* hook command named
`drive-merge-gate.sh`, `drive-stop-guard.sh`, or `drive-tool-gate.sh`, which is treated as
a stale copy of the managed gate and canonicalized to this repo's path on re-run). It adds
**four entries (three hooks)**:

- **`PreToolUse(Bash)` → `bin/drive-merge-gate.sh`** — fires on *every* Bash tool call.
  The gate inspects the command string and acts **only** on `/drive` plan/merge/ship git
  operations; every other command passes straight through (no output, exit 0). It can
  emit a `deny` that blocks a merge/ship until the matching review artifact exists.
- **`Stop` → `bin/drive-stop-guard.sh`** — a best-effort review backstop that runs when a
  session stops. No-op outside an active `/drive` run; fails open on any error.
- **`PreToolUse(GitHub-MCP writes)` and `PreToolUse(Agent|EnterWorktree)` →
  `bin/drive-tool-gate.sh`** (two entries) — fires only on the enumerated GitHub-MCP write
  tools and on the native worktree tools (`Agent isolation:"worktree"` / `EnterWorktree`).
  While a `/drive` run is active **on the same repo**, it deny-**routes** those tools back
  to the gated Bash paths (or "human-owned at Gate B" for the PR-lifecycle tools); it
  passes everything else silently. In-script errors (jq absent, unparseable stdin,
  unextractable owner/repo) fail **closed** (these tools have no ship-gate backstop);
  hook-invocation failure fails **open** by platform protocol.

Before the confirm prompt the installer runs a **read-only drift preflight** that WARNs
(never blocks) when the live enforcement worktree lacks `drive-tool-gate.sh` or lags the
settings entries. The repo never commits `~/.claude/settings.json`. Re-running is
idempotent. A custom target can be passed as `$1` or via `$DRIVE_HOOKS_SETTINGS`.

### `bin/install-operating-rules.sh` — machine-wide operating config

This is the more invasive installer — it configures Claude Code **globally for every
session in every directory**:

- **Overwrites `~/CLAUDE.md`** with a pointer that imports this repo's `OPERATING.md`
  (any existing `~/CLAUDE.md` is backed up to `~/CLAUDE.md.bak.<ts>` first).
- **Symlinks** this repo's `skills/*` → `~/.claude/skills/`, `.claude/commands/*.md` →
  `~/.claude/commands/`, and `bin/statusline.sh` → `~/.claude/statusline.sh`. Pre-existing
  real files at those paths are moved to `*-backups/` directories first.
- **Attempts to register a `/drive` autonomous-continuation `Stop` hook**
  (`bin/drive-stop-hook.py`) in `~/.claude/settings.json` — best-effort: if that file is
  unparseable the step is skipped with a "add it manually" message rather than failing the
  install, so a successful install may leave this hook unregistered. Once registered it only
  ever acts during an active `/drive` run owned by the firing session, fails open on every
  error, and self-disarms at `stage=done`.

To remove the continuation hook globally, delete the `drive-stop-hook.py` entry from
`~/.claude/settings.json` `hooks.Stop`.

## Threat model: omission-proof, not forgery-proof

The `/drive` enforcement system (`docs/drive-enforcement.md`) makes it **impossible to
skip plan/design review or code review by *omission*** — a forgetful or hallucinating
coordinator that never runs `/drive-review` is blocked at the irreversible boundary
(merge/ship) before it can act on un-reviewed code. Conformance is computed from **git
truth** (SHA-bound review artifacts checked against the actual refs being merged or
shipped), never from coordinator-writable state.

It is **NOT forgery-proof.** A coordinator that *deliberately* forges a SHA-bound
`review-N.md`, writes a sham non-empty `codex-review-<scope>.md`, or pushes under a
disguised branch cannot be fully stopped while the coordinator is itself the executor.
Defeating a determined forger requires an external trusted reviewer — **component D**, a
deterministic out-of-band driver, which is **not yet built** (tracked as a follow-up).
SHA-binding raises the forgery cost incidentally but does not claim to defeat a forger.

## Known residuals (forgery-class, → component D)

These are deliberately out of scope. Each requires *deliberately crafted* input that
`/drive` never emits; none is an omission gap for the literal command forms `/drive`
actually produces. They are documented in full in `docs/drive-enforcement.md`.

- **Symlinked / non-canonical `--git-dir` gitfile.** A symlink at a non-canonical path
  (`ln -s <wt>/.git /tmp/gd; git --git-dir=/tmp/gd …`) mis-targets the gate's `dirname`
  reduction while real git follows the symlink (TOCTOU-unsafe). The canonical
  `<worktree>/.git` case is handled.
- **`$GIT_DIR` / `$GIT_WORK_TREE` env repo-targeting.** The gate parses the command
  string and does not honor these env vars (which `/drive` never sets). A command that
  retargets git purely via them is out of scope.
- **Ref-retargeting global options (`--namespace` / `--config-env`).** The gate now parses
  these separate-arg git globals so they no longer mis-shift the subcommand (closing that
  bypass), but it does not model their *semantic* effect on which refs git resolves (a
  namespace / config-injected ref view). Local HEAD and branch resolution — what the gate
  actually keys on — are unaffected by them, so no live bypass reproduces; deeper
  namespace-retargeting is the same out-of-scope class as the env vars above.
- **Runtime-variable refs in mid-build review gates.** The mid-build per-unit review gates
  (slice-merge / phase-merge) fail **open** by design, so a runtime-variable ref
  (`git merge "$ref"`) in a non-managed-verb position is parsed with the literal token,
  not the resolved value. A managed verb with a tainted ref operand *does* trip a
  fail-closed deny; any residual is backstopped by the HEAD-based ship gate.
- **Attached short-option branch refs (`-b<branch>`).** The gate matches the separate
  (`-b slice/<id>`) and `=` (`-b=slice/<id>`) forms `/drive` emits, not the attached form
  (`-bslice/<id>` as one token). A precise parser was omitted because it introduced
  wrong-review and over-deny regressions.
- **Wrapper-command prefixes (`command` / `env`).** The gate keys off the START binary
  being literally `git`/`gh`/`glab` (after skipping `NAME=val` env-assignment prefixes), so
  `command git push` or `env GIT_TRACE=1 git push` runs git but the gate sees the binary as
  `command`/`env` and goes inert. `/drive` always emits a bare `git …`; resolving arbitrary
  wrapper indirection (`env` has its own option grammar) is the same indirection-resolution
  class as `$var` → component D.
- **Inline git aliases (`git -c alias.X=<verb> X`).** `git -c alias.p=push p` defines and
  runs a push, but the gate sees the subcommand token `p`, not a managed verb. Recognising it
  requires resolving the alias the command itself defines — arbitrary config/alias resolution,
  out of scope (→ component D). `/drive` never defines inline aliases.
- **Alternate integration verbs (`git pull` / `git rebase` / `git cherry-pick`).** The gate
  manages `git merge` / `git branch -f` (the forms `/drive` emits) but not other ways to
  integrate a ref. `git pull <repo> slice/<run>/<id>` merges a slice without a gate. Adding
  `pull` was tried and reverted: its `<repository>` positional is indistinguishable from a
  refspec to the gate's classifier, which produced both a new bypass and an over-deny on normal
  `git pull "$remote" main` — a net-negative trade. `/drive` always integrates via `git merge`.
- **Decoy refs in non-message option values.** Ref extraction is a lexical scan of the command;
  it strips the values of message flags (`-m`/`-F`/`--message`/`--file`), where a ref-shaped
  token can appear *incidentally*, but not the values of every option. A *deliberate* decoy in a
  rare structured option value (e.g. `git merge --into-name phaseInt/<bogus>/1 …`) is forgery-
  class. The multi-runId **octopus deny** still fail-closes a decoy that names a *different* run
  (slice and phaseInt alike); a same-run decoy with a wrong phase id is an over-gate at worst.
- **Escaped or quoted brace-range dot pair.** The range detector keys on two
  consecutive unquoted dots; an escaped pair like `{1\..2}` (which bash leaves literal)
  may be over-DENIED. This is an over-deny in the *safe* direction on a token `/drive`
  never emits, not a bypass.
- **Forged trivial tests.** The `impl-presence` gate proves a slice's diff *touched* a
  runnable test path (or declared a `Drive-Test-Waiver` trailer) — it does not prove the
  test is meaningful. A forged empty test (`def test_noop(): pass`) passes. Test *quality*
  is harden's lens + component-D territory.
- **Exotic `git push` forms.** Ship classification errs toward gating, but exotic forms
  (`--mirror` from a non-drive HEAD, server-side refspec expansion) can slip the
  PreToolUse matcher. The authoritative ship guarantee is the in-prose `--mode ship`
  conformance check in `drive-ship.md`.

### Non-Bash tool gate (`drive-tool-gate.sh`) residuals

The sibling hook closes **omission** bypasses only, matching the chain's threat model. Its
named residuals (full detail in `docs/drive-enforcement.md`):

- **Schema-drift silent fail-OPEN.** The MCP-write matcher fingerprints a vendor-owned,
  fast-moving tool schema; a vendor rename/addition is a clean matcher non-match → the hook
  never fires. **Retirement condition:** delete this hook when the harness ships
  conditional/managed tool policy. (Inverse drift — matcher fires, hook table lacks the
  suffix — fails CLOSED.)
- **Hook-invocation-failure fail-OPEN.** A nonzero hook exit (crash, rc 126/127, dead path)
  proceeds by platform protocol.
- **`platform-may-not-fire-PreToolUse-on-native-worktree-tools`** (Agent-with-isolation AND
  EnterWorktree) — an **interception** residual (distinct from invocation-failure): the
  fixtures prove hook logic, not that the platform routes real isolated `Agent`/`EnterWorktree`
  traffic to the hook. A live deny capture requires the gate wired into the live
  `~/.claude/settings.json` (the Gate-B activation ops step, out of this slice's scope), so
  AC-16 is **discharged by this named residual**, not by a proof captured here.
- **Forgery-class self-evasions** (→ component D): a coordinator that writes `stage:"done"`,
  **corrupts/truncates its OWN `state.json`** (silencing its own activation predicate), or
  lands work in a **second clone whose `origin` was rewritten/removed** (no origin key, no
  shared common dir → unrecognized) is not stopped — the same class as forging a review.

## Reporting a vulnerability

Report security issues **privately** — do not open a public issue for an unpatched
vulnerability.

- Preferred: GitHub → the repository's **Security** tab → **Report a vulnerability**
  (private advisory).
- Or email the maintainer: **jiazou11@gmail.com**.

Please include a reproduction (the command string, the run state, and the expected vs
actual gate behavior). Reports of new *omission* bypasses — a path that ships or merges
unreviewed code without forging an artifact — are the highest priority.
