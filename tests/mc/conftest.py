"""Package-scoped conftest for tests/mc/ — guarantees no mc/ test ever fires the
real osascript path (AC 29).

This autouse fixture only affects tests UNDER tests/mc/ (pytest applies a conftest
to its own directory subtree). Installer / hook / contract tests live in
tests/installers, tests/hooks, tests/contracts and are NOT touched by it, so they
never pay for the mc_env module-reload machinery.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_iterm_autouse(mc_env, monkeypatch):
    """Patch harvest.iterm_tab_names -> {} for EVERY test in tests/mc/, so a test that
    forgets to request the named `no_iterm` fixture still can't reach real osascript.
    Depends on mc_env so it patches the freshly reloaded harvest module."""
    monkeypatch.setattr(mc_env.harvest, "iterm_tab_names", lambda: {})
