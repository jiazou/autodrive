# gstack review pipeline (opt-in)

A structured "engineering organization" workflow for product/feature work where
scope and architecture deserve human sign-off. This is **opt-in per project** —
invoke it when a task warrants the rigor, not on every change. For quick fixes,
refactors, and mechanical edits, work directly.

Act as a structured engineering organization: don't write implementation code
immediately on a feature request. Follow this sequence:

1. **Ideation & Scope:** For a new feature, run `/plan-ceo-review` first. Don't
   proceed until I approve the product vision.
2. **Architecture:** After product approval, run `/plan-eng-review` to lock down
   data flow, API contracts, and the test matrix. Wait for my sign-off.
3. **Implementation:** Only write code against the approved engineering plan.
4. **Validation:** Before claiming done, run `/review` for race conditions and
   production risks. For UI changes, run `/browse` to visually verify the frontend.
5. **Shipping:** Run `/ship` to automate PR creation and test execution.

These slash commands are gstack skills installed globally, so this pipeline works
in any project — but it is no longer a global mandate. See the alternative
`claude-harness` autonomous pipeline (`/plan` → `/implement` → `/review` →
`/codex` → `/ship`) for repos that prefer decide-and-document autonomy with only
two human checkpoints.
