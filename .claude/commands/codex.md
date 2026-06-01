Run a cross-model second-opinion review on the most recent implementation
using gstack's /codex skill. This is your independent objectivity check --
a different model auditing the same diff against the same spec.

Steps:

1. Verify .harness/design.md exists and at least one .harness/review-N.md
   exists with verdict CLEAN. If not, stop and tell me what's missing.

2. Invoke gstack's codex review skill on the current diff. The exact
   invocation depends on how gstack registered itself in this project:
   - If gstack exposes /codex as a slash command: run /codex review
   - If gstack exposes it as a skill file: load
     ~/.claude/skills/gstack/skills/codex/SKILL.md and follow its
     instructions, passing the design path and changed-file paths

3. Capture codex's findings to .harness/codex-review.md with the same
   severity tags as team-reviewer uses.

4. Compare codex's findings to the most recent team-reviewer output:
   - Findings BOTH flagged: high confidence, definitely real
   - Findings only codex flagged: codex-only -- pay closest attention here,
     these are the bugs Claude missed
   - Findings only team-reviewer flagged: claude-only

5. Decision protocol: if codex-only findings exist at BLOCKING or MAJOR
   severity, suggest I run /implement to address them -- do NOT auto-loop
   into /implement. Cross-model disagreement is exactly the kind of moment
   I want to see.

Return: the verdict (AGREES_CLEAN | AGREES_FINDINGS | DISAGREES) and a
summary of the comparison. After this returns AGREES_CLEAN, suggest /ship.