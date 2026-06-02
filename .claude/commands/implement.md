You are running the IMPLEMENT stage (Stage 2). This stage is harness-owned —
it does NOT call any gstack skill. The design must already exist at
.harness/design.md; if it doesn't, stop and tell me to run /plan first.

Read .harness/decisions.md to load prior decisions you must stay consistent
with. Then check .harness/ for the highest-numbered review-N.md file; if any
exist, you are addressing review findings, not doing a fresh implementation.

Spawn a generic implementer subagent (the Agent tool — NOT a wshobson team-*
subagent) with the scope below. Pass file PATHS, never file contents.

----- BEGIN SUBAGENT SCOPE -----
You are the implementer. Read these files (paths, not contents, are given so
you read the current versions yourself):
- .harness/design.md          (the spec — implement to satisfy it)
- .harness/decisions.md        (prior decisions to stay consistent with)
- .harness/review-N.md         (highest N, IF it exists — you are addressing
                                its findings, not starting fresh)
- .harness/codex-review.md     (IF it exists — the cross-model findings. Codex-
                                only findings live ONLY here, so you MUST read it)

Implement code to satisfy every acceptance criterion in the design. If a review
exists, address every BLOCKING and MAJOR finding from BOTH review-N.md AND
codex-review.md — codex-only findings are real bugs the Claude reviewer missed,
do not skip them. Match codebase conventions. Write at least one test per
acceptance criterion.

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision
Principles (see CLAUDE.md).
- For implementation choices not pinned by the design (names, internal structure,
  helper extraction, test layout, library choices within the existing stack),
  DECIDE per codebase conventions + the principles. Do not return questions.
- If you must deviate from the design to make it work, DO SO and flag it in your
  return note; append the deviation to .harness/decisions.md with a
  Classification field (Mechanical | Taste | User-Challenge).
- Out-of-scope discoveries (unrelated bugs, refactor ideas): append to
  .harness/followups.md. Do not address them inline.

Return a STATUS contract as the FIRST line, then the changed-file list. Use
EXACTLY one status:
- `STATUS: DONE` — every acceptance criterion is met and its test is written and
  passing. Follow with the changed-file list (one line per file: path — what
  changed). Add a short "Flagged:" line ONLY for spec deviations / Taste or
  User-Challenge decisions you logged. No other rationale — the reviewer will not
  see this summary.
- `STATUS: BLOCKED — <reason>` — you hit a non-decision blocker you cannot
  resolve (missing dependency/tool, environment failure, internally
  contradictory spec). State the blocker and what would unblock it. Include any
  partial changed-file list.
- `STATUS: NEEDS_CONTEXT — <question>` — a genuine User-Challenge: the design's
  direction looks wrong and both the cheap fix and the right fix diverge in a way
  only the human can adjudicate. State the one question. Do not guess.
----- END SUBAGENT SCOPE -----

After the subagent returns, act on STATUS:
- **DONE** → surface the changed-file list + any "Flagged:" line. Update
  .harness/state.json (stage=review). Suggest I run /review.
- **BLOCKED** → STOP. Surface the blocker verbatim. Do not loop. This is a
  non-decision STOP — the 6 principles cannot answer a missing-tool or
  contradictory-spec fact. Tell me what would unblock it.
- **NEEDS_CONTEXT** → STOP. Surface the question via AskUserQuestion (if
  available; if not, report `BLOCKED — AUQ unavailable` and wait). This is the
  User-Challenge escalation path.

Do not invoke any other subagent on this command. Pass file paths only — never
include the implementer's notes or rationale in any later /review prompt.
