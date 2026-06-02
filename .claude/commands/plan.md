You are running the PLAN stage (Stage 1). Two steps: a planner subagent AUTHORS
a rough design, then gstack `autoplan` REVIEWS it. (autoplan is a reviewer, not
an author — it cannot produce a design from a raw task, so we author one first.)

First, read .harness/decisions.md to load prior decisions you must stay
consistent with.

## Step 1 — Author a rough design (planner subagent)

Spawn a generic planner subagent (the Agent tool — NOT a wshobson team-*
subagent) with the scope below.

----- BEGIN SUBAGENT SCOPE -----
Produce a rough design document for the task. Do NOT implement anything.

Steps:
1. Read .harness/task.md if it exists; otherwise use the task at the end of
   this prompt.
2. Read .harness/decisions.md to stay consistent with prior choices.
3. Read the relevant parts of the codebase for context.
4. Write .harness/design.md covering:
   - Goal (one paragraph)
   - Interfaces (exact signatures, types, endpoints)
   - Data flow
   - Edge cases and failure modes (at least 5, with intended behavior)
   - Acceptance criteria (numbered, testable)
   - Decisions (choices made autonomously)
   - Out of scope
   - Open questions (zero to two — genuine close calls only)
5. Return the design path and a 3-line summary.

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision
Principles (see CLAUDE.md). For design choices with a clear best option, TAKE IT and record
it under "Decisions"; also append to .harness/decisions.md with a Classification
field. Reserve "Open questions" for genuine close calls. Out-of-scope discoveries
→ .harness/followups.md.

Task: $ARGUMENTS
----- END SUBAGENT SCOPE -----

## Step 2 — Review the rough design (gstack autoplan)

Once .harness/design.md exists, run gstack `autoplan` on it. autoplan runs the
CEO → Design → Eng → DX reviews at full depth, auto-deciding intermediate
questions with the 6 principles, and ends at its OWN final approval gate.

- Invoke it as the gstack skill (so its runtime semantics apply): run `/autoplan`
  pointed at .harness/design.md, or load
  ~/.claude/skills/gstack/autoplan/SKILL.md and follow it on that file.
- **Gate A is autoplan's terminal approval gate.** Do NOT add a second gate of
  your own. Surface what autoplan surfaces (taste decisions, User-Challenges).
- autoplan writes the reviewed plan back; ensure the final reviewed design lands
  in .harness/design.md (copy it there if autoplan wrote elsewhere).

## After this stage

- If autoplan's gate returns APPROVED → update .harness/state.json
  (stage=implement, lastGate="A") and suggest /implement.
- If autoplan produced no approved design (cancelled/rejected) → STOP and report
  what is missing.

Do not begin implementation on this command.
