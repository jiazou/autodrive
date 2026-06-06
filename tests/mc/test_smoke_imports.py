"""Smoke tests for the MC reload scaffolding (AC 6 import-smoke, AC 30 reload isolation)."""
import importlib

MODULE_ATTRS = (
    "vault_tasks", "harvest", "session_summary",
    "standup", "today", "done", "weekly",
)


def test_all_modules_import(mc_env):
    """AC 6 (import-smoke): every MC module loads via mc_env and is non-None.

    These are the 7 importable MC-logic modules. The other two bin/*.py are not in
    scope: mc-hook.py is hyphenated (not importable as a module) and install_hooks.py
    is a Phase-3 subprocess target, not a reload-able logic module.
    """
    for attr in MODULE_ATTRS:
        mod = getattr(mc_env, attr)
        assert mod is not None, f"{attr} reloaded to None"
        # Bite harder than a bare distinctness count: each slot must hold the module it
        # NAMES (mc_env.harvest.__name__ == 'harvest'), so a mis-wired reload that points
        # `done` at, say, the `weekly` module is caught — a count of 7 distinct objects
        # would stay green for the wrong reason.
        assert mod.__name__ == attr, f"mc_env.{attr} holds module {mod.__name__!r}"


def _reload_chain_under(home, monkeypatch):
    """Point HOME + MC_VAULT at `home`, reload the load-bearing chain, and return the
    env-derived constants that EVERY consumer depends on. Mirrors mc_env's order
    (vault_tasks -> harvest -> session_summary) so harvest's VAULT copy is correct."""
    vault = home / "Vault"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MC_VAULT", str(vault))

    vault_tasks = importlib.reload(importlib.import_module("vault_tasks"))
    harvest = importlib.reload(importlib.import_module("harvest"))
    session_summary = importlib.reload(importlib.import_module("session_summary"))

    return {
        "vault_tasks.VAULT": vault_tasks.VAULT,
        "harvest.VAULT": harvest.VAULT,
        "harvest.VAULT_DAILY": harvest.VAULT_DAILY,
        "harvest.SESSIONS_DIR": harvest.SESSIONS_DIR,
        "harvest.BINDINGS": harvest.BINDINGS,
        "harvest.STATUS_LEDGER": harvest.STATUS_LEDGER,
        "session_summary.PROJECTS_DIR": session_summary.PROJECTS_DIR,
    }


def test_reload_isolation(monkeypatch, mc_bin_on_path, tmp_path):
    """AC 30: reloading the full load-bearing chain under two different HOMEs must
    refresh EVERY env-derived constant — not just vault_tasks.VAULT.

    This is the regression guard: if a future change stops harvest or session_summary
    from re-deriving its import-time constants on reload (e.g. caching HOME at first
    import, or moving a constant out of module scope), that constant stays pinned to
    HOME_A and the corresponding assertion below FAILS. A test that only checked
    vault_tasks.VAULT would stay green for the wrong reason.
    """
    home_a = tmp_path / "home_a"
    home_b = tmp_path / "home_b"
    home_a.mkdir()
    home_b.mkdir()

    const_a = _reload_chain_under(home_a, monkeypatch)
    const_b = _reload_chain_under(home_b, monkeypatch)

    # Every constant under HOME_A must be rooted at HOME_A...
    assert const_a["vault_tasks.VAULT"] == str(home_a / "Vault")
    assert const_a["harvest.VAULT"] == str(home_a / "Vault")
    assert const_a["harvest.VAULT_DAILY"] == str(home_a / "Vault" / "Daily")
    assert const_a["harvest.SESSIONS_DIR"] == str(home_a / ".claude" / "sessions")
    assert const_a["harvest.BINDINGS"] == str(home_a / "mission-control" / "bindings.jsonl")
    assert const_a["harvest.STATUS_LEDGER"] == str(home_a / "mission-control" / "status.jsonl")
    assert const_a["session_summary.PROJECTS_DIR"] == str(home_a / ".claude" / "projects")

    # ...and after the second reload EVERY constant must move to HOME_B (no stale leak).
    assert const_b["vault_tasks.VAULT"] == str(home_b / "Vault")
    assert const_b["harvest.VAULT"] == str(home_b / "Vault")
    assert const_b["harvest.VAULT_DAILY"] == str(home_b / "Vault" / "Daily")
    assert const_b["harvest.SESSIONS_DIR"] == str(home_b / ".claude" / "sessions")
    assert const_b["harvest.BINDINGS"] == str(home_b / "mission-control" / "bindings.jsonl")
    assert const_b["harvest.STATUS_LEDGER"] == str(home_b / "mission-control" / "status.jsonl")
    assert const_b["session_summary.PROJECTS_DIR"] == str(home_b / ".claude" / "projects")

    # Cross-check: no key kept its HOME_A value after the HOME_B reload.
    for key in const_a:
        assert const_a[key] != const_b[key], f"{key} did not refresh across reload"
