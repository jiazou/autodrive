You are starting the design phase of an engineering task.

First, read .harness/decisions.md to load prior decisions you must stay
consistent with.

Then invoke the `team-lead` subagent with the following scope (pass as the
Agent tool prompt verbatim, replacing the bracketed task placeholder):

----- BEGIN SUBAGENT SCOPE -----
Produce a design document for the following task. Do NOT implement
anything. Do NOT invoke team-implementer or team-reviewer.

Steps:
1. Read .harness/task.md if it exists; otherwise use the task description
   at the end of this prompt.
2. Read .harness/decisions.md to stay consistent with prior choices.
3. Read the relevant parts of the codebase for context.
4. Write .harness/design.md covering:
   - Goal (one paragraph)
   - Interfaces (exact signatures, types, endpoints)
   - Data flow (how data moves through the system)
   - Edge cases and failure modes (at least 5, with intended behavior)
   - Acceptance criteria (numbered, testable conditions)
   - Decisions (choices you made autonomously -- see Decision protocol below)
   - Out of scope
   - Open questions (expect ZERO to TWO entries; see Decision protocol)
5. Return the path to the design doc and a 3-line summary.

Decision protocol (this overrides any "ask the human" reflex):
- For design choices where you have a clear best option, TAKE IT. List
  alternatives and your reasoning in the "Decisions" section. Also append
  to .harness/decisions.md using the format in that file.
- Reserve "Open questions" for decisions that are genuinely close calls
  AND irreversible AND affect user-facing behavior. Expect zero to two
  per design, not five to ten.
- Default opinions (use unless the task says otherwise): match codebase
  conventions, use existing storage, fail-loud-in-dev/graceful-in-prod
  error handling, unit + integration tests, no new dependencies.
- If you genuinely cannot decide, write your top recommendation as the
  decision and flag your uncertainty in one sentence in the Decisions
  section. Do not block on it.

Out-of-scope discoveries during design: append to .harness/followups.md.
Do not address them in this design.

Task: $ARGUMENTS
----- END SUBAGENT SCOPE -----

After team-lead returns, surface to me:
- The 3-line summary
- The contents of the "Decisions" section (so I can see what was decided)
- Any "Open questions" entries (these are the only items requiring my input)

STOP and wait for my explicit approval before any implementation begins.
Do not invoke any other subagent on this command.