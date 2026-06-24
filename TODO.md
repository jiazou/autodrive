# TODO

Architectural follow-ups deferred by /drive finalize passes.

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
