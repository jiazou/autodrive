# Codex refutations — durable cross-run adjudications

When a /drive coordinator OVERRULES a codex P1 with evidence and the adjudication has
durable cross-run value, the entry lands here (promoted from
`$RUN_DIR/codex-refutations-pending.md` by drive-ship.md's activation-aware step).
Usage + replay rules (binding):

- **Bounds (the five, from drive-review.md § Refutation ledger):** (1) every entry is
  REPLAYABLE — committed entries ALWAYS carry an executable hermetic `env -i` line
  (doc-anchored refutations encode their cites as repo-relative greps); (2) entries may
  enrich REVIEW re-audit prompts ONLY — NEVER harden/finalize auditor prompts (voice
  independence); (3) entries are finding-specific, never class-level; (4) a P1→P2
  downgrade needs the coordinator's own executed fail-safe repro; (5) a repro timeout
  refutes nothing and voids nothing.
- **Replay rule:** on a re-flag, re-execute the recorded `env -i` line verbatim from the
  repo root at the reviewed tip. A differing result (output/exit) ⇒ the entry is VOID
  and the finding stands, adjudicated fresh. An executed red in the faithful env ALWAYS
  defeats an entry, whatever this ledger says.
- **Hermeticity:** the recorded env IS the complete env by construction (`env -i` +
  explicitly set vars; repo-relative cwd). Entries that cannot run hermetically are
  INELIGIBLE here and stay run-local in `$RUN_DIR/codex-refuted-<scope>.md`.

Entry schema:

```
## CR-<n> — "<one-line finding>" — REFUTED (<first-seen runId, date>)
- recurrence: <evidenced runs/rounds this class re-flagged>
- finding (specific): <the exact finding this entry refutes — never class-level>
- evidence: <file:line cites at a named SHA + reasoning>
- repro (hermetic): `env -i PATH=/usr/bin:/bin [VAR=v …] sh -c '<repo-relative command>'`
    — expected: <exact output/exit>
- scope qualifiers: <when it applies / does not>
```

## CR-1 — "a test/spec references a `.harness/` ledger entry absent from the branch" — REFUTED (r5r9-roundchurn-20260714-084250, 2026-07-14)
- recurrence: re-flagged in every run whose tests/specs name run-ledger entries (memory
  `codex-reflags-preship-absent-ledger`; e.g. the r2r4 finalize rounds).
- finding (specific): a committed test or spec cites a `.harness/decisions.md` /
  `.harness/followups.md` entry (a D-number / followup line) that does not exist in the
  branch's committed ledger files.
- evidence: the promotion-at-ship contract — run ledgers live in `$RUN_DIR` during the
  run and are appended to the committed `.harness/` ledgers only by ship's single ledger
  commit (drive-ship.md § Ship worktree + ledger promotion, "Promote the run ledgers";
  CLAUDE.md's run-state notes the committed repo ledgers are "promoted at ship"). The
  entry is absent pre-ship BY DESIGN, not by omission.
- repro (hermetic): `env -i PATH=/usr/bin:/bin sh -c 'grep -q "Promote the run ledgers" .claude/commands/drive-ship.md && grep -q "promoted at ship" CLAUDE.md'`
    — expected: exit 0
- scope qualifiers: applies ONLY while the referenced entry exists in the active run's
  `$RUN_DIR` ledgers awaiting ship (the replayer confirms that half in-run); a citation
  matching nothing in the run's `$RUN_DIR` ledgers either is a genuine finding, not
  covered here.

## CR-2 — "the R6 delta-focused round skips the mandated full-scope re-audit after logic-bearing fixes" — REFUTED (r5r9-roundchurn-20260714-084250, 2026-07-14)
- recurrence: raised at this run's design-review round 1 (decisions.md D-15 / RF-1)
  against audit sole-catcher §3.3.
- finding (specific): the delta-focused re-review form (drive-review.md § Round form on
  eligible re-reviews) violates the forced fresh full-scope re-audit after a
  logic-bearing fix.
- evidence: the landed clause's terminal invariant — the CLAUDE voice reviews FULL scope
  every round (including the round that records CONVERGED), and the delta-focused codex
  prompt carries the verbatim full-scope license "you MAY flag any P1 anywhere in
  scope"; every round is a fresh dual-voice dispatch counted inside cap-8 (audit
  sole-catcher #8, docs/efficiency-audit-2026-07-08.md — delta rounds are "accounted
  inside" the cap, not around it).
- repro (hermetic): `env -i PATH=/usr/bin:/bin sh -c 'grep -q "anywhere in scope" .claude/commands/drive-review.md && grep -q "accounted inside" docs/efficiency-audit-2026-07-08.md'`
    — expected: exit 0
- scope qualifiers: refutes re-flags of the MECHANISM only; a finding that the
  implemented WORDING drops the open-ended hunt is a NEW finding against new text — not
  covered by this entry.
