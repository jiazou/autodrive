---
name: decant
description: |
  End-of-session distillation. Surveys memory entries written during the
  session, classifies each as universal (global candidate) vs workflow-specific,
  checks for duplicates, identifies missing lessons, and recommends promotions
  to the canonical OPERATING.md. Surfaces the meta-pattern under the session's corrections.
  Use at the end of any non-trivial session — especially before clearing
  context, switching to a different effort, or after the user gives
  methodological feedback that should outlive this conversation.
triggers:
  - decant
  - distill
  - end of session
  - wrap up
  - clear context (when invoked before clearing)
  - what did we learn
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
  - Glob
  - Grep
---

# Decant — end-of-session learning consolidation

This skill is a checklist, not autonomous. Each step is explicit so the output is
predictable.

## Step 1 — Inventory what was saved this session

Read `MEMORY.md` for this project. Identify every entry added or modified
during this session (compare mtimes; the user can usually point at "since X").
List each with its description line.

Also `git grep` the project memory directory for files modified in the last
session window. Some entries may have been written by subagents.

If 0 new entries: skip to step 5 (the "no lessons saved" case). Otherwise continue.

## Step 2 — Classify each entry

For each new entry, label as ONE of:

- **Universal** — a **software-engineering working principle** that applies
  across every codebase and language. Examples: design doc updates before
  implementation; cite evidence as OLD/NEW; present choices with English +
  technical. Candidates for the canonical operating rules in
  **`claude-harness/OPERATING.md`** (which the global `~/CLAUDE.md` imports).
  **Guard against over-classification:** "broadly applicable *within one
  domain*" is NOT universal. A heuristic that holds across all of, say, hardware
  troubleshooting is still domain-specific — OPERATING.md is for how Claude does
  *software-engineering work*, not for any-broadly-useful tip. If a lesson isn't
  about writing/reviewing/shipping code, it's almost certainly domain-specific.
- **Workflow-specific** — tied to a specific review pattern, tooling, or
  collaboration setup. Stays in project memory. Example: "every architectural
  decision gets parallel Claude+Codex review" assumes that workflow exists.
- **Domain-specific** — tied to a particular domain (this codebase's domain, or
  any narrow subject area like hardware/peripheral debugging), even when broadly
  applicable *within* that domain. Stays in project memory. Examples: "classifier
  must respect its input analysis" assumes a rule-based classifier pipeline;
  "isolate the physical connection path before firmware" is a hardware-debugging
  heuristic, not a coding rule.

Lead with the English meaning of each rule, NOT its filename.

## Step 3 — Check duplicates + existing promotions

Two checks:

- `ls` the project memory directory for files with overlapping concepts.
  Duplicate filenames or near-duplicate descriptions = the user (or another
  subagent) already saved it; delete one.
- `grep` MEMORY.md for promotion markers (the
  `**promoted to canonical claude-harness/OPERATING.md** YYYY-MM-DD` line in the
  index is the authoritative signal). If an entry already shows that marker, it's
  promoted; don't propose it again.

## Step 4 — Identify missing lessons

Three questions to scan the session for:

1. **Did the user correct me on a recurring pattern that isn't yet saved?**
   Reread the session for "no", "actually", "let me clarify" turns from the
   user. Each is a candidate.
2. **Did I hit a tooling failure mode multiple times?** Tools that bail,
   timeouts, retries — if I hit the same failure ≥2x, the workaround is a
   saveable lesson.
3. **Did a synthesis or audit produce a verdict that contradicted what I
   originally thought?** That's a debiasing rule worth capturing.

Save anything missing as a new project-memory entry now. Use the Write tool;
follow the existing frontmatter format.

## Step 5 — Surface the meta-pattern (if any)

Sometimes the individual corrections cluster around a single principle (e.g.,
"don't skip rigor on intermediate work products"). Surface it as ONE sentence,
not as a new rule. Meta-patterns usually don't survive as standalone rules —
they're observation about the rules' shared structure, useful for the user.

## Step 6 — Recommend promotions; don't auto-edit OPERATING.md

Editing the canonical `OPERATING.md` (the rules everything imports) is
consequential. Present recommendations as a question with explicit options:

```
AskUserQuestion(
  question: "Promote these N universal rules to claude-harness/OPERATING.md?",
  options: [
    { label: "Yes — add all N + memory pointers (Recommended)",
      description: "<English: what changes for future sessions> ... <Technical: which files edited, format of added lines>" },
    { label: "Yes, but only these specific rules: ...",
      description: "..." },
    { label: "No — keep in project memory only",
      description: "..." },
  ]
)
```

If the user approves, perform the edits with care: add each rule to the
appropriate section of `claude-harness/OPERATING.md`, and update MEMORY.md to
mark the entry with the `**promoted to canonical claude-harness/OPERATING.md**`
marker.

## Step 7 — Final output

Produce a tight summary (~150 words) for the user:

- N entries saved this session (split into universal / workflow / domain).
- Duplicates cleaned.
- Missing lessons added (if any).
- Meta-pattern (one sentence, if applicable).
- Promotion recommendation status.

Don't restate full rule text — point at memory files by name. The user can
read the source of truth themselves.

## Anti-patterns to avoid

- **Don't auto-edit `OPERATING.md` without explicit user confirmation.**
- **Don't propose promotion of rules that are workflow- or domain-specific.**
  Just because a lesson was useful here doesn't make it universal.
- **Don't write new memory entries that duplicate existing ones.** Search
  first; merge into existing or skip.
- **Don't ramble through the session narrative.** The user already lived
  through it. Focus on what to do with the lessons, not what we learned.
- **Don't run this skill if 0 new entries were saved AND the user explicitly
  hasn't given methodological feedback.** Nothing to distill.
