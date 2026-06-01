# Claude Harness

Autonomous engineering pipeline for Claude Code. Combines:

- wshobson `agent-teams` plugin (team-lead, team-implementer, team-reviewer subagents)
- gstack `/codex` for cross-model second-opinion review
- Custom slash commands: `/plan`, `/implement`, `/review`, `/codex`, `/ship`
- A "decide and document" decision policy that overrides the default "ask the human" reflex

## Workflow

    /plan <task>   -> team-lead writes .harness/design.md  [PAUSE for approval]
    /implement     -> team-implementer writes code
    /review        -> team-reviewer writes .harness/review-N.md (loop up to 2x with /implement)
    /codex         -> cross-model review                   [PAUSE for approval]
    /ship          -> final verification + PR prep

## Setup

1. Install wshobson `agent-teams`:

       gh repo clone wshobson/agents /tmp/wshobson
       mkdir -p .claude/agents
       cp /tmp/wshobson/plugins/agent-teams/agents/team-*.md .claude/agents/

2. Install gstack (for `/codex`):

       git clone --single-branch --depth 1 \
         https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
         && cd ~/.claude/skills/gstack && ./setup

3. Start a session in this directory:

       claude

See `CLAUDE.md` for the full workflow and decision policy.

## Files

- `CLAUDE.md` -- coordinator workflow, decision policy, invariants
- `.harness/decisions.md` -- append-only autonomous-decision ledger
- `.harness/followups.md` -- append-only out-of-scope discoveries
- `.claude/commands/{plan,implement,review,codex,ship}.md` -- slash command wrappers

## Generated artifacts (gitignored)

`.harness/design.md`, `.harness/implementation/`, `.harness/review-*.md`,
`.harness/codex-review.md`, `.harness/state.json` are produced per task and
not committed.