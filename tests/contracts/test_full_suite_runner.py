"""Contract: the canonical full-suite runner exists and every "run the full suite"
surface routes through it — so "full suite" is unambiguous and CI-equivalent, and no
executor can hand-pick a subset that misses a bash gate suite.

Regression origin (run regress-selfid-20260706): the /drive ship stage ran only
`pytest` + `drive-conformance.test.sh` (both green) and shipped, while the
reviewed_sha_of change had reddened drive-enforcement-e2e / drive-merge-gate /
drive-stop-guard. CI caught it but stopped at the first failing file, masking two of
the three. The fix is one canonical runner (`bin/run-tests.sh`) that runs pytest AND
every `test/*.test.sh` with no early exit, invoked by both the /drive stages and CI.
"""
import os
import re
import stat
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "bin" / "run-tests.sh"


def _read(rel):
    return (REPO / rel).read_text()


def test_runner_exists_and_is_executable():
    assert RUNNER.is_file(), "bin/run-tests.sh (the canonical full-suite runner) must exist"
    mode = RUNNER.stat().st_mode
    assert mode & stat.S_IXUSR, "bin/run-tests.sh must be executable (chmod +x)"


def test_runner_runs_both_harnesses_with_no_early_exit():
    src = RUNNER.read_text()
    # Runs pytest via python3 (python is often absent locally) AND every test/*.test.sh.
    assert "python3 -m pytest" in src, "runner must run pytest via python3"
    assert "test/*.test.sh" in src, "runner must iterate every test/*.test.sh bash suite"
    # No early-exit masking: the bash loop must NOT `exit 1` on the first failing file —
    # it collects failures and exits nonzero at the end.
    assert not re.search(r"bash\s+\"\$f\"\s*\|\|\s*exit", src), (
        "runner must NOT exit on the first failing bash suite (that masks downstream "
        "fails — the regress-selfid miss); collect all and exit nonzero at the end"
    )
    # Mode flags so CI's two independent jobs call this same runner.
    assert "--pytest-only" in src and "--bash-only" in src, (
        "runner must support --pytest-only / --bash-only so CI's two jobs reuse it"
    )


def test_drive_stages_route_full_suite_through_the_runner():
    # Every stage whose spec says "run the full suite" must name the canonical runner,
    # so an executor cannot hand-pick pytest + one bash file.
    for stage in ("drive-harden", "drive-finalize", "drive-ship"):
        text = _read(f".claude/commands/{stage}.md")
        assert "bin/run-tests.sh" in text, (
            f"{stage}.md must route its full-suite run through bin/run-tests.sh"
        )


def test_ci_uses_the_runner_for_both_jobs():
    ci = _read(".github/workflows/test.yml")
    assert "./bin/run-tests.sh --pytest-only" in ci, "CI pytest job must use the runner"
    assert "./bin/run-tests.sh --bash-only" in ci, "CI bash-suite job must use the runner"
    # The masking loop must be gone from CI.
    assert "|| exit 1" not in ci, (
        "CI must not use the first-failure `|| exit 1` loop (it masked downstream "
        "bash-suite failures); the runner reports every failure"
    )
