# Mission Control — Related Work / Prior Art

Compiled 2026-06-02 to avoid reinventing the wheel. Nobody has stitched *task-tracking +
multi-agent-session-tracking + morning digest over a markdown vault* into one solo harness —
but every layer is solved. Verdict column = what Mission Control should steal vs skip.

## 1. Multi-agent session orchestration / dashboards

| Project | What it is | Steal / Skip |
|---|---|---|
| **Conductor** | Mac app: git-worktree-per-agent + kanban UI, per-session file-change sidebar | **Steal:** worktree-per-task as the isolation unit (code projects only) |
| **Claude Squad** | Terminal-native (tmux + worktrees) manager for many parallel agents | **Steal:** pure-terminal model, no GUI dependency |
| **vibe-kanban** | Kanban board over coding-agent sessions | Skip (board UI overkill for solo) |
| **Marc Nuri's AI Coding Agent Dashboard** | Sessions push state via **Claude Code notification hooks**; heartbeat + enricher chain | **Steal — the data model, ~verbatim:** project/branch · status · task · context-usage · PR · last-heartbeat, captured passively via hooks |
| **Claude Code Agent View** (native) | "Agent inbox": one table, **Running / Waiting / Done**, waiting floats to top; "peek" to read+reply inline | **Steal:** three-state model + "blocked-needs-me" as primary sort (already in our spike) |
| **Octogent / Agent Session Center / PI Dashboard** | Heavy web dashboards, 20+ sessions, inter-agent messaging, 3D viz | **Skip:** built for fleets, not one operator |

## 2. Binding agent sessions to work items (weakest prior art)

| Source | Idea | Steal / Skip |
|---|---|---|
| **Addy Osmani — "Conductors to Orchestrators"** | Work item = the issue; agent opens a PR referencing it; link is `issue ⇄ branch ⇄ PR`. Human work front-loaded (spec) + back-loaded (review) | **Steal:** encode task ID in the branch name so task→sessions binding is *free* for code work |
| **GitHub Copilot agent** | Assigns an agent to an issue, posts a PR back | **Steal:** the assign-then-review loop shape |
| (general) | Most session managers **don't** bind sessions to tickets — binding is implicit in branch name | **This is the gap Mission Control fills explicitly** (bindings.jsonl) |

**Key principle stolen:** task status = **rollup** of its sessions' states (blocked if any bound
session is Waiting) — never tracked independently. (A "done" task with a stuck agent is the trap.)

## 3. Maximizing parallelism (planning theory)

| Approach | Why it works | Steal / Skip |
|---|---|---|
| **Critical-Path-First** | The longest dependency chain is the day's floor; parallelism can't shorten it — protect it | **Steal:** tag tasks `depends_on:`, compute critical path, lead the standup with it |
| **Non-critical-first dispatch** | Fan idle agent capacity at off-critical-path work so *you* stay on the critical path | **Steal:** "what can I fan out right now" = ready, non-critical tasks |
| **WIP limits / Theory of Constraints** | Your bottleneck is *your* review bandwidth, not agent count | **Steal:** cap concurrent **sessions waiting on you**, not running ones |
| Formal DAG scheduling (PSA-PDAG etc.) | Academic | **Skip** the machinery, keep the concepts |

## 4. Morning digest / standup automation

| Source | Idea | Steal / Skip |
|---|---|---|
| **Pieces — automating standups** | Data already lives in commits/PRs/tickets; digest *re-presents*, never asks you to log | **Steal:** generate entirely from passive sources (git + session heartbeats + vault frontmatter) |
| **n8n morning-standup builds** | One scheduled job aggregates activity → short narrative to where you already look; documented morale boost | **Steal:** scheduled Claude job writes the daily note; lead with the 2 action items (Waiting sessions + critical path) |
| Hosted standup SaaS (Hubstaff, Kollabe, RunSteady) | Team-async tooling | **Skip:** your digest is a local job |

## 5. PARA / Obsidian-based personal operating systems

| Source | Idea | Steal / Skip |
|---|---|---|
| **ballred/obsidian-claude-pkm** | `/daily` `/weekly` `/monthly` slash commands, **PostToolUse auto-commit hook**, session-init briefing — *"zero deps, bash + markdown"* | **Steal:** the command trio + auto-commit + session-init; perfectly fits the no-plugins rule |
| **Dave Drach — "Personal OS with Obsidian + Claude"** | Strategic cascade: 3-Year → Yearly → Project → Monthly → Weekly → Daily, wikilinked; each project carries its own CLAUDE.md | **Steal:** the cascade as the linking spine so every task traces up to a goal |
| **AImaker — PARA + Claude Code + Obsidian** | Tasks inside project folders; Claude edits markdown directly | Already how Jia's vault works — **confirms the design** |
| Obsidian plugins (Periodic Notes, Tasks, Dataview) | Plugin-based periodic notes/queries | **Skip:** markdown-native commands do the same, respects no-plugin rule |

---

## Net "build" recommendation (from the research)

A thin layer that (a) captures session heartbeats from Claude Code hooks into the binding
ledger, (b) computes a critical path + WIP state over the vault's tasks, and (c) emits a short
morning daily-note digest — all in bash + markdown on the existing vault. **Every component is
proven; the only novelty is the integration** for a solo operator running many Claude sessions.

### Sources
- Marc Nuri — AI Coding Agent Dashboard: https://blog.marcnuri.com/ai-coding-agent-dashboard
- BuildFastWithAI — Claude Code Agent View: https://www.buildfastwithai.com/blogs/claude-code-agent-view-guide
- Addy Osmani — Conductors to Orchestrators: https://addyosmani.com/blog/future-agentic-coding/
- Nimbalyst — Best Claude Code Session Managers: https://nimbalyst.com/blog/best-session-managers-for-claude-code-and-codex/
- Nimbalyst — Session Kanban Boards: https://nimbalyst.com/blog/claude-code-session-kanban-organize-ai-agents/
- Octogent dashboard: https://magicshot.ai/news/octogent-claude-code-multi-agent-dashboard/
- Agent Session Center: https://github.com/coding-by-feng/ai-agent-session-center
- PI Dashboard: https://www.agent-wars.com/news/2026-04-22-pi-dashboard-live-agent-control
- Pieces — Automating Standups: https://pieces.app/blog/how-to-automate-stand-up-meetings
- Infinity Interactive — n8n Morning Standup: https://iinteractive.com/resources/blog/how-i-automated-my-morning-standup-with-n8n-and-got-an-unexpected-morale-boost
- ballred/obsidian-claude-pkm: https://github.com/ballred/obsidian-claude-pkm
- Dave Drach — Personal OS with Obsidian + Claude: https://www.davedrach.com/blog/2026/2/27/building-a-personal-operating-system-with-obsidian-and-claude
- AImaker — PARA + Claude Code + Obsidian: https://aimaker.substack.com/p/para-method-tiago-forte-claude-code-obsidian-ai-productivity-os
- DAG Scheduling & Critical Path (York): https://www-users.york.ac.uk/~ijb500/pdfs/DAG%20scheduling.pdf
