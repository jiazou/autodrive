# GitHub-MCP + native-worktree hook-stdin fixtures

Full PreToolUse hook-stdin payloads (`session_id`, `cwd`, `hook_event_name`,
`tool_name`, `tool_input`) that drive `test/drive-tool-gate.test.sh`. They exercise
`bin/drive-tool-gate.sh` — the sibling PreToolUse hook that deny-routes GitHub-MCP write
tools and the native worktree tools back to the gated Bash paths while a `/drive` run is
active on the same repo.

## Schema-derived, NOT live-captured (D9)

No GitHub MCP server is configured on this machine, so these shapes are **derived from
the vendor's tool definitions, not captured from a live server**. Every fixture carries a
`"_provenance"` header naming the source, URL, and retrieval date. The tool names and
`tool_input` parameter names were **re-verified at implement time (2026-07-05)** against
the official `github/github-mcp-server` Go tool definitions
(`pkg/github/repositories.go`, `pkg/github/pullrequests.go`) —
`create_or_update_file`(owner, repo, path, content, message, branch, sha),
`delete_file`(owner, repo, path, message, branch),
`push_files`(owner, repo, branch, files, message),
`create_branch`(owner, repo, branch, from_branch),
`create_pull_request`(owner, repo, title, head, base, body, …),
`merge_pull_request`(owner, repo, `pullNumber`, `merge_method`, …),
`update_pull_request`(owner, repo, `pullNumber`, title, body, state, base, …),
`update_pull_request_branch`(owner, repo, `pullNumber`, `expectedHeadSha`).
Note the mixed casing the vendor ships: `pullNumber` / `expectedHeadSha` are camelCase
while `from_branch` / `merge_method` are snake_case — the hook keys only on `owner`/`repo`
(plus the tool-name suffix), so casing of the other params is not load-bearing.

**Residual (documented, not defended):** these fixtures pin a vendor-owned, fast-moving
schema. If the vendor renames or adds a write tool, the settings matcher is a clean
non-match → the hook never fires → silent fail-OPEN. That is a named threat-model
residual with a retirement condition (delete this hook when the harness ships
conditional/managed tool policy) — see `docs/drive-enforcement.md` and `SECURITY.md`.

## Fixtures

Positive (write-class — the enumerated matcher selects these; each carries `owner`+`repo`):
`create_or_update_file.json`, `delete_file.json`, `push_files.json`, `create_branch.json`,
`create_pull_request.json`, `merge_pull_request.json`, `update_pull_request.json`,
`update_pull_request_branch.json`.

Negative (the matcher must NOT select these): `list_pull_requests.json`,
`get_file_contents.json` (read tools on the same server), `other_server_write.json`
(`mcp__linear__create_issue` — unrelated server, non-matching suffix).

Native-tool: `agent-worktree.json` (`Agent`, `tool_input.isolation:"worktree"`),
`agent-plain.json` (`Agent`, no `isolation` — the hot path), `enter-worktree.json`
(`EnterWorktree`). Their `cwd` here is a placeholder; the test rewrites `.cwd` to a real
temp worktree / matching-origin clone so the repo-scoped worktree deny actually fires.

`owner`/`repo` on the write fixtures are `octo-org`/`drive-fixture-repo`; the test points
a temp run repo's `origin` at that owner/repo so the MCP write is scoped as same-repo.

**Fixtures test hook LOGIC, not platform INTERCEPTION.** Piping `agent-worktree.json` /
`enter-worktree.json` into the hook exercises the hook's control flow, not whether the
platform actually FIRES a PreToolUse event for a real isolated `Agent` / `EnterWorktree`
dispatch. That interception is a distinct, named residual
(`platform-may-not-fire-PreToolUse-on-native-worktree-tools`). A live deny capture (AC-16)
would require the gate wired into the live `~/.claude/settings.json` — the Gate-B activation
ops step, out of this slice's scope — so no live evidence is captured here. Per AC-16's
fallback the criterion is **discharged by that named residual** (not proven), not by these
fixtures — see `docs/drive-enforcement.md`.
