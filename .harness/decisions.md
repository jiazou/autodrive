# Decision log

- Append-only. Do not edit or remove prior entries; supersede them with a
  new entry that references the prior one. Exception: aged entries are
  ARCHIVED — moved verbatim, never rewritten — to
  `.harness/archive/decisions-pre-<boundary>.md` when this file outgrows
  a default 2,000-line read. Archived pre-2026-07: 118 dated entries
  (2026-06-02 D1 … 2026-06-12) in `.harness/archive/decisions-pre-2026-07.md`;
  this file resumes at the first 2026-07 promoted block.
- One entry per decision. If a single design choice has several sub-decisions,
  one entry covers them -- don't fragment.
- If a new decision contradicts an earlier one, that IS an escalation. Surface
  the contradiction to the human before proceeding.

## Entry format

### YYYY-MM-DD HH:MM -- Short title
**Stage:** plan | implement | review | codex | ship
**Task:** brief reference to which task this decision belongs to
**Question:** what was being decided
**Options considered:** the alternatives, one line each
**Chosen:** which option
**Reasoning:** one or two sentences on why
**Reversibility:** easy (refactor) | medium (migration) | hard (public API, data)
**Supersedes:** (optional) link to prior entry this overrides

## Entries
(append below this line)
<!-- ===== promoted from /drive run c7-gate-bypass-20260705-225936 (2026-07-06T09:45:21Z) ===== -->
### 2026-07-05 -- C7-D1: Sibling tool-gate hook routes non-Bash bypasses to the gated Bash surface
**Stage:** plan
**Task:** Fix C7 (gate bypass) — sibling PreToolUse hook
**Question:** How to gate GitHub MCP write tools + native worktree tools that skip the PreToolUse(Bash) merge gate?
**Options considered:** (a) re-implement conformance in a new hook that checks MCP/worktree calls directly; (b) sibling PreToolUse hook that deny-routes those calls back to the canonical gated Bash paths; (c) widen the merge gate to non-Bash tools
**Chosen:** (b)
**Reasoning:** A router keeps a single source of truth for conformance (the merge gate), honors the omission-proof/not-forgery-proof threat model, and needs no per-tool conformance modes; the merge gate does the real check when the coordinator retries on the Bash surface.
**Reversibility:** easy
**Classification:** Substantive

### 2026-07-05 -- C7-D2: Active-run detection via cwd HEAD only; surgical Agent discrimination
**Stage:** plan
**Task:** Fix C7 (gate bypass) — sibling PreToolUse hook
**Question:** How does the sibling detect an active /drive run and avoid wedging /drive's own Agent fan-out?
**Options considered:** (a) detect run from ref tokens in tool input (none exist for MCP/worktree tools); (b) detect from cwd HEAD via drive-hook-lib and deny only Agent calls with isolation:"worktree" + EnterWorktree + an MCP write allowlist
**Chosen:** (b)
**Reasoning:** MCP/worktree inputs carry no ref, so cwd HEAD (mirroring the merge gate's HEAD path) is the only signal; ordinary Agent dispatches must pass or every run wedges, so the Agent match is narrowed to worktree-isolation only.
**Reversibility:** easy
**Classification:** Substantive

### 2026-07-05 -- C7-D3: One self-discriminating hook, basename-canonicalized by the installer
**Stage:** plan
**Task:** Fix C7 (gate bypass) — sibling PreToolUse hook
**Question:** One script per tool, or one script matched by a tool-name pattern?
**Options considered:** (a) separate hook scripts/entries per tool; (b) single bin/drive-tool-gate.sh managed as a third basename-keyed entry alongside drive-merge-gate.sh + drive-stop-guard.sh
**Chosen:** (b)
**Reasoning:** One canonicalized installer entry and one place for all deny-routing guidance (DRY, explicit-over-clever); reuses the installer's existing strip_managed/is_managed basename machinery unchanged.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-07-05 -- C7-D4 (design r2): detection keys off SESSION IDENTITY, worktrees gated defense-in-depth, MCP deny-by-default, fail-closed
**Stage:** plan (design review r1 -> r2 revision)
**Task:** Fix C7 (gate bypass) — sibling PreToolUse/WorktreeCreate hooks
**Trigger:** design-review r1 FINDINGS — Claude (2 P1) + codex (5 P1), both refuting the r1 cwd-HEAD detection + Agent/EnterWorktree-only worktree interception + write-allowlist. Verified against official Claude Code hook API (verified-hook-api.md).
**Revisions (supersede C7-D2's cwd-HEAD + Agent-only + write-allowlist):**
  - D-b: active-run detection via sessionId == payload.session_id && stage!=done (mirror drive-stop-hook.py), + drive-worktree cwd secondary. r1's cwd-HEAD was inert for main-context dispatches (coordinator HEAD=baseRef, feature branch checked out nowhere).
  - D-d: worktree gating defense-in-depth — WorktreeCreate event (--worktree CLI, exit-2 deny) + PreToolUse EnterWorktree + PreToolUse Agent/Task explicit isolation:"worktree". Frontmatter-isolation path = named residual (drive ships no such agents).
  - D-e: MCP writes = deny-by-default over git-hosting mcp__ namespace + READ allowlist (get_/list_/search_), matching any server prefix. Inverts r1's write-allowlist which missed delete_file/update_pull_request_branch (fail-open).
  - D-f: FAIL CLOSED for matched target tools on inspection error (no Bash retry backstop, unlike merge gate). Inert only when NO active run detected.
  - D-g: shared session-id + drive-worktree-cwd resolver in drive-hook-lib.sh (DRY, reused by both hooks).
**Reversibility:** easy (pre-implementation design)
**Classification:** Substantive (load-bearing security-gate decisions)

### 2026-07-05 -- C7-D5 (design r3): RUN-PRESENCE anchor, WorktreeCreate proof obligation, all-mcp deny, predicate pin
**Stage:** plan (design review r2 -> r3 revision)
**Task:** Fix C7 (gate bypass) — sibling PreToolUse/WorktreeCreate hooks
**Trigger:** design-review r2 FINDINGS — both voices refuted session_id as a SOLE anchor (null sessionId inert; child/background/fresh-session dispatch carries a different id; both -> inert exactly where it must bite) and escalated frontmatter-isolation from residual to a real bypass.
**Revisions (supersede C7-D4's session_id-primary):**
  - D-b: anchor on RUN-PRESENCE — any ~/.claude/harness-runs/*/state.json with stage!="done" -> deny target tools in ANY session (session-independent, fail-closed). Cheap because target tools (git-hosting MCP writes + native worktree creation) are EXACTLY what /drive never uses (it does all git via gated Bash). sessionId/cwd only enrich the deny message / narrow-fail-closed.
  - D-b2: predicate = stage!="done" ONLY; do NOT inherit stop-hook waiting/autoContinue skips (a Gate-B-waiting run must stay gate-active or MCP create_pull_request defeats Gate B).
  - D-d: WorktreeCreate is the AUTHORITATIVE worktree gate (fires on actual creation, ignores matchers, exit-2 deny); PreToolUse EnterWorktree + Agent/Task explicit isolation = early defense-in-depth. Frontmatter-isolation coverage is a PHASE-1 GATING PROOF (dump a real payload; prove WorktreeCreate fires) + SubagentStart fail-closed contingency — NOT a documented residual.
  - D-e: MCP deny-by-default over the WHOLE mcp__.* namespace + read allowlist (not enumerated github/gitlab — that reopens server-axis enumeration drift).
**Taste item for Gate A:** global-while-active deny of target tools affects concurrent unrelated sessions (recoverable route-to-Bash); deliberate (session-scoping proved leaky), near-zero cost to /drive.
**Reversibility:** easy (pre-implementation design)
**Classification:** Substantive (load-bearing security-gate decisions)

### 2026-07-05 -- C7-D6 (design r4): git-write-intent MCP pattern, completedAt anchor, both-directions worktree proof
**Stage:** plan (design review r3 -> r4 revision)
**Task:** Fix C7 (gate bypass) — sibling PreToolUse/WorktreeCreate hooks
**Trigger:** design-review r3 FINDINGS — both voices confirmed run-presence + WorktreeCreate sound and VERIFIED the Key Insight (drive does all git via Bash), but caught: (P1a) all-mcp deny wedges /drive's own MCP AskUserQuestion on Conductor-class hosts; (P1b/codex-P1(2)) substring read-allowlist lets writes masquerade as reads; (codex-P1(1)) stage!="done" anchor suppressible; (P1c) WorktreeCreate proof omitted the negative direction.
**Revisions (supersede C7-D5's all-mcp + stage-anchor):**
  - D-e: MCP deny by git-hosting WRITE-INTENT PATTERN (write-verb create|update|delete|push|merge|add|remove|set|write|fork|replace + git-noun pull_request|pr|branch|ref|commit|file|content|blob|tree|tag|release|repo). Dodges AUQ (no git noun), catches get_or_create_pull_request/list_and_delete_refs/read_write_file masquerades, server-/name-drift-resistant.
  - D-b: run-presence anchor = run dir lacks a parseable authorizing completedAt (the is_done() done-proof, DRY); missing/unreadable/unparseable state -> ACTIVE/deny (fail-closed). Replaces suppressible stage!="done".
  - D-d: WorktreeCreate proof must cover BOTH directions — POSITIVE (isolation/--worktree fires + deny blocks) AND NEGATIVE (Bash git worktree add does NOT fire, else it wedges /drive; scope-discriminate contingency).
  - Out-of-scope named residuals: Bash-side git pull/rebase/cherry-pick (pre-existing merge-gate gap, SECURITY.md:105, not C7's non-Bash scope); RemoteTrigger/CronCreate/DesignSync (forgery-class); forged completedAt (forgery).
**Reversibility:** easy (pre-implementation design)
**Classification:** Substantive (load-bearing security-gate decisions)

### 2026-07-05 -- C7-D7 (design r5): GitLab merge_request noun added; resolver bound to completedat_authorizes
**Stage:** plan (design review r4 -> r5 revision)
**Task:** Fix C7 (gate bypass) — sibling PreToolUse/WorktreeCreate hooks
**Trigger:** design-review r4 FINDINGS — both voices: (P1) noun set omitted GitLab merge_request/mr, so create_merge_request escapes on an in-scope host; (P2) resolver must bind to completedat_authorizes not is_done() (whose stage=="done" branch re-opens suppressibility), and the legacy stage=done-no-completedAt fail-closed false-positive was unnamed.
**Revisions:**
  - D-e: add merge_request|mr to git-noun set; add `accept` write verb; phase-design enumerates verb/noun against ACTUAL GitHub+GitLab MCP tool lists; issue/note/gist/comment deliberately excluded (not code-ship).
  - D-b: bind resolver to completedat_authorizes ONLY (forbid is_done() wholesale reuse — its stage=="done" branch is suppressible).
  - Out-of-scope: named the legacy stage=done-without-completedAt run as a bounded fail-closed FALSE-POSITIVE (denies target tools for a finished run until GC; safe direction, self-heals).
**Reversibility:** easy (pre-implementation design)
**Classification:** Substantive (bounded)

### 2026-07-06 -- C7-D8 (phase1 design): resolver reimplements completedAt parse in hook-lib (NOT source retention)
**Stage:** design (phase 1)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Question:** How does the shared run-presence resolver reuse completedat_authorizes when drive-retention.sh is a CLI (runs top-level on source)?
**Options considered:** (a) source drive-retention.sh from drive-hook-lib.sh; (b) move completedat_authorizes/parse_ts INTO the lib + retention sources it (out-of-scope surface + 121KB test blast); (c) reimplement a byte-faithful minimal _drive_completedat_authorizes in drive-hook-lib.sh, bound to the completedAt marker semantics ONLY (not is_done()).
**Chosen:** (c) + a followup to unify later.
**Reasoning:** (a) executes retention's whole scan on source (unsafe). (b) expands owned surface to drive-retention.sh + its tests (blast radius, not in phase boundary). (c) keeps blast radius to the owned files, honors "bind to completedat_authorizes ONLY", ~20 lines duplication logged as a followup.
**Reversibility:** easy
**Classification:** Taste

### 2026-07-06 -- C7-D9 (phase1 design): resolver keys on completedAt marker ONLY; reads no state.json
**Stage:** design (phase 1)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Question:** The task edge-case list says "unreadable state.json => fail-closed active" — but D-b/D-b2 forbid keying on stage. How reconcile?
**Options considered:** (a) read state.json + completedAt; (b) completedAt marker ONLY.
**Chosen:** (b) — active iff a run dir lacks a parseable authorizing completedAt; no state.json read for the decision. Fail-closed is on the completedAt marker (absent/unreadable/unparseable => active), which subsumes the intent for every not-yet-done run.
**Reasoning:** stage is suppressible (r3 codex-P1) — the whole reason D-b moved off it; completedAt is the authoritative done-proof. A valid completedAt + corrupt state.json is genuinely shipped (done), not active.
**Reversibility:** easy
**Classification:** Mechanical (follows D-b)

### 2026-07-06 -- C7-D10 (phase1 design): tests in test/*.test.sh, not tests/contracts/*.py
**Stage:** design (phase 1)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Question:** design.md/task said tests go in tests/contracts/*.py; the REAL gate regression guard is test/*.test.sh.
**Chosen:** New hook tests live in test/*.test.sh (drive-tool-gate.test.sh, drive-worktree-gate.test.sh, extend drive-hook-lib.test.sh + install-drive-hooks.test.sh). tests/contracts stays the doc/command pin suite (run it too — doc/installer edits may trip pins).
**Reasoning:** THE REAL CODE WINS. tests/contracts are pytest pin/shape tests for docs+command files; the gates are covered by the bash suite + CI bash-suite job. Matching the existing style keeps the regression guard coherent.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-07-06 -- C7-D11 (phase1 design): substring verb/noun match; word-bound only pr/mr; camelCase-normalize
**Stage:** design (phase 1)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Question:** How precisely to match the git-hosting write-intent pattern to be drift-resistant without absurd over-deny?
**Chosen:** Substring match for write verbs + multi-char git nouns (drift-resistant, D-e); the 2-letter nouns pr/mr matched ONLY as whole _-delimited tokens (^|_)(pr|mr)(_|$) (P3). Normalize camelCase->snake before lowercasing for server-agnosticism.
**Reasoning:** Substring keeps a new write tool caught without edits; pr/mr are the only real bare-substring hazard. Concurrent-session over-deny via multi-char substrings is the accepted Gate-A taste item; /drive uses none of these tools so is never self-wedged.
**Reversibility:** easy
**Classification:** Taste (bounded)

### 2026-07-06 -- C7-D12 (phase1 design review r1): AC-10 is a CLOSURE criterion, not proof-ran
**Stage:** design (phase 1, review r1 codex-P1 #1 BLOCKING)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: AC-10/WorktreeCreate closure was satisfiable merely because the proof RAN, leaving --worktree / Agent isolation:"worktree" creation open when the positive proof "fails".
**Revision:** AC-10 + §3 reframed as a CLOSURE criterion — satisfied ONLY when native worktree creation off a slice/<runId>/<id>-class ref (BOTH isolation:"worktree" AND --worktree) is EMPIRICALLY DENIED by an IMPLEMENTED, installed gate (exit-2 WorktreeCreate in the normal case, OR a REQUIRED SubagentStart/scope-discriminated contingency gate implemented-and-denying). A human-signed-off open gap is NOT acceptable closure. Contingencies are required implementations, not escape hatches; conditional bin/drive-subagent-gate.sh + SubagentStart wiring stay in the one slice.
**Reversibility:** easy (pre-implementation)
**Classification:** Substantive (load-bearing security-gate closure)

### 2026-07-06 -- C7-D13 (phase1 design review r1): resolver run-shape gate — require state.json presence
**Stage:** design (phase 1, review r1 codex-P1 #2 MAJOR)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: resolver counted ANY ~/.claude/harness-runs/*/ dir lacking completedAt as ACTIVE (only [ -d ]), so a stray/empty/legacy non-run dir wedges every gated MCP+worktree surface forever.
**Revision:** A dir is a RUN CANDIDATE only if it is a directory AND contains a state.json (a real run always writes state.json at setup). No state.json => not a run => skipped (never hots the gate). state.json PRESENCE is a shape gate only — contents never read for the done decision (still completedAt-marker-only, D-i/D-b2). A dir WITH state.json but missing/unreadable/unparseable completedAt stays fail-closed ACTIVE (real, possibly-corrupt run — unchanged). E-2/E-10 updated. E-10 abandoned-never-done-RUN residual kept (accepted).
**Reversibility:** easy
**Classification:** Substantive (bounded — shrinks stray-dir wedge without weakening fail-closed on real runs)

### 2026-07-06 -- C7-D14 (phase1 design review r1): merge-intent MCP deny must NOT route to ungated Bash verbs
**Stage:** design (phase 1, review r1 codex-P1 #3 MAJOR)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex (verified vs real drive-merge-gate.sh line 824-825): ship detection gates ONLY the `create` action; `gh pr merge`/`gh pr edit`/`glab mr merge` are UNGATED. The mcp-write deny routed merge_pull_request -> "gh pr merge", advertising an ungated bypass.
**Revision:** Sub-classify the mcp-write deny by verb. MERGE-intent (verb merge/accept: merge_pull_request/merge_merge_request/accept_merge_request) -> reason states "merging a PR/MR into base is NOT a drive-gated op — drive ships via gated gh pr create + Gate B, base-merge is post-run/human", routing to NO Bash verb. CREATE/PUSH/WRITE-intent -> still routes to the GATED gh pr create / git push (git merge mention dropped). Added gh pr merge/edit + glab mr merge to §7 as an explicit named residual (pre-existing Bash-gate gap, analogous to SECURITY.md:105); docs/drive-enforcement.md Limitations records it. Create-intent MCP tools unchanged (still route to gated forms).
**Reversibility:** easy
**Classification:** Substantive (security-gate correctness — do not advertise an ungated surface)

### 2026-07-06 -- C7-D15 (phase1 design review r2): merge-intent classified by FIRST verb TOKEN, not substring
**Stage:** design (phase 1, review r2 P1 #1 — internal inconsistency in D14)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** noun `merge_request` splits to tokens merge+request, so a substring OR "verb-token-anywhere" test mis-buckets create_merge_request (a SHIP action) into merge-intent, contradicting the §1.4 table (route to gated glab mr create).
**Revision:** Classify deny-route intent by the tool's LEADING verb = the FIRST _-delimited token (post camelCase-normalize). merge/accept first token => merge-intent (no Bash verb). Any other first token (create/push/update/... , or a non-verb masquerade first token) => create/write-intent => gated create/push forms. create_merge_request -> create -> correct. Tool still denied either way; wrong-message bug only.
**Reversibility:** easy
**Classification:** Substantive (internal-consistency correctness)

### 2026-07-06 -- C7-D16 (phase1 design review r2): resolver = object-state.json OR mtime-freshness (fixes D13 setup-window fail-open + foreign-state.json wedge)
**Stage:** design (phase 1, review r2 P1 #2 BLOCKING + P1 #3 MAJOR)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** (P1#2) D13's "run always has state.json" is FALSE — drive.md:40-43 mkdir claims the leaf BEFORE the first state.json write, so the state.json-presence shape gate is INERT (fail-OPEN) during the setup window. (P1#3) a non-object/unreadable state.json (`printf '[1,2,3]'`) counted as a real run => permanent wedge on an unrelated machine.
**Revision:** A dir is ACTIVE iff completedat_authorizes==false AND [ (a) state.json parses as a JSON OBJECT (jq -e type==object), OR (b) no object-state.json but dir mtime within DRIVE_SETUP_FRESHNESS_SECS=120 (fail-closed for a freshly-claimed mid-setup dir) ]. Aged dir w/ no object-state.json => INERT (stray/foreign/abandoned-empty no longer wedges forever). jq-absent => present state.json file treated as shape-satisfied (fail-closed). completedAt remains the SOLE done input; object-ness+mtime are shape gates only. Mirrors retention's isinstance(st,dict) skip. E-2/E-2b/E-10/AC-3 updated.
**Reversibility:** easy
**Classification:** Substantive (load-bearing — closes a fail-open window D13 introduced + a foreign-input wedge)

### 2026-07-06 -- C7-D17 (phase1 design review r2): AC-10 contingency is SPIKE-GATED + payload-derived, not an asserted SubagentStart file
**Stage:** design (phase 1, review r2 P1 #4 MAJOR)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: D12 over-tightened — it asserted a REQUIRED bin/drive-subagent-gate.sh, but verified-hook-api.md establishes NO SubagentStart event/payload. Don't assert an unverified hook API.
**Revision:** AC-10 closure rests on the PRIMARY WorktreeCreate exit-2 gate, whose Phase-1 spike is EXPECTED to cover both --worktree AND isolation:"worktree" (verified-hook-api documents it as THE native interception point). A fallback gate is built ONLY IF the spike shows a path uncovered, and its mechanism is chosen FROM THE ACTUALLY-DUMPED payloads then (SubagentStart is at most one candidate IF the dump reveals it — not asserted). If no event covers the uncovered path, it's a named platform residual surfaced to phase-integration review (not a silent pass). AC-10 stays a genuine closure criterion (r1 finding-1 preserved). owns note: fallback file is spike-gated conditional, NOT pre-named; expected case adds no extra file.
**Reversibility:** easy
**Classification:** Substantive (reconciles closure rigor with the verified hook API)

### 2026-07-06 -- C7-D18 (phase1 design review r2): create/push deny names both hosts (gh pr create / glab mr create / git push)
**Stage:** design (phase 1, review r2 P2 #5 MINOR)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Revision:** create/push-intent deny message names BOTH gated ship forms (gh pr create AND glab mr create) plus git push, host-appropriate.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-07-06 -- C7-D19 (phase1 design review r3): DETERMINISTIC claim-time run-active.marker (drive.md), mtime -> sub-second backstop
**Stage:** design (phase 1, review r3 codex-P1 #1 — confirmed-real fail-open)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** the 120s freshness window does NOT deterministically close the setup gap — a setup turn stalling >120s pre-state.json goes INERT and a concurrent session slips through. Two rounds of freshness-tuning didn't close it; push past the heuristic to a claim-time signal.
**Verified:** drive.md ~line 40-45 `mkdir "$RUN_DIR"` is setup step 1; first state.json write is several steps later (needs baseRef/featureBranch/repoRoot).
**Decision:** Mechanism (ii) — write $RUN_DIR/run-active.marker as the IMMEDIATE successor to the mkdir claim (before any other setup step; and on each disambiguator-retry success). Chose (ii) over (i) reorder-state.json-first because state.json's fields depend on later setup steps; the marker is minimal + non-disruptive. Resolver gate (a) = marker existence (deterministic from claim-time); object-state.json = redundant/legacy gate (b); mtime-freshness = gate (c) BACKSTOP for only the sub-second mkdir->marker gap (named residual). completedAt stays the SOLE done input; marker is a shape signal only. Phase now OWNS .claude/commands/drive.md; drive-md string-pin contract tests (tests/contracts) MUST run during implement (memory drive-md-has-contract-pin-tests + local-pytest-needs-python3). One-slice: marker is a produced(drive.md)->consumed(resolver) contract, stays in the same review unit.
**Reversibility:** easy
**Classification:** Substantive (load-bearing — deterministic closure of the setup fail-open)

### 2026-07-06 -- C7-D20 (phase1 design review r3): create/push deny message accuracy + arbitrary-branch residual
**Stage:** design (phase 1, review r3 codex-P1 #2 — message accuracy + residual)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** verified drive-merge-gate.sh gates only the DRIVE-branch push / gh pr create (lines 819-837, push_ship_runid); a denied create_branch routed to "git push" could be satisfied by `git push origin main:new-branch` which the gate leaves inert -> branch created ungated. Not a new bypass class (branch creation merges nothing into base) — deny-MESSAGE accuracy + named residual.
**Revision:** Three-way create/write message split: ship-create-intent (create/push + ship noun pr/mr) -> gated gh pr create/glab mr create/drive-branch git push; merge-intent -> no Bash verb; other-write-intent (create_branch/create_ref/create_or_update_file/delete_file/fork...) -> message that does NOT claim a gated Bash route and NAMES that arbitrary non-drive branch/ref creation (git push origin <src>:<newref>, git branch <x>) is OUTSIDE both gates. Extended the §7 named residual (+docs Limitations) to include arbitrary-branch push/branch creation alongside gh pr merge/git pull/rebase. Did NOT expand the Bash gate (scope).
**Reversibility:** easy
**Classification:** Substantive (message accuracy — do not advertise an ungated surface)

### 2026-07-06 -- C7-D21 (phase1 design review r3): method-param aggregate DENY layer; issue_write refuted; real MCP lists enumerated
**Stage:** design (phase 1, review r3 codex-P1 #3 — aggregate-tool method-param escape)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: a noun-only-named aggregate tool (e.g. mcp__github__pull_request with method:"merge") would be missed by name-only verb+noun matching -> a code-ship write PASSES. (The specific issue_write example is REFUTED: write verb but no git noun -> correctly passes; deny is verb-ANYWHERE AND noun-ANYWHERE so token order never lets a code-ship write escape.)
**Revision:** (a) Enumerated the real CURRENT GitHub + GitLab MCP tool lists — as of 2026-07 all code-ship writes are verb-in-name (no shipped noun-only aggregate code-ship tool found); recorded in §1.4 + a build-time re-confirm note. (b) Added a defensive PARAM layer: DENY iff (git-noun in name) AND (write-verb in name OR a write-verb token in a {method,action,mode,operation,command} param). Reads still pass (no write verb in name OR param -> method:"get" passes), preserving the Gate-A writes-denied/reads-pass taste (NOT broadened to deny reads). Kept the verb-first-token deny-MESSAGE classifier (extended: primary verb = name first-token if a verb, else the param verb). §1.4 rows + E-11 + AC-4b added.
**Reversibility:** easy
**Classification:** Substantive (closes the method-param omission; cheap forward-proofing)

### 2026-07-06 -- C7-D22 (phase1 design review r4): run-shape (has runId) tightening + aged-dir doc consistency; codex BLOCKING overruled to fail-closed residual
**Stage:** design (phase 1, review r4 codex-P1 #1 — OVERRULED severity + cheap tightening)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex tagged BLOCKING: aged object-state.json stray/abandoned dir stays ACTIVE forever. OVERRULE: this is the FAIL-CLOSED direction (over-deny of target tools, NOT a bypass) and the accepted E-10 residual; the object-state.json branch is REQUIRED for upgrade-safety of legacy pre-marker in-flight runs (removing it fail-OPENs a real legacy run).
**Revision:** (a) Doc consistency — E-2b/E-10/mitigation wording now states crisply: a run-shaped dir (marker OR object state.json with runId) + no completedAt stays ACTIVE regardless of age (fail-closed residual, self-heals via retention-GC followup); ONLY dirs lacking BOTH a marker AND a run-shaped object state.json age out to inert. (b) Cheap tightening (kills codex's {}-stub attack): gate (b) counts a dir as a run ONLY if the parsed object is RUN-SHAPED — has a `runId` key (jq -e 'type=="object" and has("runId")'). A {} / [1,2,3] / random-object stub is not run-shaped -> falls to marker/freshness -> ages out. Real legacy runs (runId present) stay fail-closed. §1.1 + E-2b + AC-3f updated. jq-absent still fail-closed (present state.json treated as shape-satisfied).
**Reversibility:** easy
**Classification:** Substantive (bounded — tightening + doc correctness; did NOT remove the upgrade-safety branch)

### 2026-07-06 -- C7-D23 (phase1 design review r4): push_files/base-push deny message precision (branch-blind honesty)
**Stage:** design (phase 1, review r4 codex-P1 #2 — MAJOR message precision)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: push_files (and multi-target/base-push writes) deny routing is branch-blind — the message must not falsely promise a gated route for a push whose target the hook cannot see. push_files IS denied (push+file); purely message accuracy.
**Revision:** other-write-intent message (covers push_files/create_or_update_file/create_commit/create_branch/...) now: routes drive-branch shipping to the gated drive/<runId> git push / gh pr create, AND states plainly that a direct push/write to an ARBITRARY or BASE ref (git push origin <src>:<newref>, push to main, git branch <x>) is the already-named out-of-scope Bash-surface residual — no false "this is gated" claim. Did NOT expand the Bash gate.
**Reversibility:** easy
**Classification:** Substantive (message accuracy)

### 2026-07-06 -- C7-D24 (phase1 design review r4): run-active.marker write is atomic + FAIL-CLOSED (setup STOPs on write failure)
**Stage:** design (phase 1, review r4 codex-P1 #3 — REAL new gap, FIXED)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** codex: marker-write failure was unspecified, but the marker is now the load-bearing deterministic setup signal. A failed marker write + a crash before the first state.json write -> the freshness backstop covers only the freshness window, then ages to INERT = fail-OPEN for a live orphan run.
**Revision:** §1.6/drive.md setup spec: write run-active.marker atomically (tmp + mv, like every marker) AND fail-CLOSED — if the marker write fails, setup STOPs immediately (no featureBranch, no state.json, no work dispatched). A failed marker write is a HARD setup failure. Added E-12 + AC-3e. The empty claimed dir left behind ages out harmlessly (no branch/work).
**Reversibility:** easy
**Classification:** Substantive (closes a real fail-open on the load-bearing claim-time signal)

### 2026-07-06 -- C7-D25 (phase1 design review r5): propagate the round-4 run-shape fallback everywhere (stale-doc P1)
**Stage:** design (phase 1, review r5 P1 — doc propagation; MECHANISM already correct/converged)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Trigger:** :50/:639 resolver prose still said "reads NO state.json / keys only on completedAt", contradicting the round-4 run-shaped object-state.json fallback (:88/:513) which DOES read state.json shape for legacy pre-marker upgrade-safety. An implementer following the stale text would implement completedAt-only and MISS the fallback -> a legacy pre-marker run (state.json={"runId":...}, no completedAt) reads INERT -> create_pull_request/native worktree escapes = fail-open.
**Revision:** Grepped the whole doc; rewrote the two stale copies (Divergence 3 :50-55, D-i :639-641) AND aligned two adjacent "object-ness" phrasings (:108 resolver NOTE, :379 E-2) to the ACTUAL two-decision rule: DONE keys ONLY on completedAt (state.json/marker/mtime never read for done; stage/values never read at all); ACTIVE/run-shape reads marker existence OR run-shaped state.json (has runId) OR mtime backstop. Doc now internally consistent on the one rule. No mechanism change.
**Reversibility:** easy
**Classification:** Substantive (doc-consistency; prevents an implementer fail-open)

### 2026-07-06 -- C7-D26 (phase1 design review r5): name the legacy-upgrade-window transitional residual
**Stage:** design (phase 1, review r5 P2 — bounded transitional residual)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Revision:** §7 names the legacy-upgrade fail-open: a pre-marker run killed between featureBranch creation and its first state.json write has neither marker nor run-shaped state.json -> ages to INERT for that orphan. Bounded (no early target-tool dispatch; only a concurrent session, transiently, only during the one-time upgrade), SELF-CLEARS as pre-marker runs drain (new runs write the marker at claim-time). Deliberately NO mechanism (dead code post-drain). Named, not silent.
**Reversibility:** easy
**Classification:** Taste (bounded named residual)

### 2026-07-06 -- C7-D27 (phase1 design review r5): push_files listed only under other-write (cosmetic P2)
**Stage:** design (phase 1, review r5 P2 cosmetic — Claude voice)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Revision:** push_files (noun `file`, NOT a ship noun pr/mr) deterministically routes to other-write-intent; removed it from the ship-create example lists (§1.2 classifier + reason) so an implementer does not assert the wrong message. §1.4 DENY rows unaffected (push_files still DENIED: push+file).
**Reversibility:** easy
**Classification:** Mechanical

---
**Stage:** implement (slice 1.1)
**Task:** Fix C7 — sibling non-Bash enforcement hooks
**Decision (D-impl1 — name-verb noun-strip, reconciles §1.4 AC table with the verb-anywhere intent):** `_drive_name_write_verb` in drive-tool-gate.sh STRIPS the recognized git nouns from the tool tail BEFORE the write-verb scan. Load-bearing because the ONLY write verb that is also a substring of a noun is `merge` ⊂ `merge_request`: a raw verb-substring scan (as §1.2 literally states) false-DENIES the READ `github__get_merge_request` / `gitlab__get_merge_request` — which §1.4 lists as PASS. Stripping the noun leaves `get_` (no verb ⇒ PASS) while `merge_merge_request` leaves `merge_` (⇒ DENY) and `pull_request_review_write` leaves `_review_write` (verb present regardless of token order ⇒ DENY). Preserves the design's "verb-anywhere ∧ noun-anywhere, order-independent" deny AND every §1.4 read PASS row; verified by the AC-4 deny/pass matrix in test/drive-tool-gate.test.sh.
**Reversibility:** easy (localized to one predicate)
**Classification:** Mechanical (implements the §1.4 AC table faithfully; the spec's "substring" wording was under-specified for the merge/merge_request collision)

**AC-10 spike outcome (recorded in worktree-proof/RESULT.md):** ran live via nested headless `claude` with a WorktreeCreate hook wired ONLY through `--settings` (global settings.json untouched). WorktreeCreate FIRES for BOTH `--worktree` AND subagent `isolation:"worktree"` (refuting verified-hook-api's caveat); exit 2 empirically BLOCKS creation in both cases; a Bash `git worktree add` fires NO event and succeeds. BOTH directions CLOSED by the PRIMARY exit-2 gate; NO spike-gated fallback file added.

## STOP (User-Challenge) — premise already shipped on main (discovered at slice-1.1 review)
- **Finding:** `main`/`origin/main` (tip 3057839) ALREADY contains a complete, shipped C7 fix
  (`a478cf0 feat(drive): C7 non-Bash tool gate` + slice-2.1 review fixes + phase-2 integration
  + harden + finalize; a 439-line `bin/drive-tool-gate.sh`), landed by prior run
  `drive/main-20260705-130712`.
- **Root cause:** this run's `phaseBaseSha` (0b13c65) is ~40 commits BEHIND main, cut before C7
  landed; the run re-implemented C7 from scratch off a stale base. (Commit 3057839 "pre-flight
  fast-forward baseRef to its remote on fresh run (#69)" — the guard that prevents exactly this —
  landed after this run started.)
- **Assessment:** the from-scratch `drive-tool-gate.sh` rewrite (181 lines) is redundant and would
  REGRESS the mature shipped 439-line version if merged. BUT this run's 6-round design + live AC-10
  spike surfaced REAL gaps the shipped version left open: (1) NO `bin/drive-worktree-gate.sh`
  (WorktreeCreate gate) on main — the frontmatter `isolation:"worktree"` bypass our spike proved
  real is UNCLOSED there; (2) shipped gate has ZERO GitLab `merge_request` coverage; (3) shipped
  active-run anchor is `stage!="done"` (suppressible) vs our `completedAt`.
- **Classification: User-Challenge** — surfaced, not auto-decided.

## PIVOT (user-approved) — gap-closing run against current main
- User chose Option B: rebase onto current main (305783962db50cd4c4bf4141e2f6302cb85c4e05), discard the redundant from-scratch
  drive-tool-gate.sh rewrite (kept as reference at slice commit d69bf05), and re-scope Phase 1
  to close ONLY the two gaps main's shipped C7 lacks:
    G1 — add bin/drive-worktree-gate.sh (WorktreeCreate authoritative gate) closing the
         frontmatter isolation:"worktree" bypass (our live AC-10 spike proved WorktreeCreate
         fires + blocks both --worktree AND isolation:worktree; PreToolUse-only misses it).
    G2 — add GitLab merge_request/mr coverage (+ accept verb) to the shipped drive-tool-gate.sh
         so mcp__gitlab__create/merge/accept_merge_request are denied.
- Phase 1 is REDESIGNED against the REAL shipped code (epoch r1). New base frozen from main.
- Classification: User-Challenge resolved by the user; execution is Mechanical from here.

### 2026-07-06 -- C7-RESCOPE (Phase1 delta): design G1 (WorktreeCreate gate + shared-predicate extraction) + G2 (GitLab MR)
**Stage:** phasedesign
**Task:** Fix C7 remaining gaps against the SHIPPED drive-tool-gate.sh (439 lines) on main
**Reality anchor:** shipped active-run predicate is INLINE (drive-tool-gate.sh:154-215): stage!=done + non-empty repoRoot + mtime liveness (DRIVE_TOOL_GATE_LIVE_HOURS default 24). NO completedAt, NO run-active.marker. MCP matching is EXACT SUFFIX ENUMERATION (8 GitHub suffixes), NOT verb/noun substring. The stale-reference resolver/verb-noun design is VOID for this base.

- **D-w0 — shared predicate = EXTRACTED shipped inline scan.** Lift drive-tool-gate.sh:154-196 byte-faithfully into drive-hook-lib.sh as `drive_scan_active_runs`; tool-gate calls it (covered edit, no behavior change). Both gates DRY-reuse it. **Classification:** Mechanical.
- **D-w1 — worktree-gate does NOT repo-scope; denies while ANY run active.** Safe direction (never a bypass), avoids extracting parse_origin/common_dir_of, keeps provisioning off the active hot path. Over-deny of unrelated-repo native worktree creation = named residual (route-to-Bash). **Classification:** Taste.
- **D-w2 — worktree-gate PROVISIONS (not fail-closed) on jq-absent.** A jq-less machine cannot host a /drive run; fail-closing would wedge the native worktree feature with nothing to protect. **Classification:** Mechanical.
- **D-w3 — inactive path PROVISIONS (returns a worktree path), NOT exit 0.** EMPIRICAL correction: WorktreeCreate is a provisioning hook — exit 0 with no stdout path FAILS creation (worktree-proof/claude-worktree.out: "hook succeeded but returned no worktree path"). A bare exit 0 would wedge native worktree creation machine-wide. Exact create-vs-name contract spike-finalized during implement (design-phase1.md §3). **Classification:** Substantive.
- **D-w4 — G2 = exact GitLab MR suffixes (create_/merge_/accept_/update_merge_request) across THREE spots:** install-drive-hooks.sh TOOL_GATE_MCP_MATCHER regex + drive-tool-gate.sh SUFFIX case + mcp_deny_reason branches. Shipped gate is exact-enumeration, so no noun/verb set to extend; GitLab file/branch writes already covered (shared suffixes, server-wildcard matcher). **Classification:** Mechanical.
- **D-w5 — G2 activates only on installer RE-RUN** (settings matcher is the hook-invocation trigger; live settings.json carries the old regex until re-install). Self-nudged by the drift preflight's partial-registration WARN. **Classification:** Mechanical.

### 2026-07-06 -- C7-RESCOPE r1 review revisions (2 P1 + 3 P2 folded into design-phase1.md)
**Stage:** phasedesign (review epoch r1, round 1 → revised)
- **item-1 (P1 MAJOR) — worktree-gate FAIL-CLOSES on jq-absent.** REVERSED D-w2: the authoritative WorktreeCreate gate now DENIES (exit 2) when jq is absent, matching drive-tool-gate.sh:67; a fail-open there would reopen the frontmatter-isolation bypass on the stronger gate. Residual (jq-less machine denies worktree creation) is consistent with the shipped gate. **Classification:** Substantive.
- **item-2 (P1 BLOCKING) — allow-path contract PINNED at design time.** The inactive path MUST return a worktree path (derived from payload name+cwd); a bare `exit 0` is a DESIGN VIOLATION (wedges creation, claude-worktree.out). The spike (AC-8b, now a real-creation closure) resolves ONLY I-a (create+echo) vs I-b (echo+CC-creates), not the whole contract. **Classification:** Substantive.
- **P2 (GitLab grounding) — verified against the real GitLab-MCP tool list.** zereight/gitlab-mcp (83 tools) confirms create_/merge_/update_merge_request as MR writes; accept_/rebase_merge_request enumerated defensively (real GitLab REST ops; rebase = update_pull_request_branch analog; harmless-if-absent under anchored regex). Excluded approve_/unapprove_ + *_note/*_thread (review/comment, parity with the shipped GitHub gate). G2 now adds FIVE suffixes; implementer re-confirms at build time. **Classification:** Mechanical.
- **P2b (no-repoRoot residual) — named precisely.** D-w1 sharpened: the predicate skips no/empty-repoRoot runs (inherited from drive-tool-gate.sh:187-191), so the deny is "any active run WITH a repoRoot"; both the machine-wide over-deny and the no-repoRoot skip are inherited residuals, not new gaps. **Classification:** Mechanical.
- **P2c (banner-count pin) — listed as expected update.** install-drive-hooks.test.sh:395-396 pins 'three hooks'/'four settings entries'; wiring WorktreeCreate reds them → update to "four hooks (five settings entries)", keep other banner tokens intact. **Classification:** Mechanical.
- Unchanged sound parts (per reviewer): drive_scan_active_runs extraction, G2 3-spot approach, one-slice sizing, AC-10 DENY-direction spike evidence.

### 2026-07-06 -- C7-RESCOPE r1 review ROUND 2 revisions (1 P1 + 1 P2)
**Stage:** phasedesign (review epoch r1, round 2 → revised)
- **item-1 (P1) — AC-5 rewritten to the shipped drift-defense model (verified drive-tool-gate.sh:141-149 + pinned test :149-162).** Reads/approve/note tools PASS because the installed MATCHER never selects them to invoke the hook — NOT because the hook exit-0's them. A force-piped unmatched `mcp__*` suffix MUST stay drift-DENY (`case *)` → emit_deny). G2's 3-spot approach already adds the 5 GitLab suffixes to BOTH matcher AND the enumerated `case`, so they classify as writes and never trigger the drift-deny; no AC weakens the drift defense. Fixed AC-5 + E-5. **Classification:** Substantive (contract correction).
- **item-2 (P2) — first_active_run trailing-newline defect.** `ACTIVE_RUNS="$(drive_scan_active_runs)"` strips the trailing newline; `first_active_run`'s `printf '%s' | while read` DROPS a final line lacking a newline → single-active-run case emits an EMPTY runId in fail-closed deny messages (not a bypass). FIX = covered edit (c): first_active_run:203 `printf '%s'`→`printf '%s\n'`. Corrected the §1.1 behavior-preserving text (first_active_run is NOT a heredoc consumer). Added AC-2b (single-run deny names non-empty runId, mutation-guarded). **Classification:** Mechanical (covered edit).
- Untouched (verified-sound): jq-absent fail-close, pinned WorktreeCreate allow-path contract, 5 GitLab suffixes, one-slice sizing, the extraction mechanism itself.

---
**Stage:** implement (slice 1.1, epoch r1)
**Decision (D-impl-w1 — AC-8b allow-path resolved as I-a: hook CREATES then echoes):** The live
AC-8b spike (worktree-proof/RESULT-allow.md) resolved the create-vs-echo contract as **I-a**.
Wired the FINAL `drive-worktree-gate.sh` via `--settings` only (global settings.json untouched),
with the hook's HOME pointed at an EMPTY `~/.claude/harness-runs` so its scan sees NO active run
while `claude` keeps real auth. Result: I-b (echo path WITHOUT creating) HUNG (timeout, no
worktree) — Claude Code expects the worktree to already exist at the echoed path; I-a (hook runs
`git -C "$cwd" worktree add --detach "$parent/$name"` THEN echoes the path) SUCCEEDED — the
worktree is ACTUALLY created for BOTH `--worktree` AND subagent `isolation:"worktree"` (both
present in `git worktree list`), and the sessions completed (rc 0, "DONE"). DENY direction
re-confirmed against the final gate (run active → exit 2, no worktree). Provisioning uses
`--detach` (no branch: native worktrees are not slice/<runId>/<id> refs, and there is no active
run to key one to). *Classification: Mechanical (resolves the one design-pinned spike unknown).*
**Reversibility:** easy.

**Decision (D-impl-w2 — GitLab merge/accept share one deny-reason branch):**
`merge_merge_request|accept_merge_request` share a single `mcp_deny_reason` case branch (both are
MR-into-target merges, human-owned at Gate B), printing the actual suffix via `%s` so each still
names its own tool verbatim ("GitLab MCP tool <suffix>") — the AC-4 distinct-tool assertion holds.
Mirrors the shipped GitHub gate's per-tool-name discipline. *Classification: Mechanical.*

---
**Stage:** implement (slice 1.1, review round 2)
**Decision (D-impl-w3 — worktree-gate fails CLOSED on a BLIND active-run scan; hostile-env
blinding NAMED as out-of-scope forgery-class):** Round-2 codex found the authoritative
WorktreeCreate gate failed OPEN when the scan was BLIND because `~/.claude/harness-runs` exists
but is unreadable/unsearchable (`chmod 000` → `find` enumerates nothing → empty scan → "no active
run" → provision even with a run live). FIX (gate-only, surgical): before trusting an EMPTY scan,
if RUNS_ROOT EXISTS but is not (`-r` AND `-x`) → exit 2 fail-closed DENY (like the tool-presence
pre-check). An ABSENT root is NOT blind (genuinely no runs → allow). A single unreadable SUBDIR
is NOT guarded (find enumerates the rest; self-hidden subdir = deliberate evasion). RED-then-GREEN
regression added.
**Named residuals (documentation-only, "named not silent"):** (a) a hostile actor who can
manipulate the scan's EXECUTION ENVIRONMENT — stub a scan binary that exits 0-empty on PATH, or
`chmod 000` an individual run subdir to self-hide it — can blind the run-presence scan; this is
DELIBERATE-EVASION / forgery-class, OUT OF SCOPE (consistent with the Gate-A design boundary
"omission-proof, not forgery-proof"; run-presence is far harder to accidentally/omissively
suppress than to forge → Component D / C10). (b) the SHIPPED `bin/drive-tool-gate.sh` PreToolUse
gate has the SAME pre-existing fail-open on a missing/broken scan tool (it never prechecks
find/sort) and shares `drive_scan_active_runs` — inherited, not introduced here; hardening it is a
separate forgery-class follow-up. Did NOT touch drive-tool-gate.sh / drive_scan_active_runs
(extraction stays byte-faithful for the shipped gate). *Classification: Substantive (closes the
last in-scope fail-open on the authoritative gate; bounds the rest).*
**Reversibility:** easy.

## Harden-regress P1 OVERRULED (refuted at integration) — AC-9 spaced-path WT test portability
- Claude harden-regress flagged P1: the AC-9 sp_wt_path1 assertion reds on macOS because $TMPDIR's
  trailing slash yields a double-slash expected path. REFUTED: WORK="$(mktemp -d "${TMPDIR}/…")"
  and mktemp -d returns a CANONICAL path (double slash collapsed); both the expected $SPACED_WT_GATE
  and the installer's cd&&pwd path derive from the same canonical $WORK. Reproduced 3x under the
  default macOS $TMPDIR (/var/folders/.../T/, trailing slash) → install-drive-hooks.test.sh 101/0
  PASS every run. codex harden-regress independently returned CONVERGED (no findings).
- Classification: Mechanical (evidence-based overrule; no code change).

## CORRECTION — the harden-regress "overrule" ABOVE was WRONG; the AC-9 test bug IS real
- My earlier overrule reproduced with `unset TMPDIR` (→ /tmp, no trailing slash) — an UNFAITHFUL
  repro that MASKED the bug. Driving the FAITHFUL path (default macOS $TMPDIR = /var/.../T/, trailing
  slash, NOT unset) reds install-drive-hooks.test.sh 100/1: `WORK="$(mktemp -d "${TMPDIR}/…")"` yields
  a double slash the installer's cd&&pwd collapses, so the AC-9 exact-path assertion (line 343)
  mismatches. The confirming harden auditor (harden-1-2) correctly surfaced this with reproduction
  evidence despite the "do not re-raise" steer. FIX APPLIED: canonicalize $WORK via
  `WORK="$(cd "$(mktemp -d …)" && pwd)"` (test-only). Lesson: drive the faithful env, never a shortcut.
- Classification: Mechanical (self-corrected; test-only fix).
## D-finalize1 — Installer drift preflight: add worktree-gate coverage (Taste) (2026-07-06T08:19:47Z)
Classification: Taste. Finalize adds a drift-preflight check for `drive-worktree-gate.sh`
presence + `.hooks.WorktreeCreate` registration, mirroring the existing tool-gate
variant-3/variant-4 checks, + a missing-WorktreeCreate test. Rationale: the installer now
manages 4 hooks but its drift preflight only inspected merge-gate + tool-gate; a partial
deploy leaving the AUTHORITATIVE G1 worktree gate dead was un-warned — an in-scope
completeness gap in the run's OWN installer, cheap, evidence-backed (partial deploys are an
already-handled class: variants 1–5). Codex flagged P1; the run team had deferred it as a
per-phase "nicety". Fixed at finalize as aggregate completeness. Surface at Gate B.

## D-finalize2 — OVERRULE codex P1: GitLab MR cross-forge host-blind match (2026-07-06T08:19:47Z)
Codex P1 (drive-tool-gate.sh:355): the MCP owner/repo match ignores the forge host, so a
GitLab MR carrying owner/repo colliding with an active GitHub run on the same owner/repo is
denied. REPRODUCED (owner/repo GitLab fixture vs a github.com active run → deny). OVERRULED
as an in-run code fix, WITH evidence: (1) the forge host is NOT present in the MCP tool_input
(codex's OWN ARCH item) — no in-scope fix can distinguish forges; (2) real zereight GitLab
payloads are project_id-only → they hit the unextractable-owner/repo FAIL-CLOSED deny anyway
(reproduced) — the owner/repo axis is synthetic-fixture-only; (3) over-deny is the gate's
ACCEPTED fail-closed direction (recoverable route-to-Bash). Routed to finalize-todo.md (ARCH)
+ the pre-existing "G2 vendor-schema drift" followup. Actionable residue = the GitHub-branded
deny text on shared paths → folded into de-slop (D-finalize3).

## D-finalize3 — OVERRULE codex P1: drive_scan_active_runs fail-open on scan-tool absence (2026-07-06T08:19:47Z)
Codex P1 (drive-hook-lib.sh / drive-tool-gate.sh): the shared scan swallows find/sort/perm
failures → empty → read as "no active run" (fail-OPEN) for the SHIPPED PreToolUse tool-gate.
OVERRULED as out-of-scope, WITH evidence: this is the ALREADY-LOGGED, deliberately-deferred
followup (C7-RESCOPE slice-1.1 review-r2) — it changes SHIPPED tool-gate behavior and is
FORGERY-class (this run's threat model is OMISSION). The new WorktreeCreate gate already
fails-closed on these; hardening the shipped tool-gate is a separate change. Stays in
followups.md; not fixed in-run (scope-creep HARD GATE).

## D-finalize4 — RE-AFFIRM overrule of scan fail-open (codex re-raised, round 2) (2026-07-06T08:49:21Z)
Codex round-2 re-flagged the drive-tool-gate.sh scan fail-open on find/sort-absent PATH as
P1 (reproduced again). RE-AFFIRMED overrule per D-finalize3, WITH evidence: it is a
PRE-EXISTING, inherited fail-open of the SHIPPED tool-gate (this run extracted the shared
drive_scan_active_runs predicate but did NOT introduce the posture); it is FORGERY-class (it
requires a hostile/degraded PATH stripped of coreutils `find`/`sort`, not any omission the
coordinator can make — this run's threat model is OMISSION); and the NEW G1 code
(drive-worktree-gate.sh) already fails-closed on it. Hardening the shipped tool-gate is a
SEPARATE forgery-class change, already logged in followups.md. Out of the run's blast radius
(scope-creep HARD GATE) → routed to followups (already present), does NOT block convergence
(out-of-scope real bug → followups per the finalize contract). The design-level articulation
(uncentralized fail-closed preconditions) → finalize-todo.md ARCH.

## D-finalize5 — Phase-1 harden-regress re-review to persist terminal CONVERGED artifact (2026-07-06T09:43:34Z)
On finalize-resume the ship-gate (b-i) precondition failed `no-phase-review`: highest-N
review-phase1 was review-phase1-2 (harden-regress FINDINGS, a test-only macOS exact-path bug at
98e32dc). That P1 was genuinely fixed by beab9c0 (test-only cd&&pwd canonicalization; phase
harden-1-3 = HARDENED; suites green), but the terminal CONVERGED harden-regress REVIEW artifact
was never persisted. Ran a genuine dual-voice harden-regress re-review binding beab9c0 →
review-phase1-3.md CONVERGED (reviewer: P1 resolved + no new P1 in gate code; codex: AC-9
resolved). Codex re-raised the pre-existing shipped scan fail-open as P1 → OVERRULED, verified
present in shipped main (line 199), not introduced by this run, forgery-class, out of scope
(D-finalize3/4). NOT a forge — the phase is genuinely hardened; this persists the missing
terminal review artifact. This is the [[drive-ship-conformance-sha-binding]] pattern.

# Decisions — regress-selfid

- **D1 — Marker lives in the review file body, not a sidecar.** The review already carries
  machine-read in-body lines (`reviewed-sha:`, `## Verdict:`); a body line is atomic with
  the file and read by the same grep the conformance scan already runs. Classification:
  Mechanical.
- **D2 — Marker presence = harden-regress; absence = integration (default).** Makes
  backward-compat free (old runs read as integration = current behavior) and fails safe (a
  lost marker degrades a regress file to integration, which the exact yes-vs-marked guard
  catches as a drop). Classification: Mechanical.
- **D3 (revised r1) — Redefine `regress-mismatch` as the ASYMMETRIC guard
  `marked-regress > harden-yes` (surplus only), replacing `yc > prc`.** A deficit
  (`marked-regress < harden-yes`) is NOT a fire — it is a drop/inflight/legacy transient
  healed by exact resume re-dispatch of `harden-yes − marked-regress`. Reuse the violation
  name. The asymmetry resolves both round-1 P1s (no false-fire on legacy `0 ≤ yes` nor on
  the mid-harden crash window `0 < 1`) while keeping multi-drop unmaskable. Classification:
  Taste.
- **D4 — Exact marker token deferred to /drive-design** (greppable, non-incidental,
  consistent with the existing `key: value` line style). Classification: Mechanical.
- **D5 (new r1) — No era-version/schema field added to `state.json`.** The uniform
  asymmetric guard makes backward-compat inherent (legacy `marked=0 ≤ harden-yes` never
  fires), so no cutover discriminator is needed; and `--mode checkpoint` never reads
  `state.json` (git+artifacts only), so an era signal could not live there anyway. Avoids
  the masking hole a "zero-marked ⇒ legacy fallback" branch would reopen. Classification:
  Mechanical.
- **D6 (new r1) — Marker classification uses a LINE-ANCHORED grep
  (`^harden-regress:`), never a body substring.** This feature's own phase-integration
  review contains the literal `harden-regress:` in prose; a substring match would
  misclassify it as marked and (via `marked > yes`) false-fire. Contract-test
  mutation-verify: delete the marker line → file reclassifies as integration. r2: also add
  the reverse-direction contract test (integration prose starting a line with the token must
  NOT misclassify as marked) + constrain the token so it can't legitimately begin a line.
  Classification: Mechanical.
- **D2 (revised r2) — Marker-loss deficit is a DIAGNOSTIC, not the heal trigger.** A lost
  marker shows as `marked-regress < harden-yes`; the heal fires ONLY if it left a ship-blocking
  FINDINGS terminal on a hardened phase (D7). A marker-loss on a CONVERGED terminal already
  ships (marker-agnostic b-i) → no-op, no converged→FINDINGS flip. Classification: Mechanical.
- **D7 (new r2) — Heal is an ALL-PHASES resume sweep keyed off the ship symptom.** Current
  resume has no bullet re-visiting an already-advanced phase (drive.md:235-237 = only
  `hardening`/un-advanced `hardened`), so the c7-gate-bypass case would stay unfixed. Sweep
  every phase (advanced included) BEFORE routing/`phaseBaseSha` overwrite, bind each surviving
  `phaseInt/<runId>/<P>` tip, trigger ONLY on hardened-phase + FINDINGS-terminal (deficit is a
  diagnostic, not the trigger). Classification: Taste.
- **D8 (new r2) — Heal is a BOUNDED re-review owned by the resume sweep, fail-closed to STOP.**
  Heal path sits outside the harden 3-fix-round loop, so own cap `HEAL_CAP` (small; counter
  `state.healRound[<P>]`; frozen tip → one re-review usually suffices, cap bounds marker-emit
  retries). CONVERGED → healed; FINDINGS → non-decision STOP (never forge CONVERGED);
  marker-emit-fails → bounded retry then STOP. Not a new false-block (terminal was already
  FINDINGS). Classification: Taste.
- **D7 (revised r3) — Heal trigger is a STALE ship-blocking terminal (`reviewed-sha ≠ hardened
  tip`), not the raw count.** Sweep fires only on hardened + highest-N FINDINGS + terminal
  `reviewed-sha ≠ git rev-parse phaseInt/<runId>/<P>` (missing sha = ≠tip); the re-review writes
  at the hardened tip so it self-terminates (CONVERGED flips the terminal; a genuine FINDINGS is
  now bound to the tip) — no re-heal loop. `reviewed-sha` (not "unmarked-only") heals BOTH
  marker-era (marked FINDINGS terminal) and legacy stale cases. Classification: Taste.
- **D8 (revised r3) — Heal is a SINGLE no-counter re-review per resume leg; drop `HEAL_CAP` +
  `state.healRound`.** `verdict_converged()` reads `## Verdict:` not the marker (self-terminating
  on first CONVERGED write; FINDINGS STOPs first attempt → no retry to bound); `healRound` has no
  artifact ground truth (violates `max(state,artifact)`); a `HEAL_CAP>1` retry writes a 2nd marked
  file → `marked>yes` → self-wedge on the feature's own guard. At most ONE marked file per episode
  ⟹ `marked ≤ harden-yes`. Classification: Taste.
- **D9 (new r3) — Single owner by construction: resume sweep SKIPS any phase with an open
  `inflight-harden-<P>.marker`.** Harden persists HARDENED before clearing the marker
  (drive-harden.md:141,255); a crash there leaves open-inflight + hardened + FINDINGS → both
  stranded-marker recovery AND the sweep eligible → double-dispatch → `marked>yes` HARD STOP. Skip
  rule (promoted from r2 OQ2 to approach level) makes owners disjoint; `/drive-design` pins wording
  only. Classification: Taste.
- **D1 (reaffirmed r3) — Marker atomicity covers no-partial-marker.** The marker line is written
  atomically WITH the review file and its `reviewed-sha`, so a heal file is fully written (marker +
  reviewed-sha) or not at all — no torn "unmarked FINDINGS" state → no marker-emission retry
  needed. Classification: Mechanical.
- **D10 (new r4) — Heal re-review recovers its diff base from DURABLE per-phase refs, not the
  mutable global `phaseBaseSha`.** Closes round-4 MAJOR-1: only one global `phaseBaseSha` is
  persisted, overwritten each phase (drive.md:296), so an advanced phase's base is gone. Recover
  `base(P)=phaseInt/<runId>/<P-1>` for P>1 (survives advance — drive.md:1196-1197 removes only the
  integration worktree + slice branches; equalled phase P's frozen `phaseBaseSha` at its start),
  `base(1)=baseRef`; heal diffs `git diff <base(P)>..phaseInt/<runId>/<P>`. Exact P=1 binding under a
  moved main is a /drive-design detail. Classification: Taste.
- **D11 (new r4) — `marked-regress` counted as DISTINCT `reviewed-sha` values among marked
  review-phase<P> files, not raw file count.** Closes round-4 MAJOR-2: a stranded dual-voice
  recovery appends a SECOND marked file (N=file-count+1, orphan not removed — drive-review.md:58,62,
  drive.md:508) → raw count false-fires the surplus guard. Distinct-sha dedupes it (each real fix
  round = a distinct post-fix tip; a stranded duplicate shares the tip → counted once), making both
  the surplus guard (`distinct-marked-sha > harden-yes`) and deficit immune, and protecting the
  NORMAL harden loop (not just the heal — the asymmetric guard would otherwise regress a benign
  duplicate into a false STOP). `integration-round` stays `count(unmarked)` (legacy unmarked files
  may lack reviewed-sha; inflation benign under `max(state,derived)`). Exact bash (grep reviewed-sha,
  sort -u, count) is a /drive-design detail. Classification: Taste.
- **D10 (revised r5) — Heal diff base keyed off `state.phaseList` ORDER, not arithmetic `P-1`;
  injected as an explicit review arg.** Closes round-5 MAJOR-2: phase ids are ordered but may be
  non-numeric (drive.md:1030), so `<P-1>` is wrong. `base(P) = phaseInt/<runId>/<prev>` where `<prev>`
  is the entry immediately preceding `P` in `state.phaseList`; first entry → `state.baseSha` (D12).
  base(P) is passed as an explicit override to /drive-review — never by temp-mutating the global
  `phaseBaseSha` (breaks a multi-phase sweep). Classification: Taste.
- **D12 (new r5) — Add durable `state.baseSha`, write-once at fresh-run setup, as the FIRST phase's
  heal base.** Closes round-5 MAJOR-1: `state.baseRef` is a movable branch NAME (drive.md:295,371;
  finalize/ship consume it live), so a moved `main` leaves no durable original base for phase-1's
  heal. Capture `git rev-parse baseRef` at `featureBranch` cut (drive.md:288), write-once, never
  re-derived on resume (mirrors repoRoot). NOT a checkpoint proof input (checkpoint never reads
  state.json) and NOT a counter (no max(state,derived) rule); add it to the `state.json`
  shape/`test_state_json_shape` pin. Classification: Taste.
- **D6 (OQ3 corrected r5) — Prior-epoch UNMARKED review-phase files CAN co-exist; count ALL unmarked
  across epochs.** Closes round-5 MINOR: phase-review FINDINGS→IMPLEMENT (drive.md:1167)→REDESIGN
  (drive.md:1138) with `phaseReview[<P>].round` NOT reset (drive.md:1111,1145) persists prior-epoch
  unmarked files. Counting all unmarked across epochs is the intended safe model (inflation benign
  under `max(state,derived)`); the marked/harden-yes surplus stays single-epoch by construction
  (harden never ran pre-redesign). Classification: Mechanical (correctness-forced).
- **D12 (revised r6) — Legacy run (baseSha ABSENT) first-phase heal = FAIL-CLOSED NON-DECISION
  STOP; keep `baseSha` OPTIONAL (state-lint never requires it).** Closes round-6 codex MAJOR: a run
  created before `state.baseSha` resumes fine (state-lint is a positive validator, does not require
  it — drive-conformance.sh:891-1030), but its FIRST phaseList entry has no durable base(1) and
  re-deriving is forbidden → previously undefined. FIX: the resume sweep does NOT auto-heal the first
  phase of a baseSha-absent run; it surfaces a NON-DECISION STOP to the documented MANUAL
  harden-regress recovery (bind the hardened tip, re-review for real, never forge — memory
  drive-harden-regress-must-persist-terminal-converged). Scoped ONLY to the first phaseList entry of
  a baseSha-absent run (P>1 heals off durable `phaseInt/<prev>`; a NEW run heals its first phase off
  `state.baseSha`). Do NOT make state-lint require `baseSha` (would false-reject legacy routing).
  Classification: Taste.
- **D10 (revised r6) — Inject base(P) as an OPTIONAL drive-review override, DEFAULTING to the
  global `phaseBaseSha`.** Closes round-6 codex MINOR: the injected base(P) needs a drive-review
  input-contract change (today `phase <P>` hardcodes the global `phaseBaseSha`, drive-review.md:36;
  argument-hint omits a base arg, drive-review.md:3). Pin it as an OPTIONAL override arg to
  `/drive-review phase <P>`, defaulting to the current global when not supplied — so ONLY the
  resume-sweep heal supplies it and normal build-time `phase <P>` / `phase <P> harden-regress`
  invocations are unchanged. Named as a touch-point. Classification: Taste.
- **Docs (r6, Claude MINOR) — reword the base(P) non-numeric-id rationale to the `4a`-suffix
  grammar.** The `["auth","api"]` example is impossible (state-lint enforces `^[0-9]+[a-z]?$`,
  drive-conformance.sh:929). The DECISION stays correct (arithmetic `P-1` is undefined on suffixed
  ids like `4a`/`4b`); reworded every occurrence (design ~76/203/271/453) to cite the real suffix
  grammar. Classification: Mechanical (correctness-forced doc fix).

## Phase-1 detailed-design decisions (design-phase1.md)
- **DD1 — Marker classifier VALUE-anchored `^harden-regress:[[:space:]]*yes[[:space:]]*$`, token `harden-regress: yes`.** Tightens D6's `^harden-regress:` sketch: integration prose may mention the token but won't be a whole line exactly `harden-regress: yes`; closes reverse-direction misclassification without a substring match. Classification: Mechanical (correctness-forced; D4 deferred exact token here).
- **DD2 — On surplus-guard fire, `phaseReviewRound = count(unmarked)`, NOT clamped to 0.** Integration round is now independent of the marked surplus (disjoint file sets); the old `yc>prc` clamp would undercount legitimate unmarked integration files. Surplus reported as its own `regress-mismatch`; round stays honest unmarked count (a `max(state,derived)` hint). Classification: Taste.
- **DD3 — Base override is the named defaulted token `base=<40-hex>`.** Unambiguous vs the existing optional `harden-regress` positional; `key=val` matches run conventions; only the heal supplies it. Classification: Taste.
- **DD4 — Heal-sweep placement: final resume reconciliation action (after Counter-reconstruction + Stranded-marker recovery, before Fresh-session-orientation).** Depends on settled inflight-harden state + reconstructed counters, must precede Execute re-entry (phaseBaseSha overwrite) — all satisfied. STOP routes via the existing Present-human-pause path. Recommended over hooking `hardening` (misses advanced phases = the c7 case). Classification: Taste.
- **DD5 (corrected r2, Claude P2) — `baseSha` gets a NEW presence + write-once pin in `test_state_json_shape.py`, NOT added to CORE_KEYS.** `repoRoot`'s precedent is the write-once DISCIPLINE in drive.md (:311–316), NOT a test pin (test_state_json_shape has no repoRoot pin; CORE_KEYS excludes it; test_drive_retention treats it as optional). So there is no pin to "mirror" — add a NEW baseSha presence/write-once assertion from scratch; keep it out of CORE_KEYS. Classification: Taste.
- **DD6 (new r2, Claude MAJOR / codex BLOCKING #2) — Heal dispatch uses a DISTINCT `inflight-heal-<P>.marker`, excluded from generic stranded-marker recovery, owned by the resume sweep.** Generic recovery (drive.md:161–169,:497–515) re-dispatches a stranded `inflight-review-phase<P>.marker` by scope alone as a plain `phase <P>` review → strips the heal's harden-regress flag (unmarked terminal) AND `base=` override (wrong global phaseBaseSha for an advanced phase) → NEW permanent false ship-block. Fix: distinct marker kind, carved out of generic recovery; the SWEEP recovers it (recomputes base(P) deterministically from durable data, re-dispatches at the SAME hardened tip → same reviewed-sha → deduped → never trips surplus guard; sweep-vs-recovery order irrelevant). Output still the marked review-phase<P>-N.md family; only the dispatch marker is distinct. Classification: Taste.
- **DD7 (new r2, codex BLOCKING #2) — `base=<40-hex>` is STRIPPED before `<scope>` derivation.** drive-review scans args for `^base=([0-9a-fA-F]{40})$`, captures `<diffBase>`, removes the token, then derives scope/harden-regress from the remainder (scope stays `phase<P>`). Absent → global `phaseBaseSha`. Normal build-time invocations byte-identical. Classification: Mechanical (correctness-forced).
- **DD8 (new r2, Claude MINOR) — Marker classifier is HEADER-REGION bound.** The value-exact anchor matches ONLY before the first `## Findings` (header preamble), so a fenced-code quote of `harden-regress: yes` in the review body (this feature's own review is the likely offender) cannot misclassify a file as marked. A structural fixed-position anchor over generated output, replacing the soft "wrap in backticks" plea as the load-bearing mechanism. Relies on the schema's always-present `## Findings` header (drive-review.md:115–118). Classification: Mechanical (correctness-forced).
- **Refuted r2 (codex BLOCKING #1) — stale-CONVERGED terminals do NOT false-block ship; trigger stays FINDINGS-only.** Verified: ship b-i counts a phase review on `verdict_converged`+`reviewed_sha_of` PRESENCE+`codex_present` (bin/drive-conformance.sh:480–488), NO `rsha==tip` (that check is check_scope_counts:252, used by build-time phase-merge:391, not ship b-i; terminal sha-binding at ship is b-ii/finalize :505–507). A stale-CONVERGED terminal satisfies b-i; only a FINDINGS terminal fails verdict_converged. Refutation recorded in design §1.8; do NOT expand the trigger. Classification: Mechanical (evidence-refuted).
- **drive-review.md:43 reword (r2, Claude P2) — "the ONLY difference is the counter" → TWO file-family-preserving differences** (no round increment + the `harden-regress: yes` marker). Reds the test_checkpoint_contract.py:800–808 pin; update it in the same commit (lockstep). Classification: Mechanical (correctness-forced doc fix).
- **DD9 (r3, codex BLOCKING) — Resume sweep OWNS recovery of an OPEN `inflight-heal-<P>.marker`, keyed on the MARKER (adopt/re-dispatch), ORDERED before the stale-FINDINGS trigger.** Distinct marker (DD6) alone isn't crash-safe: `/drive-review` writes the Claude file (drive-review.md:115) before the codex sibling (:141), so a crash after the marked file lands at the hardened tip leaves the terminal `reviewed-sha == tip`, which the stale-FINDINGS trigger SKIPS → with generic recovery carved out (DD6) the marker orphans (checkpoint never clean, inflight-open glob :581). Fix: sweep's FIRST per-phase action recovers the open marker via drive.md:497–515 (adopt if marked-file-at-tip + non-empty codex, else re-dispatch recomputing base(P) at the same tip; no cap → STOP unreachable), THEN the trigger runs. Classification: Mechanical (correctness-forced crash-safety).
- **DD10 (r3, codex BLOCKING) — `is_marked` uses a `found`-flag predicate, NOT `END { exit 1 }`; writer pins the marker to the header preamble.** In awk `END` runs after an earlier `exit`, so `/marker/ {exit 0}` + `END {exit 1}` overrides the match → every file UNMARKED → distinct-marked-sha=0 → surpluses false-pass. Correct form: set `found` on match, decide exit at `^## Findings` (`exit(found?0:1)`) or `END` (`exit(found?0:1)`). Verified in bash: marked→rc0, unmarked→rc1, quoted-below-Findings→rc1. Writer MUST place the marker after `reviewed-sha:` and before `## Findings` (schema drive-review.md:118→119 guarantees it; pinned so it can't drift). Classification: Mechanical (the pinned awk was non-functional).
- **DD11 (r3, codex MAJOR / Claude P2) — AC14 re-scoped: resume-sweep coverage lands in `test_checkpoint_contract.py` (executable `--mode checkpoint` fixtures + prose-grep pins); `test_rebirth_e2e.py` DROPPED from the lockstep set.** That harness does NOT run the coordinator (docstring lines 9–15). The feature's executable surface lives entirely in drive-conformance.sh (marker classification, distinct-sha, surplus guard, inflight-open on the heal marker) → behavioral tests there; the coordinator prose (sweep ordering, `inflight-heal-*` carve-out, FINDINGS→STOP, `base=` strip) → prose-grep pins there. No genuinely-executable piece needs test_rebirth_e2e.py. Lockstep set = test_checkpoint_contract.py + test_state_json_shape.py. Classification: Taste.
- **DD12 (r3, Claude MAJOR) — AC11 subtraction-pin lockstep ENUMERATED by name+line; two ABOVE-band behavioral fixtures named with corrected values; SPLIT the regress fixture.** The prior "all ~517–885" scoping UNDERCOUNTED — `test_checkpoint_clean_fixture_passes_with_counters` (:161) and `test_checkpoint_regress_mismatch_violation_and_zero_round` (:215–229) sit above the band and INVERT under the marker/distinct-sha reader (§1.3/DD2/DD3): clean `phaseReviewRound {"1":2}→{"1":3}` (3 unmarked = 3 rounds, no subtraction), and the regress fixture's yes>files premise is now a benign DEFICIT (no fire, `{"1":1}`). FIX: AC11 enumerates ALL fixtures/pins by name+line with corrected shapes — clean → `{"1":3}` (Option (a), pure integration baseline); regress SPLIT into a SURPLUS fixture that fires (2 marked distinct-sha + 1 harden-yes → `2>1`, round `{"1":1}` NOT clamped — the DD2 guard) + a DEFICIT fixture (old inputs, benign); plus in-band `test_harden_regress_no_round_increment_contract_pinned_both_voices` (mark one file → `{"1":2}` preserved) and `test_five_reconstruction_rules_pinned` rule-2 pin; plus a LOCAL `_marked_review` helper (owned; shared `_helpers.py::_review` untouched). Classification: Mechanical (correctness-forced — the "suite GREEN" guarantee was false until these are named).
- **DD13 (r4, Claude BLOCKING, refines DD12) — AC11 restructured to representative-enumeration + grep completeness backstop + green-suite gate; `test_harden_regress_no_round_increment_contract_pinned_both_voices` owned as a WHOLE-test semantic rewrite.** Round-4 found DD12's per-line enumeration STILL missed a pin — the drive.md :774–778 "1:1 marker" clause, a second assertion of the same drive.md:256–258 span §1.6 rewrites — the enumeration treadmill. FIX: AC11's BINDING acceptance is now GREEN `python3 -m pytest tests/contracts` backed by a mandatory grep sweep of `test_checkpoint_contract.py` for every subtraction-era token (`prc - yc`, `MINUS`, `- 1 yes`, `1:1 marker`, `without incrementing the round`, `would otherwise go negative`, each `regress-mismatch` premise), rewriting each surviving occurrence — so the design no longer depends on exhaustive line-enumeration. AC11 #3 rewritten to own the whole test: half-A drive-review.md :793–799 SURVIVES (harden-regress still does not increment the round); drive.md :774–778 + drive-review.md :800–808 + conformance :819/:823/:828–834 subtraction pins RE-PINNED to the marker/distinct-sha contract. Classification: Mechanical (correctness-forced).

## Finalize round 1 triage (2026-07-07T16:16:50Z)
- **D-fin1 (P1-a OVERRULE → ARCH, Mechanical):** codex flagged the heal/`base=`/`baseSha` recovery path as a P1 missing-test. Overruled as an in-run fix with evidence: grep proves these tokens exist only in drive.md/drive-review.md PROSE + substring-pin tests; bin/drive-conformance.sh has no executable consumer. An E2E test is a new harness-driver subsystem (out of blast radius). Routed to finalize-todo.md as ARCH (codex itself co-filed it ARCH).
- **D-fin2 (P1-b ACCEPT, Mechanical):** codex flagged body-only-sha / missing-`## Findings` as untested for the slice-merge & audit consumers of the shared check_scope_counts→reviewed_sha_of gate. Accepted (adversarial voice on a security gate; cheap in-scope; mutation-verifiable). Adding slice-merge + audit body-only-sha tests that RED on the pre-fix whole-file reader.

## /drive run finalize-verdict-integrity-20260709 — finalize Verdict/AppliedEdits gate integrity (2026-07-09T16:01:23Z)
Fixed TODO whole-repo-audit P1 #1: a finalize codex-only-P1 fix round left review-finalize-N.md
reading terminal (Verdict:CONVERGED + AppliedEdits:yes + reviewed-sha==tip), so a rebirth-resume /
manual ship shipped an un-re-audited fix. Two-part fix + tests.

## D1 — Right-size to ONE phase, ONE slice [Mechanical]
Producer (drive-finalize.md) + 3 consumers (drive.md, drive-ship.md, drive-conformance.sh)
+ both test suites form ONE produced→consumed contract (the AppliedEdits terminal marker).
OPERATING: keep shared-contract code in ONE review unit — splitting risks the contract
silently failing to transfer. No fan-out / staged-risk justification for a seam.

## D2 — Fix is two-part (producer honesty + consumer defense-in-depth) [Mechanical]
Not producer-only. The RED→GREEN fixture is {Verdict:CONVERGED, AppliedEdits:yes}; only a
consumer AppliedEdits check rejects it (producer honesty alone can't catch a forged/pre-fix
CONVERGED artifact). Follows directly from the task's own RED→GREEN constraint.

## D3 — Consumers require EXACTLY `AppliedEdits: no` (not merely "not yes") [Mechanical]
Fail-closed: also rejects `pending` (mid-flight) and missing. Mirrors the free confirming
round's terminal marker; a fix round writes `yes`, the terminal converged round writes `no`.

## D4 — Do NOT force the deterministic fresh-session rebirth seams (Seam A/B) [Taste — surface at Gate A]
Single-session, right-sized run with the user present. Seams A/B are context-management for
long multi-session runs; forcing 2 paste-handoffs here is pure friction. Class-A
context-pressure rebirth stays available via the installed Stop hook if the window fills.

## D5 — Consumer AppliedEdits reader: shared first-match header-region-bound helper [Mechanical — design review MAJOR]
`applied_edits_no()` in bin/drive-conformance.sh: extract the FIRST header-region
(BOF→`## Findings`) `^(##[[:space:]]*)?AppliedEdits:` line, THEN compare value == `no`
(extract-first-then-compare, like verdict_converged — NOT grep-for-`no`-in-header). Reused by
ship b-ii; prose consumers (drive.md, drive-ship.md) say "the FIRST `## AppliedEdits:` line is
exactly `no`". NOT the anywhere-grep the checkpoint yes-COUNTER uses. Defeats the body-quote
attack (finalize audits this repo, whose docs contain the literal).

## D6 — Producer rewrites the FIRST `## Verdict:` line IN PLACE on both branches [Mechanical — design review NIT]
Fix round → replace the first `## Verdict:` line with FINDINGS; no-fix confirming round →
replace it with CONVERGED (affirmative, symmetric). In-place replace, never append a second
`## Verdict:` line (consumers read first-match).

## D7 — RED/GREEN matrix covers {yes, no, body-quoted-no, pending, missing} [Mechanical — design review P2]
Behavioral --mode ship fixtures: yes→BLOCK, no→SHIP, body-quoted-no(header yes)→BLOCK,
pending→BLOCK, missing-AppliedEdits→BLOCK. Mutation-proves the exactly-`no` half.

## D8 — Prose consumers include the literal `## AppliedEdits: no` [Mechanical — phasedesign P2]
drive.md/drive-ship.md prose: "the FIRST `## AppliedEdits:` line is exactly `no` (i.e.
`## AppliedEdits: no`)" so the `_REQUIRED_CARRIERS` carrier-token pin matches.

## D9 — Test matrix adds a no-`## Findings` malformed case [Mechanical — phasedesign P2]
6th --mode ship fixture: a finalize artifact lacking `## Findings` → BLOCK (pins the helper's
fail-closed delimiter behavior).

## D10 — Fold codex slice P1 (require `##` heading in applied_edits_no) despite Claude CONVERGED [Taste — surface at Gate B]
Voices split: codex FINDINGS (optional-`##` accepts a bare `AppliedEdits: no`); Claude
CONVERGED (drift-tolerance acceptable, bare-`no` out-of-threat-model NIT). Reproduction: a
bare `AppliedEdits: no` is NOT producer-reachable (producer + seed_finalize emit the `##`
heading; a crash leaves `pending`) → forgery-adjacent, outside the stated omission/crash
threat model. FOLD anyway: the sibling gate verdict_converged requires `^## Verdict:`
(mandatory `##`); a `no`-GATE must fail closed on malformed input, not accept it; the fix is
trivial + zero happy-path cost (producer/seed_finalize emit the heading). Overruling would
leave the gate looser than its sibling. Adversarial voice is load-bearing for gates.

## D11 — Overrule codex slice round-2 P1s (zero-space header variants) WITH EVIDENCE [User-Challenge-adjacent → surface at Gate B]
codex r2 NOT-CONVERGED on `## AppliedEdits:no` / `## Verdict:CONVERGED` (zero space after colon).
Reproduced both. REFUTED-at-integration + OVERRULED: (1) not producer-reachable (producer emits
colon-SPACE-value everywhere) → forgery, outside the omission/crash threat model; (2) `[[:space:]]*`
is the universal file convention (reviewed_sha_of / verdict_converged / counter all use it) —
applied_edits_no mirrors it; tightening diverges; (3) `no` is written only on genuinely-converged
rounds, so spacing-tolerance is liveness-correct; (4) P1 #2 targets UNTOUCHED verdict_converged
(scope creep, run-wide gate). Claude CONVERGED both rounds. Round-1 (no-heading) was the meaningful
class fix; round-2 is the per-input treadmill (memory: drive-finalize-adversarial-class-fix).

## D-r2r4-1 — runId naming (Mechanical)
Used descriptive runId `r2r4-codex-20260708-144534` (spec says `<branch>-<timestamp>`; repo precedent
favors descriptive ids — e.g. c7-gate-bypass-*, regress-selfid-* — and safe-run-id memory prefers
identifiable names). featureBranch drive/r2r4-codex-20260708-144534.

## D-r2r4-2 — scope order (User-directed)
User picked R2 + R4 now, deferring R1+R3 despite TODO's R2 -> R1+R3 -> R4 order. Premise, not a
coordinator decision. R5-R9 batch untouched.

## D-r2r4-3 — one phase, not an R2/R4 staged split (Taste)
Classification: Taste (surfaced at Gate A via design.md).
Grounded: the codex wait loop is pure coordinator prose in all three review specs (no bin/ helper
exists), so R4's watchdog call-sites are the very fenced blocks R2 reorders — a writer/reader
shared contract. One unit = blocks edited once + a SINGLE pin-suite migration (same rationale as
TODO's R5–R9 one-batch rule); a staged split would double both and add a full phasedesign+harden
loop for a mid-band (~250–400 surface) change.

## D-r2r4-4 — watchdog + health probe as ONE new bin/ helper (Mechanical)
Classification: Mechanical.
Never a prose "poll the mtime" coordinator step (dont-make-the-model-the-meter). Fail direction:
kill only on a positively-observed 15-min zero-byte stall; ambiguity (stat errors) → do not kill;
3h backstop is the only unconditional bound. Dep-independent tests simulate streaming / silent /
stall-after-stream / long-but-streaming logs.

## D-r2r4-5 — killed-call salvage + marker writer (Mechanical)
Classification: Mechanical.
After kill+retry-fail the coordinator writes codex-review-<scope>.md with FIRST line
CODEX_KILLED_TIMEOUT (same write path as CODEX_UNAVAILABLE today), and the post-process subagent
still extracts pre-stall findings from the partial raw log. Gates unchanged (codex_present =
existence+non-empty); bin/drive-conformance.sh untouched; drive.md combined-verdict/run-graph
prose gains the distinct tier.

## D-r2r4-6 — probed outage on gate-enforced scopes: one bounded attempt (Taste)
Classification: Taste (surfaced at Gate A).
Premise fixes non-gate-enforced scopes → immediate degraded single-voice on a probed outage. For
gate-enforced scopes, still make ONE watchdog-bounded dispatch attempt before degrading: ≤~35
bounded minutes buys keeping the sole-catcher adversarial voice on the highest-stakes scopes.

## D-r2r4-7 — TMPDIR namespacing carried into harden/finalize codex blocks (Mechanical)
Classification: Mechanical.
Only drive-review.md wraps codex exec in mkdir/TMPDIR today (D5); harden/finalize blocks lack it.
They are being rewritten anyway (sandbox flag + watchdog wiring) — carry the wrapper uniformly.
In blast radius, cheap, no pin reds (AC13 pins only drive-review.md).
## D-r2r4-8 — autoplan housekeeping prompts deferred (Mechanical)
gstack upgrade 1.55.1->1.58.5 available: NOT upgraded mid-run (would swap load-bearing review
skill semantics under an active run; run standalone after ship). CLAUDE.md skill-routing AUQ:
skipped (its flow commits to main — forbidden during a run; user can opt in standalone).
## D-r2r4-9 — autoplan execution shape (Mechanical)
Full-depth phase execution delegated to primary-reviewer subagents (each reads its
plan-*-review SKILL.md from disk, writes $RUN_DIR/autoplan-<phase>-report.md); independent
Claude voices = autoplan's verbatim subagent prompts; codex voices run from MAIN context
(background+log, OPERATING.md rule). Reason: three ~2300-line skill files would consume the
coordinator window before review begins; analysis depth is preserved, decisions return to the
coordinator (6 principles + audit trail). Premise gate = Stage-0 user directive (R2+R4);
premise challenges surface at Gate A, not a mid-autoplan pause. Phases sequential: CEO -> Eng
-> DX; Design skipped (no UI surface in repo — grep hits are substring false positives).
## D-r2r4-10 — watchdog threshold: parameterized 15-min default + gap-logging (Mechanical, evidence-forced)
Preserved codex raw logs have NO per-line timestamps -> the "calibrate from 262 logs" fix is
not statically derivable. Resolution: premise's 15-min no-byte threshold stays the DEFAULT but
is a helper parameter (spec pins the mechanism + flag presence, not the constant); the helper
logs each call's observed max inter-append gap (live calibration corpus for later tightening);
retry-once bounds false-kill cost. Margin context: audit §1C in-codex suite runs are 6-10 min
byte-silent windows today.

## D-r2r4-11 — effort tiering mechanism is a -c config override (Mechanical, evidence-forced)
codex CLI has no first-class effort flag; global ~/.codex/config.toml pins
model_reasoning_effort="xhigh". Tiering = `-c model_reasoning_effort="<tier>"` on the dispatch
line for confirmation-class calls only. Verified vs codex exec --help (0.142.5).
## D-r2r4-12 — CEO-phase consensus dispositions (see autoplan-ceo-consensus.md)
Salvage DROPPED v1 (Taste, codex over primary; premise-faithful; raw log kept). Sandbox ladder
pre-decided w/ hard spike precondition (Taste). Effort-tier degraded-prior exclusion
(Mechanical). Gate-enforced scopes enumerated; bounded-attempt kept, codex dissent logged
(Taste). Honest bounds restated (Mechanical). Expansions E2-E5 + Gate-B degraded-count line
INCLUDED; E6/C5 excluded (unanimous). One-phase fusion KEPT (P+S endorse, C dissents; OPERATING
shared-contract rule + atomic run shipping). All Taste items surface at Gate A.

## D-r2r4-13 — killed-call v1 = NO automated salvage (Taste; SUPERSEDES the salvage half of D-r2r4-5)
Classification: Taste (flagged for Gate A).
CEO-consensus item B (C-P2e over P-T1/AD6): codex-review-<scope>.md = first line
CODEX_KILLED_TIMEOUT + one warning line; contributes zero P1 like CODEX_UNAVAILABLE but renders
as a DISTINCT tier (never folded); raw + .killed-N attempt logs kept on disk; v2 salvage gated on
the helper attempt-log showing degraded rounds are frequent. D-r2r4-5's marker-writer path and
gates-unchanged clause stand; its "post-process salvages pre-stall findings" clause is retired.

## D-r2r4-14 — sandbox ladder pre-decided (Taste)
Classification: Taste (flagged for Gate A).
Consensus item D: phase-design spike = HARD precondition (fixture-WRITING repro under read-only);
pass => --sandbox read-only on all three call sites; fail => workspace-write for code scopes +
read-only for design/phasedesign scopes. One-line spec value per call site = kill switch. Today's
trust_level="trusted" means any rung is a behavior change. Replaces design.md open question 1.

## D-r2r4-15 — watchdog threshold parameterized + per-attempt backstop (Mechanical)
Classification: Mechanical.
Consensus item E: 15-min stall threshold is the helper-parameter DEFAULT (sub-second-settable for
tests); helper logs each call's max inter-append gap (live calibration); the 3h backstop is per
ATTEMPT, stated explicitly.

## D-r2r4-16 — effort-tier predicate excludes degraded priors (Mechanical)
Classification: Mechanical.
Consensus item C (S#3/P-F3): the confirmation-class downgrade requires a genuinely-completed,
non-degraded prior codex round with zero findings; ANY first-line degradation marker in the prior
round's file => full effort.

## D-r2r4-17 — gate-enforced scopes enumerated concretely (Taste; REFINES D-r2r4-6)
Classification: Taste (flagged for Gate A; codex dissent — degrade everywhere — noted).
Consensus item F: one-bounded-attempt-on-probed-outage applies to security-sensitive-diff scopes
(bin/drive-*.sh, gate hooks, matchers/parsers/conformance) + phase-integration + finalize; ALL
other scopes degrade immediately.
## D-r2r4-18 — codex-Eng finding dispositions (Mechanical unless noted)
(1) Helper OUTCOME CONTRACT stated at design level: helper emits a machine-readable outcome
(success/degraded-killed/degraded-outage/error); success -> existing post-process subagent;
degraded -> existing coordinator marker-write path; the helper NEVER writes codex-review-*.md
(preserves today's two-writer structure, no race). (2) Sandbox rung is a scope-conditional
dispatch parameter in drive-review.md's shared block (design/phasedesign => read-only; else
ladder rung) — size note updated. (3) Effort-tier "zero findings" = machine-checkable: prior
codex file has NO severity tags per the existing tag grammar AND a non-degraded first line
(count-tags rule reused; no new metadata contract). (4) Killed-attempt logs named
codex-raw-<scope>.killed-N.log / codex-harden-<P>.killed-N.log — inside the Tier-L swept
family (drive-retention.sh:493 globs verified), zero retention edits; attempt-outcome log is
.jsonl (KEEP family). (5) E4 probe TTL cache DROPPED — probe expected <5s (E4's own skip
rule) and the cache contradicted instance-scoped state (Taste; kills codex finding 5).
## D-r2r4-19 — health-probe candidates verified (Mechanical, evidence)
codex exec has NO native idle/stall/timeout flag (0.142.5) — the helper remains necessary.
`codex doctor --json` exists: redacted machine-readable report incl. auth + HTTP reachability,
~7s wall — primary probe candidate (with its own timeout, fail-toward-degrade); alternative: a
tiny bounded `codex exec` round-trip. Choice = phase-design detail; both named in the design's
Phase-design inputs. Probe cost ~7s/round is negligible vs 5.4-min median calls (E4 cache
stays dropped).
## D-r2r4-20 — independent-Eng finding dispositions (13 findings, 2 HIGH)
ACCEPT: (1) probe caches NOTHING (E4 already dropped) + failed probe retries once w/ backoff
before declaring outage (fail-toward-degrade only after retry); (2) Gate-B clause reworded to
the artifact-honest stat "scopes degraded at their FINAL round" (retro semantics) + optional
attempt-log kill/retry counts with stated coverage — never a per-round history the artifacts
cannot prove; (4) retry ONLY on stall-kills — a 3h-backstop kill goes straight to
CODEX_KILLED_TIMEOUT (bounds tail at ~3h; honest-bounds text updated); (3,7,10,11,13)
phase-design inputs: exact prior-file naming per call site for the effort tier + tag-count
test (prose-clean-but-MAJOR-tag => full effort); helper owns child PID + fstat on open fd
(never path-stat, survives mv-aside), marker writes tmp+mv, single-writer-per-outcome,
helper-crash-between-kill-and-marker test, re-dispatch-while-orphan test; retry jitter +
probe-before-retry; scope-charset validation before path composition; helper deliberately
named bin/drive-* (self-classifies as security-sensitive diff => full-effort codex on this
run's own reviews); (8) docs/drive-enforcement.md joins the token-sweep set, swept via
pathlib not rg; (12) spike checklist: prove flag-overrides-trust_level, TMPDIR-write test,
fixture = gate-script-execution class, verify codex flush behavior.
PARTIAL (5): 15-min default STAYS (premise-pinned) — mitigations: gap-logging, spike verifies
flush behavior, probe-before-retry; log-only-first-run mode REJECTED for this run (defers R4's
value; revisit from attempt-log data). (9) already resolved: killed logs named
codex-raw-<scope>.killed-N.log (inside swept family); (6) moot (cache dropped).
## D-r2r4-21 — Eng-phase consensus + primary-reviewer dispositions
Eng consensus (3 voices): architecture/one-phase/gate-compat CONFIRMED; all amendments
additive. NEW bindings: (F-A1, Taste, SUPERSEDES the writer half of D-r2r4-18(1)) helper owns
ALL non-success marker writes (KILLED_TIMEOUT after failed stall-retry; UNAVAILABLE on probed
outage), tmp+mv atomic, single-writer-per-outcome; coordinator prose keeps ONLY the
helper-itself-missing fallback (rc126/127 -> coordinator writes UNAVAILABLE as today, F-A3);
post-process subagent runs ONLY on helper success outcome (closes the
killed-round-masquerades-as-real-voice race). (F-T1, Mechanical) codex-first ORDERING gets
AC13-style position pins in all three specs. (F-T2..T6/Q1/C1, Mechanical) riders: enrichment
clause named in pin list; sandbox-flag PRESENCE pinned per call site (mechanism not rung);
TMPDIR pin extended to harden/finalize; 4 missing helper-test branches added
(retry-success=>no-marker, backstop-fires, stat-ambiguity=>no-kill, probe-outage per scope
class); retro has TWO marker sites (:99 stats + :144 Rule-U E7) both enumerated; ship-pin
suite named for the Gate-B line; token sweep is REPO-WIDE incl. docs/drive-enforcement.md:56
(pathlib, not rg). Q2 moot (cache dropped). Layer-3 check: timeout(1) IS the refuted
wall-clock variant — custom progress-signature supervisor justified.
## D-r2r4-22 — codex-DX dispositions (5 findings)
(1) Helper contract RAISED to plan level: closed mode set (probe|dispatch) + closed outcome
enum (ok | killed-timeout | outage | error) + machine-readable stdout/exit-code contract,
matching bin/ conventions (drive-conformance --mode / drive-retention report-apply); exact
flag spellings stay phase-design. (2) Marker warning lines carry CAUSE + NEXT STEP
(probe-outage states whether a live attempt was skipped and what to inspect). (3) Attempt-log
FILENAME + schema pinned in design (codex-attempts-<runId>.jsonl in $RUN_DIR; one JSON line
per probe/dispatch/kill/retry with scope, outcome, max-gap); killed-log naming spelled
EXACTLY codex-raw-<scope>.killed-N.log / codex-harden-<P>.killed-N.log in design text
(supersedes the :116 shorthand). (4) Fenced blocks stay SHORT: blocks = invoke helper ->
inspect closed status -> post-process ONLY on ok; branchy logic (sandbox rung by scope class,
effort-tier predicate incl. prior-file tag scan, stall-vs-backstop retry) lives INSIDE the
helper behind flags. (5) docs/drive-enforcement.md gains a short operator paragraph (tier
meaning, gate semantics, investigation path) — already in the token sweep; now also a named
touch-point.
## D-r2r4-23 — helper-missing = STOP, not degrade (Taste; OVERRIDES Eng F-A3 direction)
rc126/127 on the helper = OUR shipped code broken (vs codex absent = accepted external
degradation): silent degrade would drop the adversarial voice fleet-wide unnoticed (the exact
silent-quality-erosion failure class); a STOP is loud, human-fixable in minutes, and matches
the file-recreate-drops-exec-bit precedent (gates fail closed on rc126). Coordinator surfaces
a non-decision STOP; no marker file is written for the scope. Flagged for Gate A (conflicts
with Eng F-A3 fail-open recommendation — overridden with rationale).
## D-r2r4-24 — independent-DX dispositions (2 HIGH + 7 MED); REVISES D-r2r4-23
(H1, Taste — SUPERSEDES D-r2r4-23's STOP and Eng F-A3's degrade) helper rc126/127 => NOT an
outage: fall back to the pre-R4 DIRECT codex exec dispatch (dual voice preserved; only the
watchdog is lost for that round), log distinct HELPER_FAILED in the attempt log, surface at
the next human pause; NEVER write CODEX_UNAVAILABLE for a helper failure. (H2) env-var
escape hatches per repo seam convention: DRIVE_CODEX_STALL_MINS, DRIVE_CODEX_BACKSTOP_HOURS,
DRIVE_CODEX_WATCHDOG=off, DRIVE_CODEX_SANDBOX=<rung>, DRIVE_CODEX_EFFORT_TIER=off — spec pins
defaults, env overrides; helper header documents them. (M1) marker set stays TWO tiers:
CODEX_UNAVAILABLE = absent/outage (warning line MUST carry cause: probe rc, live-attempt
skipped/failed, attempt-log pointer); CODEX_KILLED_TIMEOUT = watchdog kill ONLY (incl. a
gate-enforced bounded attempt that stalls out). (M2) warning-line fields mandated (threshold,
attempts, max observed gap, killed-log paths, attempt-log pointer); attempt-log records
effort tier + sandbox rung per attempt (weak confirmation rounds traceable). (M3) touch list
+= CLAUDE.md $RUN_DIR inventory, README.md (:110 graceful-degrade wording + bin listing);
.harness/decisions.md EXCLUDED from the token sweep (append-only history). (M4) killed-log
naming already codex-raw-<scope>.killed-N.log; SAME-SHAPE rider: rename the .log.stranded
mv-aside to .stranded.log form in the same block rewrite (retention Tier-L coverage). (M5)
sandbox spike MUST emit a durable $RUN_DIR evidence artifact (command, output, rung selected)
that the phase-design review verifies — no prose self-report. (M6) helper CLI pins repo bin/
norms: drive-*.sh name, --flag value + exit-2 usage guard, Usage header, exit codes 0/1/2,
stdout outcome tokens byte-identical to marker strings. (M7) Gate-B clause shape pinned:
per-tier counts + affected scopes, computed from final-round files + attempt log (honest).
## D-r2r4-25 — DX-phase consensus; REVISES the .stranded rider in D-r2r4-24(M4)
Primary DX APPROVE 8/10 (no P1; TTHW ~0 — zero-config rollout). ACCEPTED: warning-line
content contract (cause: stall|backstop|probe, attempts, max gap, killed-log + attempt-log
paths; rc-126 note names "chmod +x" at point of failure); ONE outcome->marker->post-process->
verdict->rendering TABLE lives in drive-review.md, harden/finalize reference it (existing
"same mechanics" pattern) under the E5 consistency pin; CLAUDE.md $RUN_DIR inventory +
README.md:110 wording ("absent, down, or stalled") + bin listing are NAMED touch-points
(token-sweep-unreachable, grep-verified); Gate-B line splits killed-timeout vs unavailable;
run-graph tier renders cause-honest ("Codex killed (stall)") — never "(partial)"; portable
BSD/GNU size-poll vehicle pinned at phase design; v2 salvage gate names "the next audit" as
its consumer; env-override escape hatch CONFIRMED (exact var names = phase design; defaults
in spec pins unchanged). REVERSAL: .log.stranded rename DROPPED — R2 premise pins
"stranded-log mechanics byte-identical"; pre-existing Tier-L blind spot for stranded logs
routed to followups instead (rare, crash-only).
## D-r2r4-26 — design converged r2; P2 depth-notes carried to phase design (Mechanical)
Design review CONVERGED round 2 (Claude 0 P1/0 P2/1 P3; codex 0 P1/1 MINOR). Carried P2s for
/drive-design: (a) drive-retro.md's declared mining-input families (~:45,:105) omit finalize
codex artifacts — covering finalize degraded markers needs family-list edits beyond the two
cited marker sites; (b) docs/drive-enforcement.md:51 hardcodes CODEX_UNAVAILABLE inside the
conformance explanation — the edit is a wording update there PLUS the new operator paragraph;
(c) Claude P3: when authoring the tier TABLE, scope the two absolutes ("post-process ONLY on
OK", "helper owns ALL non-success marker writes") to the helper-mediated flow — the
HELPER_ERROR direct-dispatch fallback is the explicit exception.

## D-r2r4-27 — helper name bin/drive-codex.sh (Mechanical)
The `drive-*` prefix matches the repo bin/ family AND self-classifies the helper's own diffs as
security-sensitive (full-effort codex on our reviews); `-codex` names what it supervises. Modes
say the rest. (design-phase1.md §A.0.)

## D-r2r4-28 — exit/token mapping + stdout discipline (Mechanical)
Exit 0=OK · 1=degraded (CODEX_KILLED_TIMEOUT|CODEX_UNAVAILABLE) · 2=HELPER_ERROR (mirrors
drive-conformance.sh 0/1/2). Stdout carries ONLY the outcome token as its LAST line; all
watchdog/diagnostic output goes to stderr + the attempt log. The coordinator branches on the
token ("inspect closed status"); shell rc 126/127 (helper unrunnable) is mapped by the
coordinator to the HELPER_ERROR lane.

## D-r2r4-29 — ONE dispatch call; probe internal (Mechanical; refines D-r2r4-22)
The coordinator makes ONE `--mode dispatch` call per codex leg; dispatch runs the health probe
INTERNALLY (same routine `--mode probe` exposes), so the fenced block stays SHORT and all branchy
logic (probe→outage→retry, sandbox rung, effort) lives in the helper. `--mode probe` stays as a
standalone, marker-free health query (closed mode set + tests + diagnostics), not called
separately in the pipeline.

## D-r2r4-30 — coordinator passes FACTS; helper applies policy (Mechanical)
Flags: `--scope-class` ∈ {design,slice,phase,finalize}, `--security-diff` (bool),
`--confirmation-class` (bool), `--prior-codex <path>`. Helper computes: sandbox rung
(design→read-only; else spike rung); outage gate-enforcement = `--security-diff` OR
scope-class∈{phase,finalize}; effort carve-out (keep full) = `--security-diff` (diff-CONTENT
only, NOT scope type — so a non-sensitive phase/finalize re-audit CAN downgrade). Helper does NO
git; the coordinator (which owns git context) computes `--security-diff` from
`git diff --name-only` vs the security path set.

## D-r2r4-31 — dispatch owns all non-success markers; probe owns none (Mechanical; per D-26(c))
`--mode dispatch` writes every CODEX_KILLED_TIMEOUT / CODEX_UNAVAILABLE marker (tmp+mv atomic,
single-writer-per-outcome); post-process runs ONLY on OK. Standalone `--mode probe` writes NO
marker. The two absolutes are scoped to the helper-mediated flow; the HELPER_ERROR
direct-dispatch fallback is the explicit exception (no helper marker there).

## D-r2r4-32 — watchdog-off keeps the backstop (Taste)
`DRIVE_CODEX_WATCHDOG=off` disables the progress-signature STALL detector only; the per-attempt
3h backstop remains the unconditional bound. Rationale: never allow a truly unbounded codex call;
a fully-unbounded escape hatch is a foot-gun the plan's tail-bounding goal exists to remove.

## D-r2r4-33 — prompt via --prompt-file; text retained in spec (Mechanical)
The codex prompt is delivered to the helper via `--prompt-file`; the spec's fenced block still
CONTAINS the byte-identical prompt text (written to the prompt file) so prompt-substring pins
(e.g. finalize's codex_block slice) do not red. R2 does NOT narrow the prompt (refuted variant).

## D-r2r4-34 — TMPDIR wrapper in each SHORT block, uniform across three (Mechanical; impl. D-7)
`mkdir -p "$RUN_DIR/tmp"; TMPDIR="$RUN_DIR/tmp" bin/drive-codex.sh …` stays in each spec's block
(the helper inherits TMPDIR for codex). The AC13 TMPDIR pin is MIGRATED to drive-review's new
codex-dispatch section and EXTENDED to drive-harden.md + drive-finalize.md.

## D-r2r4-35 — DRIVE_CODEX_CMD test seam (Mechanical)
Env seam `DRIVE_CODEX_CMD` (default `codex`) lets the helper's bash tests inject a simulated
log-writer (streaming/silent/stall/sawtooth), so the suite is dep-independent (cf.
RETENTION_TRASH_CMD).

## D-r2r4-36 — sandbox spike is a REVIEW precondition, not a self-report (Mechanical; impl. D-14/M5)
The coordinator runs the spike (main context) and emits durable
`$RUN_DIR/sandbox-spike-evidence.md` (each command, raw output, trust_level proof, TMPDIR proof,
flush cadence, RUNG SELECTED). The phase-design REVIEW verifies this artifact exists and is
complete (P1 if missing); the implementer sets the helper's rung constants from the recorded
rung. Pass ⇒ read-only everywhere; any fail ⇒ workspace-write for code scopes + read-only for
design/phasedesign.

## D-r2r4-37 — outcome token = stdout-only, channel-separated (Mechanical; round-1 BLOCKING#1)
The helper prints the outcome token to STDOUT ONLY (nothing else on stdout); ALL diagnostics +
watchdog logging go to STDERR + the attempt log. The coordinator captures `> helper-<scope>.out
2> helper-<scope>.err` (never merged `2>&1`) and reads the token from `.out`'s last line; on a
stranded re-dispatch it mv's the stale `.out`/`.err` aside first (same hygiene as the raw log), so
an orphaned prior helper's late append can't be read as this round's token. AC-H15 tests it.

## D-r2r4-38 — HELPER_ERROR is pre-launch-only; post-launch faults → CODEX_UNAVAILABLE(internal) (Mechanical; round-1 BLOCKING#2)
`HELPER_ERROR` (exit 2, no marker) is emitted ONLY for faults strictly BEFORE codex is spawned
(arg parse, `--scope` charset, missing flag, config/rung/effort resolution). From the codex-spawn
step on, NO path emits `HELPER_ERROR`: a post-launch internal fault maps to `CODEX_UNAVAILABLE`
(new cause `internal`), and stall/backstop map to `CODEX_KILLED_TIMEOUT`. This guarantees the
direct-dispatch fallback (rc126/127 or HELPER_ERROR) can never double-dispatch a second codex
against the same scope/logs (codex was never spawned); the coordinator re-validates `--scope`
before the fallback reuses it. AC-H16 tests it.

## D-r2r4-39 — --prior-codex is the site's OWN prior sibling (Mechanical; round-1 MAJOR)
The effort-tier scan reads the call site's OWN immediately-prior codex artifact: drive-harden
Step-1 audit → `codex-harden-<P>.md` (NOT the generic `codex-review-<scope>.md` — that read the
wrong file and silently defaulted to full effort); drive-review phase (incl. harden-regress
guard) → `codex-review-phase<P>.md`; drive-review slice → `codex-review-<id>.md`; drive-finalize →
`codex-review-finalize.md`. Each per-site path is pinned (AC-H12b / §F).

## D-r2r4-40 — pin methodology: bounded slices + section-bound + mutation-verify (Mechanical; round-1 MAJOR + MINOR#1)
Finalize's migration KEEPS the bounded `schema`/`codex_block` slices — never a whole-`## Step 1`
grep (the finalize test's own :319/:325 comments prove the tokens recur in Step 1 ⇒ a widened
assertion goes vacuous). The codex-first position pins (AC1) and the tier-consumer pins (AC8) are
`_section`-scoped to their own subsection (each spec has TWO `BEGIN SUBAGENT SCOPE` markers; the
`CODEX_KILLED_TIMEOUT` token recurs across all four drive.md sites) with a mutation-verify on the
load-bearing ones. Applies spec-pin-mutation-verify / two-conformance-test-suites.

## D-r2r4-41 — ONE authoritative coordinator outcome state-machine (Mechanical; round-2 class-fix)
The whole degradation/fallback surface is ONE class (design §G.0), not per-edge patches. After the
helper returns, the coordinator acts by a single table over (stdout token, exit rc,
`codex_present(marker)`): OK+non-empty-log → post-process; degraded token + marker present →
render tier; degraded token + marker ABSENT → fail-closed STOP (D-43); empty/unrecognized token +
non-zero rc → fail-closed STOP; HELPER_ERROR / shell rc126,127 → BOUNDED direct-dispatch fallback
(D-44). Every §G edge is an instance of one row.

## D-r2r4-42 — killed-latch: a watchdog-killed round stays CODEX_KILLED_TIMEOUT (Mechanical; round-2 BLOCKING#2)
Per-round `round_was_killed` latch set on the FIRST watchdog kill. Once set, the terminal degraded
outcome is `CODEX_KILLED_TIMEOUT` PERIOD — a killed round can NEVER collapse to `CODEX_UNAVAILABLE`.
The probe has two split roles: probe-as-outcome-writer (latch==0, may write the UNAVAILABLE marker
for a genuine never-launched outage) vs probe-as-launch-gate (the §A.4-5 probe-before-retry, latch
==1 — may only SUPPRESS the next attempt; writes NO marker, never switches the outcome family).
Closes the kill→failed-probe→UNAVAILABLE relabel. AC-H18.

## D-r2r4-43 — marker-WRITE failure is FAIL-CLOSED, not a degraded outcome (Mechanical; round-2 MAJOR#2; refines D-38)
If the marker tmp-write/mv ITSELF fails (unwritable path / /dev/full), the helper cannot persist
the marker its token names, so it writes NO fake marker, emits stderr, exits non-zero. The
coordinator honors a degraded token ONLY when `codex_present(marker)` is TRUE; a degraded token +
absent marker ⇒ fail-closed non-decision STOP (the absent marker also blocks the gate by
construction). Carves marker-write OUT of D-38's "internal → CODEX_UNAVAILABLE" (that path assumes
the marker CAN be written). Keeps the closed 4-token stdout set — NO 5th token. AC-H19.

## D-r2r4-44 — BOUNDED direct-dispatch fallback (Taste; round-2 BLOCKING#1) — SUPERSEDED by D-r2r4-45
The round-2 bounded fallback (bg-codex + timed-kill) still spawned a new P1 class in round-3
(kill-mislabel, wrong harden artifact family, missing-input routing, dropped sandbox rung,
single-PID kill). REVERTED wholesale by D-r2r4-45 — there is no direct-dispatch fallback.

## D-r2r4-45 — broken helper ⇒ STOP, not a direct-dispatch fallback (Taste; REVERTS D-r2r4-24-H1 toward D-r2r4-23; round-3 restructure)
A broken `bin/drive-codex.sh` (shell rc 126 not-executable / rc 127 not-found / any HELPER_ERROR
pre-launch usage/charset/missing-flag/missing-prompt/missing-marker/config-resolution fault) is a
DEV/INSTALL error in OUR OWN committed code — NOT an external degradation. codex-the-CLI being
absent or down is the SEPARATE, UNCHANGED accepted degradation the helper's OWN probe handles (→
CODEX_UNAVAILABLE, proceed single-voice). A *correct* direct-dispatch fallback would have to
replicate the entire helper (its own backstop, kill-honesty split, per-call-site raw-log/marker
paths, sandbox rung) — a DRY sink that spawned codex BLOCKING#1/#2/#3 this round. STOP-on-broken-
helper is consistent with how /drive already treats gstack/jq/tool preconditions, is honest, and
closes the whole class. CONCRETELY: deleted §G-1's bounded-fallback machinery + §G-2's fallback
lane (rc126/127 OR any HELPER_ERROR ⇒ coordinator surfaces a NON-DECISION STOP: "bin/drive-codex.sh
broken/misinvoked — <cause>; fix / chmod +x / reinstall, then resume", writes NO codex marker, does
NOT post-process, launches NO codex — codex was never spawned on any of these paths, so no
double-dispatch / no stranded codex); §G.0 rows for rc126/127 + HELPER_ERROR → STOP (first-match-
ordered; row 7 qualified rc∉{126,127}; added an OK-with-empty-log → fail-closed STOP row); §C.1
HELPER_ERROR/rc126,127 row → "coordinator STOP (broken helper); no codex tier rendered"; AC-P1
repurposed to the broken-helper-STOP pin (each of the three specs + a helper test that
HELPER_ERROR/rc126/127 yields no codex marker). RESOLVED BY this restructure: codex BLOCKING#1
(fallback kill-mislabel), #2 (fallback wrong harden artifact family), #3 (HELPER_ERROR routing
missing-input into fallback), Claude MINOR-2 (fallback dropped sandbox rung), Claude NIT-2 (fallback
single-PID vs group kill).

## D-r2r4-46 — killed-latch authoritative in step 4; probe has no exec fallback (Mechanical; round-3 Claude MAJOR + NIT-1; completes D-42)
(a) The `round_was_killed` latch is authoritative in §A.4 STEP 4 too: once a round was watchdog-
killed, a RETRY that self-exits nonzero/empty terminates CODEX_KILLED_TIMEOUT (cause stall), never
CODEX_UNAVAILABLE — closes the step-4 escape D-42 left open (probe route was closed round-2; exec-
fail route now closed). A successful retry ⇒ OK stays the intended latch-override. AC-H18 case (b)
added. (b) The probe is `codex doctor --json` ONLY (self-terminating ~7s); the "bounded codex exec
fallback if doctor absent" is DROPPED (another timed-kill sink — same anti-DRY reason as D-45); a
doctor error → the probe's retry-then-fail-toward-degrade (→ CODEX_UNAVAILABLE, never STOP).
NOTE: D-48 later re-adds a bounded timeout for the doctor probe ITSELF (its own timed-kill, per
D-19) — that is the probe's own bound, NOT a codex-exec fallback (which stays dropped).

## D-r2r4-47 — quarantine the stale codex sibling in the R2 block (Mechanical; round-4 codex BLOCKING#1)
The codex sibling `codex-review-<scope>.md` (harden: `codex-harden-<P>.md`; finalize:
`codex-review-finalize.md`) is one-file-per-scope, overwritten each round, so a prior round's sibling
survives a crash. Without a fix, resume's stranded-adopt (drive.md:641 "any non-empty sibling") pairs
a current crashed round's Claude review with the STALE prior sibling → masquerade / false-CONVERGE.
FIX: each of the three specs' SHORT R2 blocks `mv`s the stale `--marker` sibling aside (`.stranded`)
BEFORE the fresh dispatch, alongside the existing raw-log + helper-.out/.err quarantine, so a crashed
round leaves NO current sibling ⇒ stranded-adopt correctly RE-DISPATCHES. The mv-in-block alone closes
it (no drive.md:641 freshness-note change needed). §G edge-12's "no false adopt" claim corrected;
AC-P2 added.

## D-r2r4-48 — the probe carries its OWN bounded timeout (Mechanical; round-4 codex BLOCKING#2; restores D-19)
Binding design.md:172 / D-19 require the probe carry "its own short timeout"; the round-3 detailed
design dropped it, assuming `codex doctor --json` self-terminates. A hung `doctor` (wedged on the
HTTP-reachability check) would block `--mode dispatch` in step 1 BEFORE codex spawns — neither the
stall detector nor the backstop can fire pre-launch, breaking the tail-bound. FIX: bound the probe
with `PROBE_TIMEOUT_SECS` (helper constant ~10s; bg-`doctor` + timed-`kill`, NOT `timeout(1)` —
absent on macOS) + the existing retry/backoff; a timed-out/errored/absent doctor → fail-toward-degrade
(→ CODEX_UNAVAILABLE, never HELPER_ERROR/STOP). This is the ONE un-watchdogged codex call, so it must
be bounded. AC-H21 pins a hung-probe test.

## D-r2r4-49 — DROP the drive-retro.md mining-family additions (Mechanical; round-4 codex BLOCKING#4; REFUTES D-r2r4-26(a))
Verified against the REAL drive-retro.md: the mining-input list (:48) and the Rule-U carriers (:106)
use the GENERIC `codex-review-<scope>.md` pattern, which ALREADY covers `<scope>=finalize` (→
`codex-review-finalize.md`). So NO family-list extension is needed — D-r2r4-26(a)'s "declared
mining-input families omit finalize codex artifacts" premise was a design-review depth-note never
checked against the file, and is REFUTED. The ONLY drive-retro.md edits are the two TOKEN-sensitive
ones: :99 (first-line degraded count) and :144 (Rule-U E7 stub) add CODEX_KILLED_TIMEOUT. §0
divergence #3, §C.2, and AC9 corrected.

## D-r2r4-50 — doc-coherence corrections (Mechanical; round-4 codex MAJOR + BLOCKING#3 + Claude P2s/P3)
(a) §C.1's tier-table OUTCOME column is TOKEN-ONLY — exactly the 4 stdout tokens; rc126/127 (out-of-
band coordinator state) moved to §G.0, AC3 reconciled (codex MAJOR). (b) Generic contract text
(§A.1 OK row, §G.0 row 3, AC-P1) says "the passed `--marker` path", never the review-family name —
harden's marker is codex-harden-<P>.md, finalize's is codex-review-finalize.md (codex BLOCKING#3).
(c) AC8's :891/:900 pins are per-BULLET anchors (both share the `### Data sources` subsection, so a
subsection-scoped mutation-verify was vacuous — Claude P2). (d) high-level design.md's fallback
references (:8-9, :92-99, :227, :254-256, :323-325) reconciled to the STOP model, citing D-45
superseding D-24-H1 (Claude P2 — OPERATING propagate-everywhere + update-doc-before-implementer).
(e) §G.0 row 7 is a true else/catch-all + the stdout TOKEN is the PRIMARY discriminant, rc columns
descriptive (Claude P3).

## D-r2r4-51 — OK-path completeness: pre-launch marker-parent guard + post-OK completion check (Mechanical; round-5 codex BLOCKING)
Post-quarantine, an unwritable `--marker` or a crashed post-process subagent yields OK + non-empty
raw log + NO current codex artifact — undefined in §G.0, so the round could silently lose the codex
voice. FIX (two halves): (a) the HELPER prevalidates the `--marker` PARENT-dir writability PRE-LAUNCH
(`[ -w "$(dirname "$marker")" ]`) → `HELPER_ERROR` → broken-helper STOP (§A.2, §A.1, AC-H22) — a
best-effort EARLY guard, per the existing pre-launch-only invariant (D-38); it does NOT subsume the
post-launch marker-WRITE fail-closed path (D-43/AC-H19, now narrowed to a writable-parent write-time
failure so AC-H22 does not shadow it). (b) §G.0 row 3 gains a POST-OK completion contract: after OK +
post-process the coordinator REQUIRES a non-empty file at the passed `--marker` path (`codex_present`),
else a fail-closed non-decision STOP (AC-P3). Together they close the OK+non-empty-log+NO-artifact hole.

## D-r2r4-52 — "--scope validated before ANY use" corrected (refuted-as-exploit) (Mechanical; round-5 codex BLOCKING)
§A.2's "validated before ANY use" was overstated: the COORDINATOR composes `helper-<scope>.out`/`.err`,
`codex-prompt-<scope>.txt`, and review-path names from `<scope>` BEFORE the helper's charset check.
NOT reachable on the real path — the coordinator's `<scope>` is a TRUSTED, already-validated phase/
slice id (`docs/drive-enforcement.md:378-383` `--mode state-lint` constrains phase ids to
`^[0-9]+[a-z]?$`, slice ids to `^[0-9]+[a-z]?\.[0-9]+$`), so the exploit is refuted-at-integration —
but the CLAIM was false. FIX: §A.2 reworded to "the HELPER validates its OWN use of `--scope` before
the HELPER composes any `--scope`-derived path; the coordinator's `--scope` is a trusted, already-
validated id"; PLUS a one-line coordinator-side scope-charset belt-and-suspenders check in the §B
block before it composes those temp/log filenames. Light, no over-fix.

## D-r2r4-53 — hung-probe timeout GROUP-kills its own PGID (Mechanical; round-5 codex MAJOR)
The D-48 probe timeout killed only `$dpid`; a forking `doctor --json` shim leaks a child. FIX §A.4-1:
launch the probe in its OWN process group under bash monitor mode (`set -m`) and timeout GROUP-kill
`-$dpgid` (`kill -TERM -$dpgid` grace `kill -KILL -$dpgid`), MIRRORING the dispatch group-kill
(§A.4-5/§A.7); AC-H21 extended to assert NO forked child survives a timed-out probe (a forking shim +
a survivor check).

## D-r2r4-54 — bin/drive-conformance.sh COMMENT honesty; "LOGIC untouched" not "file untouched" (Mechanical; round-5 codex MINOR)
The gate's own COMMENTS (`:26`–`:28` truth-model, `:94`–`:103` `codex_present`) describe the accepted
degraded content as "a real review OR `CODEX_UNAVAILABLE`"; post-change the marker can ALSO be
`CODEX_KILLED_TIMEOUT`, so the prose is stale. FIX: a DOC-ONLY comment update naming BOTH tokens; the
gate LOGIC (`[ -s "$f" ]`, content not inspected) is byte-unchanged (AC-H11 holds). The design claim
narrows from "file UNTOUCHED" to "gate LOGIC untouched"; `bin/drive-conformance.sh` joins slice 1.1's
`owns:` for this comment-only touch (§0 div #4, §C.2, §I, Slices).

## D-r2r4-55 — UNIFORM pin-hardening: close the pin-vacuity CLASS in ONE pass (Mechanical; round-5 Claude MAJOR + codex MAJOR; extends D-40)
The recurring failure: a pin scoped to a whole `## Step`/`###` SECTION passes VACUOUSLY when its token
recurs elsewhere in that section (a tier-table row, an mv-aside quarantine line, a Step-3 marker).
Closed as ONE class, not per-pin: (a) the finalize `codex_block` went vacuous when the round-4
quarantine put both `codex-raw-finalize.log` and `codex-review-finalize.md` mv-lines AHEAD of the
dispatch inside the same fence (§I's "NO test edit needed" was FALSE) — RE-ANCHOR `codex_block` to the
DISPATCH (`_slice_between(step1, r"bin/drive-codex\.sh", r"--marker.*codex-review-finalize\.md",
inclusive)`) + explicit mutation-verify (delete `--raw-log`/`--marker` → reds). (b) the three specs'
inline degradation pins (drive-review `:207`–`:209`, drive-harden `:169`, drive-finalize `:233`)
become BOUNDED SLICES on the `Degradation (do NOT hard-fail):` paragraph — NOT section-scoped (their
sections host/reference the tier table §C.1, whose row carries `CODEX_KILLED_TIMEOUT`). (c) AC3
(tier-table outcome column — bounded to the table rows), AC5 (TMPDIR mkdir→dispatch precedence), AC1
(codex-first position) each restated as a bounded/precedence pin with an explicit mutation-verify.
Binding acceptance stays the token-sweep + green `bin/run-tests.sh` (AC12), never per-line enumeration.

## D-r2r4-56 — stranded-family retention followup breadth (Mechanical; round-5 Claude NIT — followup, not an in-run fix)
The stranded-quarantine mvs now create FOUR `.stranded` families the Tier-L globs do not sweep:
`<raw>.log.stranded`, `helper-<scope>.out.stranded` / `helper-<scope>.err.stranded`, and the AC-P2
`codex-review-<scope>.md.stranded` / `codex-harden-<P>.md.stranded`. EXTEND the existing
`.log.stranded`-only retention followup (`$RUN_DIR/followups.md`, §A.8) to name all four so the
eventual retention audit covers them. A FOLLOWUP, not an in-run fix (broadens the D-25-routed
pre-existing blind spot).

## D-r2r4-57 — §B coordinator scope-check uses the HELPER's permissive charset, not the bare-id grammar (Mechanical; round-6 Claude MAJOR — happy-path regression)
The D-52 belt-and-suspenders check asserted `<scope>` against the BARE phase/slice-id grammar
(`^[0-9]+[a-z]?$` / `^[0-9]+[a-z]?\.[0-9]+$`), but the real `<scope>` tokens are `design`,
`phasedesign1`, `phase1`, `finalize`, and slice `1.2` (drive-review.md:64) — FOUR of five FAIL that
grammar, so as literal bash it would fail-close the codex dispatch for every design/phasedesign/phase/
finalize review (design is the most common leg). FIX: mirror the HELPER's OWN permissive charset
`case "$scope" in *[!A-Za-z0-9._-]*) …STOP… ;; esac` — accepts all five, still rejects
path-traversal/injection chars. The bare-id grammar stays ONLY as the citation for WHY the
coordinator's `<scope>` is already a trusted validated id (drive-enforcement:378-383), not the check
itself. Optional tiny spec pin so the grammar can't silently regress.

## D-r2r4-58 — snapshot the prior codex sibling BEFORE the quarantine (restores effort-tiering) (Mechanical; round-6 codex MAJOR)
The AC-P2 stale-sibling quarantine `mv`s the LIVE per-site codex sibling aside BEFORE dispatch, and
`--prior-codex` named that SAME live sibling — so a confirmation round always saw an ABSENT prior ⇒
silent full-effort ⇒ effort-tiering DEAD in the integrated flow (the failure was SAFE — full-effort
default — but the optimization never fired). FIX: §B step 0 `cp`s the prior sibling to a STABLE
snapshot `$RUN_DIR/tmp/codex-prior-<scope>.md` BEFORE the quarantine `mv`; `--prior-codex` is ALWAYS
the snapshot. Ordering invariant: SNAPSHOT (`cp`) → QUARANTINE (`mv`) → DISPATCH. §B table + §F
updated; AC-P2 gains the ordering + effort-tiering integration guard.

## D-r2r4-59 — helper installs a reaping trap so its death kills the codex PGID (Mechanical + right-sizing Taste deferral; round-6 codex MAJOR)
Only the LIVE helper enforced the backstop; a killed helper orphaned the codex PGID (recovery only
mv-asides logs, never reaps), so the "unconditional backstop" claim was false for a dying helper. FIX:
§A.4-2 installs an `EXIT INT TERM HUP` trap → `kill -TERM/-KILL -$pgid` so a dying helper REAPS its
codex child group; the §A.7 / D-32 "unconditional" claim narrowed to "while the helper lives". HONEST
residual: `kill -9` is uncatchable, so a `-9`'d helper STILL orphans the child — bounded by OS reaping
+ stranded-log recovery + the fresh dispatch's fstat watchdog on the fresh inode; a separate
detached-killer process is DEFERRED to followups (over-engineering for a rare chaos case — right-sizing,
do NOT build now). AC-H23 chaos test: helper `SIGTERM`'d mid-watch ⇒ codex child dies too.

## D-r2r4-60 — AC-P2 is a BOUNDED ordering pin, not `_section`-scoped (Mechanical; round-6 codex MINOR)
AC-P2 was `_section`-scoped and thus vacuous — the section also holds the raw-log/helper `.stranded`
mvs and the marker path in the dispatch + post-process, so deleting ONLY the marker-sibling `mv`
stayed green (the same vacuity class §I eliminates). FIX: bind AC-P2 to the EXACT
snapshot→quarantine→dispatch line ORDER (`cp` index < `mv` index < `bin/drive-codex.sh … --mode
dispatch` index) with mutation-verify; the integration stale-sibling + prior-snapshot test is the
load-bearing guard. Applies the uniform §I discipline to AC-P2.

## D-r2r4-61 — ONE attempt-log op spelling: `helper_error`, not `HELPER_FAILED` (Mechanical; round-6 codex MINOR)
§A.10 enumerated op `helper_error` but the coordinator appended `HELPER_FAILED` (§G-1) ⇒ a non-closed
JSONL enum. FIX: use op `helper_error` EVERYWHERE (the closed enum member); §A.10, §G.0 edge 1, and
AC-H14 reconciled; AC-H14 pins the closed op enum spelling.

## D-r2r4-62 — finalize codex_block start anchor tightened + §D proof-4 poller aligned to evidence (Mechanical; round-6 Claude P2)
(a) §I's `codex_block` start regex was a bare `r"bin/drive-codex\.sh"` — a FIRST-match anchor a future
prose mention of the helper name before the fenced dispatch would re-capture, re-pulling the quarantine
mv lines into the slice and re-vacuating it. TIGHTEN to `r"bin/drive-codex\.sh.*--mode\s+dispatch"` so
it binds the DISPATCH line uniquely regardless of authoring. (b) The coordinator made
`sandbox-spike-evidence.md` proof #4's poller EXACT (a `kill -0 "$CODEX_PID"` pid-loop + `wc -c` +
`sleep 0.5`, cap 480 iters); §D proof #4 is aligned to that exact command so §D and the evidence stay
byte-identical (the evidence artifact is coordinator-owned — NOT modified here).

## D-r2r4-63 — AC8 harden/finalize degradation slices use CLAUSE-level stop anchors (Mechanical; round-6 Claude P3)
drive-review's degradation slice stops on the unique clause `does NOT parse the marker`; harden `:169`
/ finalize `:233` stopped on "the next `##` header" (coarser — future content between the paragraph and
the next header could widen the slice). FIX: clause-level stop anchors for PARITY — harden
`uniform across review and harden`, finalize `inspects existence + non-emptiness only` (each
implementer RETAINS the named clause). Cheap; folds into the uniform §I bounded-slice discipline.

## D-r2r4-64 — post-process writes the marker ATOMICALLY (tmp+mv), no torn file (Mechanical; round-7 codex MAJOR)
Row 3 / AC-P3 required only a NON-empty marker, but a post-process crash mid-write leaves a non-empty
PARTIAL file that `codex_present` (`-s`) accepts → corrupted/lost codex voice. FIX: the post-process
step writes `codex-review-<scope>.md` ATOMICALLY — to `$RUN_DIR/tmp/codex-review-<scope>.md.tmp.$$`
then `mv` into place — so the marker is NEVER torn (the complete new file, or none). `-s` then
genuinely suffices (byte-compat preserved, NO gate change). §B step 4, §G.0 row 3, AC-P3 updated; new
AC-P4 pins the atomic tmp+mv post-process write (bounded-slice pin + a crash-after-tmp-before-mv test).

## D-r2r4-65 — re-dispatch ⇒ FULL effort (conservative) (Mechanical; round-7 codex MAJOR)
On a stranded re-dispatch / fix-round / re-run of the SAME round, the §B step-0 snapshot may capture
the CRASHED CURRENT round's codex file (one file per scope, overwritten each round), not the prior
COMPLETED round (D-16 wants the prior completed round) → a wrong low-effort downgrade. FIX (conservative,
no correctness regression — full effort is the safe default): the coordinator, which already knows it
is re-dispatching (~~a prior `review-<scope>-N.md` for the current round exists, or~~ an open
`inflight-review-<scope>.marker`), OMITS `--confirmation-class` on that path ⇒ FULL effort;
down-tiering fires ONLY on a clean FIRST dispatch whose prior-COMPLETED-round file is unambiguous. §F +
§B updated; new AC-H12c pins "re-dispatch ⇒ full effort". **[REFINED round-8 / D-r2r4-72: the
re-dispatch signal is the PRE-EXISTING OPEN inflight marker ALONE — NOT the existence of prior-round
`review-<scope>-N.md`, which a confirmation re-audit legitimately has; the original phrasing would
have wrongly force-fulled every confirmation round.]**

## D-r2r4-66 — SIGKILL residual is ACCEPTED and EXPLICITLY UNBOUNDED (claim correction) (Mechanical + right-sizing; round-7 codex BLOCKING)
The round-6 "bounded in practice by OS reaping + stranded recovery + fresh watchdog" residual claim
was FALSE: a `kill -9`'d helper cannot run its EXIT/INT/TERM/HUP trap, so it orphans the codex child
PGID, and that orphan is reaped by NONE of those mechanisms (none signal it) — it self-terminates ONLY
when its OWN codex review completes (bounded by codex's run, NOT by the helper backstop). CORRECT the
claim to an ACCEPTED, from-/drive's-view UNBOUNDED residual for the SIGKILL-during-dispatch chaos case;
narrow "the per-attempt backstop is the sole unconditional bound" to "while the helper PROCESS lives".
§A.4-2, §A.7, §G.0 edge 9 corrected. Out-of-process reaper / PGID-persist-for-resume-kill DEFERRED to
followups.md — NOT built (right-sizing for a rare chaos case).

## D-r2r4-67 — masquerade "race closed" NARROWED to single-session; cross-session orphan-marker residual documented (Mechanical + right-sizing; round-7 codex BLOCKING)
Every "race closed" claim (§G.0 edge 10/12, §A.9 single-writer-per-outcome) NARROWED: the
SINGLE-SESSION killed-round / stale-sibling masquerade is closed (helper owns the marker; post-process
ONLY on OK; quarantine-before-dispatch). A CROSS-SESSION orphan-marker race REMAINS — a helper orphaned
by a session crash can, after resume re-dispatches the same scope, write a fresh marker to the shared
`--marker` PATH (path-based `mv`, unlike the fd/inode-based token file, which IS immune) that the new
session may honor. Stated as an ACCEPTED residual bounded by (a) rarity (crash + resume + orphan-alive
+ orphan-degrades + timing align) and (b) ~~the TERMINAL re-review~~. **[CORRECTED round-8 / D-r2r4-70:
bound (b) is FALSE for the FINALIZE/terminal scope — finalize IS terminal, nothing re-reviews it, so
an orphan CAN repopulate `codex-review-finalize.md` and the `-s`-only ship gate honors it. Only
NON-terminal scopes are superseded downstream. See D-r2r4-70 for the honest statement + human decision
to accept/defer.]** Attempt-scoped-marker hardening DEFERRED to followups.md — NOT built now.

## D-r2r4-68 — §I finalize codex_block rationale names the round-6 cp as a third pre-dispatch occurrence (Mechanical; round-7 Claude P3)
§I's re-anchor rationale enumerated only the two round-4 quarantine mv lines as pre-dispatch
occurrences of `codex-review-finalize.md`; add the round-6 `cp …codex-review-finalize.md …codex-prior-
finalize.md` snapshot line as a THIRD pre-dispatch occurrence the START-at-`--mode dispatch` anchor
already excludes. Cosmetic — the anchor was already robust.

## D-r2r4-69 — HONESTY SWEEP: no completeness claim overstates its guarantee (Mechanical; round-7 class-fix — ends the adversarial treadmill)
Swept the whole design for completeness superlatives (`race closed`, `unconditional`, `sole`,
`single-writer`, `never`, `cannot`, `bounded`). NARROWED every chaos/orphan/backstop OVERCLAIM to
exactly what the integrated path guarantees, documenting each rare-chaos edge as an ACCEPTED, BOUNDED,
DEFERRED residual: race-closed → single-session; unconditional backstop → "while the helper process
lives"; single-writer-per-outcome → within one session; the SIGKILL orphan and the cross-session
orphan-marker as accepted unbounded/bounded residuals with their real bounds. KEPT the proven-structural
claims (killed-latch `PERIOD`, bounded-slice "cannot widen", fstat-on-fd "cannot fool the poll",
fd/inode token immunity) — each proven against the real mechanism. The class-fix: an honest design with
documented residuals has NO overclaim left for the adversarial voice to refute.

## D-r2r4-70 — terminal-gate cross-session orphan-marker residual: accept + document + defer (User-Challenge; human decision)
Classification: User-Challenge (resolved by the HUMAN at the round-8 cap-8 non-convergence STOP).
The round-8 codex BLOCKING is REAL, REACHABLE, and SECURITY-RELEVANT: the cross-session orphan-marker
race is NOT bounded by the terminal re-review for the FINALIZE scope (the round-7/8 "bounded by the
terminal re-review" claim was FALSE — finalize IS terminal, nothing downstream re-reviews it). A
session-A orphaned bash helper can overwrite the shared `codex-review-finalize.md` with a DEGRADED
marker AFTER session B re-dispatches, and the terminal ship gate (`codex_present` = `-s`-only, content
NOT parsed) HONORS it — a foreign/degraded codex voice reaching the ship gate. R4 INTRODUCES this
vector (pre-R4 the marker writer was a session-bound subagent that dies with the crash; R4's surviving
bash helper can outlive its session). The honest FIX (attempt-scoped / freshness-token markers, gate-
verified) requires the ship GATE to PARSE the marker, which BREAKS the design's load-bearing "gate
untouched / byte-compatible" premise and is a HARNESS-WIDE change out of scope for R2/R4. **HUMAN
DECISION:** SHIP R2/R4 with this residual DOCUMENTED HONESTLY (no false bound anywhere) and the fix
DEFERRED to a follow-up (followups.md). The design is corrected to state the honest residual (§G.0
edge-12, §A.9, §A.4-2, edge-10); the two round-8 codex MAJORs are fixed IN-DESIGN (D-r2r4-71 watchdog
`kill_confirmed`; D-r2r4-72 re-dispatch⇒full-effort branch-specific pin) and enforced at implement.

## D-r2r4-71 — watchdog killed-classification keys on `kill_confirmed`, not `watchdog_initiated` (Mechanical; round-8 codex MAJOR)
The `watchdog_initiated` flag means "the watchdog DECIDED to fire", not "the signal killed a live
codex" — a codex that self-exits after the watchdog arms but BEFORE the signal lands was mislabeled a
stall-kill. FIX (§A.4-3/5, §A.7): record a SEPARATE `kill_confirmed` bit = the signal actually hit a
STILL-ALIVE target (PGID alive at signal time AND the child's terminal `wait`-status reflects
death-by-OUR-signal 143/137, not a self-exit). Step-5 CODEX_KILLED_TIMEOUT classification branches on
`kill_confirmed`, NOT `watchdog_initiated`; a `kill_confirmed=0` self-exit-race falls through to step-4
(classified by codex's real rc/log). AC-H17 updated to assert a self-exit-just-as-the-watchdog-fires ⇒
`OK`, NOT `CODEX_KILLED_TIMEOUT`.

## D-r2r4-72 — re-dispatch⇒full-effort is a CONDITIONAL BRANCH + branch-specific pin, not prose-only (Mechanical; round-8 codex MAJOR)
The re-dispatch⇒full-effort behavior was pinned only by a section-scoped prose pin while the live §B
dispatch example still showed `[--confirmation-class …]`. FIX (§B, AC-H12c): §B builds
`--confirmation-class`/`--prior-codex` in an explicit CONDITIONAL branch (`CONF=(…)` on a clean first
dispatch guarded ONLY by "no PRE-EXISTING open `inflight-review-<scope>.marker`" — the re-dispatch
signal is the open inflight marker, NOT the existence of prior-round `review-<scope>-N.md`, which a
confirmation re-audit legitimately has [corrects the round-6/7 D-65 imprecision that would have
force-fulled every confirmation round]; `CONF=()` on the re-dispatch else-branch) and the invocation
expands `"${CONF[@]}"`. AC-H12c becomes
TWO branch-specific bounded-slice pins: the re-dispatch branch LACKS `--confirmation-class`; the
clean-first-dispatch branch INCLUDES it. Mutation-verify: make it unconditional → the re-dispatch pin
reds.

## D-r2r4-73 — implement drift: two sanctioned test knobs + probe-timeout flag (Mechanical; slice 1.1 implement)
The helper `bin/drive-codex.sh` adds THREE test-only affordances not enumerated in §A.2/§A.3, each
sanctioned by an AC that requires a DETERMINISTIC test and each documented in the Usage header
(precedent: `--poll-secs` "test knob", `DRIVE_CODEX_CMD` test seam):
(1) `--probe-timeout-secs <N>` — optional flag mirroring `--poll-secs`, so AC-H21's hung-probe test
    bounds the probe in ~0.3s instead of the 10s prod default (PROBE_TIMEOUT_SECS_DEFAULT unchanged);
(2) `DRIVE_CODEX_INJECT_INTERNAL_FAULT=1` — env that forces a POST-launch internal fault, exactly the
    "injected stat-flavor probe failure" AC-H16 calls for, proving it maps to CODEX_UNAVAILABLE
    (cause=internal), never HELPER_ERROR;
(3) AC-H17 (kill_confirmed, D-71) is tested WITHOUT a new knob — the fake TRAPS SIGTERM and exits 0,
    so the watchdog fires (watchdog_initiated=1) but the child's wait-status is 0 (self-exit), giving
    kill_confirmed=0 ⇒ classified OK by step 4. Faithful to D-71 (classification keys on the
    death-by-our-signal wait-status 143/137, not on the watchdog decision). No prod behavior changes;
    all three are inert when unset (default probe timeout 10s; no injection; a real codex TERM-kill
    yields 143 ⇒ kill_confirmed=1 ⇒ CODEX_KILLED_TIMEOUT).

## D-r2r4-74 — finalize r2: probe-mode probe-log dir preflight (Mechanical; completes R5-A class)
Finalize round-2 codex flagged a real (mutation-verified) misclassification: standalone `--mode
probe` writes `codex-probe-<scope>.log` in `dirname --attempt-log`, whose writability was NOT
preflighted (dispatch mode's is, via R5-A on the raw-log parent). A writable attempt-log inside a
read-only dir ⇒ false CODEX_UNAVAILABLE (exit 1) instead of HELPER_ERROR (exit 2). FIXED (commit
8955fe3): probe-mode pre-launch guard on the probe-log dir ⇒ HELPER_ERROR; test PM-RO. Classified
Mechanical (completeness + DRY: R5-A's local-fault→HELPER_ERROR class applied uniformly across
modes). Bounded honestly: `--mode probe` is TEST-ONLY (zero pipeline invocations) and the trigger
needs a read-only $RUN_DIR (coordinator never produces one), so this is defense-in-depth completing
the class, NOT a live-path bug. Claude reviewer had CONVERGED both rounds; the adversarial codex
voice caught it — the load-bearing voice for this security-sensitive helper. Surface at Gate B.

## D-r2r4-75 — finalize r3: OVERRULE codex exact-probe-log-node P1 + imprecision budget (Taste)
Finalize round-3 codex flagged the exact `.probe.log` NODE type as unchecked (vs the raw-log node,
R4-A). OVERRULED at integration with evidence (not a live-path bug): the `.probe.log` is the
HELPER's OWN derived scratch path — never coordinator-created (real dispatch passes only a clean
`$RUN_DIR/codex-raw-<scope>.log`; the sibling is written fresh as a regular file each run); a
pre-existing dir/FIFO there = filesystem tampering, out of threat model. `--mode probe` is test-only
(zero pipeline invocations). The actual coordinator input (raw-log node + parents, both modes) IS
preflighted. Failure mode is safe (degrade to single-voice). Both Claude finalize reviewers CONVERGED
independently. Per OPERATING (gate edge-hardening on evidence the failure occurs; overrule an
adversarial blocking refuted-at-integration WITH evidence). IMPRECISION BUDGET (stated to end the
adversarial per-variant treadmill — rounds r2/r3 each surfaced a more-obscure pathological-fs-node
variant): the "pathological pre-existing node at a helper-owned scratch path" meta-class is
defense-in-depth vs fs tampering, NOT reachable; load-bearing correctness = the reachable behavioral
paths + mutation-verified tests. Further same-class findings pre-overruled → followups. Kept the r2
parent-dir fix (committed, green, harmless class-completion; reverting = churn). Surface at Gate B.


## /drive run mc-vault-blocklist-20260710-092624 — 2026-07-10T05:33:12Z

# Decisions — mc-vault-blocklist-20260710-092624


## PLAN-stage decisions (mc-vault-blocklist)
- Restrict block-list accumulation to empty-valued keys only (header form); keys with a scalar/inline value never absorb following `- ` lines. Additive, backward-compatible. Classification: Taste
- Block-list items reuse inline-list item coercion (strip `- ` marker, then strip quotes) so `- "a"` == `[ "a" ]`. Classification: Taste
- Only `- ` marked lines accumulate; plain colon-less lines stay skipped; a new `key:` line rebinds the active target — preserves the two pinned SKIP tests and inline/scalar behavior. Classification: Mechanical
- Blank/comment lines inside a block are skipped as today and do not terminate an active block. Classification: Taste
- Scope: ONE phase, 2 touch-points (`vault_tasks.py:_parse_frontmatter` + `tests/mc/test_vault_tasks.py`), ~10-15 production SLOC. No change to `load_tasks`/`_parse_scalar`. Classification: Mechanical

## D1 — Right-size the plan-stage reviews (autoplan light + one dual-voice design review)
Classification: Mechanical
The change is a single additive ~15-SLOC edit to one function (`_parse_frontmatter`) + tests.
Running autoplan's full 4-phase per-phase dual-voice gauntlet AND a separate /drive-review
design dual-voice over the same 40-line design.md is review-churn (OPERATING: "review-churn
and over-design are the same failure"), not added correctness signal (identical content).
Decision: autoplan runs as a proportional advisory pass (premise/scope/eng/dx assessed
honestly inline; CEO+DX near-vacuous for an internal parser fix with no product-strategy or
developer-facing surface); the load-bearing adversarial dual-voice (Claude reviewer + codex)
is the `/drive-review design` step, which also produces the SHA-bound plan-gate artifacts
(review-design-N.md + codex-review-design.md). One thorough dual-voice pass, not two.

## D2 — autoplan advisory verdict (proportional)
Classification: Mechanical
- Premise (CEO gate): ACCEPTED — a pre-confirmed, hand-verified TODO P2 bug (block-style YAML
  frontmatter lists silently dropped → mc standup mislabels a blocked task "Ready to start now").
  Right problem; no reframing yields more impact.
- Scope (P1 completeness / P2 boil-lakes): ONE phase, additive, disjoint from the in-flight
  R1/R3 run. In-blast-radius siblings (tags block-lists) folded in. No expansion beyond depends_on/tags.
- Design lens: N/A — no UI scope.
- Eng lens (load-bearing): approach sound — accumulation restricted to empty-valued keys keeps
  the change additive and preserves the two pinned colon-less SKIP tests + inline-list/scalar tests.
  One genuine design choice deferred to detailed design (indentation strictness for continuation
  items). Test coverage plan is adequate (block depends_on/tags, empty header, quoted items,
  standup-level regression). No P1.
- DX lens: mission-control is a dev tool, but THIS diff adds no developer-facing surface (no new
  command/flag/error-message/API) — it is internal parser correctness. DX review N/A with reason.
Verdict: no P1; no User-Challenge; no Taste decision requiring a human. Proceed to dual-voice
design review.

## D3 — Round-1 design-review FINDINGS resolved (P1 orphan-skip + fold in empty-tags fix)
Classification: Mechanical (P1) + Taste/boil-lakes (P2)
Round-1 dual-voice design review: codex 0 P1 / 1 P2, Claude 1 P1 / 1 P2.
- P1 (Claude, MAJOR): design under-specified the orphan `- ` line (list marker with no active
  empty-valued key). An unguarded append would crash all mc (traceback outside load_tasks's
  try/except). RESOLUTION: added a Decision — orphan `- ` lines are skipped; the append is
  guarded on an active empty-valued key (never .append on None/non-list). Design now specifies it.
- P2 (BOTH voices): empty `tags:` yields `""` not `[]` (load_tasks coerces empty depends_on->[] at
  :159 but not tags at :172). RESOLUTION: folded the fix into scope (change :172 to
  `fm.get("tags") or []`) — in blast radius, ~1 line, both voices flagged it, makes
  "empty block header → []" true for both keys. Moved from followups into scope.
- Resolved the sole open question (indentation strictness) → indentation-agnostic continuation.

## D4 — Round-2 design review CONVERGED; non-blocking P2/P3 carried to detailed design
Classification: Mechanical
Round 2 (revised design): codex 0 P1 / 1 P2 / 1 P3; Claude 0 P1 / 3 P3. CONVERGED (no open P1).
Non-blocking items to honor in /drive-design + implement (logged, not blocking Gate A):
- [P2, both voices] PRECEDENCE: the `- ` continuation check MUST run BEFORE the generic
  `":" in line` branch, else a colon-bearing block item (`tags:\n  - "a:b"`, `- k:v`) is
  misparsed as a `key: value` line. Pinned into design Decisions.
- [P3] Skip an empty block item (a bare `- ` with no content) rather than appending "".
- [P3] Consolidate the duplicate `## Out of scope` sections (doc-hygiene; a round-1-edit artifact).
No 3rd review round (P2/P3 incorporation of the reviewers' own suggestions is not a re-convergence
trigger; avoids review-churn per OPERATING).

## D5 — Continue in-session at Seam A (skip the proactive post-Gate-A context-clear handoff)
Classification: Taste (proportionality)
The spec fires a deterministic Seam-A handoff on Gate-A approval so Execute starts in a fresh
session. That is proactive context-hygiene, NOT a correctness gate — durable run state lives in
$RUN_DIR, and the class-A context-pressure rebirth is the safety net if the window fills. For a
~15-SLOC one-file fix in a short, un-pressured session, a context-clear handoff only adds a
manual `/drive <runId>` paste-stall (the latency the efficiency audit flags as the #1 waste).
Decision: continue Execute in this session; if context pressure arises later, the class-A rebirth
handles it. Gate B (the outward-action gate) is unaffected and remains human.

## D6 — Block-item coercion is the inline per-item transform, not `_parse_scalar`
Classification: Mechanical (correctness)
Block items are coerced with `stripped[2:].strip().strip('"').strip("'")` — exactly the
transform inline-list items already use (`_parse_scalar` line 82) — NOT `_parse_scalar(item)`.
`_parse_scalar` bracket-detects, so a wikilink item `[[X]]` would wrongly become the nested
list `["[X]"]` and `- [a,b]` a nested list. Mirroring the inline transform makes `- "a"` ==
`[ "a" ]`, keeps every item a `str`, and sidesteps nested-list ambiguity (out of scope).

## D7 — Empty-item skip tested on the coerced item
Classification: Taste
`if item:` (post quote-strip) skips both a bare `- ` and an explicitly-empty `- ""`, rather
than appending `""`. Matches the PLAN P3 decision (skip empty block items).

## D8 — Only a real `key:` line rebinds `active`; blank/comment/colon-less lines do not
Classification: Taste
`active` is armed only by an empty-valued `key:` line (`parsed == ""`) and disarmed only by a
non-empty `key:` line. Blank, comment, and plain colon-less lines `continue` without touching
`active`, so a block survives interleaved/stray lines. The two pinned SKIP tests are unaffected
(`active` is `None` throughout them).

## D9 — `active` detection uses `parsed == ""` (the `_parse_scalar` result)
Classification: Mechanical
Only the bare-header `key:` form (parses to `""`) becomes an accumulation target. An inline
empty list `tags: []` parses to `[]` (`[] != ""`), so it disarms — inline empty lists never
absorb trailing `- ` lines.

## D10 — List promotion is the crash guard
Classification: Mechanical (correctness)
Before the first append, `if not isinstance(fm.get(active), list): fm[active] = []` promotes
the stored `""` header to a list. Combined with the `active is not None` guard, the append can
never run against a `None`/`str` target — closing the crash-all-mc path (`_parse_frontmatter`
is called outside `load_tasks`'s try/except). Zero-item headers keep the stored `""`, which
`load_tasks` coerces to `[]`.

## D11 — Restrict block-list accumulation to the list-valued keys {depends_on, tags} (closes codex P1)
Classification: Mechanical (correctness) — SUPERSEDES the "generic to any empty-valued key" part of D8/D9.
Phasedesign round-1 dual voice: codex MAJOR (P1), Claude MINOR (P2) — same issue. Arming block
accumulation on ANY empty-valued key means a malformed scalar-key block corrupts or crashes:
- `status:` + `- done` → fm["status"]=["done"] → load_tasks `_scalar(["done"],"todo")` → "done"
  (SILENT corruption; changes bucket()/classify_ready). This is a REGRESSION vs pre-change
  behavior (old: `- done` skipped → status defaults "todo").
- `due:`/`scheduled:` + `- x` → a list-valued `due` → `bucket()` prio-sort `(priority, list)`
  vs `(priority, "9999")` → TypeError comparing list vs str → crash-all-standup.
Verified against the real code (vault_tasks.py `_scalar`:86, load_tasks status/due:167,157,
bucket prio-sort:200). RESOLUTION: introduce module constant `_LIST_KEYS = frozenset(("depends_on",
"tags"))` and arm `active` ONLY when `parsed == "" and key in _LIST_KEYS`. A `- ` under any
scalar key stays a skipped orphan → the scalar key is byte-for-byte unaffected. This makes the
whole change additive: only depends_on/tags gain block-list support. New AC8 guards it (RED vs
arm-on-any-key). Note: adding a future list-valued key needs a one-token `_LIST_KEYS` update —
acceptable given only these two keys are list-valued in the whole schema.

## D12 — Overrule codex phasedesign1 round-2 P1 as pre-existing + out-of-scope (with evidence)
Classification: Mechanical (adversarial-BLOCKING adjudication)
codex round 2 confirmed the round-1 P1 (block-list arming on any empty key) CLOSED by _LIST_KEYS,
but raised a NEW MAJOR (P1): a `due:[x]` inline bracket -> list -> `bucket()` `'str' < 'list'`
TypeError. REPRODUCED against unmodified main: real crash. BUT it is via the pre-existing
`_parse_scalar` inline-bracket path (UNCHANGED by this run), and the `_LIST_KEYS` restriction means
the block-style change adds NO new list-`due` path (`due:`+`- x` -> "" on main AND post-change).
Not introduced, not worsened, orthogonal to block-style list parsing. Overruled as out-of-scope,
routed to followups.md with the repro. Claude reviewer round-2 = CONVERGED (0 P1). Combined verdict:
CONVERGED (the sole codex P1 is a documented, evidenced overrule per OPERATING "refuted-at-integration
-> overrule WITH evidence, never silently drop"). AC8 remains correctly scoped to BLOCK-STYLE scalar
keys; the design's Out-of-scope now names the pre-existing inline-bracket crash explicitly.

## D13 — INCIDENT: implementer subagent ran in the MAIN repo, committed to main; recovered
Classification: Mechanical (process failure + recovery)
The Agent tool does NOT set the subagent's cwd from the prompt — a subagent inherits the
main-repo cwd. The slice-1.1 implementer, told "cwd IS the worktree", edited relative paths
against the MAIN repo and did `git add <files> && git commit` on `main`, creating commit
d97eaeb ("feat(mc): parse block-style YAML lists...") and advancing the user's main branch
(cf43393 -> d97eaeb). The content was correct (mutation-verified, 157 passed), just on the
wrong branch. RECOVERY: (1) `git reset --hard d97eaeb` in the slice worktree -> slice branch
now carries the commit (1 commit past base, both owned files); (2) `git reset --hard cf43393`
on main -> restored to origin/main (d97eaeb never pushed), clean, _LIST_KEYS absent; d97eaeb
stays reachable via the slice branch. Independently re-verified 157 passed on the slice tree.
FIX FORWARD (applies to every worktree-scoped subagent — implement/harden/finalize): the
dispatch MUST instruct the subagent to `cd "<abs-worktree>"` as its FIRST action and CONFIRM
`git rev-parse --abbrev-ref HEAD` == the expected branch BEFORE editing, and use the absolute
worktree path for any Edit/Write. A plain "your cwd is the worktree" sentence is NOT enough.

## D14 — Slice 1.1 review CONVERGED; benign off-schema P2 noted (no action)
Classification: Mechanical
Both voices 0 P1. codex sole P2 (MINOR): a frontmatter line `- foo: bar` with NO active list key
is now SKIPPED (the `- ` branch precedes the colon partition), whereas before it created a junk
key `"- foo"`. This is off-schema garbage (no legitimate frontmatter key starts with `- `); the
new behavior (drop it) is at worst harmless and arguably cleaner. No pinned test covers it. No
action. Claude sole P3 (`tags: ""` explicit-quoted-empty arms accumulation — harmless list-key
semantics) — no action.

## D15 — Harden round 1: fix codex P1 (quoted-empty arming) + add P2 coverage
Classification: Mechanical (correctness)
Harden audit: Claude 0 P1 / 3 P2 (test gaps); codex 1 P1 / 3 P2. codex P1 CONFIRMED by repro:
a QUOTED-empty header `tags: ""` / `depends_on: ''` parses (via _parse_scalar quote-strip) to ""
and ARMS block accumulation, absorbing following `- x` items -> `["x"]`, while base returned ""
and dropped them. Breaks the "empty-header-only / strictly-additive" contract (D9). FIX: arm on
the RAW value being bare (`val.strip() == ""`), not the parsed value (`parsed == ""`), so a
quoted-empty scalar no longer arms (bare `tags:` still does). + a regression test (RED against
current). P2 test gaps added: empty-item-skip false branch; disarm/rebind across two NON-empty
blocks (depends_on->tags) and `tags:[a,b]`+`- c`; CRLF-inside-a-block. Slop (8) persisted to
followups (deferred to finalize), not fixed here.

## D16 — Harden round 2 (final fix round): add last 2 edge-case coverage tests
Classification: Mechanical
Round-2 confirming audit: 0 P1 (both voices confirm the round-1 arming fix correct, logic clean,
suite green). 2 cheap in-blast-radius P2 test gaps remain (the last of the 8 design edge cases):
(1) [Claude] a blank/comment line INSIDE an active block does not disarm (edge case 8, D8);
(2) [codex] a non-empty SCALAR value under a list key (`tags: foo` + `- c`) disarms (same
`val.strip() != ""` branch as the existing inline-list-disarm test, but a distinct input shape).
Per harden Step 2 (cheap + in blast radius → fix), applying both in ONE final fix round. This is
BOUNDED (the 8 edge cases are finite; these are the last). If a round-3 audit still surfaces new
cheap P2s, they route to followups (no treadmill). 2 new slop notes persisted to followups.

## D17 — Finalize CONVERGED (clean confirming round; codex de-slop adjudicated to followups)
Classification: Mechanical (voice-disagreement adjudication)
Finalize dual voice: Claude 0 P1 / 0 applicable-slop / 0 ARCH (CONVERGED); codex 0 P1 / 2 cheap
de-slop P2 / 0 ARCH. Adjudicated the 2 codex de-slop items as NON-applicable with evidence:
(1) stale test docstring is PRE-EXISTING + outside the run-diff LINES → finalize scope-creep gate
routes it to followups (not fixed in-run); (2) the `# pre-fix bug:` regression-provenance comments
are the non-obvious "why" (OPERATING: comments keep the why), Claude assessed keep-worthy — not
slop. Applicable de-slop set empty → CONVERGED (AppliedEdits: no), no fix round, finalizeRound=0.
review-finalize-1.md binds featureBranch tip 8377e03 (== tip, R..tip empty) — the terminal ship
artifact. No ARCH findings → no finalize-todo.md (no TODO promotion at ship).

## Run sonnet4-window-20260710-092355 (2026-07-10) — phantom Sonnet-4 window fix

## D-plan-1 (Mechanical) — right-size the plan review
Given the <30 SLOC mechanical bugfix scope, the load-bearing plan gate is the dual-voice
design review (Claude + codex), which both converged with 0 P1 over 2 rounds. The heavy
gstack `autoplan` (CEO/Design/Eng/DX) pass is disproportionate for a phantom-string bugfix
and was folded into the dual-voice review. Rationale: OPERATING "right-size at design;
review-churn and over-design are the same failure" + principle 3 (pragmatic).
Classification: Mechanical.

## D-p1-1 (Mechanical) — restore 3bf4866's two-rule TEST structure, adapted for D1+D3
Phase-1 design. Restore the per-rule mutation test (windows[0]=1M / windows[1]=200k
indexing), real `Sonnet 4`/`claude-sonnet-4-20250514` in known_200k, the 1M id-forms incl.
the collision id `claude-sonnet-4-6`, the expanded json↔statusline boundary params, and the
layout suite's 1M-rule anti-drift check. TWO forced adaptations from a verbatim 3bf4866 test
restore, both mandated by prior decisions: (a) keep the `case "$MODEL $MODEL_ID"` regex +
id-forms in both case arms (D1 preserves 0a76c89), NOT 3bf4866's `$MODEL`-only case; (b) bare
`Haiku` (D3) means do NOT add bare `"Haiku"` to test_resolve_window_default_is_1m (3bf4866
did — under bare Haiku it now resolves 200k) — instead pin D3 via `Haiku 3.5`/
`claude-3-5-haiku-20241022`→200k in known_200k. Rationale: principles 1 (completeness) + 4
(DRY) + not undoing prior fixes. Classification: Mechanical.

## D-p1-2 (Mechanical) — py docstring needs no wording change
Phase-1 design. bin/rebirth_thresholds.py's docstring already describes the ordered 1M-first
two-rule table (incl. the `Sonnet 4.6` contains `Sonnet 4` note); the HEAD single-rule json
made it stale, and restoring the table re-syncs reality to it. Expected diff: zero; correct
only a genuinely-stale example if one surfaces during implement. Rationale: OPERATING "edit
the source of truth, cut gratuitous churn" + principle 3 (pragmatic). Classification: Mechanical.

## D-p1-3 (Mechanical) — sweep scope: grep-clean + all-five-green, no artificial edits
Phase-1 design. "No window-test suite left un-swept" = every phantom form
(`Sonnet 4.0`/`sonnet-4-0`/`sonnet-4.0` + the prose `4.5/4.0`) gone from bin/ + all five test
files (grep-clean, AC7) AND every one of the five suites green under the restored table (AC8).
test_rebirth_e2e.py and test_drive_stop_hook.py carry no phantom form and their Opus/Haiku
fixtures survive the restore (bare-Haiku keeps `claude-haiku-4`→200k) → verify-clean, NOT
injected with artificial Sonnet-4 assertions (right-size; no gold-plating). Behavioral Sonnet-4
pins land on the window-resolving surfaces (resolver test + statusline bash test); the collision
pin (Sonnet 4.6→1M, Sonnet 4→200k) lands on BOTH surfaces. Rationale: OPERATING "right-size at
design" + principle 3 (pragmatic). Classification: Mechanical.

## D-p1-4 (Mechanical, from design review r1) — load-bearing id pins + structural lock-step
Phase-1 design, closing two P1 review gaps. (a) A "generic display + 1M id → 1M" test is
VACUOUS — the 1M defaultWindow / `*)` arm catches a deleted id-form, so it passes on the buggy
path. Every 1M-id-form pin must instead use the id-beats-a-colliding-200k-display shape (id
`claude-sonnet-4-6` contains the 200k substring `sonnet-4`, so `("Sonnet 4","claude-sonnet-4-6")
→1M` reds if `sonnet-4-6` is dropped from the 1M rule/arm — the only shape that reds on
deletion); and `_statusline_case_window` must be extended from display-only to match
`"$MODEL $MODEL_ID"` so id-forms are exercised on the statusline surface. (b) A STRUCTURAL
compare — json rule→match-token sets == inline-`case` arm→glob-token sets under identical
window assignment — replaces the sampled per-model checks, but its HONEST guarantee is
CROSS-SURFACE parity (one surface drifts, the other doesn't → reds), NOT "any 1M-entry drift
reds": a coordinated both-surface deletion of a NON-colliding 1M id-form (`fable-5`, `opus-4-8`)
is functionally inert (resolves 1M via the default present-or-absent) and stays green — a
non-regression intentionally left unpinned (right-size). Colliding 1M id-forms are pinned by
AC4 (fall to 200k on deletion). AC5/edge-case-#6 wording is scoped to this bound (no "ANY drift
reds" absolute); lock-step covers only the two executable surfaces (docstring human-maintained,
AC9 verify-only). Rationale: OPERATING "a green test can lie — verify it exercises the real
path" + "anchor load-bearing gates on the deterministic source" + right-size (don't pin a
non-regression). Classification: Mechanical.

## D-p1-5 (Mechanical) — 200k id-forms are load-bearing; pin the whole real-200k-id class (AC12)
Slice review r1 (codex, workspace-write). D-p1-4's "coordinated both-surface deletion is inert"
reasoning holds ONLY for 1M id-forms (default is 1M). A 200k id-form deleted from BOTH surfaces
drops its model to the 1M defaultWindow = a REAL regression (this run's target class). Codex
proved it: removing `opus-4-5` from json AND the inline case left all suites green while
`claude-opus-4-5` misresolved 1M (90% not 454%). Fix the CLASS in one round: a per-model
behavioral pin for every real 200k model id (`claude-sonnet-4-20250514`, `claude-sonnet-4-5`,
`claude-opus-4-5`, `claude-opus-4-1`, `claude-3-5-haiku-20241022`/`claude-haiku-4`/`claude-haiku-4-5`)
asserting →200k on BOTH resolver and statusline, mutation-verified to red on a token drop (AC12).
Imprecision budget: 1M id-forms stay unpinned (inert); non-existent future ids out of scope
(fail-safe). Rationale: OPERATING "a green test can lie — verify it exercises the real path" +
fix the whole input-class in one round (avoid the per-token treadmill). Classification: Mechanical.

## D-p1-6 (Mechanical) — harden P1/P2 routed to followups (scope gate), phase HARDENED
Harden phase 1 (codex). Codex flagged a P1 (resolve_window non-string-model robustness,
bin/rebirth_thresholds.py:61) and a P2 (display-only `Opus 4.1` unpinned). BOTH reproduced.
The P1 is PRE-EXISTING and OUT-OF-DIFF (bin/rebirth_thresholds.py unchanged this phase; last
touched 831e998) and contingent on non-production input (message.model is always a string) →
routed to followups F3, NOT fixed (harden scope-creep HARD GATE forbids editing unrelated
out-of-diff working code that is not the root cause of a phase P1; and a defensive non-string
bolt-on is a deliberate design call, not a harden fix — net-negative risk). The P2 `Opus 4.1`
display token is redundant with the pinned `opus-4-1` id-form for real sessions (same class as
sonnet-4-5) → followups F4, intentional per D-p1-5. Actionable phase-surface fix set EMPTY →
HARDENED (AppliedEdits: no; hardenRound stays 0). Slop persisted to followups for finalize.
Rationale: OPERATING harden scope discipline + right-size + refuted/scope-routed WITH evidence,
never silently dropped. Classification: Mechanical.

## D-finalize-1 (Mechanical) — finalize diff scope = frozen baseSha, not moved `main`
`main` advanced e8ed271→d2d717f after branch-cut (docs/todo reconcile commits touching
`.harness/followups.md` + `TODO.md`). `git diff main..featureBranch` therefore injects
ledger-divergence noise (the branch looks to "revert" main's newer ledger edits). The
honest whole-run diff is `baseSha(e8ed271)..featureBranch` — the 6 files the run actually
changed (bin/rebirth-thresholds.json, bin/statusline.sh, +4 test files). Finalize audits
that scope. The followups/TODO divergence is a trivial append-only-ledger conflict resolved
at ship (materialize real merge into main, suite on merged tree, flag at Gate B) —
[[diverged-base-ship-verify-merged-tree]].
## Run r1r3-latency-20260710-081223 (2026-07-10) — R1 auto-resume rebirth seams + R3 push-notify decision-bearing parks + observability
# Decisions — r1r3-latency (R1 auto-resume + R3 notify/observability)
(D-numbers prefixed `D-r1r3-N`; inline `DN` references are run-local to this block.)

## D-r1r3-1 — R1 atomic-claim edits the resume consumer, not only I1 step 6 (Mechanical; completeness)
TODO's "edit I1 step 6 ONLY" governs the fenced-block preservation + outgoing trigger-scheduling; the
atomic mv-rename claim is inherently INCOMING-resume behavior, so R1 also edits the resume
marker-consume bullet (drive.md L80-85) and the Durable-checkpoint single-use rule (L624-626), both
currently "validate then DELETE". Minimal coherent edit set; fenced block stays byte-for-byte.

## D-r1r3-2 — fresh-session trigger specified by CAPABILITY, feature-detected (Mechanical; C12 capability-over-id)
The trigger is described as "a primitive that spawns a FRESH session firing /drive <runId>", never a
hardcoded tool id — survives rename/replacement of the primitive, degrades to the fenced-block
fallback where absent. CronCreate (same-session/in-memory) explicitly does NOT qualify.

## D-r1r3-3 — R3 transport is a config-driven bin/drive-notify.sh with a no-op fail-open default (Mechanical)
A backgrounded, timeout-bounded shell send can never wedge the pause turn or the stop-hook
allow-stop-when-waiting contract; a harness tool-call would not background and would not exist for
non-Claude consumers. Unset config → exit 0 (inert default; can never break a run).

## D-r1r3-4 — sub-events are write-only forward-only event-log lines, one authoritative rule (Mechanical)
subagent-started/codex-started/suite-run-started/finished/fix-applied/idle_detected(>30min), date -u,
JSON-safe via jq, APPEND-only. Never a new PARSED surface — the NEVER-parse-event-log.jsonl invariant
holds.

## D-r1r3-5 — Fable-5 entry-presence proven by a MUTATION test (Mechanical; C2 protocol)
Fable pins are pre-fix GREEN (fallthrough already yields 1M), so a naive golden/resolve pin passes
without the explicit entry. Entry-presence power comes from a mutation test (mutate the Fable rule →
assert resolve_window('Fable 5') changes), per decisions.md:2900/3001-3006.

## D-r1r3-6 — coordinator authored the high-level design.md directly (Mechanical; avoid lossy re-derivation)
Rather than re-dispatch a planner subagent to re-derive grounding already produced by the 4-reader
surface-map workflow + full spec-set reads, the coordinator authored design.md from that complete
context; the dual-voice design review supplies the required independent fresh-context check.

## D-r1r3-7 — folded 2 post-convergence design P2s (reviewer-requested clarifications; no re-review) (Mechanical)
Design review CONVERGED at round 3 (0 P1 both voices). Two logged P2s were folded in as final polish
BEFORE Gate A — they add reviewer-requested binding notes with NO approach change, so they cannot
reopen a P1: (a) codex P2 — /harvest committed to Phase 1 at the single minimal read-only surface (drop
the fuzzy maybe-defer); (b) reviewer P2 — the winner's re-prove must re-source `markerValid`/proof from
the CLAIM-TARGET file R1 renamed the marker to, else the legitimate winner false-STOPs on every
auto-resume (fail-safe, never double-drive, but would defeat R1's feature). Both are binding notes for
/drive-design, not new machinery.

---

## Phase 1 detailed-design decisions (D8–D26; /drive-design, see design-phase1.md)

## D-r1r3-8 — the atomic CLAIM folds into bodies[0]'s first action; resume-bullet index map UNCHANGED (Mechanical)
REVISED (round-1 review): the sessionId-rebind is HARD-PINNED at resume-bullet index 0
(test_rebirth_handshake.py:307/709/737, test_checkpoint_contract.py:1174/1189 whose comment guards "a NEW
bullet inserted ahead of the rebind breaks the pin"). Constraint (i) needs the claim BEFORE the
`state.sessionId` write, which lives in bodies[0] — so the claim's ONLY pin-legal home is bodies[0]'s FIRST
sub-step, before the `freshSessionResume` capture. No new bullet, no relabel, no index shift: rebind[0]/
marker[1]/rebirth[2] and their labels stay; only BODY PROSE changes (bodies[1] rewords DELETE→validate-
from-claim-target; bodies[2] consults markerValid from the claim-target). (Supersedes round-1 D8's "claim
as new bullet [0]", which would red all the index/label pins.)

## D-r1r3-9 — loser detection = glob-by-tip + content; liveness ADVISORY-ONLY, never an authorization (Taste)
REVISED (round-2 codex: 1 BLOCKING + 1 MAJOR, both REAL). The loser detects a real winner by GLOBBING
`checkpoint-claimed-*-<tip>.marker` + content-validating (`proof.tip==tip`) — NOT by reconstructing the
name from `state.sessionId` (round-2 BLOCKING: that misses the winner's sid-named target in the
claimed-but-not-yet-rebound skew → clobber). On a content-valid claim-target the loser writes NOTHING (no
state.sessionId, no waiting) and EXITS with an advisory note — UNIFORMLY safe for LIVE and DEAD winners:
drive-stop-hook.py:193 `_allow()`s a session owning no run, so writing nothing never double-drives; a dead
winner is recovered manually (mv the claim-target back to checkpoint-complete.marker + re-paste). Liveness
is an ADVISORY hint in the note only — a wrong hint is harmless because the loser writes nothing. NO
procStart cross-check (session `procStart` "Wed Jul 8 02:59:31 2026" vs `ps -o lstart` "Wed Jul 8 10:59:31
2026" for the SAME live pid differ by 8h/TZ → hardened liveness would misfire every race), NO
fail-closed-vs-silent branch, NO wall clock. This DISSOLVES codex's liveness MAJOR (no weak-signal
authorization to exploit). Supersedes round-1's 10-min staleness and round-2's name-from-state.sessionId +
procStart-hardened liveness.

## D-r1r3-10 — outgoing trigger = fractional I1 step 5.7, not a step-6 rewrite (Mechanical; pin-safety)
`_I1_STEP_RE` enumerates only INTEGER steps; AC1 pins marker=step4/waiting=step5/adjacent + len>=6.
Inserting the trigger as fractional step 5.7 (after 5.5 decant, before 6 present) preserves all integer
indices; step 6 + the fenced ↻ REBIRTH block stay byte-for-byte. Divergence from design.md's literal
"within step 6" framing, resolved against the real pins.

## D-r1r3-11 — Fable-5 rule APPENDED (windows[0]==200k denylist preserved) (Mechanical; minimal churn)
test_mutating_json_changes_resolution hardcodes windows[0]==200k denylist; inserting Fable at windows[0]
reds it. "Fable 5" collides with no 200k substring so 1M-first-for-collisions doesn't require Fable-first
→ append. The Fable mutation test (D5) finds the rule by CONTENT, not index.

## D-r1r3-12 — drive-notify.sh transport = $DRIVE_NOTIFY_CMD, message on STDIN, always exit 0 (Mechanical)
Injection-safe (message via STDIN, never shell-interpolated; command is the operator's trusted config);
backgrounded + timeout-bounded; ALWAYS exit 0 on every path; never writes state.json; unset → pure no-op.

## D-r1r3-13 — dedup slug = sanitize+truncate + sha256[:12] of raw waiting (Mechanical)
`notified-<slug>-<tipSha>.marker`, slug = ([^A-Za-z0-9._-]→`_`, trunc 40) + `-` + sha256[:12] of the RAW
waiting (collision-resistant for spaces/`/`). shasum absent → skip dedup, bias-to-SEND (dup ping benign,
a miss is worse).

## D-r1r3-14 — the coordinator builds the notify MESSAGE per waiting-kind (Mechanical)
gateB message = the gate QUESTION + "reply 'approve' after reviewing the diff", NEVER a `/drive <runId>`
line; drive-notify.sh is content-agnostic transport. Notify fires only for waiting∈{gateA,gateB,stop:,ask:},
never rebirth.

## D-r1r3-15 — ONE authoritative sub-event rule; idle_detected at the clear-after-record step (Mechanical)
Six schemas (subagent/codex/suite-run-started/finished/fix-applied/idle_detected), date -u, jq-built,
APPEND-only, WRITE-ONLY (NEVER-parse invariant holds). idle_detected hangs off the single clear-after-record
step (uniform across all inflight kinds); startedAt absent/unparseable → no emit (fail-open).

## D-r1r3-16 — /harvest minimal surface committed to Phase 1, no escalation (Mechanical)
Read-only `drive_waiting_runs()` glob of harness-runs/*/state.json + a conditional render section listing
waiting∈{gateA,gateB,stop:,ask:} (excludes rebirth); NO overlay/join/mc-hook change. Minimal surface is
trivial → no scope escalation to followups.

## D-r1r3-17 — ONE slice (Taste)
The Fable-hygiene disjoint-file seam is clean but ~3 SLOC — right-sizing (marginal parallelism < worktree
+review overhead) + a single all-suite token-sweep favour one slice; drive-notify.sh↔drive.md notify hook
is a produced-then-consumed contract that must be one slice regardless.

## D-r1r3-18 — claim-target keyed on CID + single-use lifecycle (Mechanical; REVISED round-3)
Claim-target = `checkpoint-claimed-<claimerSid>-<CID>.marker` (CID = hash of the marker content, D23/D24).
DETECTION globs the CURRENT `state.pendingCID` + content (`proof.tip==tip`), so a stale older-CID same-tip
leftover is IGNORED (fixes the round-3 stale-same-tip poison). The sid in the name is for the ADVISORY hint
+ manual recovery only. Winner re-sources markerValid from it, removes it on completion, and consumes its
scheduled-marker. Supersedes round-2's tip-keyed claim-target.

## D-r1r3-19 — step-5.7 per-CID dedup marker; unsound failure-detection DROPPED (Taste; REVISED round-3)
The scheduled-marker `auto-resume-scheduled-<CID>.marker` is a pure per-CID create-only dedup (at most one
trigger per checkpoint across leave-pending re-presentations), consumed by a successful resume. The round-2
"marker-exists ⇒ prior auto-resume failed → failure-notify + suppress" inference is DROPPED (unsound — the
marker existing may just mean the trigger has not fired yet); the CID-conditional resume no-op (D25) gives
idempotency instead. Repeated-failure-notify + exponential backoff + crashed-winner auto-reclaim DESCOPED to
followups.md F1.

## D-r1r3-20 — winner/loser/absent sub-cases + bodies[0] claim sub-steps are PROSE, not `- **` bullets (Mechanical; FIX-1)
The handshake bold-span regex `^[ \t]+- \*\*(.+?)\*\*` enumerates `- **` at ANY indent — a nested bold
sub-bullet inside bodies[0] would land ahead of bodies[1] and shatter the index map. So the claim sub-steps
and the winner/loser/absent cases render as prose / non-`- **` lines; only the three top-level bullets
bold-enumerate.

## D-r1r3-21 — /harvest + R3 notify filter key on the authoritative waiting grammar (Mechanical; FIX-5/FIX-D)
Quote the ANCHORED `^(gateA|gateB|stop:.+|ask:.+)$` verbatim (excluding rebirth), mirroring
drive-conformance.sh:1164 — EXACT for gateA/gateB, PREFIX for stop:/ask:; the anchors block the `gateAfoo`
false-match (never a loose unanchored "startswith").

## D-r1r3-22 — the resume WRITE-DISCIPLINE INVARIANT, pinned as drive.md prose (Mechanical; REVISED round-3 — CID-scoped)
ONE invariant closes the whole concurrency-correctness class (skew clobber, double-drive, stale-same-tip
poison, late-trigger clobber): only the rename-WINNER, or the SOLE resumer when NO content-valid claim-target
for the CURRENT checkpoint (`state.pendingCID`) exists AND `waiting != "rebirth"`, writes state.json; a
session that LOST the rename to a current-CID claim-target writes NOTHING and exits; an AUTO-TRIGGER NEVER
takes the sole-resumer path (D25). Detection is glob-by-CID + `proof.tip==tip`. Pinned as a drive.md PROSE
clause (AC13), not only exercised by the AC4 test.

## D-r1r3-23 — CID = the per-handoff identity, threaded EVERYWHERE (Mechanical; REVISED round-3)
`drive/<runId>` moves ONLY at the step-6 advance (drive.md:620-621), so the tip is NOT a unique handoff
identity (Seam A + state-only handoffs recur at the same tip). CID = hash of the checkpoint-complete.marker
CONTENT (per-handoff `at` + proof), distinct across handoffs even at the same tip. CID keys the claim-target
(D18), the scheduled-marker (D19), `state.pendingCID` (D24), and the auto-trigger payload (D25) — ONE
identity everywhere.

## D-r1r3-24 — pendingCID is a TOLERATED-EXTRA routing field, documented in drive.md ONLY (Mechanical; REVISED round-4 / FIX-4)
`state.pendingCID` (set by I1 in the SAME write as `waiting="rebirth"`; cleared by the resume with
`waiting=null`) is a resume-ROUTING HINT — NOT a checkpoint-proof input (the fail-closed dual-mode re-prove
stays the CONTINUE authority; `--mode checkpoint` never reads state.json). It is a TOLERATED-EXTRA field:
add it to the drive.md state.json template (default null) + the resume prose; do NOT add it to CORE_KEYS /
state-lint-required (would red legacy runs), do NOT add it to CLAUDE.md (unowned; carries subset/inventory
pins — test_claude_md_imports, test_drive_codex_contract:455-464). test_state_json_shape.py:91 (core-keys-
PRESENT subset) stays GREEN UNMODIFIED. The loser matches `checkpoint-claimed-*-<state.pendingCID>.marker`
(the CURRENT CID), so an older-CID same-tip leftover is IGNORED and a forged rebirth (no pendingCID) falls
closed to `stop:checkpoint-unprovable` exactly as today.

## D-r1r3-25 — capability predicate adds clause (c) HOST-LOCAL; CID-conditional no-op, NO liveness (Mechanical; REVISED round-4 / FIX-2)
A qualifying fresh-session trigger capability must satisfy ALL of: (a) spawns a NEW session firing `/drive
<runId>`; (b) can carry a resume payload `CID_N` (env/arg); (c) is HOST-LOCAL — the spawned session reaches
this run's local `$RUN_DIR` (`~/.claude/harness-runs/<runId>/state.json`). Run state is local/non-portable
and drive.md only takes the resume branch when the local state.json exists, so a cloud/remote trigger
(satisfies a+b, not c) would no-op or misengage a wrong-host FRESH run → does NOT qualify → degrade to
fenced-block-only. The auto-trigger carries `CID_N` and resumes ONLY IF `state.pendingCID == CID_N` AND
`waiting == "rebirth"`; otherwise it EXITS as a clean no-op (NO state.json, never sole-resumer) — idempotent,
NO liveness. A human paste (no CID_N) is the general resume, unaffected. (Round-3's CID-conditional gate,
plus round-4's host-local clause.)

## D-r1r3-26 — the marker-claim is REBIRTH-GATED; closes the I1 step-4→step-5 crash window (Mechanical; round-4 codex BLOCKING / FIX-1)
I1 writes checkpoint-complete.marker (step 4) BEFORE `pendingCID`+`waiting="rebirth"` (step 5, one write); a
crash between leaves marker-present + `waiting != "rebirth"` + no pendingCID, and an UNGATED claim then fell
into a sole-resumer clobber. FIX: the atomic claim + loser-disambiguation in bodies[0] runs ONLY IF
`waiting == "rebirth"`. A non-rebirth resume SKIPS the claim entirely (a leftover marker is inert,
overwritten by the next checkpoint) → normal reconcile, no clobber. The marker-claim is thus a REBIRTH-resume
mechanism; a non-rebirth resume never claims. A real rebirth resume always has pendingCID (I1 atomic), so the
"pendingCID absent" branch is reachable only for a forged rebirth → STOP. Pins preserved: the rebind
sub-steps + `freshSessionResume`-before-`state.sessionId` still run for every resume (the claim is a
conditional FIRST sub-step of bodies[0]).

## Post-convergence P2 folds (both voices CONVERGED 0 P1; binding-note clarifications, no approach change — D7 precedent)
Design LOCKED at round-4 convergence. Three reviewer-requested clarifications folded (no re-review): (1)
§1.2's illustrative bodies[0] prose flattened to non-`- **` forms so the design is self-consistent with the
§0.3/AC1 rule it mandates for shipped drive.md. (2) BOTH-suite honesty (guards the two-conformance-suites
trap): the Fable-5 statusline pin also lives in the BASH suite `test/statusline-window.test.sh` (:54
`golden_for`) — AC10 + §6 now add a "Fable 5" bash golden case (owned-files updated), so the §1.9 arm change
does not red the bash suite while pytest is green. (3) AC14 gains an EXECUTABLE state-lint assertion (bash
`test/drive-conformance.test.sh` § state-lint) proving a pendingCID-bearing state.json is `clean` — the
tolerated-extra is test-backed, not prose-only. No D-number changes (D8–D26 stand).

---

## Phase 1 slice-1.1 implementer decisions (D27–D29; /drive-implement)

## D-r1r3-27 — drive-notify.sh arg-parse hardened against a dangling final flag (Mechanical; AC6 fail-open)
The design's `while … case … shift 2` loops forever on a dangling final flag (`--waiting` with no
value): bash `shift 2` fails silently when <2 args remain, so `$#` never decrements. Fixed with
`shift 2 || shift` (drop the flag, always make progress). Required by AC6 ("bad args → exit 0");
surfaced by the test, not the static spec.

## D-r1r3-28 — AC14 bash state-lint case backed by a new mk_state_lint `pendingcid` fixture (Mechanical; test-support)
The AC14 executable state-lint case (`test/drive-conformance.test.sh`, an owned file) needs a
pendingCID-bearing state.json fixture. All `mk_state_lint` variants live in `test/fixtures/mkfixture.sh`
(the shared fixture generator the bash suite sources), so the `pendingcid` variant was added there —
following the established pattern rather than inlining a fixture. mkfixture.sh is not in the literal
owned-files list, but it is test-support for an owned bash test; no parallel slice, so no ownership
conflict. FLAGGED in the STATUS report.

## D-r1r3-29 — harvest drive-waits section also renders on the no-live-sessions path (Mechanical; strictly-more-correct)
The design says "append AFTER the unbound block" (the has-live path). A /drive run parked at a gate
whose Claude session has already EXITED would then be invisible in a no-live harvest. `_append_drive_waits`
is called on BOTH the no-live early-return and the normal path so a parked run always surfaces — a
minor correctness enhancement with no downside (empty/None → nothing, per the design).

## D-r1r3-30 — slice-1.1 round-1 review fixes (3 P1s from codex-review-1.1.md) (Mechanical; security + test-rigor)
(a) BLOCKING drive-notify.sh --tip path-traversal: sanitize --tip the same way as the slug
([^A-Za-z0-9._-]→'_', trunc 64) so the marker ALWAYS stays directly inside $RUN_DIR; a 40-hex SHA
passes through unchanged. Faithful repro test (pre-created intermediate dir) reds against the
unsanitized code, green after. (b) MAJOR vacuous AC4(d)/AC5 pins: factored the rebirth gate+claim
into ONE shared faithful mirror `_resume_rebirth` (reads waiting/pendingCID from disk, applies the
D26 gate internally) + `_auto_trigger_proceeds`; AC4(d)/AC5 + the other rebirth-gate tests drive
THROUGH it, not an inline gate (guard-drop mutation reds both — verified). (c) MAJOR CID not
content-bound: `_resume_claim` now DERIVES the CID from the marker content (`_cid(marker)`) and
asserts it == pending_cid (binds the routing hint to content, D23); AC15 uses `_cid()` on real
files + verifies the loser glob ignores a same-tip DIFFERENT-CID target + a new test rejects a
forged/stale pendingCID. Full bin/run-tests.sh green.

## D-r1r3-31 — phase-1 harden fix round 1 (union of Claude + codex audits; 4 fixes, all mutation-verified) (Mechanical/Taste; test-rigor + a documented deviation)
(1) drive-notify.sh dedup TOCTOU → chose the ATOMIC O_EXCL `noclobber` claim
`( set -o noclobber; : > "$MARKER" ) 2>/dev/null || exit 0` over `mkdir` because it keeps the marker a
FILE — zero disruption to the existing marker-glob assertions — while giving the same create-only atomic
semantics (preserves ALWAYS-exit-0 + NEVER-writes-state.json + --tip sanitization).
(2) AC8 concurrency test — DEVIATION worth flagging: the SHIPPED narrow-window TOCTOU does NOT reliably
red black-box (empirically N=80 racers on the unmodified pre-fix → exactly 1 send; process-startup +
~8 pre-marker forks de-sync racers past the sub-ms mv window — the audit itself only reproduced it with
an injected sleep). A test that can't red the bug is vacuous, so the concurrency test is a DETERMINISTIC
mutation guard instead: real atomic script → exactly-1 send; a racy variant built from the real script
(check-then-create + widened `sleep 0.3` window) → many sends under the SAME N-racer harness; plus an
anchor-presence assertion that reds if the atomic claim is ever reverted. This proves the harness detects
double-sends AND that atomicity is the load-bearing difference (mutation-verified: reverting the fix reds
the test).
(3) harvest.py non-object state.json → `isinstance(st, dict)` guard mirroring drive-stop-hook.py.
(4) Fable-5 statusline FALLBACK arm mutation cover — the arm is REDUNDANT with the 1M `*)` default, so a
pure DELETE cannot red a PCT pin (Fable stays 1M via the default). Mutation-covered via a value-mutation
guard (arm window→250000 → Fable PCT 363≠90); this reds when the arm is removed (the sed target vanishes).
The redundant arm is intentional documentation (guards a future default change) — NOT removed; flagged as a
possible de-slop candidate for /drive-finalize to weigh.

## D-r1r3-32 — finalize round-1: winner-path CID==pendingCID verification closes a spec/mirror divergence (Mechanical; completeness/security — codex-only P1, integration-confirmed)
Codex (adversarial finalize voice) flagged, and reproduction against the artifacts CONFIRMED, that the
drive.md rebirth WINNER-path (§ Run setup & resume, bodies[0] case (b)) computes `CID` from the
checkpoint-complete.marker CONTENT and claims to `checkpoint-claimed-<sid>-<CID>.marker` WITHOUT verifying
`CID == state.pendingCID`, while the LOSER globs `checkpoint-claimed-*-<state.pendingCID>.marker`. The
e2e mirror `_resume_claim` (tests/contracts/test_rebirth_e2e.py:122-126) ASSERTS `content_cid ==
pending_cid` — so the executable mirror DEFENDS the invariant but the shipped drive.md PROSE (what the
coordinator follows) does NOT mandate it: a spec/mirror divergence (green test, unguarded real path). The
auto-trigger parent gate (drive.md:57 `pendingCID == CID_N`) does NOT cover it — human-paste rebirth resumes
carry no CID_N and bypass that gate entirely, so the winner has NO content-CID guard. If a stale/forged/
wrong-handoff marker (CID(marker) != pendingCID) is present with waiting==rebirth, the winner's claim-target
is keyed on the wrong CID → the loser's pendingCID-keyed glob MISSES it → both drive (the D-4269 double-drive
class R1 exists to close). The Claude reviewer returned CONVERGED (it reasoned about the atomic-rename window,
not the claim-key vs loser-glob-key divergence); OVERRULED with evidence per the adversarial-is-load-bearing
rule for gate code. FIX (finalize round 1): (1) drive.md bodies[0] case (b) — before the os.replace, VERIFY
`CID == state.pendingCID`; on MISMATCH do NOT claim → fall through to the loser/fail-closed re-prove
(stop:checkpoint-unprovable), so the winner only ever claims a marker whose content-CID == pendingCID (loser
glob always matches). Written as PROSE (no nested `- **`, os.replace still precedes `freshSessionResume =` —
AC1 index-map invariant preserved). (2) a matching prose-pin in test_rebirth_handshake.py (mutation-verified:
deleting the clause reds it). Folded cheap in-scope: a shasum-absent test for bin/drive-notify.sh (R3
fail-open/portability, both voices P2) + audit-confirmed-present deferred-slop comment/docstring cleanups.


## Run codexstdin-20260711-100912 (2026-07-11) — drive-codex.sh stdin hang + false-OK-on-empty-review
## D1 (Mechanical) — FIX 1 redirects BOTH codex spawn launches from /dev/null
`codex exec` (dispatch, ~L448) AND `codex doctor` (probe, ~L407) get `< /dev/null`. Uniform;
prevents the inherited-open-stdin hang. Both voices confirm no fd-9/PGID/watchdog interaction.

## D2 (Taste) — FIX 2 matcher is a FULL-LINE anchored exact-banner match, not a substring strip
`_log_banner_only`: banner-only iff every CR/space-normalized non-blank line == exactly
`Reading additional input from stdin...`. Rejects the degenerate log without false-positiving a
real review line that quotes the banner. Banner pinned to live-captured codex v0.142.5 bytes.
Rationale: prefer structural/precise over a byte-floor/turn-marker heuristic that would red the 183 fakes.

## D3 (Taste) — banner-only routes to a DISTINCT ATTEMPT_RESULT=degenerate-log, not exec-failed
rc was 0; labeling it exec-failed misleads debugging. Distinct cause `degenerate-log` →
emit_degraded CODEX_UNAVAILABLE (same fail-closed token family + marker). Honest diagnostics; low surface.

## D4 (Mechanical, boil-lakes) — FIX 3: guard the --prior-codex down-tier scan with the same helper
Line ~610: add `&& ! _log_banner_only "$PRIOR_CODEX"`. A degenerate prior fails toward FULL effort
(conservative). In blast radius (same false-clean class, same helper), trivial effort. Both design
voices flagged it (codex MAJOR / Claude P3). `_log_nonempty` itself left untouched for its other callers.

## D5 (Mechanical) — regression tests split by surface, each mutation-verified RED
FIX-1 asserts RAW-LOG CONTENT (fd0-sensitive fake); FIX-2 asserts the token (always-banner fake);
plus a banner-precision (quoted-banner→OK) and a FIX-3 (no down-tier) test. Token-only FIX-1 test is vacuous.

## D6 (User-Challenge-class, resolved by evidence) — OVERRULE codex r3 "banner+visible-residue" BLOCKING
codex escalated across 3 review rounds finding degenerate-log variants: r2 banner+hidden-byte (NUL/
BEL/ANSI/U+200B) — FIXED (ECMA-48 escape strip + printable-ASCII normalize); r3 banner+VISIBLE
printable residue (banner...X, banner\n.\n) — OVERRULED with evidence. Independent adjudicator (high
confidence) + integration evidence: real codex → non-TTY file → plain 39-byte banner (its own complete
line); banner+X is stub-only AND byte-indistinguishable from banner+terse-review, so NO content
threshold converges (N beaten by N+1; reds terse reals). FIX-1 (< /dev/null) is load-bearing; FIX-2 is
defense-in-depth catching the observed degenerate + escape/control-byte drift. Documented at the code
site (IMPRECISION BUDGET / ACCEPTED RESIDUAL). Per OPERATING: refuted-at-integration → overrule WITH
evidence, never chase per-shape (treadmill).
## Run deflake-notify-20260711-100816 (2026-07-11) — de-flake test_drive_notify _wait_for


## D1 (Mechanical) — fix the shared `_wait_for` helper with exact-content-match
Fix `_wait_for(path, expected=...)` to poll until file content EQUALS `expected` (exact-match),
falling back to non-empty+byte-stable only when a caller cannot name the content. Chosen over
byte-stable-only because exact-match cannot false-early-return on a stable partial prefix
(design-review codex P1, round 1). All three affected callers know their exact expected bytes.
Classification: Mechanical.

## D2 (Mechanical) — bounded timeout, fail-loud on timeout
Keep the existing bounded `timeout` (default 3.0s); return `False` on timeout so a genuine
non-delivery still fails at the `assert _wait_for(...)` site, never silently swallowed.
Classification: Mechanical.

## D3 (Mechanical) — expected literals are byte-exact (no trailing newline)
drive-notify.sh delivers via `printf '%s' "$MESSAGE"` (no trailing newline) and `cat` copies
exactly, so the `expected` literals are the raw messages with NO trailing newline
("the message body" / "hi" / "first"). Classification: Mechanical.

## /drive run drive-planresume-fix-20260712-015606 — decisions


## D1 — Gate PAST-Execute on a positive "Execute-entered" precondition
Classification: Mechanical
The PAST-Execute derivation fires ONLY when `phaseList` is non-empty AND `lastGate == "A"`,
not merely by special-casing the empty list. Closes the whole vacuous-"all ancestors" class
(completeness + explicit-over-clever), anchored on the deterministic upstream fact that Execute
began.

## D2 — Plan route reuses existing plan-stage resume rules
Classification: Mechanical
The guard only redirects an empty-phaseList / pre-Gate-A resume into Stage 1 Plan; it does not
re-specify Plan resume. No new mechanism (DRY, pragmatic).

## D3 — No conformance edit unless a real drift surfaces
Classification: Mechanical
`--mode state-lint` already treats empty-phaseList-while-executing as malformed, consistent with
the guard. Cross-check is verification, not a scoped edit; edit conformance only if implement
finds an actual disagreement (pragmatic, no gold-plating).

## D4 — ONE phase / ONE slice; guard prose + pin in one review unit
Classification: Mechanical
No fan-out, no staged risk; guard prose and its RED→GREEN pin are shared-contract and stay in a
single review unit so the pin provably binds the guard (right-size, bias-to-action).
# Run drive-planresume-fix-20260712-015606 (2026-07-12) — /drive resume Plan-stage misroute fix

## D1 (correctness, evidence-driven; surfaced at Gate A) — pre-Execute route keys on phaseList emptiness ALONE, NOT lastGate
Premise proposed `phaseList empty OR lastGate != "A"`. All 3 autoplan review voices (codex
Critical/High + 2 Claude subagents HIGH) refuted the lastGate term with concrete attack states:
(a) `lastGate != "A"` false-ROUTES a done run {stage:done, lastGate:B, phaseList:["1"]} back to
Plan (done-teardown sits AFTER the guard, drive.md:251>189); (b) `lastGate == "A"` false-BLOCKS a
legit execute resume with stale/absent lastGate; (c) lastGate is NOT on the --mode state-lint
validated routing surface. Correct predicate: phaseList non-empty ⟺ Execute-entered (parsed
atomically at Gate A, never re-emptied). SUPERSEDES the premise's literal proposal; better
satisfies the premise's own "cross-check state-lint" instruction. Classification: correctness,
surfaced at Gate A for human veto.

## D2 (completeness, fail-closed) — empty phaseList at a later stage STOPs, does not restart Plan
Empty phaseList + stage ∈ {execute,finalize,verify,ship,done} is the exact state-lint
`phaselist-malformed` case → fail closed (STOP), never silently restart at Plan (which would
discard real Execute progress — the mirror wrong-outcome). Guard = exact routing-side mirror of
state-lint's stage-branch.

## D3 (completeness, wire-the-callee) — the fix ADDS the Plan-resume route, not redirects to an assumed one
No pre-existing plan-stage reconcile bullet. Specify: set stage=plan, re-invoke /drive-plan from
reconstructed designReview counter, do NOT re-enter Premises when task.md/design.md exist.

## D4 (DRY) — no bin/drive-conformance.sh change; state-lint already encodes the mirrored stage-branch.
## D5 (right-size) — ONE phase / ONE slice; guard prose + all pins (positive/negative/fail-closed) in one review unit.

## D6 (mechanical; Phase-1 detailed design) — pin home, guard label/index, STOP reason
Classification: Mechanical
(a) Pins live in tests/contracts/test_rebirth_handshake.py — it has the section-bounding helpers
(_resume_section, _resume_bullet_bodies, _resume_section_of) and the mutation-flip precedent the
four pins + non-vacuity proof need; keeps guard prose + binding pins in one review unit (D5). P5
(atomic Gate-A transition) may co-locate in test_checkpoint_contract.py (targets the Stage-1
body). (b) Guard sub-bullet label begins "Pre-Execute resume route (phaseList emptiness …):",
inserted at resume-bullet INDEX 3 — after waiting=="rebirth" (index 2), before Current phase — so
both _RESUME_BULLET_RE variants enumerate it and indices 0/1/2 (rebind/marker/rebirth) are
preserved (existing ordering + reset-on-resume pins stay green). (c) Fail-closed STOP reason
string = "stop:phaselist-malformed", matching the --mode state-lint violation name so the
routing-side mirror is textually explicit and P4 has a distinct token to bind.

## D7 (correctness; dual-voice review of design-phase1.md — F3 + F5) — TOTAL (emptiness × stage) matrix; drop designReview claim
Classification: Mechanical (design-shape correction, routing logic unchanged/validated sound)
Review MAJOR F3: the earlier draft justified an UNCONDITIONAL non-empty fall-through by claiming
non-empty phaseList is "exactly and only Execute-entered" — an overclaim (--mode state-lint,
drive-conformance.sh ~1073, rejects only the EMPTY case outside premises/plan; it does NOT police
{stage:plan, phaseList:["1"]}). Fix: the guard is now a TOTAL function over (emptiness × stage) —
the non-empty branch fails closed on the SYMMETRIC corner (non-empty + {premises,plan}/unknown →
stop:phaselist-malformed) and falls through ONLY for stage ≥ execute. The atomic Gate-A write
makes the corner unreachable in a clean run, so it NEVER false-blocks a legitimate resume
(non-empty ⟹ stage ≥ execute). New pin P4b + a symmetric mutation-flip bind it. F5 (minor): the
autonomous-Plan route no longer asserts state.designReview is /drive-plan's loop counter (not
grounded in the shipped contract, not load-bearing) — logged to followups F2. Also corrected the
line-local-regex hazards the review caught: guard inner sub-bullets use no leading "- **" (F1,
else _resume_bullet_bodies truncates the guard span); the Current-phase bold label stays on ONE
physical line (F2, else it drops from enumeration); P6 asserts ADJACENCY (guard == rebirth+1,
phase == guard+1), not bare ordering (F4).

## D8 (mechanical; implement — Classification: Mechanical) — all pins in test_rebirth_handshake.py; test_checkpoint_contract.py untouched
Placed P5 (atomic Gate-A transition) alongside P1–P4b/P6/P7 in
tests/contracts/test_rebirth_handshake.py rather than test_checkpoint_contract.py. Per design
DD1/§5 (implementer's call): that file already carries the accessors P5 needs
(`_stage_section`, `_section`, `_drive_plan_md`) which test_checkpoint_contract.py lacks, so
co-locating is DRY (Principle 4) and keeps the guard prose + every binding pin in ONE review
unit (D5). test_checkpoint_contract.py needs no edit; its existing
test_sessionId_rebind_is_first_resume_bullet stays green (rebind index 0, len(labels) 5→6).

## D9 — Overrule codex harden P1 (drive-plan.md Gate-A atomicity) with evidence
Classification: Mechanical (adversarial finding reproduced + refuted at integration).
Codex round-2 confirming audit flagged P1: drive-plan.md line 129 "clear waiting=null on approval" allegedly reopens the {stage:execute, phaseList:[]} split-write intermediate the atomic Gate-A clause (line 141) makes unreachable. REFUTED against the real file: line 129 is the Present-human-pause routine's generic waiting-clear and writes NEITHER stage NOR phaseList; only line 141 writes stage=execute, atomically committed with phaseList. The only intermediate line 129 can produce is {stage:plan, phaseList:[], waiting:null} — a LEGITIMATE plan-state the new guard routes safely to re-invoke /drive-plan (not the dangerous execute-empty state). The atomic-write invariant is about stage+phaseList being written together; line 129 does not touch either. Overruled as not-a-P1. Residual: line 128-129 prose could be marginally clearer that the waiting clear is part of the atomic After-this-stage write; logged as a P3 clarity followup (NOT fixed — a prose edit to a refuted-P1 risks pin-churn for a non-bug).

## D10 (finalize; adversarial-overrule with evidence) — codex finalize P1×4 verified against the real integrated path
Codex finalize tagged 4 P1s on the pre-Execute resume guard; each verified against the REAL
resume flow (drive.md) + `git show main`, none is a NEW misroute-to-Finalize (the guard fails
CLOSED on every pre-Execute empty-phaseList path — the gate is sound for its purpose):
- P1.1 done→verify regress — PRE-EXISTING (main reaches the identical Current-phase bullet;
  non-empty branch is "fall through UNCHANGED"), out-of-scope per "no behavior change to other
  stages" → F3.
- P1.2 premises route ambiguity — unreachable corner (no Stage-0 checkpoint boundary), stays in
  Plan tier → F5 clarity, not churned.
- P1.3 state-lint symmetric under-policing — DOCUMENTED (drive.md:222-224); guard fails closed;
  D4 chose no drive-conformance.sh edit; outside diff → F4 defense-in-depth.
- P1.4 no routing-matrix test — codex's own ARCH (prose-as-command); string-pins + per-arm
  mutation-flips are the mechanism → not actionable.
Codex P2 "remove mutation-test block (1213-1304)" is VETOED: those flips ARE the run's
acceptance criterion (task: "mutation-verified: reverting the guard reds it") — removing them
DROPS criterion coverage. Applied ONLY Claude P2 docstring de-slop (test:1258 reword).
