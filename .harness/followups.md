# Follow-ups

Out-of-scope discoveries during engineering tasks. Bugs unrelated to the
current task, refactor opportunities, suspicious code, dependency upgrades,
etc. Subagents and the main session APPEND here instead of pausing or
addressing inline.

The human reviews this file periodically and decides what to promote to a
real task.

## Entry format

### YYYY-MM-DD -- Short title
**Found during:** which task / stage
**Where:** file:line or area of the codebase
**Observation:** one or two sentences
**Suggested action:** what would be worth doing about it (optional)
**Severity guess:** low | medium | high

---

## Entries

(append below this line)
## From run drive-review-hooks-20260603-135659

- **Component D (forgery-proof driver):** rewrite the per-slice loop as a deterministic external driver (Workflow/shell) so review is a function call, not a remembered step, and proof is produced out-of-band. Only this defeats an adversarial coordinator that forges SHA-bound review artifacts. The hook-based C+A+B delivered here defeats OMISSION (the observed failure) with auto-remediation; it does not claim forgery-proofness.
- **Extend git-truth enforcement to IMPLEMENT-stage** (test-presence, etc.) using the same conformance pattern.
- **2.1 gate matcher hardening (exotic git global-option forms):** `git_target_repo()` treats `-C`/`--git-dir`/`--work-tree` as last-path-wins; git actually *composes* stacked `-C a -C b` and `-C /repo --git-dir=.git`. The gate can wrong-target on these. /drive never emits `-C` forms (it cd-s into worktrees), and the ship gate (HEAD/whole-tree) backstops any merge-gate miss, so this is hardening vs adversarial/pathological input, not an omission-threat gap. Fix: model composed git path options properly.
