"""Shared pytest fixtures for the claude-harness test suite.

This is the ONLY owner of conftest.py (slice 1.1). The central fixture is `mc_env`:
it redirects HOME + MC_VAULT into a per-test tempdir and RELOADS the mission-control
modules so their import-time path constants (vault_tasks.VAULT, harvest.SESSIONS_DIR,
session_summary.PROJECTS_DIR, ...) are derived from the fake env. See design D3.

Builders (`vault`, `claude_state`) write fixture data the REAL readers accept — the
JSON / frontmatter keys here are matched against mission-control/bin/*.py, not invented.
"""
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

# tests/ on sys.path so `import _helpers` works regardless of invocation cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers  # noqa: E402


# --------------------------------------------------------------------------- #
# Repo / path setup
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def repo_root():
    """Absolute repo root (the parent of tests/)."""
    return _helpers.REPO_ROOT


@pytest.fixture(scope="session", autouse=True)
def mc_bin_on_path():
    """Put <repo>/mission-control/bin on sys.path ONCE so bare `import vault_tasks`
    / `import harvest` resolve (the bin/*.py are not a package). Autouse + session
    scope: every test inherits it, the insert happens at most once."""
    bin_dir = str(_helpers.REPO_ROOT / "mission-control" / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    return bin_dir


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """A per-test fake HOME at tmp_path/home with $HOME pointed at it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


# --------------------------------------------------------------------------- #
# The central fixture: env + reloaded modules
# --------------------------------------------------------------------------- #
@dataclass
class MCEnv:
    home: Path
    vault: Path
    sessions_dir: Path
    projects_dir: Path
    bindings: Path
    status_ledger: Path
    daily_dir: Path
    vault_tasks: object
    harvest: object
    session_summary: object
    standup: object
    today: object
    done: object
    weekly: object


@pytest.fixture
def mc_env(fake_home, monkeypatch, mc_bin_on_path):
    """Set the MC env into the fake HOME and reload the MC modules in dependency
    order so their import-time constants are derived from this env.

    Import/reload order is load-bearing: vault_tasks first (freezes VAULT/TASKS_GLOB),
    THEN harvest (its `import vault_tasks` + VAULT copy happen at its import time),
    THEN session_summary, then the consumers. SELF_ID is frozen to "" here; a test
    needing a non-empty self-id sets it via monkeypatch.setattr(mc_env.harvest,
    "SELF_ID", sid) (see design — the env var alone won't take without a second reload).
    """
    home = Path(fake_home)
    vault = home / "Vault"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MC_VAULT", str(vault))
    monkeypatch.setenv("MC_VAULT_NAME", "TestVault")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "")

    # vault_tasks first, then harvest (copies vault_tasks.VAULT at its import), then
    # the rest. Use import_module then reload so a stale module from a prior test is
    # rebuilt against THIS env.
    vault_tasks = importlib.reload(importlib.import_module("vault_tasks"))
    harvest = importlib.reload(importlib.import_module("harvest"))
    session_summary = importlib.reload(importlib.import_module("session_summary"))
    standup = importlib.reload(importlib.import_module("standup"))
    today = importlib.reload(importlib.import_module("today"))
    done = importlib.reload(importlib.import_module("done"))
    weekly = importlib.reload(importlib.import_module("weekly"))

    # Daily dir: prefer harvest's own VAULT_DAILY (the real derivation). The fallback
    # mirrors the real derivation (<vault>/Daily) so it can't silently mask a future
    # rename of the constant.
    daily_dir = Path(getattr(harvest, "VAULT_DAILY", vault / "Daily"))

    return MCEnv(
        home=home,
        vault=vault,
        sessions_dir=home / ".claude" / "sessions",
        projects_dir=home / ".claude" / "projects",
        bindings=home / "mission-control" / "bindings.jsonl",
        status_ledger=home / "mission-control" / "status.jsonl",
        daily_dir=daily_dir,
        vault_tasks=vault_tasks,
        harvest=harvest,
        session_summary=session_summary,
        standup=standup,
        today=today,
        done=done,
        weekly=weekly,
    )


# --------------------------------------------------------------------------- #
# Vault builder
# --------------------------------------------------------------------------- #
class VaultBuilder:
    """Writes vault fixtures under mc_env.vault that vault_tasks._parse_frontmatter
    (regex `^---\\n(.*?)\\n---`, scalars + `[a, b]` lists) accepts."""

    def __init__(self, vault):
        self.vault = Path(vault)

    def add_task(self, slug, *, project="P", status="todo", priority="p2",
                 due=None, scheduled=None, needs_review=False, depends_on=None,
                 tags=None, title=None, dod=None, type="task",
                 extra_frontmatter="", body=""):
        """Write 01 Projects/<project>/Tasks/<slug>.md. Keys are emitted only when
        not None; `needs_review` as lowercase true/false; lists as `[a, b]`; `dod`
        as a `## Definition of done` checkbox section. Returns the Path."""
        fm = [f"type: {type}"]
        if project is not None:
            fm.append(f"project: {project}")
        if status is not None:
            fm.append(f"status: {status}")
        if priority is not None:
            fm.append(f"priority: {priority}")
        if due is not None:
            fm.append(f"due: {due}")
        if scheduled is not None:
            fm.append(f"scheduled: {scheduled}")
        fm.append(f"needs_review: {'true' if needs_review else 'false'}")
        if depends_on is not None:
            fm.append("depends_on: [" + ", ".join(depends_on) + "]")
        if tags is not None:
            fm.append("tags: [" + ", ".join(tags) + "]")
        if extra_frontmatter:
            fm.append(extra_frontmatter.rstrip("\n"))

        h1 = title if title is not None else slug
        parts = ["---", "\n".join(fm), "---", "", f"# {h1}", ""]
        if dod is not None:
            parts.append("## Definition of done")
            parts.append("")
            for item in dod:
                parts.append(f"- [ ] {item}")
            parts.append("")
        if body:
            parts.append(body)

        path = self.vault / "01 Projects" / project / "Tasks" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(parts), encoding="utf-8")
        return path

    def add_raw(self, rel_path, text):
        """Write an arbitrary file under the vault (malformed-frontmatter / non-task
        fixtures). Returns the Path."""
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def add_daily_template(self, text):
        """Write 03 Resources/Templates/daily-note-template.md. Returns the Path."""
        return self.add_raw("03 Resources/Templates/daily-note-template.md", text)


@pytest.fixture
def vault(mc_env):
    return VaultBuilder(mc_env.vault)


# --------------------------------------------------------------------------- #
# Claude-state builder
# --------------------------------------------------------------------------- #
class ClaudeStateBuilder:
    """Writes ~/.claude + ~/mission-control fixtures whose keys match the real
    readers (harvest.load_live_sessions / session_meta / load_bindings /
    load_status_overlay)."""

    def __init__(self, mc_env):
        self.mc_env = mc_env
        self.sessions_dir = Path(mc_env.sessions_dir)
        self.projects_dir = Path(mc_env.projects_dir)
        self.bindings = Path(mc_env.bindings)
        self.status_ledger = Path(mc_env.status_ledger)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.bindings.parent.mkdir(parents=True, exist_ok=True)

    def add_session(self, sid, *, pid=None, cwd="/x", status="idle"):
        """Write ~/.claude/sessions/<sid>.json. Keys match load_live_sessions:
        pid / sessionId / cwd / status. pid defaults to os.getpid() (a live pid so
        pid_alive passes). Returns the Path."""
        if pid is None:
            pid = os.getpid()
        path = self.sessions_dir / f"{sid}.json"
        path.write_text(json.dumps(
            {"sessionId": sid, "pid": pid, "cwd": cwd, "status": status}
        ), encoding="utf-8")
        return path

    def add_transcript(self, sid, events):
        """Write ~/.claude/projects/<slug>/<sid>.jsonl (one JSON object per line).
        The project slug is arbitrary (harvest globs PROJECTS_DIR/*/<sid>.jsonl);
        `events` is a list of dicts already shaped for session_meta (type +
        sessionId + agentColor/agentName/aiTitle) or tail_text (type user/assistant
        + message.content). Returns the Path."""
        proj_dir = self.projects_dir / "-fake-project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        path = proj_dir / f"{sid}.jsonl"
        path.write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
        )
        return path

    def add_binding(self, sid, *, event="bind", project=None, task=None, ts=None):
        """Append one JSON line to ~/mission-control/bindings.jsonl, matching
        load_bindings (session_id / event; project/task optional). Returns the Path."""
        rec = {"ts": int(ts if ts is not None else time.time()),
               "event": event, "session_id": sid}
        if project is not None:
            rec["project"] = project
        if task is not None:
            rec["task"] = task
        with open(self.bindings, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        return self.bindings

    def add_status(self, sid, status, ts=None):
        """Append one JSON line to ~/mission-control/status.jsonl, matching
        load_status_overlay (session_id / status). Returns the Path."""
        self.status_ledger.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(ts if ts is not None else time.time()),
               "session_id": sid, "status": status}
        with open(self.status_ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        return self.status_ledger

    def dead_pid(self):
        """A pid known to be dead: spawn `true`, reap it, return its now-free pid so
        pid_alive returns False deterministically."""
        p = subprocess.Popen(["true"])
        p.wait()
        return p.pid


@pytest.fixture
def claude_state(mc_env):
    return ClaudeStateBuilder(mc_env)


# --------------------------------------------------------------------------- #
# Edge stub (NOT root-autouse — only mc/ tests that import harvest use it)
# --------------------------------------------------------------------------- #
@pytest.fixture
def no_iterm(mc_env, monkeypatch):
    """Replace harvest.iterm_tab_names with `lambda: {}` so no osascript fires.
    Deliberately not autouse at root: installer/contract phases don't import harvest."""
    monkeypatch.setattr(mc_env.harvest, "iterm_tab_names", lambda: {})
