---
description: RETRO pass — trace-mining over ONE completed run's $RUN_DIR artifacts (event log, review/harden rounds, decisions, markers), emitting classified harness-lesson PROPOSALS to $RUN_DIR/retro-<runId>.md. Auto-invoked by /drive at the true run-wrap (before the wrap-/decant); still operator-invocable, completed-run-only, single-run. Consults OPERATING.md / memory index / TODO.md READ-ONLY for proposal dedup. Never mutates rules, memory, or run state.
argument-hint: <runId>
---
You are running the RETRO pass over **one completed `/drive` run**: mine its durable `$RUN_DIR`
artifacts for harness-lesson signal and emit classified lesson **proposals**. Retro is SINGLE-RUN
and completed-run-only, auto-invoked at the true run-wrap and still operator-invocable, not a gated
numbered pipeline stage; cross-run aggregation is out of scope; it is wired into drive.md Completion
at the true run-wrap, before the wrap-`/decant`.
Complement boundary: `/decant` surveys what the coordinator NOTICED (session memory); `/drive-retro`
mines what the TRACES SHOW (`$RUN_DIR` artifacts); retro classifies WHERE a lesson lands (decant's
scope test runs at promotion time) — retro proposes, the existing channels promote.

## 1 — Bind the run

Bind `RUNS_ROOT = ${HARNESS_RUNS_ROOT:-$HOME/.claude/harness-runs}`; `RUN_DIR = $RUNS_ROOT/<runId>`.
Resolve `<runId>` three-way: (1) exact directory match → proceed. (2) no exact match but EXACTLY
ONE run dir has the argument as a name prefix → use it, and REBIND `<runId>` to that dir's FULL
basename before ANY downstream use (the `retro-<runId>.md` filename, the `# Retro <runId>` title,
the header `source:` line) — prefix and full-id invocations of the same run write the IDENTICAL
single file; state the resolution in the terminal report. (3) zero or ≥2 matches, or no argument
given → STOP: print usage plus the available run ids (`ls -1t "$RUNS_ROOT"`, newest first, capped
~20) and write NOTHING. Never guess among multiple matches; never default to the latest run.

## 2 — Completeness gate (fail closed)

The run is COMPLETED iff the standalone marker FILE `$RUN_DIR/completedAt` — a file drive-ship.md
writes, never a `state.json` key — carries a parseable timestamp (first line, surrounding
whitespace trimmed; any remaining interior whitespace ⇒ unparseable), OR `state.json.stage ==
"done"`: `is_done()` in `bin/drive-retention.sh`, the real done-authority. EITHER signal alone
passes; the header's `completed:` field renders the accepted path — the marker content when
parseable, else `completed: stage=done (marker absent)` when the marker is entirely ABSENT and
`stage == "done"` (a full accepted done path: stats and Overlap compute normally).
Neither signal → STOP without writing, reporting `stage`/`waiting` when readable. NO override or
partial mode exists (v1 is completed-run-only; in-flight/stuck-run mining is a followups.md
follow-on, not a mode). Two degraded done paths PROCEED:
- Marker parseable, `state.json` missing/unreadable → every `state.json`-sourced stat row renders
  `n/a (state.json unreadable)`; repoRoot-dependent Overlap entries render `not checked (repoRoot
  unknown)`. The output header never degrades (it has no state-derived field).
- Marker present but unparseable, `stage == "done"` → the header renders
  `completed: stage=done (marker unparseable)`; nothing else degrades.

## 3 — Inputs (two classes)

**Mining inputs — durable `$RUN_DIR` artifacts ONLY** (`.md`/`.json`/`.jsonl`/`*.marker`; these
survive retention GC — never `wt/` or the `codex-raw-*.log`/`codex-harden-*.log` raw logs, so
retro behaves identically on fresh and aged runs): `completedAt`; `state.json`; `event-log.jsonl`;
`review-<scope>-N.md` + `codex-review-<scope>.md`; `harden-<P>-N.md` + `codex-harden-<P>.md`;
`decisions.md`, `followups.md`, `finalize-todo.md` if present; `redesign-<P>-r<R>.marker`,
stranded `inflight-*.marker`, `checkpoint-complete.marker`; `task.md`/`design.md` (context only).

**Dedup references — a FIXED, READ-ONLY set consulted SOLELY to fill each proposal's Overlap
field** (never mined for stats or findings, never written). With `REPO_ROOT = state.json.repoRoot`
(absolute): `$REPO_ROOT/OPERATING.md`, `$REPO_ROOT/TODO.md`, `$REPO_ROOT/.harness/decisions.md`,
`$REPO_ROOT/.harness/followups.md`; plus the auto-memory index
`~/.claude/projects/<proj>/memory/MEMORY.md` where `<proj>` = the absolute repoRoot with every `/`
and `.` replaced by `-`. A missing/unreadable reference ⇒ that Overlap entry renders `not checked
(<file> unavailable)`; unknown repoRoot ⇒ `not checked (repoRoot unknown)`, no cwd fallback —
never a STOP.

## 4 — Parse the event log (tolerant stream decode)

Line-split parsing is FORBIDDEN: the real log interleaves single-line records with pretty-printed
multi-line JSON objects. Decode the whole file as a stream (`python3`):

```python
import json, re
raw = open(f"{RUN_DIR}/event-log.jsonl").read()
dec, i, events, skipped = json.JSONDecoder(), 0, [], 0
while i < len(raw):
    i = re.compile(r"[ \t\r\n]*").match(raw, i).end()  # inter-record whitespace: NEVER counted
    if i >= len(raw): break
    try: obj, i = dec.raw_decode(raw, i); events.append(obj)
    except ValueError:  # decode error at non-whitespace: skip to next newline, count ONE segment
        nl = raw.find("\n", i); i = len(raw) if nl < 0 else nl + 1; skipped += 1
```

Only genuinely undecodable spans count — a well-formed mixed log reports 0 skipped; the skipped
count is surfaced in the output header. Missing/empty log → degrade, don't abort: the header notes
"event-log absent — timeline stats omitted"; event-derived stats show `n/a`.

## 5 — Derive stats (script/grep-derived, never eyeballed; a metric row never hard-fails)

- `state.json` counters: `phaseDesign[*].round/redesigns`, `phaseReview[*].round/hardenRound/status`,
  `slices[*].reviewCount/step`, `finalizeRound`, `budget.calls`, `lastGate`, final `waiting`
  (non-null on a done run is abnormal — report as signal). Review-round cross-check: count of
  pure-integer-N `review-<scope>-<N>.md` files (the same reconstruction drive-review.md /
  `bin/drive-conformance.sh` use); harden/finalize FIX rounds dual-sourced — the
  `hardenRound`/`finalizeRound` counters against `harden-<P>-N.md` / `review-finalize-N.md` files
  carrying `## AppliedEdits: yes` (the file counts are the fallback when `state.json` is
  unreadable). Any counter-vs-file-count mismatch is itself reported as signal.
- Event-log stats (gates + timestamps · dispatches by kind · wall-clock) are BEST-EFFORT by
  contract: computed over whatever objects/fields the decoder yields; NO stat requires a specific
  event kind; underivable ⇒ `n/a`, never a STOP. Wall-clock = earliest → latest parseable `at`/`ts`
  across all decoded objects.
- NO STOP-cause stat is emitted (not durable on a completed run); the durable residuals stand in:
  final non-null `waiting`, stranded `inflight-*.marker`, `redesign-*.marker` epochs.
- Codex-degraded scopes: `codex-review-<scope>.md`/`codex-harden-<P>.md` whose FIRST LINE begins
  with `CODEX_UNAVAILABLE` (prefix match) — a degraded scope, mined for nothing (files are
  overwritten per round: the stat is "scopes degraded at their last round"; claim nothing about
  earlier rounds).

## 6 — Mine findings: Rule U (unified extraction — mining is signal, not accounting)

ONE line-level, shape-agnostic rule over ALL finding files (`review-<scope>-N.md`,
`harden-<P>-N.md`, `codex-review-<scope>.md`, `codex-harden-<P>.md`); NO per-file or per-family
rule selection. Locate candidates by grep on the carrier patterns (streaming; no full-file reads).
A line is a candidate iff, after stripping leading whitespace, it matches one of four CARRIERS,
each anchoring a word-bounded UPPERCASE severity token (`BLOCKING|MAJOR|MINOR|NIT|P[123]`,
case-SENSITIVE — lowercase prose never grades):
- **heading-bracket** — a `###`–`######` heading whose `[...]` bracket contains a token;
- **heading-bare** — a `###`–`######` heading beginning with a token (`##`-level token headings
  are section groupers, never candidates — their tagged body lines are);
- **line-bracket** — optional list marker (`-`, `*`, `N.`, `N)`), optional `**`, then a `[...]`
  bracket containing a token;
- **line-bare** — optional list marker, optional `**`, then a leading token.

Tag window = the bracket's content (bracket carriers) or the maximal leading tag group (bare
carriers; tokens separated by `/`, single spaces, or `,`). Grade from tag-window tokens ONLY —
severity words later in the prose never re-grade. Token→P-level mapping: P1 = {BLOCKING, MAJOR,
P1}; P2 = {MINOR, P2}; P3 = {NIT, P3}; a compound window counts ONCE at its highest P-level
(P1 > P2 > P3). The counted unit is FINDING-MENTIONS per artifact — cross-round re-mentions are
churn signal, not error; `FIXED` is deliberately NOT a resolution token (harden's found-and-fixed
findings count). Uniform guards, applied to every candidate in every file:
1. **Negation** — a token immediately preceded by `non-`/`non ` never classifies.
2. **Resolution/veto** — word-bounded `RESOLVED|VETOED|OVERRULED|REFUTED|CLOSED` excludes:
   case-insensitive inside a bracket window, UPPERCASE-only elsewhere on the line.
3. **Verdict-continuation** — the text after the tag window (skipping one optional parenthesized
   token list, and one `:` ONLY when it immediately follows the window with no intervening
   space — space-separated `:line:` metadata is not a count) BEGINS with a named guard form,
   matched word-bounded, lowercase-as-written. The NAMED list (extendable only via a decisions.md
   calibration note, never silently): every carrier — `remains`, `remaining`, `none`,
   `is addressed`, `closed`, `split correct`; non-heading carriers — a digit, `count`, `counts`
   (kills per-round verdict-count/scoreboard lines like `P1: 0 · P2: 2`); PLAIN line-bare
   carriers only (no bracket, no `**`) — `fix`, `fixes`, `fixed` (bracket-carrier fix
   re-listings are real finding-mentions and count).
4. **Hyphen back-reference** (non-heading carriers only) — a token immediately followed by `-` +
   alphanumeric (`P1-2`, `MAJOR-1(a)`) is prose back-referencing a finding, not a finding;
   heading carriers are EXEMPT (`### P2-1 (MINOR) — …` is a real numbered finding heading).

Per-line dedup: a candidate whose nearest preceding `###`–`######` heading is itself a Rule-U
finding is not separately counted (the heading counts once for its section); a bare `P1:` label
line counts once, its untagged child bullets never — a stated best-effort undercount. E7
`CODEX_UNAVAILABLE` stubs are mined by nothing. Imprecision budget: ≤2% residual misgrades over
graded findings — a stray line is a calibration-note entry plus a guard-list addition, never
grounds to re-architect the rule.

## 7 — Write the ONE output, then report

Exactly ONE write: `$RUN_DIR/retro-<runId>.md` (`<runId>` = the resolved FULL basename). Re-run
OVERWRITES it (no `-N` versioning); say "overwrote existing retro" when it did. Fixed section
order: the `# Retro <runId>` header block (`generated:` / `completed:` / `source:` lines +
`inputs: <n> review files, <m> harden files, <k> events (<j> unparsed segments skipped)`) →
`## Run statistics` (a `| metric | value | source |` table from step 5) → `## Recurrence themes`
→ `## Lesson proposals` → `## No-action notes` → `## Operator next step`.
- **Recurrence themes** is INSTRUCTED SYNTHESIS, not a computed metric: YOU group the script-mined
  finding list; every cited finding MUST appear in the mined candidate list (Rule U). Grouping
  keys: filename scope token, mapped P-level, normalized finding title (heading carriers: the
  bracket/tag-stripped title; line carriers: the post-tag-window text, ~80-char truncation). A
  theme needs ≥2 cited findings from ≥2 distinct artifacts; one line + citations (artifact
  filename + finding title) each; cap top ~10, remainder as a one-line count.
- **Lesson proposals** — each `### RL-<n> — <one-line lesson>` carries 5 fields: **Evidence** ≥2
  `$RUN_DIR`-relative citations, or 1 + an explicit `single-instance` flag; **Class**
  behavioral-rule | tool/env-gotcha | skill-gap | process-signal | one-off; **Destination
  (proposal only)** OPERATING.md | project CLAUDE.md/docs | skill/command file <name> |
  auto-memory | TODO.md (OPERATING.md §Self-Improvement's matrix + process-signal → TODO.md);
  **Draft** ≤2 sentences, absolute-directive form; **Overlap** the existing rule / memory entry /
  TODO item / ledger entry it extends or duplicates, filled from the step-3 dedup references —
  "none" only after checking the available references; extend > new. Emit ≥1 proposal when the
  run shows signal: ≥1 P1-mapped finding under Rule U; any scope round/reviewCount > 1; ≥1
  harden/finalize FIX round (`hardenRound ≥ 1` or `finalizeRound ≥ 1`, or `## AppliedEdits: yes`
  artifacts when state is unreadable); ≥1 redesign marker; a stranded inflight marker; non-null
  final `waiting`. A clean run may emit ZERO proposals iff No-action notes states why (never
  invent a lesson to fill quota).
- **No-action notes**: signals inspected and deliberately not proposed, one line each with why.
- **Operator next step** (one line): proposals are inert until the operator acts; accepted ones
  flow through the existing promotion channels — /drive-retro never writes them.

**Proposals-only invariant (absolute):** never edit OPERATING.md, CLAUDE.md, TODO.md,
MEMORY.md/auto-memory, skill or command files, `state.json`, or `event-log.jsonl`; never append
events; no repo write of any kind. Reading the dedup references is sanctioned; writing them is not.

Terminal report (chat): the output path + one headline line (rounds, P1 count under the Rule-U
mapping, proposal count) + the list of proposal titles — the operator decides what to act on.
