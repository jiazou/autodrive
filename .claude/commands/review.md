You are starting a review pass. The design must exist at .harness/design.md
and the implementation must already be on disk.

Determine N: count existing .harness/review-*.md files and add 1. If N > 2,
STOP and surface to me -- we've hit the loop cap and the implementer and
reviewer are not converging. Summarize what each side has been asserting.

Otherwise, invoke the `team-reviewer` subagent with the following scope.

CRITICAL CONTEXT BOUNDARY: Do NOT include any of the implementer's notes,
rationale, summary, or descriptions of what they did in the reviewer's
prompt. The reviewer judges the code against the spec on its own merits.
If you find yourself about to paraphrase what the implementer said, stop --
pass file paths only.

----- BEGIN SUBAGENT SCOPE -----
Audit the diff against the spec.
Spec: .harness/design.md
Prior decisions to respect: .harness/decisions.md
Changed files: [list paths from the most recent implementation]

Decision protocol (this overrides any "ask the human" reflex):
- When a finding's severity is ambiguous, PICK ONE. Do not return
  "is this blocking or major?" questions.
  - BLOCKING: production incident risk, data loss, security hole,
    spec violation that breaks acceptance criteria
  - MAJOR: clear bug, missing edge case the design listed, test gap on
    an acceptance criterion
  - MINOR: code quality, readability, performance with no spec impact
  - NIT: style; usually omit
- Do NOT flag style issues not specified by codebase conventions.
- Do NOT flag improvements the design marked out of scope.
- Out-of-scope discoveries (real bugs not related to this task):
  append to .harness/followups.md, do not include in this review.

Write .harness/review-N.md with structure:
  # Review N
  ## Verdict: CLEAN | FINDINGS
  ## Findings
  ### [SEVERITY] Short title
  **Where:** file:line
  **Issue:** what's wrong
  **Why it matters:** what breaks
  **Suggested fix:** what the implementer should do

CLEAN = no BLOCKING or MAJOR findings. FINDINGS = any BLOCKING or MAJOR.

Return only: the path, the verdict, and a one-line count
("3 findings: 1 blocking, 2 major" or "no issues").
----- END SUBAGENT SCOPE -----

After team-reviewer returns, surface the verdict to me. If FINDINGS, suggest
I run /implement again to address them. If CLEAN, suggest I run /codex for
a cross-model second opinion before /ship.