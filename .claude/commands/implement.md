You are starting the implementation phase. The design must already exist at
.harness/design.md -- if it doesn't, stop and tell me to run /plan first.

Read .harness/decisions.md to load prior decisions you must stay consistent
with. Then check .harness/ for the highest-numbered review-N.md file; if any
exist, you are addressing review findings, not doing a fresh implementation.

Invoke the `team-implementer` subagent with the following scope:

----- BEGIN SUBAGENT SCOPE -----
Read .harness/design.md. Read .harness/decisions.md. If a review file
exists at .harness/review-N.md (highest N), also read it.

Implement code to satisfy every acceptance criterion in the design.
If addressing review findings, address every BLOCKING and MAJOR finding.
Match codebase conventions. Write tests for each acceptance criterion.

Decision protocol (this overrides any "ask the human" reflex):
- For implementation choices not specified by the design (variable names,
  internal structure, helper extraction, test organization, library
  choices within the existing stack), DECIDE based on codebase conventions
  and the default opinions in CLAUDE.md. Do not return questions.
- If you must deviate from the design to make it work, DO SO and flag the
  deviation in your one-line return note. Append the deviation as a
  decision entry in .harness/decisions.md.
- Out-of-scope discoveries (unrelated bugs, refactor ideas): append to
  .harness/followups.md. Do not address them inline.
- Escalate to me only if you hit something that meets ALL the criteria in
  the CLAUDE.md decision policy (irreversible AND no clear recommendation
  AND in scope). Otherwise, decide.

Return only:
- List of changed file paths, one line per file describing what changed
- Any spec deviations or autonomous decisions you want flagged
- DO NOT include reasoning, justifications, or design discussion. Keep
  the return tight. The reviewer will not see this summary.
----- END SUBAGENT SCOPE -----

After team-implementer returns, surface the changed-file list to me. Do not
invoke any other subagent on this command. Suggest I run /review next.