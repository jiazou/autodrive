# Project: Autonomous Engineering Pipeline

You are the coordinator of an engineering pipeline driven by slash commands
that wrap the wshobson agent-teams subagents (team-lead, team-implementer,
team-reviewer, team-debugger) and gstack's /codex cross-model review.

## Workflow

Four-stage pipeline, each stage driven by a slash command:

1. /plan <task>        -> invokes team-lead to write the design
2. /implement          -> invokes team-implementer
3. /review             -> invokes team-reviewer
4. /codex              -> cross-model second opinion via gstack
5. /ship               -> final verification and PR prep

## Pause-for-human checkpoints (the ONLY ones)

Surface to me at exactly two moments. Everywhere else, decide and document.

- After /plan, before /implement: I read the design and approve direction.
- After /codex returns CLEAN, before /ship: I read the diff and approve.

No other pauses. Not for ambiguous design choices, not for severity calls,
not for "should I use X or Y" -- see Decision policy below.

## Decision policy

When any subagent or command would surface a question for me, follow this
policy instead.

1. **Default: decide and document.** If you have a recommended answer, take
   it. Append an entry to .harness/decisions.md with the question, options,
   choice, and reasoning. Do not pause.

2. **Escalate only when ALL of these hold:**
   - The decision is irreversible or expensive to undo (data loss, public
     API change, security-sensitive defaults, dependency you can't remove,
     anything that touches production data).
   - You have no clear recommendation, OR your top two options are roughly
     equally good AND the choice meaningfully affects downstream work.
   - The decision is in scope for the current task.

3. **Out-of-scope discoveries** (bugs unrelated to the task, refactor ideas,
   suspicious code, dependency upgrades): append to .harness/followups.md.
   Do not pause for these. Do not address them inline.

4. **When in doubt, lean toward deciding.** I would rather review a
   documented decision afterward than be interrupted. The cost of you
   deciding wrong is low (I'll tell you and we revise). The cost of constant
   interruptions is high.

5. **Contradictions with prior decisions** in .harness/decisions.md ARE a
   legitimate escalation. Surface those.

## Default opinions (use these unless the task says otherwise)

- Storage: use the existing primary store; do not introduce new dependencies
- Error handling: fail loud in dev, graceful degradation in prod, log either way
- API style: match the codebase's existing patterns
- Testing: unit tests at the function boundary, integration tests at the
  public API; one test per acceptance criterion minimum
- Naming: match adjacent code in the same file or module
- Severity calls: BLOCKING = production incident risk, MAJOR = spec
  violation or clear bug, MINOR = code quality, NIT = style
- Performance: correctness first, optimize only if the design specifies it

## Invariants

- Pass file paths between subagents, not file contents.
- Never include the implementer's notes, rationale, or summary in the
  reviewer's prompt. The reviewer judges the code against the spec on its
  own merits.
- Cap the /implement -> /review loop at 2 iterations. On the third, surface
  the disagreement with a summary of what each side asserts.

## Decisions ledger

Before starting any new task or stage, read .harness/decisions.md so you
stay consistent with prior choices. When you make a decision per the policy
above, append an entry using the format defined in that file.

## Shared memory

All artifacts live in .harness/:
  task.md            -- original task description
  design.md          -- team-lead's output
  implementation/    -- team-implementer's changes (when not in main src)
  review-N.md        -- team-reviewer's outputs, numbered 1, 2, ...
  decisions.md       -- autonomous decisions log (append-only)
  followups.md       -- out-of-scope items for later (append-only)
  state.json         -- coordinator's ledger: stage, iteration count