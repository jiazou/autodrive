You are completing the engineering task. This is the second and final
human checkpoint.

Verify all of these:
1. .harness/design.md exists and was approved (look for my approval in the
   session, or the existence of any .harness/review-*.md as evidence
   implementation already proceeded)
2. Implementation changes are on disk
3. At least one .harness/review-N.md exists with verdict CLEAN
4. .harness/codex-review.md exists with verdict AGREES_CLEAN
5. Tests pass (run them now if not already run since the last change)

If any check fails, STOP and tell me which one and what to do.

If all pass:
- Read .harness/decisions.md and surface a one-line summary of every
  decision made autonomously during this task
- Read .harness/followups.md and surface anything added during this task
- Propose a commit message and PR description based on the design and the
  changes
- Do NOT actually open the PR or push -- that's my call
- Wait for my approval to proceed

After my approval, run the actual git commit and PR creation.