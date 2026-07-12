# Repo efficiency audit — new lenses — 2026-07-12

**Provenance.** Measured 2026-07-12 (~14:00 CST) from the slice worktree at
`ce12c422bb0eb78df5550c10b2cf585c5cb1968f` (phaseBaseSha). Four lenses the
2026-07-08 audit did not cover: token/cost per run, spec bloat as context cost,
test-suite/CI runtime, repo hygiene. Prior-audit boundary:
`docs/efficiency-audit-2026-07-08.md` — everything in its scope (wall-clock seams,
gate latency, codex tail, round churn, R1–R12, its refuted list) is out of scope
here; §3 is the dedup ledger.

**Cite convention (binding for every `file:line` in this doc and in the TODO.md plan
section):** line numbers are as-of phaseBaseSha `ce12c42…`, PRE-insertion — this run's
own TODO.md section insert shifts every downstream TODO.md line. Dedup rows also carry
a stable quoted text anchor so they stay resolvable after the insert and after
ship-time ledger appends.

**Evidence corpus, as-of this audit's own measurement run** (external corpora drift
continuously; each figure below was produced by the pinned enumeration command shown.
Design-time references of the same date — 69 / 120 MB, ~1,033 / 278 MB, 13, 6 — are
drift comparators only):

| Corpus | Pinned enumeration command | Measured 2026-07-12 |
|---|---|---|
| Top-level session transcripts | `ls ~/.claude/projects/-Users-jiazou-workspace-autodrive/*.jsonl \| wc -l` | 69 files |
| — bytes | `du -ch ~/.claude/projects/-Users-jiazou-workspace-autodrive/*.jsonl \| tail -1` | 120 MB |
| Subagent transcripts (both layouts: depth-3 `<session>/subagents/agent-*.jsonl` and depth-5 `<session>/subagents/workflows/wf_*/agent-*.jsonl`) | `find ~/.claude/projects/-Users-jiazou-workspace-autodrive -path '*/subagents/*.jsonl' \| wc -l` | 1,038 files |
| — bytes | `find ~/.claude/projects/-Users-jiazou-workspace-autodrive -path '*/subagents/*.jsonl' -print0 \| xargs -0 du -ch \| tail -1` | 280 MB |
| Run-level event logs | `ls ~/.claude/harness-runs/*/event-log.jsonl \| wc -l` | 13 logs |
| codex-attempts files | `ls ~/.claude/harness-runs/*/codex-attempts-*.jsonl \| wc -l` | 6 files |
| codex raw logs | `ls ~/.claude/harness-runs/*/codex-raw-*.log \| wc -l`; `du -ch ~/.claude/harness-runs/*/codex-raw-*.log \| tail -1` | 73 files / 11 MB |

Pinning is layout-derived: under `~/.claude/harness-runs/` run-root globs ONLY (a bare
recursive `find` ingests pytest fixture scratch under `<run>/tmp/pytest-of-*` — 41 vs 13
event logs, 128 stray codex artifacts at design time); under the projects dir a
root-scoped `-path` with NO depth pin (a depth pin silently drops the 125
workflow-nested transcripts). The corpus includes this run's own live event log — counts
taken minutes apart drift by a few records (343→347 parseable within this measurement
session); every figure here is as-of its command's run.

**Divergence notes (design-time figure/claim vs measured — the measured value wins):**

1. `du -sh ~/.claude/harness-runs/` → **278 MB** measured, vs 249 MB at phase-design
   time and ~179 MB in the high-level design — the residue grows between measurements
   (this run's own worktrees/logs are part of it).
2. codex-attempts files: **6** runs covered (high-level design said 5; phase design
   verified 6 — confirmed).
3. Event-log corpus: **13** surviving logs (the 07-08 audit mined 22 — retention swept
   the rest; all corpus claims here are bounded to N=13), with a HETEROGENEOUS
   vocabulary across run eras (123 distinct event tokens; §1.1c). Per-token drift vs
   design-time: `subagent-started` 11→12, `codex-started` 34→39 (two more runs logged
   since).
4. Subagent stratum: **1,038** transcripts / **280 MB** (design-time reference ~1,033 /
   278 MB — live drift, expected).
5. The high-level design's D6 mis-attributed two dedup surfaces to
   `.harness/followups.md`; both are TODO whole-repo-audit surfaces (corrected per D21;
   see §3 rows — surface SET unchanged, only the attribution moved).

**Unit conventions (D10 cost model, binding).** Two units with observed harm:
*context-window occupancy* (drives rebirth pressure) and *usage-quota consumption*
(drives session-limit kills; cached `cache_read_input_tokens` vs uncached
`input_tokens` + `cache_creation_input_tokens` always distinguished when
transcript-derived). Any byte-only figure is labeled **static proxy** (est. tokens ≈
bytes/4 — an estimate, not a measured token count).

**Output-block convention (every evidence block in §1):** blocks quote the stated
command/procedure's VALUES verbatim as measured at the audit timestamp; layout,
labels, column packing, and path ellipses are editorial. Any line that is a sum,
ratio, or percentage of printed values is DERIVED (arithmetic on the procedure's
output, not an extra measurement). A rerun diffs against the values (modulo
live-corpus drift), never the layout.

## 1. Evidence — measurements per lens

### 1.1 Token/cost per run

**(a) Per-turn machine-global baseline.**

Static proxy:

```
$ wc -c OPERATING.md CLAUDE.md ~/CLAUDE.md ~/.claude/projects/-Users-jiazou-workspace-autodrive/memory/MEMORY.md
   19531 OPERATING.md
   12739 CLAUDE.md
     356 /Users/jiazou/CLAUDE.md
   19072 .../memory/MEMORY.md
   51698 total
```

≈ **12.9k tokens (static proxy)** riding every turn of every session on this machine
AND every Agent-subagent dispatch (the operating rules + project instructions +
auto-memory are injected into subagent context too).

Primary (transcripts): full-stratum streaming line-tolerant parse over all 69
top-level transcripts. **Procedure P1 (rerunnable; reruns drift per D22):**

```
python3 - <<'EOF'
import json,glob,os,statistics as st
fs=sorted(glob.glob(os.path.expanduser('~/.claude/projects/-Users-jiazou-workspace-autodrive/*.jsonl')))
recs=[];per=[];side=0
for fp in fs:
    n=i=c=r=o=0
    for line in open(fp,errors='replace'):
        try:d=json.loads(line)
        except Exception:continue
        if not isinstance(d,dict):continue
        if d.get('isSidechain') is True:side+=1
        u=d.get('message');u=u.get('usage') if isinstance(u,dict) else None
        if not isinstance(u,dict):continue
        cr=u.get('cache_read_input_tokens') or 0
        n+=1;i+=u.get('input_tokens') or 0;c+=u.get('cache_creation_input_tokens') or 0
        r+=cr;o+=u.get('output_tokens') or 0;recs.append(cr)
    if n:per.append((n,i,c,r,o))
tot=[sum(p[k] for p in per) for k in range(5)]
print('files',len(fs),'sessions-with-usage',len(per),'records',tot[0],'sidechain',side)
print('input',tot[1],'cache_creation',tot[2],'cache_read',tot[3],'output',tot[4])
print('median cache_read/record',st.median(recs),'p90',sorted(recs)[int(len(recs)*.9)])
print('per-session medians:',st.median([p[0] for p in per]),
      st.median([p[2] for p in per]),st.median([p[3] for p in per]))
EOF
```

The D16 threshold (≥20 usable usage records) is far exceeded, so the E1 static-proxy
fallback was NOT taken. The block below is DERIVED from P1's output at the audit
timestamp — every value maps 1:1 to a P1 print (values verbatim, labels/layout
editorial), except the `uncached total` and `cached:uncached` line, which is
arithmetic on P1's printed sums:

```
sessions with >=1 usage record: 68 / 69
usage records total:            20,541
sum input_tokens (uncached):         3,038,085
sum cache_creation (uncached):     150,523,987
sum cache_read (cached):         6,302,200,596
sum output_tokens:                  30,016,544
uncached total (derived):          153,562,072   cached:uncached = 41.0 : 1
median per-record cache_read:          262,238   (p90 606,851)
per-session medians: 234 usage records; 1,400,092 cache_creation; 45,822,624 cache_read
```

- **Occupancy:** the median assistant message re-reads a **262k-token cached prefix**
  (occupancy floor; medians above 200k reflect the 1M-window sessions in the corpus —
  a measurement caveat, not an anomaly).
- **Quota:** consumption is overwhelmingly cached (41:1), so the levers are the
  *uncached* pools: 150.5M cache-creation tokens — prefix (re)creation events —
  dominate the 153.6M uncached total.

Baseline-rides-subagents evidence (subagent stratum — `isSidechain:true` occurs ONLY
here; the full top-level parse found **0** top-level sidechain records (P1's
`sidechain` counter), confirming the originally-designed top-level scan is dead):
1,038 dispatch transcripts (pinned command above) ≈ **15 dispatches per top-level
session** (1,038/69). Newest-20-by-mtime sample, FIRST usage record per file (the
per-dispatch prefix-creation cost). **Procedure P2 (rerunnable):**

```
python3 - <<'EOF'
import json,glob,os,statistics as st
root=os.path.expanduser('~/.claude/projects/-Users-jiazou-workspace-autodrive')
fs=[p for p in glob.glob(root+'/**/*.jsonl',recursive=True) if '/subagents/' in p]
fs.sort(key=os.path.getmtime,reverse=True)
cc=[];cr=[]
for fp in fs[:20]:
    for line in open(fp,errors='replace'):
        try:d=json.loads(line)
        except Exception:continue
        u=(d.get('message') or {}).get('usage') if isinstance(d,dict) and isinstance(d.get('message'),dict) else None
        if isinstance(u,dict) and any(u.get(k) for k in ('input_tokens','cache_creation_input_tokens','cache_read_input_tokens')):
            cc.append(u.get('cache_creation_input_tokens') or 0)
            cr.append(u.get('cache_read_input_tokens') or 0);break
print('subagent transcripts',len(fs),'sampled',len(cc))
print('first-record cache_creation: median',st.median(cc),'min',min(cc),'max',max(cc))
print('first-record cache_read: median',st.median(cr),'min',min(cr),'max',max(cr))
EOF
```

P2's aggregates at the audit timestamp (values verbatim, labels editorial; P2 prints
aggregates only — no per-file rows; the sample is a rolling newest-20 window, so
reruns re-sample):

```
first-record cache_creation_input_tokens: median 26,968  (min 20,968, max 37,552)
first-record cache_read_input_tokens:     median  9,054  (min 0,      max  9,501)
```

Reading (a SAMPLED median — newest 20 of 1,038 — plus extrapolation, NOT a
per-dispatch measurement of the full stratum): **the sampled median dispatch pays
~27k tokens of uncached prefix creation**, and the ~12.9k-token machine-global
baseline is **~48% of it** (static-proxy share of the sampled median). Extrapolated
(sampled median × stratum count — an estimate): 1,038 × 26,968 ≈ **28.0M uncached
tokens ≈ 18%** of the corpus's entire uncached consumption is dispatch prefix
re-creation, roughly half of that the baseline.

**(b) Coordinator-resident spec weight.**

```
$ wc -c .claude/commands/drive*.md
    6684 drive-design.md     10223 drive-plan.md     22549 drive-review.md
   33367 drive-finalize.md   14067 drive-retro.md    23523 drive-ship.md
   22705 drive-harden.md      6906 drive-implement.md
  120903 drive.md            260927 total
```

drive.md ≈ **30.2k tokens (static proxy) of window occupancy per /drive leg**; each
stage invocation adds its own spec (finalize 33.4 kB / ship 23.5 kB / harden 22.7 kB /
review 22.5 kB). Not transcript-confirmed: /drive-leg transcripts are not labeled as
such in the corpus, so attributing a specific early `cache_creation` spike to spec
loading would be a guess — the static proxy stands (per the lens contract).

**(c) Subagent multiplication (durable artifacts PRIMARY; event logs best-effort — D19).**

PRIMARY (era-independent durable artifact families, run-root globs):

| Family | Command | Count |
|---|---|---|
| review round artifacts | `ls ~/.claude/harness-runs/*/review-*-*.md \| wc -l` | 106 (each ⇒ ≥1 reviewer dispatch) |
| harden audit artifacts | `ls ~/.claude/harness-runs/*/harden-*-*.md \| wc -l` | 18 |
| codex-attempts files (distinct runs) | `ls ~/.claude/harness-runs/*/codex-attempts-*.jsonl \| wc -l` | 6 runs covered |
| — attempt VOLUME (line counts; never a run count) | `wc -l ~/.claude/harness-runs/*/codex-attempts-*.jsonl` | 127 attempt records (9–36/run) |
| codex raw logs | `ls ~/.claude/harness-runs/*/codex-raw-*.log \| wc -l`; `du -ch ~/.claude/harness-runs/*/codex-raw-*.log \| tail -1` | 73 logs / 11 MB — static proxy for codex burn (codex tokens are a SEPARATE budget) |
| subagent transcripts | (§ provenance) | 1,038 — the direct dispatch count |

BEST-EFFORT (event logs; coverage-bounded): one-pass vocabulary enumeration over the
pinned glob `~/.claude/harness-runs/*/event-log.jsonl`. **Procedure P3 (rerunnable;
the figures below are P3's values at the audit timestamp — table layout editorial):**

```
python3 - <<'EOF'
import json,glob,os,collections
logs=sorted(glob.glob(os.path.expanduser('~/.claude/harness-runs/*/event-log.jsonl')))
v=collections.Counter();pl=collections.Counter();n=any_disp=0
D={'dispatch','subagent-started','codex-started'}
for lg in logs:
    seen=set()
    for line in open(lg,errors='replace'):
        try:d=json.loads(line)
        except Exception:continue
        if not isinstance(d,dict):continue
        n+=1;e=d.get('event',d.get('kind')) or '<no-event-key>';v[e]+=1;seen.add(e)
    for e in seen:pl[e]+=1
    if seen & D:any_disp+=1
print('logs',len(logs),'parseable',n,'distinct',len(v))
for t in sorted(D):print(t,v[t],'in',f'{pl[t]}/{len(logs)}','logs')
print('union',sum(v[t] for t in D),'; logs with >=1 dispatch-class token',f'{any_disp}/{len(logs)}')
EOF
```

→ 13 logs, 347 parseable records, **123 distinct event tokens** — the vocabulary is
heterogeneous across run eras (era variants like `run_init`/`run-setup`/`run_setup`;
one era logs per-slice tokens like `slice1.1_review_r1`). Dispatch-class tokens,
reported PER TOKEN with coverage bounds (never a single-token grep):

| Token | Records | Logs containing it |
|---|---|---|
| `dispatch` | 40 | 4/13 |
| `codex-started` | 39 | 5/13 |
| `subagent-started` | 12 | 3/13 |
| union (lower bound only — measured: 9/13 logs carry ≥1 dispatch-class token, 4/13 carry none) | 91 | 9/13 |

The durable-artifact families are the load-bearing counts; the event-log union (91) vs
the transcript stratum (1,038) shows how badly event logs undercount dispatches.

**(d) Ledger-read tax (D9 framing — correctness first).**

CLAUDE.md:203-205 (anchor: "Read `.harness/decisions.md` at the start of a task")
instructs a task-start read; a default Read ingests the first 2,000 lines of the
6,064-line file:

```
$ head -n 2000 .harness/decisions.md | wc -c                     → 214,560 B
$ head -n 2000 .harness/decisions.md | grep -E '^### ' | tail -1 → ### 2026-06-11 …
$ grep -E '^### ' .harness/decisions.md | tail -1                → ### 2026-07-06 …
$ awk 'NR>2000' .harness/decisions.md | grep -cE '^### '         → 51   (of 168 total)
```

The live defect is **recency (correctness)**: because the ledger is append-only, the
default read serves the OLDEST third and misses the **51 newest entries — everything
after 2026-06-11** — exactly the ones "read decisions.md to stay consistent" exists
for. The 214,560 B ≈ 53.6k tokens (static proxy) of stale ingest is the rider, not the
headline. (Window figures are stable at the frozen SHA; the gap dates are as-of this
measurement — ship-time appends will widen the file-newest date.)

### 1.2 Spec bloat as context cost

Per-section byte weights,
`awk '/^## /{if(s)print b"\t"s; s=$0; b=0; next}{b+=length($0)+1} END{print b"\t"s}' <spec> | sort -rn`,
top sections:

| File | Heaviest `##` sections (bytes) |
|---|---|
| drive.md (120,903 B) | **Run setup & resume 46,683 (39%)** · Pipeline 20,133 · Emit run graph 15,273 · I1 rebirth handler 13,431 · Durable checkpoint contract 11,528 |
| drive-finalize.md (33,367 B) | Step 1 Audit 9,631 · Step 3 Fix 3,995 · Phase-2 wiring obligations 3,161 (KNOWN-stale — §3) · Step 2 Triage 3,006 |
| drive-ship.md (23,523 B) | Ship worktree + ledger promotion 7,729 · After approval 7,079 |
| drive-harden.md (22,705 B) | Step 1 Audit 7,790 · Step 3 Fix 3,520 |
| drive-review.md (22,549 B) | Step 1 codex 6,739 · Step 2 Claude reviewer 5,729 |

Trim-candidate analysis (narration the OPERATING lean-spec rule bans), each with its
measured pin-migration cost (`grep -l '<tokens>' tests/contracts/*.py test/*.test.sh`):

- **drive.md § "Run setup & resume" (46,683 B ≈ 11.7k tok/leg static proxy)** — the
  single heaviest spec block in the pipeline; 39% of every /drive leg's spec occupancy.
  Pin exposure: the literal heading is pinned by **4 suites**;
  `checkpoint-complete.marker` tokens by **3**; run-graph tokens by **3**; drive.md is
  referenced by **10 pytest contract files + 1 bash suite** overall. Any trim is a
  token-sweep migration — never a quick win. New delta only (finding N3): the
  *concentration measurement*; the cross-file rebirth-prose portion of this section is
  a KNOWN surface (§3 row, followups.md:303).
- Known-item exclusions (§3): finalize "Phase-2 wiring obligations" stale section
  (TODO.md:211); cross-file rebirth-prose duplication (followups.md:303); retention
  3-layer authority drift (TODO.md:590).

### 1.3 Test-suite / CI runtime

Verdict carried from plan-time measurement (D4) and refreshed this audit:

```
$ gh run list --limit 3          → success 2m28s · success 2m21s · success 2m12s
$ python3 -m pytest --collect-only -q | awk -F': ' '/: [0-9]+$/{s+=$2} END{print s}' → 776
```

Repo is PUBLIC (macOS minutes free); pytest suite 776 tests in ~55 s; bash suite
~139 s; CI total ~2.5 min. **No new material findings — valid empty lens (E3).**
Residuals are plan-doc-only and carried in the TODO section: the D8-demoted CI
`concurrency:` item (full constraint list there, incl. the
`bin/drive-ci-wait.sh:114` CANCELLED-as-green interaction) and the bash-suite parallel
driver, risk-weighed against the canonical runner's no-early-exit guarantee.

### 1.4 Repo hygiene

```
$ wc -c -l .harness/decisions.md .harness/followups.md
    6064  606063 .harness/decisions.md
    1144  115706 .harness/followups.md
$ git ls-files | grep -E '__pycache__|\.pyc$' | wc -l   → 0
$ du -sh ~/.claude/harness-runs/                        → 278M
```

- **Committed ledgers**: unbounded append-only, promoted at every ship. decisions.md
  (606 kB) is the N2 surface (§1.1d). followups.md (1,144 lines) fits ENTIRELY inside
  one default 2,000-line Read — it has NO recency defect (this refutes the "possibly
  followups.md too" half of the archival forecast; §5).
- **docs/ weights** (`wc -c docs/*.md`): drive-enforcement.md 57,912 B —
  live-referenced from OPERATING.md:71 → context weight, not a finding; flow.md
  18,669 B — spot-checked CURRENT (describes the live three-tier progressive design
  refinement) → staleness hypothesis refuted (§4); trellis-analysis.md 33,591 B —
  historical but live-referenced by TODO.md:469 (anchor "## Trellis pattern adoption")
  → keep; efficiency-audit-2026-07-08.md 27,771 B — the prior audit's evidence record,
  referenced by TODO's R1–R9 plan → keep.
- **Classics clean**: no committed `__pycache__`/`.pyc`; `.tmp*/` gitignored
  (design-verified).
- **External-but-adjacent**: `~/.claude/harness-runs/` = 278 MB (corpus total — NOT a
  reclaimable figure; see below); retention tooling exists (`bin/drive-retention.sh`)
  but is **report-only by default** ("WITHOUT --apply it is byte-for-byte
  report-only" — script header) — residue shrinks only when a human runs `--apply`.
  **Measured eligibility (the REAL classifier, run read-only:
  `bash bin/drive-retention.sh --json`, 2026-07-12):** 13 runs classified;
  **Tier-L eligible today = 0 runs / 0 bytes** (per-run reasons: 5 `not-aged`, 7
  `waiting`, 1 `inflight-open` — the classifier's quiet+done+≥14-day gates);
  **Tier-W eligible = 0** of 2 classified `wt/` children. The tool's reclaim
  UNIVERSE is bounded by design: Tier-L covers only heavy logs
  (`codex-raw-*.log`/`codex-harden-*.log` — sum of the report's `tierL.bytes` =
  15,973,632 B ≈ 15.2 MiB corpus-wide) and Tier-W only drive-owned worktrees under
  `<run>/wt/` (`du -sk ~/.claude/harness-runs/*/wt` → 9 dirs, ~12 MiB); history
  (`.md`/`.json`/`.jsonl`) is NEVER touched (script header). The corpus bulk is
  per-run `tmp/` scratch outside BOTH tiers (`du -sk ~/.claude/harness-runs/*/tmp \|
  sort -rn` vs the run-dir totals — the three largest runs measured 92 of 101 MiB,
  61 of 64 MiB, and 61 of 68 MiB `tmp/`). Noted as external plan item N4; any change
  is machine config, never a repo diff.

## 2. Ranked recommendations

Ordered by savings/effort in the D10 units. Every finding is new (N-namespace);
§3 holds everything excluded as already known.

**N1 — Machine-global baseline diet (biggest uncached-quota lever)**

- **Lens:** 1.1a. **Evidence:** §1.1(a) — 51,698 B ≈ 12.9k tok (static proxy) baseline;
  measured median 26,968 uncached cache-creation tokens per subagent dispatch
  (newest-20 sample); 1,038 dispatches in corpus; extrapolation ≈ 28.0M uncached
  tokens ≈ 18% of total uncached consumption (estimate).
- **Cost denomination:** quota — the baseline is ~48% of the sampled-median
  dispatch's ~27k uncached prefix creation (static-proxy share; newest-20 sample of
  1,038); occupancy — ~12.9k tokens of every window, all sessions machine-wide.
- **Run-level effect:** fan-out quota burn.
- **Effort:** medium (three surfaces; two live outside the repo diff or are
  user-voice).
- **Savings estimate:** a one-third baseline cut ≈ 4.3k uncached tok/dispatch ≈ ~4.5M
  tokens over a corpus-equivalent dispatch volume (estimate); scales with every future
  dispatch and session turn.
- **Disposition:** external-surface plan items — MEMORY.md diet (external, no repo
  diff); OPERATING.md conciseness pass (**agent-authorship pending user decision,
  OQ1/D13**); plus a repo plan item: CLAUDE.md trim (12.7 kB; strings pinned by
  contract suites → its own token-sweep migration, independent of the R5–R9 batch —
  disjoint files/pins). Never quick-wins (D5).

**N2 — decisions.md bounded-read recency defect → archival split**

- **Lens:** 1.1d + 1.4. **Evidence:** §1.1(d).
- **Cost denomination:** correctness primary — the 51 newest entries (post-2026-06-11)
  are invisible to the instructed task-start read; rider: 214,560 B ≈ 53.6k tok
  (static proxy) of stale occupancy per task-start read.
- **Run-level effect:** correctness (the D18-permitted label for this finding only);
  occupancy rider.
- **Effort:** trivial–small. **Savings:** recency gap 25 days → 0 (the post-split live
  file — 1,971 lines / 187,713 B from the first 2026-07 entry — fits ONE default
  Read); beyond-window entry count 51 → 0.
- **Disposition:** **quick-win → §5 QW1** (Phase 2 of this run). Ledger-header
  amendment pre-declared in §4.

**N3 — drive.md per-leg spec-weight concentration**

- **Lens:** 1.2. **Evidence:** §1.2 — "Run setup & resume" = 46,683 B = 39% of
  drive.md; drive.md ≈ 30.2k tok/leg (static proxy).
- **Cost denomination:** occupancy — ~11.7k tok of every /drive leg sits in one
  section (static proxy).
- **Run-level effect:** rebirth pressure (per-leg window occupancy).
- **Effort:** medium — token-sweep across the measured pin surface (10 pytest + 1 bash
  file reference drive.md; 4 suites pin the section heading's tokens).
- **Savings estimate:** ~2–3k tok/leg for a narration-only trim (estimate, static
  proxy).
- **Disposition:** plan item; **sequence with/after TODO's pending R5–R9 one-batch
  spec edit** so the pin-suite migration window is paid once (D11). Extension — delta
  only vs the known rebirth-prose item (§3 row states the boundary).

**N4 — harness-runs retention is manual (report-only default)**

- **Lens:** 1.4. **Evidence:** §1.4 — 278 MB corpus total (not all reclaimable);
  `bin/drive-retention.sh` report-only without `--apply`; MEASURED eligibility via
  the real classifier in report mode: 0 bytes eligible today in either tier (5
  not-aged / 7 waiting / 1 inflight-open); tool-reclaimable universe = heavy logs
  ~15.2 MiB + `wt/` worktrees ~12 MiB, gated quiet+done+≥14-day per run.
- **Cost denomination:** cost only — disk bytes, zero tokens (static proxy
  denomination inapplicable; no window/quota component).
- **Run-level effect:** cost only (plus corpus hygiene: bounded residue keeps the
  pinned enumeration corpora honest).
- **Effort:** trivial–small (schedule a periodic report+notify, or a confirm-gated
  `--apply`).
- **Savings estimate:** ~0 D10-unit tokens (denomination inapplicable). Disk,
  measured: **0 B eligible today**; upper bound of what the tool can EVER reclaim at
  the current corpus ≈ **27 MiB** (15.2 MiB heavy logs + 12 MiB worktrees) as runs
  age past the quiet+done+≥14-day gates. The ~278 MB corpus total is a SIZE, not a
  reclaimable figure — the bulk (per-run `tmp/` scratch + history
  `.md`/`.json`/`.jsonl`) is outside both tiers by design (§1.4). The scheduling
  value is BOUNDING future growth, not a one-time reclaim.
- **Disposition:** external-surface plan item (machine config — no repo diff). The
  retention CONTRACT's 3-layer drift is a KNOWN surface (§3) — N4 deliberately scopes
  to scheduling the existing tool only. Constraint if scheduling is ever
  automated/unattended `--apply`: the per-run advisory lock pre-declared at
  followups.md:408 (anchor "If `--apply` ever becomes automated/unattended, revisit
  with a per-run advisory lock (flock on `$RUN_DIR/.gc.lock`)") becomes mandatory;
  the manual/confirm-gated posture needs no lock.

## 3. Already known / out of scope — dedup exclusion table

All `file:line` cites as-of phaseBaseSha `ce12c42…` (pre-insertion); each row carries a
stable text anchor.

**(a) Surfaces checked** (every candidate finding was cross-checked against ALL of
these):

1. **07-08 audit § Dropped components — all 10 refuted items**
   (docs/efficiency-audit-2026-07-08.md:104, anchor "### Dropped components (refuted
   at verification)"): pressure-conditional Seam A/B; reviewer-prompt narrowing to
   "is-the-class-closed"; settled-scope re-audit prohibition; slice-review adoption as
   the phase review; plan+phasedesign collapse; same-invocation harden/finalize
   convergence on suite-green; 15/30-min wall-clock codex kill; blanket round-2+
   effort downgrade; textual "a pin exists"→P2; time-boxed overrule repros minting
   refutations. Nothing here re-proposes any of them (notably: NO review-layer
   trimming of any kind appears in §2).
2. **R1–R12 individually** (R1–R9 in TODO.md:250 § "/drive efficiency plan R1–R9";
   R10–R12 live ONLY in the 07-08 doc — TODO.md:273, anchor "Also out of scope for
   this plan: R10–R12"): R1 auto-resume (pending, TODO.md:297) · R2 codex-first
   overlap (**DONE PR #78**, TODO.md:286) · R3 push-notify parks (pending,
   TODO.md:317) · R4 codex progress-watchdog (**DONE PR #78**, TODO.md:338) · R5
   class-sweep contract (:359) · R6 delta-scoped re-reviews + suite-rerun ban (:376) ·
   R7 refutation ledger (:392) · R8 design author-verification (:414) · R9 pin-depth
   mutation-survival standard (:434) · R10 confirm-round diet
   (docs/efficiency-audit-2026-07-08.md:89) · R11 single-phase/single-slice fast paths
   (07-08 doc:94) · R12 phase-finding routing (07-08 doc:99).
3. **TODO whole-repo-audit items as a group** (TODO.md:5, anchor "## Whole-repo audit —
   bugs / logic / inconsistency / slop (2026-07-09)"), with the individually-collided
   items cited: `.gitignore` settings.local.json — TODO.md:158-162 (anchor
   "`.gitignore:19` — `.claude/settings.local.json` is excluded only by machine-local
   ignores"); statusline/rebirth-thresholds dual window table — TODO.md:87-101, marked
   **DONE** (anchor "restored `3bf4866`'s ordered 1M-first window-match table"), with
   its architectural dual-source follow-ups at TODO.md:617-621 (anchor "duplicated
   window table") and TODO.md:695-704 (anchor "TWO executable model tables"); finalize
   stale section — TODO.md:211-214 (anchor "the \"Phase-2 wiring obligations — NOT
   built here\" section describes long-shipped wiring").
4. **The four named followups entries** (.harness/followups.md): cross-file
   rebirth-prose duplication — :303 (anchor "[P3] Cross-file rebirth prose duplication
   across drive.md/drive-plan.md/drive-review.md"); bash↔python duplicate
   checkpoint/state-lint coverage — :295 (anchor "[P2] Duplicate behavioral coverage
   of checkpoint/state-lint"); CONTRIBUTING absence — :79 (anchor "The repo has no
   CONTRIBUTING.md / dev-setup doc"); Component D — :27 (anchor "Component D
   (forgery-proof driver)").

A candidate colliding with a DONE item is excluded as already-fixed.

**(b) Excluded candidates** (candidate → exact overlapping surface → disposition):

| Candidate (surfaced by this audit's lenses) | Overlapping surface | Disposition |
|---|---|---|
| finalize "Phase-2 wiring obligations" section is stale narration (lens 1.2: 3,161 B section) | TODO.md:211-214, anchor "describes long-shipped wiring … Rewrite present-tense (token-sweep pin migration)" | excluded |
| cross-file rebirth prose duplication (drive.md I1 / checkpoint sections ↔ drive-plan.md / drive-review.md) | followups.md:303, anchor "[P3] Cross-file rebirth prose duplication … (~150-250): collapse into one authoritative section" | **extension — delta only**: N3 ranks ONLY the section-concentration delta (in-file setup/resume narration beyond the duplicated rebirth prose); the duplicated-prose portion stays excluded |
| retention contract expressed in three drifting authority layers | TODO.md:590-599, anchor "expressed in THREE authority layers" | excluded (N4 scopes to SCHEDULING the existing tool, not its contract) |
| duplicated statusline/JSON window table (DRY candidate, hygiene lens) | TODO.md:87-101 (DONE; anchor "restored `3bf4866`'s ordered 1M-first window-match table") + TODO.md:617-621 (anchor "duplicated window table") / TODO.md:695-704 (anchor "TWO executable model tables") | excluded — already-fixed at the executable layer; the single-source design change is a known follow-up |
| `.claude/settings.local.json` missing from committed .gitignore (hygiene-lens classic) | TODO.md:158-162, anchor "`.gitignore:19` — `.claude/settings.local.json` is excluded only by machine-local ignores" | excluded |
| codex re-runs the full suites inside every review round (visible across the 73 codex-raw logs) | R6's suite-rerun ban — TODO.md:376-377, anchor "Delta-scoped round-N≥2 re-reviews (class-scoped, with suite-rerun ban)"; also docs/efficiency-audit-2026-07-08.md:69, anchor "### R6. Delta-scoped round-N≥2 re-reviews" | excluded |
| codex tail/outage burn (11 MB raw-log corpus; historical silent deaths) | R4 — TODO.md:338, anchor "DONE (PR #78, 2026-07-09). Codex progress-watchdog + outage degrade" | excluded — already-fixed |
| bash suite (139 s) re-tests python-covered checkpoint/state-lint behavior (lens 1.3 residual) | followups.md:295, anchor "[P2] Duplicate behavioral coverage of checkpoint/state-lint" | excluded (the runtime rider is noted in the TODO item's risk-weighing only) |
| seam/gate human-latency, round churn, review-layer cost (any form) | docs/efficiency-audit-2026-07-08.md:22, anchor "## 1. WHERE THE DAY GOES" (buckets A–F) + :118, anchor "## 3. WHAT NOT TO TOUCH" | excluded — prior audit's entire scope |

## 4. Known refutations (pre-declared review answers)

1. **Ledger append-only-header amendment plan (pre-declared).** Phase 2's archival
   split (QW1) WILL edit `.harness/decisions.md`'s header: the rule at
   decisions.md:10-11 (anchor "Append-only. Do not edit or remove prior entries") is
   amended to name the archival convention — entries older than the boundary move
   VERBATIM to `.harness/archive/`, the live file keeps its path, entry format, and
   append discipline. A review flag of the class "the diff edits prior ledger content /
   violates append-only" is answered here in advance: no entry is rewritten; the
   header amendment is the reviewed exception, planned before the edit.
2. **Pre-ship-absent ledger entries (known codex re-flag class).** Any test/artifact
   naming a `.harness` ledger entry not present in the branch pre-ship is BY DESIGN:
   the run's `$RUN_DIR` ledgers promote into `.harness/` at ship (CLAUDE.md:203-205
   region). The known refutation stands (memory: codex-reflags-preship-absent-ledger);
   do not add a committed entry mid-run — it breaks the ship gate's ≤1-commit
   allowlist.
3. **"flow.md is stale" — REFUTED** by spot-check: its content describes the live
   three-tier progressive design refinement and current stage commands (§1.4).
4. **"drive.md rides every session turn" — refuted at plan time (D3), re-stated here**
   so review does not re-raise it: CLAUDE.md:12 imports only `@OPERATING.md`; drive.md
   is per-/drive-leg context (§1.1b), not per-turn.
5. **"median cache_read 262k exceeds a 200k window" — not an anomaly:** the corpus
   contains 1M-window sessions; the figure is a per-record occupancy floor, not a
   200k-window claim.
6. **"hygiene classics" (committed bytecode, stale branches, unignored scratch) —
   REFUTED:** `git ls-files | grep -E '__pycache__|\.pyc$'` → 0; `.tmp*/` ignored
   (§1.4). No hygiene quick-win exists beyond the ledger split.
7. **WARN-only / pathological-input findings:** none arose; recorded as the standing
   discipline — a finding refuted with executed evidence in the faithful env is
   overruled WITH that evidence, never silently dropped.

## 5. Quick-win shortlist (Phase-2 input)

Exactly one item qualifies; the empty-adjacent shortlist is a valid outcome (D12) and
Phase 2 must not invent more.

**QW1 — `.harness/decisions.md` archival split (from N2).**

- **Change:** move the pre-2026-07 entries — lines 1–4093, 138 of 168 entries
  (`awk '/^### 2026-07/{print NR; exit}'` → 4094) — VERBATIM into
  `.harness/archive/decisions-pre-2026-07.md`; live file keeps path, entry format,
  append discipline, gains a 2–3-line index note pointing at the archive; amend the
  append-only header rule per §4.1. followups.md is NOT included (refuted below).
  No CLAUDE.md edit needed: its instruction (CLAUDE.md:203-205) is path-based and the
  live path is unchanged.
- **SLOC estimate:** ≤30 new/changed (index note + amended header rule + archive-file
  header); the verbatim content move is excluded from the bound (D12).
- **Before/after metric (name + measuring command):**
  - *newest entry date within the default read window* —
    `head -n 2000 .harness/decisions.md | grep -E '^### ' | tail -1`:
    before `2026-06-11 …` → after = the file's newest entry (2026-07-06 at this
    measurement; later at ship).
  - *entries beyond the window* —
    `awk 'NR>2000' .harness/decisions.md | grep -cE '^### '`: before 51 → after 0
    (post-split live file = 1,971 lines plus only the live-file share of the new
    lines — the 2–3-line index note + amended header rule, ≤10 lines; the archive
    file's header is not in the live file — comfortably within one default Read at
    split time; ship-time appends grow it later, and the `^### `-date metric above
    stays the binding check either way).
- **Risk:** exactly **7** in-repo surfaces reference the COMMITTED ledger —
  `grep -ln '\.harness/decisions\.md' tests/contracts/*.py test/*.test.sh bin/*.sh` →
  tests/contracts/{test_drive_base_preflight_wiring, test_drive_finalize_contract,
  test_drive_retro_contract}.py, test/{drive-base-preflight,
  drive-enforcement-e2e}.test.sh, bin/{drive-base-preflight.sh,
  drive-conformance.sh} — all reference the live PATH (unchanged) and/or append
  semantics; Phase 2 must verify none pins ARCHIVED entry content, then run the full
  canonical suite. (A loose `decisions\.md` grep also matches
  tests/contracts/test_drive_retention.py and
  tests/contracts/test_rebirth_handshake.py, but both reference ONLY the RUN-LOCAL
  `$RUN_DIR`/run-dir `decisions.md` — fixture history lists at :872/:1511 and
  checkpoint-source prose at :647/:667 respectively — so they are OUTSIDE the
  committed-ledger risk surface; an earlier draft over-counted 9 from the loose
  grep.)
- **Pin exposure:** both suites (the 3 pytest + 2 bash files above); expected green
  without migration since the pins target path/format, not pre-2026-07 entry
  content — proven by the full `bin/run-tests.sh` run, not assumed.

**REFUTED forecast items (E6 — Phase 2 must not build these):**

- *"… and possibly followups.md"* (the archival forecast's optional half) — REFUTED:
  followups.md is 1,144 lines (`wc -l`); a default 2,000-line Read already ingests it
  ENTIRELY — the recency defect the split fixes does not exist there.
- *"small hygiene/doc corrections"* (forecast quick-win #2) — REFUTED: no qualifying
  instance found (classics clean, flow.md current, all heavy docs live-referenced —
  §1.4, §4.3, §4.6). Phase 2's scope is QW1 only.
