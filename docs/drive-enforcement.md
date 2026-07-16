# `/drive` review enforcement

Make it **impossible to skip plan/design review OR code review by omission** in a
`/drive` run, with automatic remediation (a blocked action feeds Claude the exact
command to run, then it retries and proceeds — `/drive-review` for the plan/design/
slice/phase gates, `/drive-finalize` for the ship gate).

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
   git tip **equals** its `reviewed-sha` (the `ship` gate is the one exception — see the
   ship-mode paragraph below). A stale CONVERGED file cannot cover commits
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
drive-conformance.sh <RUN_DIR> --mode plan-gate | phasedesign-gate:<P> | slice-merge:<id> | phase-merge:<P> | impl-presence:<id> | ship | audit | checkpoint | state-lint
```

The `checkpoint` and `state-lint` modes back the **context-pressure rebirth** handoff
(§ "Durable checkpoint & rebirth"); the others gate the review/test chain below.

A review artifact **counts** iff: the highest-N `review-<scope>-N.md` has
`## Verdict: CONVERGED` **and** a `reviewed-sha:` line equal to the git tip the mode
checks (the `ship` gate is the one exception — see the ship-mode paragraph below),
**and** `codex-review-<scope>.md` exists and is **non-empty**. The codex file's
content is **not** inspected — *any* non-empty `codex-review-<scope>.md` satisfies the
codex requirement, whether it is a real codex review OR a `CODEX_UNAVAILABLE` /
`CODEX_KILLED_TIMEOUT` degradation note (the explicit first-line tokens the supervisor
`bin/drive-codex.sh` writes). Only a missing file or an empty one (a bare `touch`) fails.

> **Operator note — codex degradation tiers.** The dual-voice review's codex leg runs under
> `bin/drive-codex.sh`, which watchdogs a byte-silent call and records an HONEST degradation as the
> marker's first line: `CODEX_UNAVAILABLE` (the codex CLI is absent, or a health probe confirmed an
> outage) or `CODEX_KILLED_TIMEOUT` (the watchdog killed a stalled/over-long call). Both contribute
> **zero P1** and let the run continue single-voice. **The gate never parses the marker** — it only
> checks existence + non-emptiness (byte-compatible with a real review), so a degradation NEVER
> silently satisfies more than a present-codex requirement. To investigate a degraded scope, read the
> attempt log `$RUN_DIR/codex-attempts-<runId>.jsonl` (one JSON line per op: probe/dispatch/kill/
> retry/degrade, with the effort tier + sandbox rung + max inter-append gap) and the quarantined
> `codex-raw-<scope>.killed-N.log` / `codex-harden-<P>.killed-N.log` raw logs. Output is JSON on stdout
(`{"clean":bool,"mode":...,"tip":...,"violations":[...]}`). **Exit codes:** `0` clean,
`1` violations, `2` usage/IO/git error. The fail-open vs fail-closed policy for exit 2
lives in the **hooks**, not the checker.

The `ship` mode is keyed off the run's terminal **finalize** review and tolerates exactly
the one bookkeeping commit SHIP makes after it. The tip-binding candidate-`R` is the
CONVERGED finalize artifact — the highest-N `review-finalize-N.md` with `## Verdict:
CONVERGED` and a non-empty `codex-review-finalize.md` sibling — whose `reviewed-sha = R`
must be an ancestor of the tip, with `R..tip` touching only the **ship-ledger allowlist**
— the exact four files `.harness/decisions.md`, `.harness/followups.md`, repo-root
`TODO.md`, and `.harness/codex-refutations.md` (NOT the whole `.harness/` dir) — and
`R..tip` at most one commit. **PLUS** a
precondition: ≥1 COUNTING phase-integration review must exist (a converged, SHA-bound,
codex-backed `review-phase*` — else `no-phase-review`), since a run that never produced
one never legitimately reached finalize. No converged finalize artifact → no candidate-`R`
→ ship blocks `no-review`. I.e. *the finalize review covers the shipped tip; only the
single ledger commit moved it after.*

The `impl-presence:<id>` mode enforces an **IMPLEMENT-stage invariant** that is independent
of the review modes: before a slice `slice/<runId>/<id>` merges, its diff against its
fork-point off `drive/<runId>` (`base = merge-base(slice, drive/<runId>)`) must **add or
modify a runnable test path** — `test/*.test.sh` (the bash-suite root, one segment only — a
nested `test/sub/x.test.sh` does NOT count) OR a path under `tests/` whose basename is
`test_*.py` / `*_test.py` (excluding support files: `_helpers.py`, `conftest.py`, any
`fixtures/` segment, `*.pyc`, any `__pycache__/` segment) — OR a commit in `base..tip` must
carry a real `Drive-Test-Waiver: <reason>` git **trailer** (parsed as a trailer, not matched
as a body substring, so quoted/example prose does not falsely waive). Pure git-truth (no
`state.json`): `base` is derived via `merge-base`, so an unresolvable slice / `drive/<runId>`
ref or genuinely-disjoint histories → exit 2 (abnormal), never a silent empty base.

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
| **plan-gate** | `git worktree add … -b slice/<runId>/<id>` (any slice worktree) | `plan-gate` | `review-design-*` CONVERGED + `codex-review-design` present — implementation cannot begin until the whole-run **design** review converged | **fail-CLOSED** (deny) |
| **phasedesign-gate** | the SAME `git worktree add … -b slice/<runId>/<id>` — for each slice's phase `P` (= the id prefix before the first `.`) | `phasedesign-gate:<P>` | the **current-epoch** `review-phasedesign<P>[-r<R>]-*` CONVERGED + `codex-review-phasedesign<P>[-r<R>]` present — a phase's slices cannot be built until its **detailed (Tier-2) design** review converged. Like plan-gate, audits a design DOC (no `reviewed-sha`) | **fail-CLOSED** (deny) |
| **slice-merge** | `git merge … slice/<runId>/<id>` (each slice token in the command) | `slice-merge:<id>` | SHA-bound CONVERGED review for the slice tip | fail-OPEN (silent) |
| **impl-presence** | same `git merge … slice/<runId>/<id>` boundary — runs *alongside* the review check, per slice token | `impl-presence:<id>` | the slice diff makes **any non-deletion change** (add, modify, rename-into, copy-into, type-change — `--diff-filter=d`, i.e. exclude deletions only) to a runnable test path **OR** a commit carries a real `Drive-Test-Waiver:` trailer (a DELETED test path does **not** count — and since `--name-only` prints only a rename's destination, a rename *away from* a test path also does not count while a rename *into* one does; a dotfile basename like `test/.x.test.sh` never counts — the real runners skip dotfiles) | **fail-CLOSED** (deny) |
| **phase-merge** | `git branch -f drive/<runId> phaseInt/<runId>/<P>` or `git merge … phaseInt/<runId>/<P>` | `phase-merge:<P>` | SHA-bound CONVERGED review for the phase-integration tip (naturally requires the post-harden review, since HARDEN re-emits `reviewed-sha`) | fail-OPEN (silent) |
| **ship** | `gh pr create`, `glab mr create`, or any `git push` whose head is the drive branch (incl. bare `git push`, `git push -u origin HEAD`) | `ship` | a CONVERGED finalize review (`review-finalize-N.md` + codex sibling) covers the shipped tip — `R..tip` tolerated only for the single 4-file ledger commit ({`.harness/decisions.md`, `.harness/followups.md`, `TODO.md`, `.harness/codex-refutations.md`}); ≥1 counting phase-integration review is a precondition | **fail-CLOSED** (deny) |
| **mcp-write** *(sibling hook `drive-tool-gate.sh`)* | a GitHub- or GitLab-MCP write tool matching `^mcp__.+__(update_pull_request_branch\|create_or_update_file\|create_merge_request\|accept_merge_request\|rebase_merge_request\|merge_merge_request\|update_merge_request\|create_pull_request\|merge_pull_request\|update_pull_request\|create_branch\|delete_file\|push_files)$` | *(non-conformance; active-run evidence scan)* | a `/drive` run is active on the **same repo** (`tool_input.owner`/`repo` match the run's origin, or the no-origin common-dir repo name) — deny-routes back to the gated Bash path (or "human-owned at Gate B" for the PR/MR-lifecycle tools) | **fail-CLOSED** in-script (jq-absent / unparseable stdin / unextractable owner-repo while a run is live); **fail-OPEN** on hook-invocation failure |
| **native-worktree** *(sibling hook `drive-tool-gate.sh`)* | `Agent` with `tool_input.isolation:"worktree"`, or `EnterWorktree` | *(non-conformance; active-run evidence scan)* | a `/drive` run is active on the actor's repo (the payload `cwd`'s **origin identity** OR shared **git common-dir** matches the run) — deny-routes to the gated `git worktree add … -b slice/<runId>/<id>` | **fail-CLOSED** in-script; **fail-OPEN** on hook-invocation failure |
| **worktree-create** *(sibling hook `drive-worktree-gate.sh`)* | the `WorktreeCreate` event — native worktree creation via the `--worktree` CLI flag **or** subagent `isolation:"worktree"` (fires on ACTUAL creation, IGNORES matchers) | *(non-conformance; active-run presence scan)* | **any** `/drive` run with a non-empty `repoRoot` is active on the machine (NOT repo-scoped — D-w1) — DENY with **exit 2**, routing to the gated Bash `git worktree add … -b slice/<runId>/<id>`; when idle it **provisions** the worktree so native creation still works | **fail-CLOSED = DENY (exit 2)** on jq-absent (matches `drive-tool-gate.sh`); **fail-OPEN** on hook-invocation failure |

**Epoch-aware phasedesign gate.** A phase can be **redesigned** (a slice's assumption check
finds the Tier-2 design stale → REDESIGN). Each redesign opens a durable **epoch** marker
`redesign-<P>-r<R>.marker`, and that epoch's design reviews are scoped
`review-phasedesign<P>-r<R>-N.md` (epoch 0 keeps the bare `phasedesign<P>` token). The
phasedesign-gate and `--mode checkpoint` resolve the **current** epoch `R` (highest backing
marker) and require *that* epoch's CONVERGED review — so a stale **pre-redesign** CONVERGED
review no longer satisfies the gate after a REDESIGN. The checkpoint proof adds three
epoch-integrity violations: `epoch-unmarked` (an epoch-suffixed review/codex artifact with
**no** backing `redesign-<P>-r<R>.marker` — fail-closed, the resolved scope is untrustworthy),
`epoch-gap` (the `r1..rR` marker set is not gapless), and `regress-mismatch` (more
`AppliedEdits: yes` harden files than phase-review files).

**Asymmetric fail mode (D4):** the **run-/phase-boundary** gates — `plan-gate` (run start),
`phasedesign-gate` (phase start), and `ship` (end) — fail **closed** on a checker/git error
(never wave through the start of build or a PR). The **mid-build REVIEW** gates (`slice-merge`
review + `phase-merge` + the Stop backstop) fail **open** so a transient filesystem/git error
cannot wedge a mid-build run — the ship gate is their fail-closed backstop. If no `runId`
resolves or `RUN_DIR` is absent, every gate is inert (`exit 0` silent — not a managed drive run).

**Posture asymmetry at the slice-merge boundary (Decision C3):** the slice-merge boundary
runs **two** checks per slice token with *different* fail postures. The `slice-merge` REVIEW
check fails **open** (above) because ship backstops it. The `impl-presence` TEST-presence
check fails **CLOSED** — both rc 1 (violation: no test, no waiver) AND rc 2/abnormal
(missing/corrupt `drive/<runId>` or slice ref) → DENY. The reason is the missing backstop:
`ship` mode re-checks review ancestry against the shipped tip but **never re-derives
test-presence** (the merged `featureBranch` has lost per-slice identity), so a fail-OPEN
impl-presence would let an abnormal result silently allow a no-test merge with nothing
catching it later — defeating the invariant. Slice-merge is therefore the **irreversible
boundary** for test-presence and must fail closed there (OPERATING: "place the hard gate at
the irreversible boundary, failing closed"). The deny names the remediation: add a test for
the slice, or mark it test-less with a `Drive-Test-Waiver: <reason>` commit trailer. In a real
run `drive/<runId>` is the live featureBranch, so rc 2 is genuine corruption, not normal flow
— fail-closed will not false-block legitimate merges.

The "per slice token" wording means each token is checked against **its own** runId. `/drive`
emits one `git merge slice/<runId>/<id>` per slice, so every slice token in a single merge
shares one runId. A merge that references slice branches from **more than one distinct runId**
in one `git merge` (e.g. `git merge slice/runA/4a slice/runB/4a`) is **not** a `/drive`
operation: the gate keys `RUN_DIR` + conformance to a single runId, so it cannot check the
other runs' slices as one unit. Such a multi-runId octopus merge therefore **fails CLOSED
(deny)** up front. The distinct-runId check runs **before** the single-runId resolution and
`RUN_DIR` lookup, so the deny is **order-independent**: it fires even when the first slice
token's runId has no `RUN_DIR` on disk (otherwise that first runId would `exit 0`-inert at the
lookup and silently bypass the net, leaving the other runs' slices unchecked). The remediation
is to merge each run's slices separately, one run at a time, so each slice's review +
test-presence is enforced against its real run.

`bin/drive-hook-lib.sh` provides the pure ref→run resolution the gates source
(`drive_runid_from_command`, `drive_runid_from_head`, `drive_run_dir`) plus the shared
active-run scan predicate (`drive_scan_active_runs`) the tool-gate and worktree-gate both reuse.

## The non-Bash tool gate (`drive-tool-gate.sh`)

`bin/drive-merge-gate.sh` fires on **Bash only**, so two tool classes could land run work
without ever tripping a gate while a `/drive` run is active on the same repo:

- **GitHub/GitLab-MCP write tools** (`create_pull_request`, `push_files`, `merge_pull_request`, …)
  reach the remote host without issuing a Bash `git`/`gh` command — the merge/ship gate never sees them.
- **Native worktree tools** (`Agent` with `isolation:"worktree"`, `EnterWorktree`) create a
  worktree on a **harness-named branch** (not `slice/<runId>/<id>`). **Recorded trace**
  (verified against `bin/drive-merge-gate.sh`): no `git worktree add … -b slice/…` Bash
  command is issued → `plan-gate`/`phasedesign-gate` never fire → the coordinator later
  integrates with `git merge <harness-branch>`, which matches **no** slice/phaseInt token → is
  **inert** to the merge gate → the slice review **and** the fail-closed `impl-presence`
  test-presence check are both skipped, and impl-presence has **no ship backstop** — so the
  per-slice test-presence invariant is voided **end-to-end**. A specific existing guarantee is
  voided by a concrete omission chain, so the worktree matchers are **built** (trace-or-drop).
  *(Only the `git push` landing chokepoint is HEAD-gated; `git merge` is ref-key gated ONLY
  for `slice/`/`phaseInt/`-named branches — that asymmetry is what makes this an omission
  chain, not a forgery.)*

`bin/drive-tool-gate.sh` is a second **PreToolUse** hook (registered on the two matchers in
the gate table above) that deny-**routes** those tools back to the gated Bash paths while a
run is active on the actor's repo. **Deny-only composition** (like the merge gate): a deny is
JSON + `exit 0`; every clean / non-matching / unrelated-repo path emits nothing. It sources
`drive-hook-lib.sh` for the shared `drive_scan_active_runs` active-run predicate (the
WorktreeCreate gate reuses the SAME predicate — DRY).

**Activation predicate (D-p2-2).** A run is **ACTIVE** iff its `~/.claude/harness-runs/<id>/`
dir has a `state.json` that parses with `.stage` a non-empty string `!= "done"` AND a
`state.json`|`event-log.jsonl` mtime within `DRIVE_TOOL_GATE_LIVE_HOURS` (default **24**). The
scan is one liveness-bounded `find` then `jq` on the ≤3 survivors. The deny is then
**repo-scoped** (concurrent-session collateral pricing — this machine runs parallel sessions,
so a machine-wide any-run-active deny is wrong):

- **MCP class** — deny iff `tool_input.owner`/`repo` (both lowercased) equal the `owner`/`repo`
  parsed from the run's `git remote get-url origin`, **or** `tool_input.repo` equals the run's
  **no-origin repo name** (basename of `RUN_COMMONDIR` — the git common dir — sans `/.git`; the
  fallback when the run has no origin). A matched write whose `owner`/`repo` is **unextractable**
  while ≥1 run is live **DENIES** (over-deny, names the run) — the class has no ship backstop.
- **Worktree class** — deny iff the payload `cwd`'s repo identity matches an active run by
  EITHER **origin identity** (the canonical parse of `git -C <cwd>`/`<repoRoot>` origin yields
  the same `host/owner/repo` key — catches a second independent clone of the same GitHub repo)
  OR **git common-dir** fast-match (`realpath(git … --git-common-dir)` — catches a linked
  worktree of the active clone; derived symmetrically on both sides, **not**
  `realpath(<repoRoot>/.git)`, which is a gitfile pointer when `repoRoot` is itself a worktree).

The **canonical origin parse** is PINNED (the SAME parse both classes use): it handles the
scp form `[user@]host:owner/repo[.git]` AND the URL form
`scheme://[user@]host[:port]/owner/repo[.git][/]`, strips `[userinfo@]` and a trailing `:port`,
lowercases `host`/`owner`/`repo`, and strips a trailing `.git`/`/` — so an SSH scp clone, an
HTTPS clone, case differences, a trailing slash, and a `:port`+userinfo URL of the same repo
all collapse to one key.

**Per-tool deny classes (§ every reason states problem + cause + exact retry path):**
`create_or_update_file` / `delete_file` (route to edit+commit → gated `git merge
slice/<runId>/<id>`), `push_files` / `update_pull_request_branch` (→ gated `git push` from the
ship worktree), `create_branch` (→ gated `git worktree add $RUN_DIR/wt/<id> -b
slice/<runId>/<id>`), `create_pull_request` (→ gated `gh pr create`), `merge_pull_request` /
`update_pull_request` (**PR lifecycle is human-owned at Gate B** — the deny closes the MCP
omission path; the Bash `gh pr merge`/`gh pr edit` twins stay ungated, a deliberately-deferred
asymmetry, not a global prohibition), and the two native worktree tools (→ gated `git worktree
add … -b slice/…`, then dispatch without isolation). A matched `mcp__` suffix **absent from the
hook's own table** (settings-vs-hook drift) fails **CLOSED** (generic write-class deny) — it
never mis-routes.

**GitLab `merge_request` coverage (G2).** The gate is exact-suffix enumeration, so the GitLab
MR-write tools are enumerated alongside the GitHub PR tools (in BOTH the settings matcher AND
the hook's `case` + deny-reason builder): `create_merge_request` (→ gated `glab mr create`),
`merge_merge_request` / `accept_merge_request` (**MR merge is human-owned at Gate B** — the
Bash `glab mr merge` twin stays ungated, the same deferred asymmetry as GitHub),
`update_merge_request` (→ human-owned at Gate B; the `glab mr update` twin stays ungated), and
`rebase_merge_request` (the GitLab analog of `update_pull_request_branch` — rewrites the MR
source branch on the remote → gated ship-worktree `git push`). GitLab **file/branch** writes
(`create_or_update_file` / `push_files` / `create_branch` / `delete_file`) already share
suffixes with GitHub and are server-wildcarded (`mcp__.+__…`), so they were already denied — G2
adds only the `merge_request`-family. Reads and review/comment tools (`get_merge_request`,
`list_merge_requests`, `approve_merge_request`, the `*_note`/`*_thread` family) are deliberately
**excluded** (parity with the shipped GitHub gate — not code-ship writes) and PASS because the
matcher never selects them. The real dominant server (`zereight/gitlab-mcp`) keys MR tools on
`project_id`, not `owner`/`repo`, so such a write hits the **unextractable-owner/repo
fail-CLOSED** over-deny (still DENY); fixtures carry `owner`/`repo` to exercise the per-tool
reasons on the server-schema axis that does.

**D3 reconciliation (no new sentinel).** Tool inputs carry no drive ref, so ref-keying (D3)
cannot fire — the evidence scan is the only signal available, not a substitute. It introduces
no new sentinel: `state.json.stage` already exists for routing, staleness self-heals via the
mtime bound (a stale "active" claim goes dormant in 24h; a parked run at Gate A/B re-arms
automatically because resume rewrites `state.sessionId` — refreshing the mtime — before any
dispatch), and scan errors degrade per-dir. A corrupt/unreadable **third-party** run dir is
**skipped with one stderr warning**; fail-closed applies to the hook's OWN logic only, never to
someone else's dir contents.

**Residuals (this hook, beside the merge gate's):**

- **Schema-drift silent fail-OPEN.** The matcher fingerprints a vendor-owned, fast-moving tool
  schema. A vendor rename/addition (`push_files` → `push_files_v2`) is a clean matcher
  non-match → the hook never fires → silent fail-OPEN, which "fail-closed on errors" cannot
  catch. **Retirement condition:** delete this hook when the harness ships conditional/managed
  tool policy. (Inverse drift — matcher fires, table lacks the suffix — fails CLOSED.)
- **Hook-invocation failure fail-OPEN.** A nonzero hook exit (crash, rc 126/127, dead path
  after a bad checkout) proceeds by platform protocol = fail-OPEN. Applies to the whole hook
  chain; the drift preflight (§ Installation) makes the dead-path case visible at install time.
- **`platform-may-not-fire-PreToolUse-on-native-worktree-tools` (Agent-with-isolation AND
  EnterWorktree)** — an **interception** residual, distinct from invocation-failure. The whole
  worktree closure rests on one runtime assumption the fixtures cannot prove: that the platform
  actually FIRES a matchable PreToolUse event for a real isolated `Agent` / `EnterWorktree`
  dispatch. Piping a fixture into the hook exercises hook LOGIC, not platform interception. A
  live deny capture (AC-16) needs the gate wired into the live `~/.claude/settings.json` — the
  **Gate-B activation ops step, out of this slice's scope** — so this slice records no live
  evidence and claims none. Per AC-16's fallback, the criterion is **discharged by this named
  interception residual** (NOT by proof); the residual plus the implement-time live observation
  taken when activation lands are the binding.
- **Forgery-class self-evasions** (consistent with the chain's omission-proof-not-forgery-proof
  model → component D): a coordinator that writes `stage:"done"`, **or corrupts/truncates/
  chmod's its OWN `state.json`** (silencing its own activation predicate — the same class as
  `stage:"done"`), or lands work in a **second clone whose `origin` was rewritten/removed** (no
  origin key, no shared common dir → unrecognized). None is an omission gap for the forms
  `/drive` emits.
- **Origin host-alias non-reconciliation.** The parse keys on the literal `host` in `origin`, so
  two same-repo clones using a `~/.ssh/config` host alias (`github.com-work`) vs `github.com`
  under-match. A followup.
- **Parked-run dormancy window.** A run parked beyond the liveness window is fail-open until
  resume re-arms it — acceptable, a parked run isn't dispatching.

## The WorktreeCreate gate (`drive-worktree-gate.sh`)

The PreToolUse tool gate above catches `Agent` with `tool_input.isolation:"worktree"` and
`EnterWorktree`, but the subagent **frontmatter** `isolation:"worktree"` field is NOT reliably
surfaced in `tool_input` (verified against the Claude Code hook API), so a PreToolUse-only gate
can **miss** it. `WorktreeCreate` is the **authoritative** interception point: it IGNORES
matchers and fires on ACTUAL native worktree creation for **both** the `--worktree` CLI flag AND
frontmatter `isolation:"worktree"` (empirically proven in this repo's spike — both fire the
event and both are blocked by exit 2; a Bash `git worktree add` subprocess fires **no** event,
so `/drive`'s own Bash-created slice/phase/ship worktrees are never wedged).

`bin/drive-worktree-gate.sh` is a **WorktreeCreate** hook. It sources `drive-hook-lib.sh` and
self-gates purely on the shared `drive_scan_active_runs` predicate — the SAME active-run scan
the tool gate uses (extracted into the lib for DRY):

- **DENY = exit 2 + a stderr routing reason** while a run is active (the documented
  WorktreeCreate deny is exit 2 — there is no `permissionDecision` JSON for this event). The
  worktree is not created; the reason routes to the gated Bash `git worktree add … -b
  slice/<runId>/<id>` so the merge gate can enforce review.
- **jq absent → FAIL-CLOSED = DENY (exit 2)** (D-w2), matching the PreToolUse tool gate's
  jq-absent posture. A fail-OPEN here would reopen the exact frontmatter-isolation bypass this
  authoritative gate exists to close.
- **Idle (no active run) → PROVISION.** `WorktreeCreate` is a **provisioning** hook: once
  installed it OWNS the outcome, and a bare `exit 0` with **no** stdout path is itself an error
  that FAILS creation ("hook succeeded but returned no worktree path"), which would wedge ALL
  native worktree creation machine-wide. So the idle path **creates** the worktree (derived from
  the payload `name`+`cwd`) via `git worktree add --detach` and **echoes its path** to stdout —
  the empirically-verified contract (a bare echo without creating does NOT work: Claude Code
  expects the worktree to already exist at the echoed path). A bare `exit 0` is a design
  violation.

**Not repo-scoped (D-w1).** Unlike the tool gate, the WorktreeCreate gate denies while **any**
active run with a non-empty `repoRoot` is present on the machine (`drive_scan_active_runs`
already skips no/empty-`repoRoot` runs, so an early-setup run does not force a deny). This is
the SAFE direction — an over-deny of native worktree creation in an unrelated repo is
recoverable via Bash `git worktree add` — and it keeps repo-scoping's `parse_origin`/common-dir
machinery off the active hot path (during a run the gate is pure exit-2).

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
"reason":…}`. It persists across turns until the audit is clean; the human can always
interrupt, and any platform consecutive-block limit overrides it (correct escalation, not
infinite persistence). It exists to catch the narrow window where hooks were installed mid-run
inside an in-flight phase; the merge → advance → ship gate chain is the actual
guarantee.

## Durable checkpoint & rebirth

A long run can fill its context window before DONE. `/drive` detects the pressure and hands
the run off to a fresh session at a **proven-safe boundary** (the flow-level walkthrough is
`docs/flow.md` § "Context-pressure rebirth"). The handoff is irreversible, so it is gated on
a **narrator-independent proof of resumability** — the same git-is-truth posture as the
review gates above.

**The proof = `--mode checkpoint` AND `--mode state-lint`, both clean** (fail-closed: a
failing proof never opens the pause; resume **re-proves** before continuing). The two modes
are deliberately separate:

- **`--mode checkpoint`** is a pure function over **git refs + durable `$RUN_DIR` markers** —
  it **NEVER reads `state.json`**, so the proof can be re-run by any successor or external
  auditor to the same answer. It is clean iff: no open `inflight-*.marker`; every
  `phaseInt/<runId>/<P>` ref resolves and relates to `drive/<runId>` by ancestry (else
  `phaseInt-divergent`); every `slice/<runId>/<id>` ref resolves; and every counter artifact
  is well-formed (`unparseable-review` / `unparseable-harden` / `unparseable-finalize` /
  `epoch-gap` / `regress-mismatch` / `epoch-unmarked` otherwise). An open in-flight marker → `inflight-open`.
  Its envelope carries a `counters` key — the single artifact-derived computation point the
  resume-repair path consumes. Markers:
  - **In-flight dispatch markers** (`inflight-<kind>-<scope>.marker`) — one per coordinator
    dispatch unit, written before dispatch and cleared only after the result is fully
    recorded. Any open marker at the proof = "not a safe boundary".
  - **Redesign-epoch markers** (`redesign-<P>-r<R>.marker`) — append-only, written before the
    epoch's state mutation; they make `redesigns` reconstructable from disk.
  - **`checkpoint-complete.marker`** — the proof RECORD (not an authorization). Its `proof.tip`
    must equal the `drive/<runId>` tip — necessary, **not sufficient** (later work can postdate
    a tip-matching file), so any consumer needing current safety re-runs the proof. It is
    **single-use**: the resume path validates then deletes it as its first act.
- **`--mode state-lint`** is the **ONLY** mode that reads `state.json`. It sanity-checks the
  load-bearing **routing fields** the successor's resume reads — `state.json` parses as a JSON
  object (`unparseable-state` otherwise); `stage` is a real pipeline stage (`stage-malformed`);
  `phaseList` is a non-empty array of phase ids each matching `^[0-9]+[a-z]?$` (digits + an
  optional single lowercase-letter epoch suffix, e.g. `1`, `2`, `4a`) — empty only while
  `stage` ∈ {premises, plan} (`phaselist-malformed` otherwise); each slice-id KEY matches
  `^[0-9]+[a-z]?\.[0-9]+$` (phase id `.` slice number, e.g. `1.2`, `4.3`), its `step` is in
  the 6-value enum, `owns` is a non-empty string array, and `deps` is an array whose every
  element matches the same slice-id grammar (`slice-routing-malformed`, one per offending
  slice, or `slices-malformed` for a non-object container past plan); `verify`/`ship` are well-shaped
  (`verify-malformed` / `ship-malformed`); and `waiting` is `null` or a known pause token
  (`gateA`|`gateB`|`rebirth`|`stop:<…>`|`ask:<…>`) the resume/Stop-hook branch on
  (`waiting-malformed` otherwise). It validates **routing-field presence + meaningful
  routability only** — never value cross-checks against git.

**sessionId rebind on resume.** The Stop hook attributes a run by exact
`state.sessionId == payload.session_id` match (`bin/drive-stop-hook.py`). So the resume path
rewrites `state.sessionId` to the live session **first**, before anything else — otherwise
the continuation hook never re-attaches and the run could rebirth at most once.

**Detection data file.** Window-by-model thresholds live in `bin/rebirth-thresholds.json`,
read by both the statusline and the Stop hook. It is **canonical-by-reference** — installers
symlink `bin/`, never copy it, so the data file + its resolver (`bin/rebirth_thresholds.py`)
resolve by sibling path with **no install or sync step** (§ Installation). Known
200k-window model families get `windows[].match` entries; an unknown model falls back to
`defaultWindow` (1M) — see the window-table residual note under § Rebirth residuals.

## Installation

```
bin/install-drive-hooks.sh
```

Idempotently `jq`-injects the **four** enforcement hooks (**five** settings entries) into
`~/.claude/settings.json`: PreToolUse(Bash) → `drive-merge-gate.sh`, Stop →
`drive-stop-guard.sh`; for the non-Bash tool gate — PreToolUse(the enumerated GitHub/GitLab-MCP
write matcher) → `drive-tool-gate.sh` **plus** PreToolUse(`^(Agent|EnterWorktree)$`) →
`drive-tool-gate.sh`; and WorktreeCreate → `drive-worktree-gate.sh` (matcher-less). Both
`drive-tool-gate.sh` and `drive-worktree-gate.sh` are **reserved basenames** in the installer's
strip-managed/append canonicalization; each is registered as a **bare path, no argv**. Keyed on
the script basename so re-running is a no-op and a moved/renamed path migrates (each
independently). It writes a timestamped backup, preserves all existing hooks, and fails loudly
on malformed JSON. A target other than the default can be passed as `$1` or via
`$DRIVE_HOOKS_SETTINGS` (used by the tests).

**The MCP matcher activates only after a re-install (D-w5).** The live `~/.claude/settings.json`
carries the OLD matcher regex until `install-drive-hooks.sh` is re-run — the settings matcher is
what triggers hook invocation, so the G2 GitLab suffixes (and any future matcher change) only
take effect after re-install. A machine on the old matcher shows the drift preflight's partial
tool-gate registration WARN (matcher-string mismatch), nudging the re-install — self-healing,
not a wedge.

Before the confirm prompt the installer runs a **READ-ONLY drift preflight**: it derives the
live gate directory from the settings file and WARNs (never blocks) if the live enforcement
worktree lacks `drive-tool-gate.sh`, lags the settings entries, or runs a `drive-merge-gate.sh`
that differs from this checkout's — the machine-checked verification of "merged ≠ live".

**Activation location is load-bearing.** The live gate hooks execute from the pinned
`~/.claude/drive-enforcement-worktree` (detached HEAD). Merging to `main` does NOT activate the
new hook — re-run `install-drive-hooks.sh` **from INSIDE that worktree** (after advancing it),
because the installer's basename-keyed canonicalization would otherwise MIGRATE the live gates
to whatever checkout you run it from. The repo never commits `~/.claude/settings.json`; the PR
carries the scripts, installer, and docs.
Requires `jq` on `PATH`.

### Verify it's active

```
jq '.hooks.PreToolUse, .hooks.Stop, .hooks.WorktreeCreate' ~/.claude/settings.json   # all five entries
# PreToolUse: drive-merge-gate.sh (matcher "Bash") + drive-tool-gate.sh (MCP-write matcher)
#             + drive-tool-gate.sh (matcher "^(Agent|EnterWorktree)$"); Stop: drive-stop-guard.sh;
# WorktreeCreate: drive-worktree-gate.sh (matcher-less)
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
(`drive-conformance.sh`, `drive-merge-gate.sh`, `drive-tool-gate.sh`, `drive-worktree-gate.sh`,
`drive-hook-lib.sh`, `drive-stop-guard.sh`, plus the installer and the end-to-end enforcement
test). Run them with a per-file loop (and they also run in CI as the `bash-suite` job):

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
- **Gate matcher — shell-accurate command tokenization (the boundary principle).** The
  command parsers (`subcommand_of`, `action_after`, `git_target_repo`, `push_ship_runid`)
  lex `$CMD` through ONE shared `tokenize_cmd` (a bash-3.2 char state machine — no `eval`, no
  command execution) rather than raw `set -- $CMD` whitespace word-splitting. The gate
  intercepts the command STRING in a PreToolUse hook **before the shell expands it**, so it
  faithfully reproduces only what is a deterministic function of the literal string:
  **quote-removal + word-splitting**, plus two cheap lexical resolutions —
  **line-continuation** (a backslash immediately followed by a newline is elided, both
  unquoted AND inside double quotes, exactly as bash does; NOT inside single quotes) and a
  **leading `~/` or bare `~`** in a repo-locating path value (`-C`/`--git-dir`/`--work-tree`),
  which `expand_tilde` resolves to `$HOME`. This closes silent bypasses on **legitimate**
  input: a quoted path **with a space** (`git -C "/tmp/unreviewed repo" push`) is now one
  `-C` value (not split into `"/tmp/unreviewed` + `repo"`); `""`/`''` preserve an **empty
  arg** (so `git -C "" push` is a git no-op → identity stays `$CWD` → the drive HEAD is seen
  → DENY); a line-continued `git push \`↵ and `git -C ~/drive-repo push` both resolve to the
  same target git would use. The tokenizer handles single/double quotes and backslash
  escapes.
  - *Fail-safe (unterminated quote):* an **unterminated quote** is a real shell error — the
    command would be rejected and git would never run — so the tokenizer returns "no tokens"
    and the gate goes **inert**, never emitting a mis-split argv that could desync the gate
    from git (safe because the command cannot execute). NOTE: a **trailing bare backslash**
    is *not* a shell error — bash runs `git push \` as `git push`, dropping the dangling
    backslash — so it does NOT fail-closed-as-unparseable; the lexer drops the backslash to
    match bash, and any residual evasion via a trailing backslash is a forgery-class residual,
    not an omission gap. (The round-2 comment that lumped a trailing backslash in with
    unterminated quotes as "the shell rejects it" was factually wrong and has been corrected.)
  - **Quote-aware expansion-active flags (`_TOK_EXP`).** The lexer emits, per token, a flag
    marking whether that token carried a construct bash WOULD expand from the literal string —
    an **unquoted or double-quoted** `$`/backtick, an **unquoted brace expansion** — BOTH the
    **comma form** `{…,…}` (a `,` inside an open brace) AND the **range form** `{…..…}` (a `..`
    inside an open brace): an embedded range CAN synthesize a managed verb or ref
    (`pus{g..h}`→`pusg push`, `slic{e..f}/R/4a`→`slice/R/4a`), so both are flagged fail-closed —
    or an **unquoted leading `~user`**. A **single-quoted** `'slice/$run/4a'` or
    `'~root/repo'` is LITERAL (bash never expands inside `'…'`), so its flag is **0** — the
    gate does not mistake it for an expansion. This preserves quote context that a strip-then-
    rescan of the quote-removed token would lose. (Brace expansion is deterministic from the
    string, like line-continuation, but resolving its cartesian product is out of scope — the
    gate detects the brace and fails closed rather than reimplement it.)
  - **Ref extraction reads the LEXED command (`CMD_LEX`), not the raw `$CMD`.** The
    `slice/…` / `phaseInt/…` ref greps and `drive_runid_from_command` consume the command
    re-serialized from the lexed tokens (one per line), so they see the SAME string the argv
    parsers do — line-continuations elided, quotes removed. Reading the raw `$CMD` here would
    **desync** the gate from git: a ref split by a `\`↵ continuation (`git merge sli\`↵`ce/R/4a`)
    is one token `slice/R/4a` to git AND the lexer, but the raw string still holds the
    backslash+newline → a raw grep would miss the ref → the gate would go inert on a real
    managed merge.
  - **Fail-closed on unresolvable shell EXPANSION (`managed_git_expansion_deny`).** The gate
    resolves the literal string + line-continuation + `~/`; it CANNOT reproduce expansions
    that need external context — `$var`, `$(…)`, backticks, `$'…'` (ANSI-C), `~user` (passwd
    lookup), or a brace expansion `{…,…}` (comma) / `{…..…}` (range — `pus{g..h}`→`push`).
    *(Precision limit, fail-closed-safe: the range detector keys on two consecutive UNQUOTED
    dots; a pathologically escaped/quoted dot pair like `{1\..2}` — which bash leaves literal —
    may still be flagged and DENIED. This is an over-deny in the SAFE direction on a token
    `/drive` never emits, not a bypass.)* When an **expansion-active** token (per `_TOK_EXP`)
    sits in a **decision-critical** position of a **would-be-managed operation**, the gate
    **FAILS CLOSED = DENY** ("cannot safely parse a managed command containing shell expansion
    … use a literal, fully-expanded form"). Two managed-binary branches:
      - **git** (START binary `git`, subcommand a managed verb `push`/`merge`/`branch`/
        `worktree` OR the subcommand token *itself* expansion-active so a managed verb can't be
        ruled out, e.g. `git $'push'` / `git {push,}`): decision-critical tokens are the
        subcommand, every `-C`/`--git-dir`/`--work-tree` value, and the **per-verb ref operand(s)
        ONLY** — extracted exactly as the gate's matchers read them (`push` → refspecs after the
        remote; `merge` → the ref positionals, skipping `-s`/`-X`/`--strategy*`/`-m` VALUES;
        `branch` → the name + start-point, skipping `-u`/`--set-upstream-to`; `worktree add` →
        the `-b`/`-B` branch VALUE only, **NOT** the worktree-PATH positional or the start-point
        sha). This **precise** scan (not a blanket positional scan) is what keeps `/drive`'s OWN
        commands from being false-denied: `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id>
        <sha>` (the `$`-path is the worktree path, the literal `-b` is the real ref) and
        `git merge -s $strategy slice/<runId>/4a` (the `$`-strategy is a value, the literal is the
        ref) both stay allowed; only a tainted REAL ref (`git merge $ref`, `git push origin $ref`,
        `git worktree add /p -b $branch`) denies.
      - **gh/glab** (START binary `gh`/`glab`): ship detection manages `gh pr create` /
        `glab mr create`, so if the **subcommand** (`pr`/`mr`) OR the **action** (`create`) token
        is expansion-active — `gh {pr,} create`, `gh pr {create,}`, `glab {mr,} create` — the
        pair can't be confirmed from the literal string → DENY. A clearly-different literal pair
        (`gh pr view --json $x`, `gh issue list`) is NOT force-denied (no over-deny on unrelated
        gh/glab).
    This ends the bypass class where `git $'push'` / `git {push,}` / `gh {pr,} create` lexed to a
    non-managed subcommand → went inert, or `git -C ~user/repo push` mis-targeted. It is
    omission-safe: an unresolvable managed command DENIES instead of silently bypassing.
    **Non-managed commands are unaffected** — `echo $X`, `ls $HOME`, `git commit -m "$msg"`,
    `git log --format=$x`, and a **read-only verb that merely names a managed ref**
    (`git -C "$HOME/repo" show slice/R/4a` — `show` is not a gated op) all stay **inert** (no
    over-deny; a managed ref alone does NOT make a command would-be-managed — only a
    managed/unresolved *verb* does). Full `$var`/`$(…)` *resolution*
    (computing the runtime value) remains out of scope by design (→ Component D), the same
    class as the literal-ref / `$GIT_DIR` limitation below; the gate refuses what it cannot
    safely interpret rather than reimplement the shell. *Residual (forgery-class, → Component
    D):* a single-quoted **`'~/repo'`** (literal `~/`, which bash does NOT expand inside `'…'`)
    is still tilde-resolved by `git_target_repo`'s `expand_tilde` to `$HOME/repo`, a marginal
    mis-resolution — non-exploitable in practice (the literal `~/repo` dir almost never exists,
    so git errors and nothing ships).
  - **Variable refs that pass the per-unit gates remain a documented limitation only where
    fail-closed does NOT fire.** The mid-build per-unit REVIEW gates (slice-merge review /
    phase-merge) deliberately fail
    **OPEN** (a transient error can't wedge a run); a runtime-variable ref in a *non-managed-
    verb* position that those gates would have read (e.g. `git merge "$ref"` where `$ref`
    holds a slice ref) is parsed with the literal token, not the runtime value — but a managed
    verb (`merge`) with a tainted REF operand now trips the fail-closed deny above. Any
    residual is backstopped by the HEAD-based ship gate (whole-tip diff) plus the `/drive`
    literal-ref instruction. Same forgery/evasion class as the `$GIT_DIR`/`$GIT_WORK_TREE`
    env residual below (→ Component D), not an omission gap for the literal command forms
    `/drive` actually emits.
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
- **`impl-presence` is omission-proof, not forgery-proof.** The IMPLEMENT-stage TEST-presence
  check proves a slice's diff *touched* a runnable test path (or declared a `Drive-Test-Waiver`
  trailer) — it does NOT prove the test is meaningful. A **forged trivial/empty test file**
  (`tests/test_noop.py` with `def test_noop(): pass`) passes the gate, exactly like a forged
  SHA-bound review. Test *quality* is harden's "add missing tests" lens + Component-D territory,
  not this gate's. Same class as the other forgery residuals here.
- **Attached short-option branch refs (`-b<branch>`) are out of scope.** The gate matches
  branch/ref operands in the SEPARATE (`-b slice/<id>`) and `=` (`-b=slice/<id>`) forms that
  `/drive` emits; git also accepts the ATTACHED form (`-bslice/<id>` as one token) for
  `worktree add`/`checkout`/`switch`. A managed ref smuggled via the attached form is a
  forgery-class residual (→ Component D): `/drive` always emits the separate literal form, and
  a precise verb/position-aware attached-form parser was deliberately NOT added because the
  shortcut (a global token split) introduced wrong-review and over-deny regressions — the
  cost/risk of a correct attached parser is not warranted for a form `/drive` never emits.
- **`git push` classification is best-effort over arbitrary push syntax.** The ship
  gate errs *toward* gating — it gates a push if any refspec source is the drive branch,
  an aggregate flag (`--all`/`--mirror`) is present, or HEAD is the drive branch — so the
  common forms (and `git push origin main drive/<id>`) are caught. But exotic forms (e.g.
  `--mirror` from a non-drive HEAD, or server-side refspec expansion) can still slip the
  PreToolUse matcher. The **authoritative** ship guarantee is therefore the in-prose
  `--mode ship` conformance check in `drive-ship.md` plus the single canonical push form
  `/drive` actually emits — the matcher is the fast path, not the sole guard.
- **WorktreeCreate gate is machine-wide, not repo-scoped (D-w1).** While a `/drive` run with a
  non-empty `repoRoot` is active, native worktree creation (`--worktree` / subagent
  `isolation:"worktree"`) is blocked in **every** repo on the machine, not just the run's repo —
  the SAFE direction (never a bypass; recoverable via Bash `git worktree add`), chosen to keep
  repo-scoping's `parse_origin`/common-dir machinery off the active hot path. Repo-scoping it to
  the payload `cwd` is a follow-up. A run still in **early setup** (no `repoRoot` yet) does NOT
  force a deny — the shared predicate skips no/empty-`repoRoot` runs (inherited verbatim from the
  tool gate's scan); a native worktree created in that brief window is un-gated by this event
  (bounded — no slice/phase work is dispatched that early; self-resolves once `repoRoot` is
  written). Both are inherited from the shared predicate, not new gaps.
- **WorktreeCreate gate denies on a jq-less machine (D-w2).** With `jq` absent the active-run
  scan cannot run, so the gate fail-CLOSES (denies native worktree creation) — CONSISTENT with
  the PreToolUse tool gate's identical jq-absent fail-closed, and `jq` is a documented `/drive`
  precondition, so this is the accepted safe direction. The narrower corrupt-active-run
  fail-open (a genuinely-active run whose OWN state.json is corrupted, when it is the only run)
  is the shared predicate's documented own-logic-only posture — inherited, not new.
- **Hook-chosen worktree path (D-w3).** With the WorktreeCreate gate installed, the native
  worktree location is hook-chosen (a sibling of the repo dir, named for the worktree) rather
  than Claude Code's built-in default. Reconcile with the platform's documented default path
  convention if the divergence annoys — a follow-up, not a correctness issue.
- **Forgery / hostile-environment scan-blinding residual (non-Bash gates; out of scope).** Both
  non-Bash gates decide on a run-presence scan of `~/.claude/harness-runs`. A hostile actor who
  can manipulate the scan's **execution environment** can blind it: e.g. put a stub `find`/`sort`
  on `PATH` that exits 0 with no output, or `chmod 000` an individual run's own **subdir** to
  self-hide it from `find` (find still enumerates the rest of the root). This is
  **deliberate-evasion / forgery-class**, explicitly OUT OF SCOPE — consistent with the system's
  stated boundary ("omission-proof, not forgery-proof"; run-presence is far harder to
  *accidentally/omissively* suppress than to *deliberately* forge → Component D). The
  WorktreeCreate gate DOES fail-closed on the two **non-hostile / accidental** blind-scan cases
  it can cheaply detect — a **missing** scan binary (jq/find/sort/dirname/git absent, D-w2) and a
  present-but-**unreadable ROOT** (`chmod 000 ~/.claude/harness-runs` → exit 2) — but it does not
  defend a *broken-but-present* tool or a self-hidden subdir (that needs a trusted execution
  environment the design does not assume).
- **Inherited: the shipped PreToolUse `drive-tool-gate.sh` has the SAME scan fail-open.** The
  shipped gate never prechecks its scan tools (`find`/`sort`) and shares
  `drive_scan_active_runs`, so a missing/broken scan tool fails it OPEN identically. This is a
  **pre-existing** shared-scan residual — inherited, NOT introduced by the WorktreeCreate gate,
  which was hardened here — and hardening the shipped PreToolUse gate is a separate follow-up
  (it changes shipped gate behavior and is forgery-class).

### Rebirth residuals (acknowledged limits)

The context-pressure rebirth (§ "Durable checkpoint & rebirth") makes honest, bounded claims —
these are its known limits, stated rather than overclaimed:

- **Single-catastrophic-turn overshoot.** Detection fires at a turn END (the Stop hook steer).
  One enormous single turn can exhaust the window mid-turn before the steer fires — no check
  can interrupt a turn already in flight.
- **Absent-hook degradation.** The Stop hook is the SOLE detector; with **no** Stop hook
  installed there is NO context-pressure detection at all (the prior coordinator soft-check
  fallback was removed — heuristic self-measurement over-triggered false handoffs). Install
  the hook via `bin/install-operating-rules.sh`.
- **Gate/STOP-collision human-restart edge.** When a Gate (A/B) or non-decision STOP and a
  rebirth are both due, the **gate/STOP wins** and `rebirth_pending` is re-derived in the
  successor (not carried). The rebirth handoff's paste-ready `/drive <runId>` line is the
  resume path; Gate A's Seam A handoff emits the resume line and Gate B emits none (immediate
  push) — no goal is handed at any gate (the installed Stop hook drives turn-to-turn
  continuation).
- **"Lossless" is precise.** A resume reconstructs from **git + durable artifacts** (refs,
  markers, review/harden files) — those are authoritative. `state.json` is a best-effort
  **routing HINT**: written atomically (temp + `mv`, never a torn in-place write) and
  sanity-checked by `--mode state-lint` for routing-field *shape*, but its values (the
  counters) are never a proof input — the load-bearing position is always re-derived from
  artifacts. **Out of scope (followup):** deep cross-validation of each slice's `owns`/`deps`
  GRAPH against git truth — state-lint validates presence + routability, not graph correctness.
- **Prompted, not programmatic.** The rebirth handshake is a HUMAN handshake by design — the
  harness does not use programmatic self-restart/session-spawn; a fresh session is started by
  the human pasting the `/drive <runId>` resume line. The handoff only *proves + presents*; re-entry is external.
- **Legacy-run residual.** Runs whose artifacts predate Phase 1 have no in-flight/epoch
  markers; marker-absence reads as "safe" and `redesigns` falls back to the `state.json` hint.
  Acceptable — such runs never had marker discipline.
- **Stale pre-redesign CONVERGED review residual (now closed).** The epoch-aware
  phasedesign-gate now rejects a stale pre-redesign CONVERGED `review-phasedesign<P>-N.md`
  after a REDESIGN (it resolves the current epoch) — a hole closed as a side effect.
- **Window-table maintenance.** An unknown model falls back to `defaultWindow=1000000`
  (fail-open — a future 200k model never arms until it gets a `windows[].match` entry in
  `bin/rebirth-thresholds.json`; owned by the C1 arming-by-window-match follow-up).
- **`-r<digits>`-suffixed phase id.** The epoch delimiter `-r<digits>` makes a phase id that
  itself ends in `-r<digits>` ambiguous against an epoch token; the conformance gate
  fail-closes (flags) such ids, so they are effectively unsupported.
