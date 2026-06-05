# `/drive` review enforcement

Make it **impossible to skip plan/design review OR code review by omission** in a
`/drive` run, with automatic remediation (a blocked action feeds Claude the exact
`/drive-review` command to run, then it retries and proceeds).

## The problem

The coordinator that runs `/drive` is also the thing that's *supposed to remember*
to run `/drive-review`. A forgetful or hallucinating coordinator skips the step,
leaves state inconsistent, or records a result that never happened — and nothing
catches it. This is not hypothetical: run `phase3-slice4-20260603-075205` marked 6
slices `converged` (one `shadow`) and **shipped a PR with zero `review-*.md` /
`codex-*.md` artifacts** — review provably never ran. Trusting the coordinator's own
state (`step`, `phaseReview`) to gate review is circular: the same component that
forgets to review also writes the state that says it did.

## The mechanism — git is the source of truth

Three shifts make the check independent of coordinator-writable state:

1. **SHA-bound proof.** `/drive-review` records `reviewed-sha: <40-hex>` (the tip it
   actually diffed) in `review-<scope>-N.md`. A review only *counts* for code whose
   git tip **equals** its `reviewed-sha`. A stale CONVERGED file cannot cover commits
   added after it — "reviewed an old tip, then added unreviewed commits" is caught as
   a `sha-mismatch`.
2. **Truth from git refs, not state.** Conformance never reads `step`/`phaseReview`
   for its verdict. It asks git *what is actually being merged or shipped* and
   requires each such ref to have a matching CONVERGED, SHA-bound review. Leaving
   `step` unset or `phaseReview` empty does not help — if the code is in the merge/PR,
   it needs a review bound to its SHA.
3. **Ref-keyed self-location, no sentinel.** `featureBranch = drive/<runId>` and
   `RUN_DIR = ~/.claude/harness-runs/<runId>/`. The gate extracts `<runId>` from the
   `drive/<runId>` / `slice/<runId>/<id>` ref named in the command (or from
   `git rev-parse --abbrev-ref HEAD` in the cwd for `gh pr create` / bare `git push`).
   No cwd-hash, no mutable sentinel, nothing to go stale or be bypassed.

### Conformance checker

`bin/drive-conformance.sh` is a pure function over git + the run dir:

```
drive-conformance.sh <RUN_DIR> --mode plan-gate | slice-merge:<id> | phase-merge:<P> | ship | audit
```

A review artifact **counts** iff: the highest-N `review-<scope>-N.md` has
`## Verdict: CONVERGED` **and** a `reviewed-sha:` line equal to the git tip the mode
checks, **and** `codex-review-<scope>.md` exists and is **non-empty**. The codex file's
content is **not** inspected — *any* non-empty `codex-review-<scope>.md` satisfies the
codex requirement, whether it is a real codex review OR a `CODEX_UNAVAILABLE`
degradation note (the explicit token written when the codex CLI is absent). Only a
missing file or an empty one (a bare `touch`) fails. Output is JSON on stdout
(`{"clean":bool,"mode":...,"tip":...,"violations":[...]}`). **Exit codes:** `0` clean,
`1` violations, `2` usage/IO/git error. The fail-open vs fail-closed policy for exit 2
lives in the **hooks**, not the checker.

The `ship` mode tolerates exactly the one bookkeeping commit SHIP makes after the last
review: it requires **∃** a counting phase/integration review with `reviewed-sha = R`
such that `R` is an ancestor of the tip, `R..tip` touches only the **ship-ledger
allowlist** — the exact two files `.harness/decisions.md` and `.harness/followups.md`
(NOT the whole `.harness/` dir) — and `R..tip` is at most one commit. Selection is
existential, not "highest-N" (N is a per-scope counter, so max-N can mis-select an
early phase across phases). I.e. *all shipped code was reviewed; only the single
ledger commit moved the tip.*

## The gate chain

`bin/drive-merge-gate.sh` is a **PreToolUse(Bash)** hook. It classifies the command
by structural git/ship intent, resolves `runId`, and runs conformance for the matched
mode. It emits a `deny` **only** (clean or non-matching → no output, exit 0) so it
composes with the repo's existing Bash PreToolUse hooks and never overrides their
destructive `ask`; correctness relies on Claude Code's documented **deny-beats-allow**
precedence (a multiline `gh pr create --body $'…\n…'` trips an existing `allow` hook,
and the gate's `deny` must still win).

| Gate | Fires on (command match) | Mode | Blocks until | Exit-2 |
|------|--------------------------|------|--------------|--------|
| **plan-gate** | `git worktree add … -b slice/<runId>/<id>` (the first slice worktree of the run) | `plan-gate` | `review-design-*` CONVERGED + `codex-review-design` present and non-empty — implementation cannot begin until the **design** review converged | **fail-CLOSED** (deny) |
| **slice-merge** | `git merge … slice/<runId>/<id>` (each slice token in the command) | `slice-merge:<id>` | SHA-bound CONVERGED review for the slice tip | fail-OPEN (silent) |
| **phase-merge** | `git branch -f drive/<runId> phaseInt/<runId>/<P>` or `git merge … phaseInt/<runId>/<P>` | `phase-merge:<P>` | SHA-bound CONVERGED review for the phase-integration tip (naturally requires the post-harden review, since HARDEN re-emits `reviewed-sha`) | fail-OPEN (silent) |
| **ship** | `gh pr create`, `glab mr create`, or any `git push` whose head is the drive branch (incl. bare `git push`, `git push -u origin HEAD`) | `ship` | all shipped code covered by a counting review (ledger-only `R..tip` tolerated) | **fail-CLOSED** (deny) |

**Asymmetric fail mode (D4):** the two **run-boundary** gates — `plan-gate` (start)
and `ship` (end) — fail **closed** on a checker/git error (never wave through the
start of build or a PR). The **mid-build** per-unit gates (slice/phase merge + the
Stop backstop) fail **open** so a transient filesystem/git error cannot wedge a
mid-build run — the ship gate backstops them. If no `runId` resolves or `RUN_DIR` is
absent, every gate is inert (`exit 0` silent — not a managed drive run).

`bin/drive-hook-lib.sh` provides the pure ref→run resolution the gates source
(`drive_runid_from_command`, `drive_runid_from_head`, `drive_run_dir`).

## The Stop backstop

> `/drive` installs **two distinct Stop hooks** that coexist in `~/.claude/settings.json`.
> This section covers the **review-omission backstop** (`bin/drive-stop-guard.sh`, installed
> by `bin/install-drive-hooks.sh`). The other is the **autonomous-continuation** hook
> (`bin/drive-stop-hook.py`, installed by `bin/install-operating-rules.sh`), which blocks a
> stop while a run still has autonomous work so the pipeline keeps driving across turns —
> a different concern from review enforcement. Both fail open and are no-ops outside an
> active `/drive` run.

`bin/drive-stop-guard.sh` is a **Stop** hook (best-effort, not the guarantee). It
resolves `runId` from `git HEAD` in the cwd and runs conformance `--mode audit`, which
flags **only** slices merged into the **current live `phaseInt/<runId>/<P>`** that
lack a counting review. Because it reports only merged-but-unreviewed work, it can
*never* false-block a run that is merely idle, queued, in-flight, or paused at Gate A/B
— and it does not depend on reaped slice branches. Violations → `{"decision":"block",
"reason":…}`. It persists up to Claude Code's 8-consecutive-block cap, after which the
platform overrides and the run surfaces to the human (correct escalation, not infinite
persistence). It exists to catch the narrow window where hooks were installed mid-run
inside an in-flight phase; the merge → advance → ship gate chain is the actual
guarantee.

## Installation

```
bin/install-drive-hooks.sh
```

Idempotently `jq`-injects the two hook entries into `~/.claude/settings.json`
(PreToolUse(Bash) → `drive-merge-gate.sh`, Stop → `drive-stop-guard.sh`), keyed on the
script path so re-running is a no-op. It writes a timestamped backup, preserves all
existing hooks, and fails loudly on malformed JSON. A target other than the default can
be passed as `$1` or via `$DRIVE_HOOKS_SETTINGS` (used by the tests). The repo never
commits `~/.claude/settings.json`; the PR carries the scripts, installer, and docs.
Requires `jq` on `PATH`.

### Verify it's active

```
jq '.hooks.PreToolUse, .hooks.Stop' ~/.claude/settings.json   # both entries present
```

Or exercise the checker directly against any run dir:

```
bin/drive-conformance.sh ~/.claude/harness-runs/<run-id>/ --mode audit
```

Defense-in-depth: `/drive` and `/drive-ship` also run `drive-conformance.sh` in-prose
(`--mode plan-gate` before the first IMPLEMENT dispatch, `--mode audit` before
assembly, `--mode ship` before push), so enforcement degrades gracefully on a machine
where the hooks were never installed.

## Regression guard

The `test/*.test.sh` bash suites are the regression guard for the gates described here
(`drive-conformance.sh`, `drive-merge-gate.sh`, `drive-hook-lib.sh`,
`drive-stop-guard.sh`, plus the installer and the end-to-end enforcement test). Run them
with a per-file loop (and they also run in CI as the `bash-suite` job):

```
for f in test/*.test.sh; do bash "$f" || exit 1; done
```

## Limitations

- **Forgery is out of scope.** This system is **omission-proof, not forgery-proof**. A
  coordinator that *deliberately* forges a SHA-bound `review-N.md`, writes a sham
  non-empty `codex-review-<scope>.md`, or pushes under a disguised branch cannot be fully
  stopped while the coordinator is itself the executor — only an external trusted
  reviewer can. That is **component D** (a deterministic external driver / out-of-band
  reviewer), recorded as a follow-up. SHA-binding raises the forgery cost incidentally
  but does not claim to defeat a determined forger.
- **Gate matcher — shell-accurate command tokenization.** The four command parsers
  (`subcommand_of`, `action_after`, `git_target_repo`, `push_ship_runid`) lex `$CMD`
  through ONE shared `tokenize_cmd` (a bash-3.2 char state machine — no `eval`, no command
  execution, no `$var` expansion) rather than raw `set -- $CMD` whitespace word-splitting.
  This closes silent bypasses on **legitimate** input: a quoted path **with a space**
  (`git -C "/tmp/unreviewed repo" push`) is now one `-C` value (not split into `"/tmp/unreviewed`
  + `repo"`, which mis-read the subcommand and skipped ship detection), and `""`/`''`
  preserve an **empty arg** (so `git -C "" push` is a git no-op → identity stays `$CWD` →
  the drive HEAD is seen → DENY, instead of resolving `$CWD/""` and silently failing). The
  tokenizer handles single/double quotes and backslash escapes. *Fail-safe:* an
  **unterminated quote** is unparseable — the real shell would reject the command and git
  would never run — so the tokenizer returns "no tokens" and the gate goes **inert** rather
  than emit a mis-split argv that could desync the gate from git (safe because such a
  command cannot execute). **Variable refs remain a documented limitation:** the gate sees
  the PRE-expansion string by design (no `$var`/`$(…)` expansion), so a command that names
  its repo/ref purely through a runtime variable — `git -C "$dir" push`, `git merge
  "slice/$v/$id"` — is parsed with the literal token, not the runtime value; such mid-build
  merges silently pass the per-unit gate and are backstopped by the HEAD-based ship gate
  (whole-tip diff) plus the `/drive` literal-ref instruction. This is the same forgery/
  evasion class as the `$GIT_DIR`/`$GIT_WORK_TREE` env residual below (→ Component D), not
  an omission gap for the literal command forms `/drive` actually emits.
- **Gate matcher — composed git global-option resolution.** `git_target_repo()` now
  models the way *real git* resolves the repo identity: `-C` is composed left-to-right
  (`-C a -C b` → `a/b`; an absolute `-C` resets the accumulator), `--git-dir` is the
  identity axis (last-wins, resolved relative to the `-C` cwd, both `--git-dir <p>` and
  `--git-dir=<p>` forms), and `--work-tree` is **parsed-and-discarded** — it is *not* a
  repo-identity axis (git reads HEAD/refs from the gitdir, which `--work-tree` does not
  change), closing the prior silent-allow bypass where `git --work-tree=<reviewed> push`
  from an unreviewed drive cwd shipped the cwd while the gate inspected `<reviewed>`. A
  linked-worktree `.git` **gitfile** is reduced to its parent worktree root so the callers
  (`git -C`/`cd`) get a directory. *Residual (forgery-class, out of scope → Component D):*
  a **symlinked / non-canonical `--git-dir` gitfile wrapper** (`ln -s <wt>/.git /tmp/gd;
  git --git-dir=/tmp/gd …`) mis-targets the `dirname` reduction while real git follows the
  symlink, and the `-f` gitfile test itself follows symlinks (TOCTOU-unsafe). A
  deliberately-crafted symlink at a non-canonical path is a forgery/evasion construct, the
  same class as the `$GIT_DIR`/`$GIT_WORK_TREE` env residual below; the canonical
  `<worktree>/.git` case IS handled (a strict improvement — the symlink case was already
  cd-fail-fail-open pre-change).
- **`$GIT_DIR` / `$GIT_WORK_TREE` env repo-targeting is out of scope.** The gate parses
  the attacker-influenced *command string*; it does not honor `$GIT_DIR`/`$GIT_WORK_TREE`
  env vars (which `/drive` never sets). A command that retargets git purely via those env
  vars is a forgery-class residual (→ Component D), not an omission gap.
- **`git push` classification is best-effort over arbitrary push syntax.** The ship
  gate errs *toward* gating — it gates a push if any refspec source is the drive branch,
  an aggregate flag (`--all`/`--mirror`) is present, or HEAD is the drive branch — so the
  common forms (and `git push origin main drive/<id>`) are caught. But exotic forms (e.g.
  `--mirror` from a non-drive HEAD, or server-side refspec expansion) can still slip the
  PreToolUse matcher. The **authoritative** ship guarantee is therefore the in-prose
  `--mode ship` conformance check in `drive-ship.md` plus the single canonical push form
  `/drive` actually emits — the matcher is the fast path, not the sole guard.
