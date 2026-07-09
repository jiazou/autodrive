# TODO

Architectural follow-ups deferred by /drive finalize passes.

## Whole-repo audit — bugs / logic / inconsistency / slop (2026-07-09)

Multi-agent adversarial audit over the whole tree (10 lens auditors → per-finding
refuter → completeness critic). ~40 unique issues survived dedup against this file and
`.harness/followups.md`. The workflow's automated verifier pass completed only for the
specs/gates/critic dimensions (session-limit killed the mission-control verifiers), so
**every item below was subsequently confirmed by direct hand-trace this session** —
the mission-control findings first, then all 18 specs/gates/critic findings independently
re-traced against the real code (spec cross-references read, the P1 finalize-CONVERGED
chain walked through all three consumers, regexes tested live, git history checked,
substring matches run, live `~/.claude/commands` link set and file modes inspected).
Zero refutations on hand-trace. All carry **[V]**. Two caveats found during that pass:
`skills/decant/SKILL.md:140` is mitigated by the single-remote fallback rule, and
`bin/install-drive-hooks.sh:209` bails gracefully (no corruption) via the sanity net at
:285-290. Mission-control (Python + shell) had no prior TODO coverage and is where most
new bugs live.

### P1 — real defects with gate-integrity or corruption impact
- [x] **[V] `.claude/commands/drive-finalize.md:341`** — a codex-only-P1 fix round re-binds
  `reviewed-sha` to the post-fix tip but never downgrades the Claude `## Verdict: CONVERGED`
  line, so all three finalize-CONVERGED consumers (drive.md resume router, drive-ship
  precondition #3, `drive-conformance.sh --mode ship`) read the artifact as terminal and a
  rebirth-at-boundary → ship silently skips the mandated fresh dual-voice re-audit of a
  logic-bearing fix (a TODO-named sole-catcher). *Fix:* on any `AppliedEdits: yes` round
  rewrite `## Verdict:` to FINDINGS (a fix round can never be terminal-converged); mirror in
  drive.md's resume criterion. Run the drive*.md pin suites. — **DONE (PR #76, 2026-07-09):**
  producer rewrites the FIRST `## Verdict:` line in place on both branches + all 3 consumers
  require the first `## AppliedEdits:` header == `no` via a shared first-match `applied_edits_no()`.
- [x] **[V] `.claude/commands/drive-ship.md:86`** — line 79 runs the Design-doc handoff audit
  *after* the single ledger commit, then line 86 claims the appended `HANDOFF:` entries "are
  promoted into `.harness/followups.md` by the ledger commit already made above" —
  chronologically impossible. The entries strand in `$RUN_DIR/followups.md` (GC-swept); a 2nd
  commit to fix it trips the ≤1-commit ship allowlist. *Fix:* run the handoff audit BEFORE the
  ledger-promotion commit; delete the "already made above" claim. — **DONE (2026-07-10):** audit
  runs as the ledger-promotion's FIRST action (forward-path only) so HANDOFF entries ride the
  same single commit; claim corrected; idempotent append closes the pre-commit-resume dup window
  (codex P2).
- [x] **[V] `mission-control/bin/done.py:41`** — `LOG_SECTION_RE = r"(^##\s+Log[ \t]*\r?\n?)…"`
  has a fully-optional terminator, so it prefix-matches `## Logistics` / `## Logs` / `## Logbook`
  (confirmed live: group1 → `## Log` for all three). `mc done` then splits the heading and
  mangles the user's note — silent corruption by the self-described "ONE writer into task
  notes". *Fix:* require a line boundary: `r"(^##[ \t]+Log[ \t]*(?:\r?\n|\Z))"`; add a
  `## Logistics` regression test. — **DONE (already fixed by `2e032c5`, PR #75):** the exact
  line-boundary regex landed + `tests/mc/test_done.py:123` `## Logistics` regression test.

### P2 — correctness / contract defects
- [x] **[V] `mission-control/bin/vault_tasks.py:145`** — `project = (fm.get("project") or "").strip("[]")`
  crashes `AttributeError` when `_parse_scalar` returns a list (confirmed live for
  `project: [[Autodrive]]` → `['[Autodrive]']`, and `status: [todo]`). One bracketed scalar in
  any task note tracebacks `mc tasks/standup/today/weekly`, the SwiftBar plugin, and the 6:45am
  launchd job. *Fix:* coerce list→scalar for project/status/priority/area (mirror the
  `depends_on` guard at :148-150). — **DONE (already fixed by `2e032c5`, PR #75):** added the
  `_scalar()` helper (:86) applied to project/status + `test_load_tasks_wikilink_project_coerced_to_scalar`.
- [ ] **[V] `mission-control/bin/vault_tasks.py:94`** — `_parse_frontmatter` skips any line with
  no `:` , so block-style YAML lists (`depends_on:\n  - other-task`, Obsidian's Properties
  serialization) parse as `''` → `depends_on` silently dropped → `mc standup` lists a blocked
  task as "Ready to start now" and the parallel plan dispatches work whose dep is still open.
  `tags` lists are lost the same way. *Fix:* accumulate subsequent `- item` lines under the
  preceding key as a list.
- [x] **[V] `mission-control/bin/session_summary.py:47,63`** — `tail_text` opens `hits[0]` with
  no guard and `summarize` calls it *outside* its try, so a removed/unreadable transcript (or a
  non-dict `message`) raises through `harvest.build_summaries`' `ex.map`, crashing the whole
  unattended `harvest --summarize` job — violating the docstring's "on any failure prints {}"
  per-session degrade contract. *Fix:* wrap the `tail_text` read in try/except returning "". —
  **DONE (2026-07-10):** `tail_text` read wrapped (returns "" on any read failure) + non-dict
  `message`/entry guarded with `isinstance`; RED→GREEN tests (non-dict message, unreadable file,
  summarize degrade) in tests/mc/test_session_summary.py.
- [x] **[V] `bin/drive-merge-gate.sh:293`** — `action_after`'s post-subcommand loop treats
  `--repo` as valueless (`--*=*|--*) shift`), so `gh pr --repo owner/repo create` returns
  `owner/repo` as the action, `is_ship` stays false and the ship/finalize-review gate goes inert
  (empirically reproduced: this form is INERT while bare `gh pr create` DENYs). *Fix:* consume
  separate-arg flag values (`-C|-c|-R|--repo|--git-dir|--work-tree`) in that loop and in the twin
  walker in `managed_cli_expansion_deny` (~:670), matching `detect_subcommand`. — **DONE
  (2026-07-10):** both action-loops now consume the separate-arg flag value; RED→GREEN tests
  (`gh pr --repo o/r create`, `-R`, `glab mr`, brace-tainted twin) in test/drive-merge-gate.test.sh;
  codex find-the-bypass: no residual fail-open / over-deny.
- [ ] **[V] `bin/rebirth-thresholds.json:4` + `bin/statusline.sh:35`** — the 200k tokens
  `"Sonnet 4.0"/"sonnet-4-0"/"sonnet-4.0"` are phantom forms: the real Sonnet-4 display `Sonnet 4`
  and id `claude-sonnet-4-20250514` contain none of them (confirmed), so a Sonnet-4 session falls
  through to the 1M default → the class-A rebirth hard-threshold (0.85×1M) is unreachable in a
  200k window and statusline shows ~16% at real 80%. Working `"Sonnet 4"/"sonnet-4"` entries
  shipped in `3bf4866` but the `60c4579` merge kept the broken table. Paired: **[V]
  `bin/rebirth_thresholds.py:16`** docstring describes the discarded 1M-first ordered table, and
  **[V] `tests/hooks/test_rebirth_thresholds.py:74`** never samples a real Sonnet-4 form, so the
  clobber shipped green. *Fix:* restore `3bf4866`'s ordered table in both json and statusline
  case; pin `Sonnet 4` + `claude-sonnet-4-20250514` in the five window test files (token-sweep).
- [ ] **[V] `.claude/commands/drive-design.md:74` + `.claude/commands/drive.md:247,256`** —
  REDESIGN re-queues a slice with `reviewCount:0`, but drive.md's counter reconstruction is
  one-directional `max(state, count of review-<id>-N.md)` and slice review files aren't
  epoch-qualified, so any resume resurrects the old count and shrinks the fresh cap-8 the reset
  intended. *Fix:* pick one horn — REDESIGN keeps the cumulative cap, OR epoch-qualify slice
  review filenames (like phasedesign `-r<R>`) and scope the count to the current epoch.
- [ ] **[V] `.claude/commands/drive.md:247`** — `designReview` is a seventh cap-8 counter but
  the "all six counters" reconstruction list (and the checkpoint `counters` JSON in
  `drive-conformance.sh:913`) omit it, so a crash mid-plan lets the next design review overwrite
  `review-design-N.md` and undercount the cap. *Fix:* add rule 7 `designReview = max(state,
  count of pure-integer review-design-N.md)` and add it to the checkpoint counters output.
- [ ] **[V] `.claude/commands/drive-review.md:77,82`** — no N-derivation rule for
  `harden-regress`-marked `review-phase<P>-N.md` files: the general `N = counter+1` is explicitly
  forbidden for regress but no alternative is given (round-2 harden overwrites round-1's marked
  regress review), and the state-absent fallback counts ALL pure-integer files (incl. marked)
  while claiming consistency with `drive-conformance.sh`, which counts unmarked only → false
  "N>8 STOP". *Fix:* number a regress file as (highest existing pure-integer N in the family)+1;
  exclude `harden-regress: yes` files in the phase-scope fallback.
- [ ] **[V] `.claude/commands/drive.md:127`** — the resume "Current phase" rule
  (`lowest phase in phaseList not yet an ancestor; all ancestors → PAST Execute`) is vacuously
  "PAST Execute" when `phaseList` is `[]` (plan stage), so a class-A rebirth during planning
  routes to Finalize over an empty diff → trivial converge → advance toward ship instead of
  resuming planning. *Fix:* add an explicit route — empty phaseList / `lastGate != "A"` → resume
  Stage 1; require a non-empty phaseList for the PAST-Execute derivation.
- [ ] **[V] `.claude/commands/drive.md:1318` + `CLAUDE.md:127`** — both coordinator surfaces claim
  harden "vetoes edits that would drop a criterion's coverage", but `drive-harden.md` defines no
  veto (`rg -i veto` empty; removed with de-slop). The protection is one round weaker than
  documented (only the after-the-fact harden-regress review catches it). *Fix:* reword both to
  "the harden-regress regression guard catches …", OR add an explicit veto to drive-harden.md
  Step 2/3. Pin suites apply.
- [ ] **[V] `.claude/commands/drive.md:1384`** — Stage 4c/retro resolve
  `~/.claude/commands/drive-finalize.md` (and `drive-retro.md`), but `install-operating-rules.sh`
  links commands only on re-run with no freshness preflight; the live `~/.claude/commands` holds
  a stale 7-link set missing both files, so a run driving an outside project wedges fail-closed at
  finalize. *Fix:* add a drift preflight to `install-operating-rules.sh` (warn when repo commands
  lack links), and/or fall back to the repo-checkout `.claude/commands` path in drive.md.
- [ ] **[V] `.claude/commands/drive-finalize.md:316` + `drive-harden.md:236` + `drive-ship.md:90`** —
  the "driven project's FULL test suite" is hardcoded to this repo's `bin/run-tests.sh`
  (`python3 -m pytest tests/` AND `test/*.test.sh`), so `/drive` on any other project BLOCKs each
  phase or improvises a subset — the exact under-run the canonical runner was built to prevent.
  *Fix:* "the driven repo's `bin/run-tests.sh` if present, else its documented full-suite command
  (all suites, no early-exit)" in all three specs.
- [ ] **[V] `bin/install-operating-rules.sh:156`** — the Stop-hook registration early-exits on a
  substring presence check, so re-running after a clone move (the remedy the installed `~/CLAUDE.md`
  itself recommends) keeps the dead old-path `drive-stop-hook.py` entry and refuses the new one —
  the sole context-pressure detector silently fails open. *Fix:* strip every Stop hook referencing
  `drive-stop-hook.py`, then append the current path (mirror `install_hooks.py._strip_mc`).
- [ ] **[V] `SECURITY.md:20`** — says the installer adds "four entries (three hooks)"; it actually
  writes five entries / four hooks and SECURITY.md never mentions the `WorktreeCreate →
  drive-worktree-gate.sh` hook that DENYs all native worktree creation during a run. *Fix:* update
  to four hooks / five entries, add a WorktreeCreate bullet + fail-closed posture, add
  `drive-worktree-gate.sh` to the canonicalized-basename list at :18.
- [ ] **[V] `README.md:240`** — the Testing section still teaches the first-failure
  `for f in test/*.test.sh; do bash "$f" || exit 1; done` loop that `bin/run-tests.sh` was created
  to replace (the regress-selfid masking bug, commit 611e6a6) and never names the canonical runner.
  *Fix:* replace with `./bin/run-tests.sh`; extend `test_full_suite_runner.py` to pin README.
- [ ] **[V] `.gitignore:19`** — `.claude/settings.local.json` is excluded only by machine-local
  ignores, not the committed `.gitignore`; on any other clone a subagent `git add -A` (the
  documented 1497-file sweep) can commit personal permission allowlists to the public repo.
  *Fix:* add `.claude/settings.local.json` + `.claude/scheduled_tasks.lock` to the committed
  `.gitignore`.
- [ ] **[V] `.harness/followups.md:262`** — the binding SHIP ACTION (D-coord-2) to append a
  premise-stale annotation to the `defaultWindow=200_000` ledger entry was never executed, so the
  inverted pre-C2 guidance ("falls back to 200_000 … add a `windows[].match` entry") still reads as
  live and a future maintainer would reintroduce the exact stale claim C2 removed. *Fix:* append the
  D-coord-2 annotation now (post-C2 default is 1_000_000 fail-open; add-an-entry direction inverted);
  log the missed ship action in decisions.md.
- [ ] **[V] `mission-control/README.md:30,42`** — documents an `iterm_session` binding field
  "auto from `$ITERM_SESSION_ID`" that nothing writes/reads (`mc-bind.sh` records only
  ts/event/session_id/project/task/tab_name). *Fix:* drop the field from the data model + identity
  table, or capture it in mc-bind.sh.
- [ ] **[V] `mission-control/README.md:178` + `mission-control/skills/mc/SKILL.md:54`** — both claim
  "no existing task/doc is ever modified" / "only --draft/--log write", contradicted by `done.py`
  ("the ONE writer into task notes") and the weekly skill editing frontmatter. Misleads a user
  evaluating install safety and an in-session agent into running `mc done` as if read-only. *Fix:*
  reword to name `mc done` as the one task-note writer (atomic, logged).

### P3 — slop / doc-drift / minor inconsistency
- [ ] **[V] `today.py:98`** SwiftBar rows hardcode `color=#000000` → illegible in dark mode; use a
  `#000000,#ffffff` light,dark pair. **[V] `today.py:93`** the project name (free-text from
  `mc bind --project`) isn't `|`-sanitized like the label, so `Ops | Infra` breaks the SwiftBar row.
- [ ] **[V] `install_hooks.py:67`** builds `f"{sys.executable} {MC}/bin/mc-hook.py {status}"` unquoted
  → a spaced deploy path breaks all three MC hooks silently (sibling installers quote). Use
  `shlex.quote`.
- [ ] **[V] `harvest.py:344` + `standup.py:68,206`** use `str.replace(HOME, "~")` — the exact
  mangling `harvest.home_rel`'s own comment warns against ($HOME appearing twice, or as a
  non-prefix substring). Route all three through `home_rel()`.
- [ ] **[V] `vault_tasks.py:97`** indented/nested frontmatter keys shadow top-level ones (reader
  strips indentation; `done.py` writes column-0 only) → reader/writer disagree. **[V]
  `vault_tasks.py:157`** priority is never case-normalized, so ASCII sort ranks `P3` above `p1`.
- [ ] **[V] `mc-bind.sh:43,62`** — short-id resolution globs dead session files (no `kill -0`
  liveness like harvest) so "No live session matches" / false-ambiguous; and a 13+-char non-UUID
  arg is stored verbatim, writing a binding that never joins any session. **[V]
  `session_summary.py:43`** picks `hits[0]` (arbitrary glob order) instead of newest transcript.
- [ ] **[V] `done.py:56`** `_resolve` opens the matched note unguarded (sibling `load_tasks` wraps
  the read) → a non-UTF-8/unreadable note tracebacks instead of the clean not-found path.
- [ ] **[V] `mission-control/README.md`** doc-count drift: "the three skills" but four are deployed
  (`:80,143` omit `mc`); Commands table (`:132`) omits the shipped `mc done`; "auto-launches at
  login" (`:94,141`) but `install.sh` never registers a login item.
- [ ] **[V] `skills/harvest/SKILL.md:40,91`** — stale pre-rename codename "Orchard" (product is
  Mission Control) and a wrong claim that the binding carries `color`; the vault-listing `ls` skips
  the `~/mission-control/config` fallback the engine resolves, so a config-only vault reports zero
  tasks.
- [ ] **[V] `skills/decant/SKILL.md:41`** — Step 1 tells the agent to `git grep` the memory dir,
  which is not a git repo (`fatal: not a git repository`) and can't select by mtime → the
  subagent-entry inventory is silently skipped. Use `find … -newermt`/`ls -lt`. **[V] `:43`** the
  "0 new entries → skip to step 5" jump skips Step 4's missing-lessons scan (the step that case
  exists for) — retarget to step 4. **[V] `:140`** binds `UPSTREAM` as "(this project: `upstream`)"
  but autodrive has only an `origin` remote.
- [ ] **[V] `.claude/commands/drive-finalize.md:368` (+ `:24,349`)** — the "Phase-2 wiring
  obligations — NOT built here" section describes long-shipped wiring (ship terminal-R, checkpoint
  finalize classifier, `finalizeRound`, run-graph node, TODO promotion) as pending; an agent may
  re-implement or distrust the live gate. Rewrite present-tense (token-sweep pin migration).
- [ ] **[V] `.claude/commands/drive-ship.md:83`** — the Design-doc handoff audit references an
  undefined "shared design doc" and emits a never-bound `<design-doc path>` placeholder → the agent
  fabricates a path into the committed ledger or skips the step. Bind the doc (e.g. the one
  CLAUDE.md/docs names; else `(no design doc — create one)`).
- [ ] **[V] `.claude/commands/drive-harden.md:157` + `drive-finalize.md:225`** run bare `codex exec`
  without the `mkdir -p "$RUN_DIR/tmp"` + `TMPDIR=…` export that `drive-review.md` mandates (D5), so
  each round litters `/tmp` with un-swept codex scratch. Prefix both blocks (check the fenced-block
  pin tests first).
- [ ] **[V] `.claude/commands/drive.md:1259`** references "the declared gitignored config allowlist
  (`.env`, …)" with no declaration site anywhere → the coordinator either skips the copy (slice
  tests needing `.env` BLOCK) or guesses. Bind it (e.g. a `state.json`/design `configAllowlist`;
  absent → copy nothing). **[V] `:648`** the stranded-marker `mv codex-raw-<scope>.log` aside rule
  covers review units only; a stranded harden unit's `codex-harden-<P>.log` has the same orphan-
  append hazard.
- [ ] **[V] `CLAUDE.md:166`** the state.json run-model enumeration omits `task`, `baseSha`,
  `phaseList`, `verify`, `ship` (drive.md's template has all five; `phaseList`/`baseSha` are
  load-bearing for the resume router). Add them; extend `test_state_json_shape.py` if applicable.
- [ ] **[V] `bin/install-operating-rules.sh:104`** the command/skill symlink loops never prune links
  for files removed/renamed in the repo (the plan.md→drive-plan.md rename already happened), leaving
  dangling `~/.claude/commands/<old>.md` symlinks that re-runs never heal. Prune repo-owned links
  whose target no longer exists before linking.
- [ ] **[V] `bin/install-drive-hooks.sh:209`** the comment claims hook containers are "normalised to
  arrays" but jq `// []` only defaults null/missing — a wrong-typed shape (`{"hooks": []}`, or a
  bare-dict Stop entry) aborts the install under `set -e` with a raw jq error and `.tmp.$$` litter.
  Type-normalize like the sibling installer, or fix the comment.
- [ ] **[V] `bin/rebirth_thresholds.py:4`** docstring says "**Both** `bin/drive-stop-hook.py` …
  import this module" but names one consumer (the coordinator soft-check was removed) — leftover
  dual-consumer phrasing. **[V] `test/drive-tool-gate.test.sh`** is the sole bash suite committed
  `100644` (no exec bit) — `git update-index --chmod=+x`.
- [ ] **[V] `TODO.md:379`** — the "Wire `/drive-retro` into the run-wrap sequence" directive is
  already implemented in `drive.md:1454-1461`; mark done / delete with a pointer, and sweep the
  matching stale HANDOFF at `followups.md:682`.

## /drive efficiency plan R1–R9 — from docs/efficiency-audit-2026-07-08.md (2026-07-08)

**Problem:** a ~1000-line change takes a full day. The audit (19-agent workflow: 5 history
miners over 22 runs' event logs / 262 codex logs / 189 review artifacts → 12 candidates →
12 adversarial verifications) found the day is NOT mostly review compute:
- ~half is **human latency**: 43.2h of decision-free `/drive <runId>` paste waits at
  rebirth seams (16 seams / 7 runs, median 2.12h each — an *attended* Seam B handoff costs
  7 min) + 40.2h of unnoticed gate parks (6 runs parked at human-answer states as of the
  audit date, one at gateB 3+ weeks).
- Next third is **codex**: ~72% of machine-active loop time; median 5.4 min/call, p90
  10.3 min, 12 calls >1h, one silent 10.4h overnight auth-outage death; codex re-runs the
  full suites (321 pytest + 216 bash) inside every round.
- **Round churn** is real but third-order: of 101 classified rounds ≥2, only ~12% found a
  genuinely NEW orthogonal P1; ~23% same-class residuals, ~28% pure all-clear
  certifications, ≥13 rounds adjudicating codex false-positives (worst overrule 3h28m).

**Quality constraint (binding):** every item below preserves the layers history shows are
sole catchers. DO NOT revive the refuted variants — each was killed by a specific
historical counterexample recorded in docs/efficiency-audit-2026-07-08.md § Dropped
components: pressure-conditional seams, reviewer narrowed to closure-verification,
settled-scope re-audit prohibition, slice-review-adopted-as-phase-review,
plan+phasedesign collapse, same-invocation harden/finalize convergence on green-suite,
wall-clock codex kill, blanket round-2+ effort downgrade, textual pin-exists→P2,
time-boxed overrule repros minting refutations. Also out of scope for this plan: R10–R12
(confirm-round diet, single-phase fast paths, phase-finding routing) — opportunistic,
lower ratio, some parked behind a TR-9-style re-measure.

**Global implementation constraints:** (1) any `.claude/commands/drive*.md` edit reds
string-pin contract tests in BOTH suites — run `python3 -m pytest` AND
`test/drive-conformance.test.sh` (canonical: `bin/run-tests.sh`) during implement, and use
the token-sweep + green-full-suite migration pattern (OPERATING.md), never per-line pin
enumeration. (2) R5–R9 are all spec edits over the same three review specs — land them as
ONE batch (single pin-suite migration), not five. (3) Implementation order by
(hours-saved / risk): R2 → R1+R3 → R4 → R5–R9 batch.

### Tier A — human-latency pool (the biggest lever, ~3–8h/run)
- [ ] **R2 (P1/small/spec-only)** Codex-first dual-voice overlap: in drive-review.md
  (Step 1 ~L87 / Step 2 ~L172), drive-harden.md (~L105–166), drive-finalize.md
  (~L152–230), launch the background `codex exec` FIRST, spawn the Claude reviewer while
  codex runs, wait for BOTH before the Combine step. Log/marker/stranded-log mechanics
  byte-identical. While in there: add `--sandbox read-only` to the review/harden/finalize
  codex calls, and pin that coordinator prompt enrichment may reference PRIOR rounds only
  (no same-round Claude→codex flow — none exists in any of 17 raw logs). Verified SAFE:
  gates check artifact existence/verdict/SHA, never voice ordering; the overlapped
  behavior already ran ad hoc in production (regress-selfid slice-1.1 rounds 4–8), and an
  overlapped round is where codex caught its best Claude-missed BLOCKING (is_marked EOF
  fallback). Saves 0.5–1.5h/run of pure serialization. Do this first — one afternoon.
- [ ] **R1 (P1/medium/code)** Auto-resume at rebirth seams — **this is C3 (Tier 4 below),
  promoted to top priority by the audit; implement as ONE item, keep C3's scoping.**
  Audit additions to C3's spec: key strictly on `waiting=='rebirth'` + a valid
  `checkpoint-complete.marker`; the resume **atomically claims the marker (mv-rename)
  before proceeding** so a simultaneous human paste and auto-resume cannot double-drive
  (the loser reads run status and exits) — the same fix class decisions.md D-4269
  required; one resume attempt per marker, exponential backoff, notify on repeated
  failure. gateA/gateB/stop:/ask: stay strictly human. The fenced ↻ REBIRTH block stays
  byte-for-byte as the plain-CLI fallback; edit drive.md I1 step 6 only. Quality-safe
  because the resume path is initiator-agnostic and fail-closed by design
  (`bin/drive-conformance.sh --mode checkpoint` / `--mode state-lint` re-prove before
  continuing; a forged `waiting` without the prove→marker→wait sequence STOPs; gate hooks
  are global in `~/.claude/settings.json` so a spawned session inherits the full
  enforcement chain); fresh-context-per-leg + decant-at-clear are untouched. Residual
  from closed C2 to fold in: a verified `claude-fable-5` entry in
  bin/rebirth-thresholds.json (+ statusline.sh inline fallback) — hygiene, not
  load-bearing. REFUTED sibling (do not build): pressure-conditional Seam A/B — the
  43.2h pool is paste latency, not seam ceremony (attended Seam B = 7 min), and it would
  make the never-once-fired class-A rebirth the sole overflow guard. Captures ~all of the
  43.2h pool (2–6h/run).
- [ ] **R3 (P1/small/code+spec)** Push-notify decision-bearing parks + observability
  logging. Notification side-effect on every transition to `waiting` ∈ {gateA, gateB,
  stop:, ask:}, with four HARD constraints: (1) fail-open by construction — always exit
  0, never a block decision, network send backgrounded with timeout (must never wedge
  drive-stop-hook.py's allow-stop-when-waiting contract); (2) gateB content
  differentiated — carries the gate QUESTION + "reply 'approve' after reviewing the
  diff", NEVER a bare `/drive <runId>` paste line (memory drive-gate-repaste-not-approval:
  a repaste is the continuation token, not approval of a push); (3) never writes
  state.json — dedup via `notified-<waiting>-<tipSha>.marker` in $RUN_DIR (a torn
  state.json write trips the waiting-malformed lint, drive-conformance.sh ~L1129–1135);
  (4) coordinator-side sub-event logging (subagent-started, codex-started,
  suite-run-started/finished, fix-applied, idle_detected at >30min), `date -u`
  forward-only, never rewrite historical log lines. Key /harvest on `state.waiting`.
  Scope pings to decision-bearing waits (exclude rebirth once R1 lands). Quality-safe:
  purely additive — no layer/round/gate is cut; all event-log consumers are tolerant by
  contract (retention skips unparseable lines; retro pins "NO stat requires a specific
  event kind"; conformance validates waiting grammar, never event kinds). Saves 1–4h/run
  + kills the multi-week parked tail; the logging half converts the 61.9h
  unattributable-stall bucket into measurable classes for the next audit.

### Tier B — codex tail-bounding (~15 min vs 8–10h worst case)
- [ ] **R4 (P1/small/code+spec)** Codex progress-watchdog + outage degrade. Kill a codex
  call ONLY when `codex-raw-<scope>.log` has appended **no bytes for 15 minutes**
  (mtime/size polled in the existing wait loop), absolute backstop 3h; retry once; then
  write a DISTINCT first-line marker `CODEX_KILLED_TIMEOUT` (never masquerading as
  `CODEX_UNAVAILABLE`, which the combined-verdict rule reads as "contributes zero") and
  continue on the already-spec'd degraded single-voice path. Health-probe before
  dispatch; a probed outage → degraded single-voice for non-gate-enforced scopes. Effort
  tiering ONLY for call classes history shows are pure confirmations (harden-regress
  re-confirmations; finalize/phase re-audits whose immediately-prior round had zero codex
  findings) — NEVER blanket round-2+ (round-2+ codex repeatedly returned NEW P1s,
  including a round-7 fresh-regression catch), and gate/hook/parser/conformance files are
  security-sensitive at EVERY round. REFUTED variant (do not build): any wall-clock
  kill — the corpus's single best catch was a 109-minute round-1 call that reproduced a
  BLOCKING fail-open in the WorktreeCreate gate the Claude voice CONVERGED past; genuine
  long calls stream continuously, only the pathologies (.neterr, .r5-failed, .r1-died,
  the 8.7h outage pair) go silent — the progress signature separates them where a wall
  clock cannot. Degradation is already gate-accepted (15/178 CODEX_UNAVAILABLE summaries;
  trash-dash-convert shipped fully degraded). x-ref C12 (extend, not duplicate: C12's
  degraded-second-voice tier + distinct-marker requirement is the same mechanism).

### Tier C — round-churn set (~1.5–3h/run; land as ONE spec-edit batch)
- [ ] **R5 (P2/small/spec-only)** Class-sweep as a fix-round contract (fix-side only).
  drive-implement.md / drive-finalize.md fix-dispatch prompts: when a P1 is a
  parser/validator/regex/classifier/reader/wording defect, grep-enumerate every sibling
  site of the same input shape, fix ALL in one round, state the class boundary in the
  commit message, mutation-verify per site. Codex round-1 prompt gains: "enumerate all
  members of any class you flag, with file:line". Include the de-slop wording-class sweep
  (c7 RL-1: GitHub→GitLab wording recurred across all 4 finalize rounds). The round-N+1
  reviewer prompt ADDS "verify the stated class boundary is closed" as a checklist item
  but RETAINS the unchanged open-ended adversarial hunt. Class members outside the
  slice's owned files: record and route via the existing BLOCKED/ownership-widening path,
  never edit. Evidence: regress-selfid slice 1.1 burned rounds 2–6 on ONE parser class,
  one instance per round (the r4 review note literally says "sibling of r3; fix whole
  class"); promotes memory drive-finalize-adversarial-class-fix to spec. REFUTED variant
  (do not build): narrowing the reviewer to closure-verification — the reviewer certified
  "class closed" twice in the flagship run and was wrong both times; codex's open-ended
  hunt then found real BLOCKINGs in the conformance gate. Saves ~1–1.5h per parser-shaped
  run.
- [ ] **R6 (P2/small-medium/spec-only)** Delta-scoped round-N≥2 re-reviews (class-scoped,
  with suite-rerun ban). drive-review.md gains a round-N≥2 diff-scope form: "the fix
  delta PLUS the prior finding's full class and consumer surface", with "do not re-verify
  acceptance criteria the delta doesn't touch; you MAY flag any P1 anywhere in scope" —
  explicitly NO settled-scope prohibition (REFUTED: three genuine repro-confirmed P1s
  lived in settled scope untouched by the preceding fix — regress r4/r5/r6; discovery was
  empirically serial, the rounds would relocate not vanish). Security-sensitive scopes
  (bin/drive-*.sh, gate hooks, matchers, parsers) keep FULL-scope codex every round —
  every historical settled-scope BLOCKING lived there. Unconditional cheap win: the
  round-N≥2 codex prompt says "do NOT re-run the full test suites — spot-run only tests
  pinning your prior finding" (suite re-runs were most of each call's 6–10 min and
  duplicate the implementer's runs). Terminal full-scope confirming round kept; delta
  rounds do NOT increment cap-8 (mirroring the harden-regress exception). Evidence: the
  improvised round-8 delta prompt in regress-selfid ran 63k codex tokens vs 116–211k
  full-scope, ~3 min vs 6–10, and still caught a genuine in-delta MAJOR. Saves
  0.5–1.5h/run + 6–10h aggregate codex time.
- [ ] **R7 (P2/small-medium/spec+$RUN_DIR files)** Durable refutation ledger +
  severity-tag triage (replay-based). `$RUN_DIR/codex-refuted-<scope>.md` + a repo-level
  cross-run file, with five HARD bounds: (1) every entry records the verbatim
  reproduction command + full env; on any re-flag the coordinator RE-EXECUTES the
  recorded repro in the faithful env (minutes, vs the 3h28m worst re-adjudication) — a
  differing result voids the refutation, and an executed red in the faithful env ALWAYS
  defeats the ledger; (2) the refutation preamble is NEVER injected into harden/finalize
  auditor prompts (the c7 TMPDIR catch depended on that voice's independence from the
  do-not-re-raise steer); (3) repo-level entries are finding-specific with recorded
  evidence and run-scope qualifiers — never class-level "X-like findings are settled"
  (regress-selfid's "forgery-class" contained both an overruled trick AND the genuine
  body-only-sha hole); (4) the P1→P2 downgrade path requires the coordinator's OWN
  reproduction of the fail-safe direction (retention DP9/DP8: believed-fail-safe designs
  failed open), and the threat-model arm applies only to verbatim
  docs/drive-enforcement.md exclusions; (5) a repro timeout leaves the finding
  UN-refuted — it never mints a ledger entry (the shortcut repro — unset TMPDIR — is
  exactly what poisoned c7's AC-9 overrule; see memory
  unset-tmpdir-masks-trailing-slash-test-bug). Codify count-tags-not-prose
  (codex-severity-tag-outranks-prose-verdict) in drive-review.md Step 3. Evidence: ≥7
  explicit overrule events in history; the pre-ship-absent-ledger class re-flagged EVERY
  run (memory codex-reflags-preship-absent-ledger); c7's retro RL-2 independently
  proposed this mechanism. Saves 0.5–2h per churn-heavy run.
- [ ] **R8 (P2/small/spec-only)** Design author-verification gate. drive-plan.md +
  drive-design.md pre-round-1 checklist: (1) every citation/snippet/empirical claim ships
  with an ARTIFACT-shaped verification transcript (`verify-design-claims-<P>.md`,
  commands + outputs) whose existence the coordinator checks — never a prose "verified"
  attestation (memory dont-make-the-model-the-meter; main pd2 r1's falsified completedAt
  claim was written by an author who believed it verified; regress pd1 burned a codex
  BLOCKING on a pinned awk snippet non-functional as written); (2) classifier/matcher
  rules require a runnable calibration script + corpus + stated imprecision budget as
  design INPUT, which reviewers run for precision IN ADDITION TO — never instead of — an
  independent recall probe (main pd2 r6: the author's script inherits the rule's blind
  spots; the missed bold-before-bracket carrier dropping 36 real findings was found only
  by independent shape enumeration; x-ref memory
  calibration-treadmill-restructure-not-patch); (3) new-machinery P1s may exit to a
  revision leg that whole-chain-traces before re-entering, but the leg consumes a
  phaseDesign.round tick (preserves the D12 cap-8 runaway detector), mints no new
  artifact family (avoids the epoch-unmarked conformance trap), and re-entry is a full
  fresh dual-voice round. Evidence: scopes with unverified round-1 empirical claims
  averaged 5+ review rounds vs ~1.6 for verified ones. Budget the saving at ~1 round per
  design-heavy run — regress design rounds 2–7 were codex's sequential discoveries, not
  author sloppiness.
- [ ] **R9 (P2/small/spec-only)** Pin-depth design standard with mutation-survival
  semantics. drive-design.md: a required pin-depth-per-AC section fixes test-pin depth
  (mutation-verified vs smoke) at design time, with token-sweep + green-full-suite as the
  default spec-pin-migration pattern (the already-promoted OPERATING.md rule applied
  proactively). drive-review.md: "a pin exists" is defined by MUTATION SURVIVAL, not
  textual presence — a pin counts only if it reds on deletion/partial-revert of the exact
  clause it guards; a vacuous pin = NO pin = stays P1 (REFUTED variant: textual
  pin-exists→P2 — a vacuous pin once green-lit a reverted fail-closed gate,
  main-20260705 parseable-gate; see memory spec-pin-mutation-verify). "Could be stronger"
  (reds on core mutation but lacks permutation/exclusivity/composed-order coverage) = P2,
  logged for harden/finalize. Demoting a codex BLOCKING/MAJOR on pin depth requires
  SHOWING the core-mutation red (preserves codex-tag-outranks-prose). Fail-closed gate
  surfaces (drive-conformance contracts, gate hooks, drive-retention safety clauses) are
  carved out: exclusivity/composed-order gaps there stay P1. Evidence: the pin-depth
  churn instances (lever2 1.3 r2/r4/r5, main 2.1 r2, retention finalize r3) all fall on
  the P2 side and none caught a product bug — the real bugs in those runs were caught by
  integration review, harden, and finalize, all preserved. Gates parse no severity
  tokens → no hook conflict. Saves 0.5–1.5h/run.

**What must NOT be touched (audit § 3, evidence-backed sole-catchers):** full-scope
adversarial codex on gates/matchers/parsers every round; the phase-integration fresh
review even on single-slice fast-forward (caught a BLOCKING after 7 clean slice rounds);
the forced next-invocation fresh dual-voice re-audit after any logic-bearing fix round
(retention harden-2-3: fix-introduced P1 found AFTER regress-CONVERGED at the same tip);
finalize's whole-run fresh sweep (out-of-delta TOCTOU catch); Seams A/B themselves
(R1 automates the paste, not the seam); Gate A/B human-only semantics +
repaste-is-not-approval; the SHA-bound omission-proof artifact chain and cap-8 counters;
the overrule-with-evidence discipline.

**Expected net effect** (audit § Net effect): R1+R3 remove 3–8h of pure human latency;
R2+R4 remove 0.5–1.5h serialization and bound the multi-hour codex tail to minutes;
R5–R9 remove 1.5–3h of round churn without touching any sole-catcher layer. A run that
today spans a full day compresses to an attended morning: ~4–6h machine-active, human
touches only at Gate A, Gate B, and genuine STOPs.

## Trellis pattern adoption — from docs/trellis-analysis.md (2026-07-04)

- [ ] **TR-2 (S/L2)** Per-turn `<drive-state>` breadcrumb: a UserPromptSubmit hook reading
  `$RUN_DIR/state.json`'s real fields (runId, stage, phase, waiting) and deriving the expected
  next step from stage/phase (as the run-graph does), breadcrumb bodies pinned by a contract
  test — kills T-1 (coordinator drift corrected pre-violation,
  between gate denies; survives auto-summarization context loss); lands on `bin/` new hook +
  `bin/install-drive-hooks.sh` + `tests/contracts`; x-ref C11 (extend, not duplicate: C11
  trims /goal ceremony, TR-2 adds hook-supplied steering; land compatibly with C11's pinned
  clauses); rec detail: docs/trellis-analysis.md §Recommendations. **Trigger:** next /drive
  run that trips a coordinator-drift STOP, a merge-gate deny on a forgotten review, or a
  Stop-hook nag loop.

## Fable 5 / Claude 5 harness compatibility audit (2026-07-03)

12 verified findings (none refuted on a two-lens adversarial verify). Baseline: the
current harness auto-summarizes context (sessions no longer hard-die), subagents run in
the background by default and are reliable, fresh-session triggers exist (create_trigger
with create_new_session_on_fire), Workflow orchestration exists on some surfaces (verify
on the live harness), and the Claude 5 family is 1M-context.

**Framing:** autodrive is THREE layers. Each item below is tagged L1 or L3; layer 2 is
untouched by the audit, by design.
1. *Dispatch mechanics* (spawn/babysit/collect/retry loops, STATUS text contracts,
   flakiness workarounds, class-A context-pressure rebirth — class-B seams and the
   checkpoint proofs are layers 2–3 and stay) — natively owned by the harness; shed.
2. *Direction control* — premises → plan (Gate A) → per-phase design against the REAL
   prior-phase code → slice assumption check with REDESIGN escalation, plus fresh-context
   role separation (designer ≠ implementer ≠ reviewer; reviewer never sees implementer
   rationale). Keep — appreciates with model capability: cheap direction checks before
   expensive commitment; fresh-context checks beat self-critique.
3. *Verification + enforcement* — git-truth omission-proof gates, independent second
   voice, fail-closed ship gating, durable $RUN_DIR state, human gates A/B. Keep —
   layer 3 verifies the thing was built right; layer 2 verifies it's the right thing.
Refactor direction: shed layer 1 (C1 C2 C3 C5 C8 C9 C11 C12); keep and re-target
layer 3 (C4 C6 C7 C10) — the coordinator states contracts and checks direction at the
seams; the model/harness owns how work gets dispatched.

### Tier 1 — wrong today, small fixes
- [x] **C6 (P1/small/L3)** drive-ship.md:133 hardcodes `Co-Authored-By: Claude Opus 4.8` into
  every shipped commit — sole occurrence, nothing pins it; make harness-agnostic.
- [x] **C4 (P2/small/L3)** Prose sweep: "Claude Code cannot self-initiate a fresh session"
  (CLAUDE.md, docs/flow.md, docs/drive-enforcement.md; decisions.md D3) is stale — reword
  as capability-conditional; annotate D3 premise-stale (don't rewrite); also fix the
  8-consecutive-block-cap comments in bin/drive-stop-guard.sh + bin/drive-stop-hook.py.
- [x] **C2 (P2/medium/L1)** bin/rebirth-thresholds.json maps bare "Sonnet" → 200k, but
  Sonnet 5 / Sonnet 4.6 are 1M models (rebirth steer would fire at ~17% real usage);
  claude-fable-5 gets defaultWindow=1M only by fallthrough (happens to be correct: 1M).
  Version-qualify the legacy 200k substrings, add verified Claude-5-family entries, keep
  statusline.sh inline fallback in sync (AC6), update the
  five pinned test files in ONE review unit. Sequence after C1.

### Tier 2 — correctness under the new harness
- [ ] **C9 (P2/small/L1)** drive.md:437 in-session stranded-inflight-marker rule
  ("not actively awaiting" → adopt/re-dispatch) double-dispatches over LIVE background
  workers (background-default dispatch + auto-summarization can erase coordinator memory).
  In-session stranded must require positive worker-death evidence from the harness surface
  (completion notification / Monitor); at-resume rule unchanged; keep the
  test_checkpoint_contract.py pinned phrases.
- [x] **C7 (P1/medium/L3)** Enforcement gates are PreToolUse(Bash)-only
  (install-drive-hooks.sh:140): GitHub MCP write tools (create_pull_request, push_files,
  merge_pull_request, …) ship with the merge gate never firing, and Agent
  isolation:"worktree" / EnterWorktree create worktrees off the gated slice/<runId>/<id>
  refs — both omission-class bypasses of the gate chain's core guarantee. Add a sibling
  hook (distinct basename — the installer strips/re-appends drive-merge-gate.sh entries)
  that deny-routes MCP writes + native-worktree tools back to the canonical Bash paths
  while a drive run is active; extend install-drive-hooks.sh to manage it.
  *(closed: GitHub-MCP write class gated by bin/drive-tool-gate.sh; worktree claim resolved
  KEPT — recorded trace shows the harness-branch chain voids the plan/design + slice
  review/impl-presence gates.)*

### Tier 3 — shed the dead-premise machinery (do C1 + C11 together)
- [ ] **C1 (P1/large/L1)** Class-A context-pressure rebirth assumes sessions hard-die at
  context exhaustion — false under auto-summarization, which also breaks the token math
  (compaction drops the token sum below the high-water mark and stales the one-way
  rebirth_pending latch). Arm class A by the existing window match table (legacy 200k
  models keep it; unmatched/1M models disarm), add explicit override, then run the
  deferred leaner-rebirth-v2 cut. KEEP: class-B deterministic seams (lossless $RUN_DIR
  handoff > lossy auto-summary), /decant at boundaries, checkpoint/state-lint proofs,
  inflight-marker crash-safety, the /goal rebirth-pause clause (class B still uses it).
- [ ] **C11 (P3/small/L1)** Demote the per-leg /goal ceremony (leg-condition table, re-arm
  choreography) to optional reinforcement — the harness now bakes in the autonomous
  continuation contract, and drive.md documents the Stop-hook contract as working without
  /goal. Must land with C1 (same AC7/AC12-pinned clauses in test_rebirth_handshake.py).
- [ ] **C5 (P2/small/L1)** "Subagents bail ~50%" (OPERATING.md:44) is stale; relax
  codex-never-in-a-subagent to an either/or dispatch note AROUND the canonical fenced
  codex blocks (AC13 pins the mkdir/TMPDIR/redirect block text — do not rewrite it), and
  relax the 150-word digest cap.

### Tier 4 — new-capability adoption (opt-in, staged)
- [ ] **C3 (P1/medium/L1)** *(promoted: implement as R1 in the efficiency plan above —
  same item, R1 adds the atomic marker-claim race guard and backoff/notify semantics;
  keep this entry's scoping constraints.)* Self-scheduled seam resume: at non-gate context-clear seams,
  feature-detect fresh-session triggers (create_trigger with create_new_session_on_fire —
  send_later is same-session, not a seam) and schedule `/drive <runId>` instead of
  requiring the human paste; the fail-closed resume path (single-use checkpoint marker +
  re-prove) is already initiator-agnostic. Keep the fenced ↻ REBIRTH block as the
  plain-CLI fallback, byte-for-byte; edit inside drive.md I1 step 6 only. Gates A/B
  stay human.
- [ ] **C12 (P3/medium/L1)** Per-role model/effort hints (log-summarizer subagents =
  small/fast+low effort; adversarial reviewers = high effort) as capability-class prose,
  never hardcoded IDs; degraded second-voice tier when codex is unavailable (independent
  Claude reviewer, distinct first-line marker — NOT under CODEX_UNAVAILABLE, which the
  combined-verdict rule reads as "contributes zero").
- [ ] **C8 (P2/large/L1)** Opt-in `/drive --workflow` backend for the Stage-2/3 slice layer:
  Workflow parallel() over implementers with schema-validated returns replaces the manual
  concurrencyCap loop + fragile `STATUS:` first-line contract. HARD preconditions: verify the
  orchestration primitive (Workflow parallel() + schema returns) on the live harness;
  land C7 first; git topology (worktree add, merges, literal slice/<runId>/<id> refs) stays
  main-session Bash so the gates fire; one inflight marker per Workflow invocation;
  dual-voice loop crossing the Workflow boundary decided explicitly. Default OFF.
- [ ] **C10 (P3/large/L3)** Component D (forgery-proof out-of-band reviewer) re-costed on
  native primitives: opt-in ship-mode predicate requiring an independent-session review
  whose provenance comes from harness-owned evidence (Workflow journal / trigger firing
  records), NOT a $RUN_DIR file the coordinator can write. Append a new dated
  followups.md entry (keep :27 intact); with the marker absent, ship mode stays
  byte-identical (141 ship pins across 4 bash suites stay green).

Full audit with per-candidate evidence and both lens verdicts: session artifact
`fable5-compat-audit.md` (2026-07-03).

## /drive run drive-retention-hygiene-20260622T073209 — architectural follow-ups (2026-06-23T18:50:09Z)
- bin/drive-retention.sh + .claude/commands/drive.md + .claude/commands/drive-ship.md +
  tests/contracts/test_drive_retention*.py — the retention/teardown contract (done-signal,
  completedAt-after-proven-removal gate, Tier-W/Tier-L eligibility) is expressed in THREE
  authority layers: the executable policy (bin/drive-retention.sh), the lifecycle prose
  (drive.md §E + drive-ship.md "After approval"), and large string-pin contract tests. They can
  drift independently (the round-1 finalize audit's own done-signal confusion is an instance of
  reading one layer without the others). Out of THIS run's blast radius to unify; consider a
  single machine-checked source of truth (e.g. generate the doc-pinned tokens from the script, or
  a single contract fixture both the script and docs are checked against) in a dedicated follow-up.

## /drive run todo-triage-20260704T135831 — architectural follow-ups (2026-07-05T14:14:46Z)

- **bin/install-drive-hooks.sh `is_managed` — spaced-path cross-checkout duplicate.** A
  cross-checkout re-run from a space-containing checkout path leaves stale managed entries
  un-stripped → duplicate hooks with no drift WARN. Pre-existing (on origin/main before this
  run's C7 work), affects the merge-gate + stop-guard identically. Loosening the
  metachar/`$cmd == $full` collapse matcher is a security-sensitive change needing its own
  adversarial find-the-bypass review. Already recorded in followups + decisions D-coord-4;
  listed here to discharge finalize's TODO-routing duty. Out of this run's diff — not fixed.
- **bin/drive-tool-gate.sh — ungated Bash `gh pr merge`/`gh pr edit` twins + GitLab-MCP writes.**
  The MCP `merge_pull_request`/`update_pull_request` denies close the MCP omission path, but
  their Bash `gh pr merge`/`gh pr edit` twins stay ungated (drive-merge-gate.sh gates only
  `pr create`/`mr create`), and GitLab-MCP write tools are the same bypass class under different
  names, uncovered by the GitHub-named matcher. Deliberate, decision-logged asymmetry (the deny
  wording states it truthfully); named residuals in followups. Decide in a follow-up, not a code
  fix here.
- **bin/statusline.sh + bin/rebirth-thresholds.json — duplicated window table.** The deployed
  statusline is symlinked away from its `rebirth-thresholds.json` sibling, so the window
  "single source of truth" is actually a duplicated inline `case` table (statusline.sh:34-38)
  requiring dual maintenance with the json. AC6 pins them to identical numbers as an accepted
  stopgap; the durable fix (a single source resolved at deploy time) is deferred (codex ARCH).
# Finalize TODO routing (promoted to repo-root TODO.md at ship)

- **Wire `/drive-retro` into the run-wrap sequence, ordered BEFORE the wrap-decant**
  (user-directed, 2026-07-05). At the TRUE run-wrap only (after Gate B, once
  `completedAt` / `stage=done` exist — retro's completeness gate requires a finished
  run): `/drive` Completion runs `/drive-retro <runId>` first, then the standing
  wrap-`/decant`, so retro's classified proposals in `retro-<runId>.md` are on disk as
  INPUT EVIDENCE for decant's survey/promotion pass. Per-seam rebirth decants (I1
  step 5.5) are unaffected — retro cannot run mid-run. Touches drive.md's Completion
  step (string-pin contract tests apply). Supersedes the bare "automatic run-wrap
  wiring" line in followups.md by adding the ordering contract.

## /drive run main-20260704-180725 — architectural follow-ups (2026-07-05T04:10:44Z)

- **`.claude/commands/drive-retro.md` + `tests/contracts/test_drive_retro_contract.py`** — the
  feature's hard part is an algorithmic spec (tolerant stream-JSON decode, Rule-U line-level
  extraction, recurrence grouping, proposal routing), but v1 deliberately ships PROSE + STRING
  PINS only (TR-3's stated "no shipped code" boundary; DP2-23/AC17). Residual risk (codex ARCH,
  finalize r1): the most failure-prone semantics can drift while all string-pin tests stay green —
  there is no fixture-driven behavioral oracle over sample $RUN_DIR artifacts. Follow-on if
  /drive-retro grows an executable extractor (the DP2-5 `bin/drive-retro-stats.py` path): add a
  golden-fixture oracle over a captured $RUN_DIR so the extraction contract is behaviorally, not
  just lexically, pinned. Out of this run's scope (would breach the no-shipped-code boundary).

## 2026-07-05 — drive-ctx-summary run (finalize follow-ups)


Architectural / out-of-scope findings routed at the finalize stage (NOT fixed in-run;
promoted to repo-root TODO.md at ship).

- [P3][docs/test-accuracy] `tests/contracts/test_rebirth_handshake.py` module docstring
  (line ~18) claims "Each load-bearing pin is proven to RED against a mutated COPY … in the
  accompanying `test_*_flips_on_*` cases." No function in THIS file follows that naming
  convention — the pins are inline section-bounded string-pins, and the `*_flips_on_*`
  mutation-proof convention actually lives in sibling `test_checkpoint_contract.py`. This
  inaccuracy is PRE-EXISTING (byte-identical in base 9beeac4), not introduced by this run —
  hence routed, not fixed here. Fix: either add per-pin mutation-proof `test_*_flips_on_*`
  cases for the load-bearing pins, or reword the docstring to describe the actual
  inline-string-pin methodology. Out of the whole-run diff's introduced surface.

## /drive run c7-gate-bypass-20260705-225936 — architectural follow-ups (2026-07-06T08:19:47Z)
- bin/drive-tool-gate.sh (MCP repo-scoping, ~line 344-356): the GitHub/GitLab MCP write
  scoping matches owner/repo only and is FORGE-HOST-BLIND, because the MCP tool_input exposes
  no forge host. Consequence: an owner/repo collision across forges (e.g. github.com/acme/x
  active-run vs a gitlab.com/acme/x MR) over-denies (safe direction, recoverable route-to-Bash),
  and real project_id-only GitLab payloads fail-closed-deny. Distinguishing gitlab.com from
  gitlab.internal from foo/bar is impossible from current hook input alone. Out of scope for
  this run (needs a richer hook input contract / managed tool policy). Related: the existing
  "G2 vendor-schema drift" followup.
- bin/drive-hook-lib.sh / drive-tool-gate.sh / drive-worktree-gate.sh (shared active-run
  predicate): the fail-closed PRECONDITIONS around drive_scan_active_runs (scan-tool present,
  runs-root readable) are NOT centralized — drive-worktree-gate.sh hardens them locally,
  drive-tool-gate.sh (shipped) does not. Centralizing the fail-closed guard into the shared
  predicate (or a shared wrapper) would close the residual shipped-tool-gate fail-open uniformly.
  Forgery-class; out of scope for this omission-focused run. Pairs with the deferred
  "harden shipped drive-tool-gate.sh fail-closed" followup.

## /drive run regress-selfid-20260706-143429 — architectural follow-ups (2026-07-07T16:16:50Z)
- **.claude/commands/drive.md, .claude/commands/drive-review.md (coordinator resume/heal semantics)**: the new inflight-heal / `base=<sha>` / `baseSha` recovery path — and coordinator resume semantics generally — live as markdown protocol pinned by substring/contract tests, with NO executable state-machine consumer (grep confirms these tokens are absent from bin/drive-conformance.sh). Consequence: the highest-risk cross-phase behavior (a real resumed run writing baseSha once, stripping `base=` before scope derivation, and heal/adopt/re-dispatch) is verifiable only by a full harness E2E, not a unit test. Out of scope for this run (an E2E driver is a new subsystem, boil-the-ocean). Consider extracting the resume consumer into executable code testable end-to-end. (Raised by both finalize voices; codex flagged P1-as-missing-test + ARCH.)

## /drive run r2r4-codex-20260708-144534 — architectural follow-ups (2026-07-09T21:06:11Z)

- `.claude/commands/{drive-review,drive-harden,drive-finalize,drive,drive-ship}.md`: the codex
  token/marker state machine (OK / CODEX_KILLED_TIMEOUT / CODEX_UNAVAILABLE / HELPER_ERROR →
  render/degrade/STOP) is specified in Markdown prose across the spec runners, NOT in executable
  coordinator code. Consequence (codex finalize ARCH): contract tests can pin the *wording* of each
  branch but cannot run a full review/harden/finalize leg end-to-end, so branch-coverage of the
  combine state-machine is structurally spec-integration-only. This is a deliberate harness
  architecture (operational /drive stages are prose runners the coordinator executes, per CLAUDE.md),
  not a defect introduced by this run — recorded as a durable follow-up: if the combine state-machine
  grows further, consider extracting it into a small `bin/` helper (like `drive-codex.sh` itself)
  that is directly unit-testable. Out of scope for R2/R4 (whole-harness refactor).
