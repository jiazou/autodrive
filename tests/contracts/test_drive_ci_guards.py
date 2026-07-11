"""Contract pins — the post-push CI-wait gate + the pre-push portability advisory in /drive-ship.

These close the gap that required human intervention in PR #88 (a local-green/CI-red test shipped
because nothing waited on CI). Per [behavioral-memory-is-not-a-check], the fix is a GATE, not a
memory — so these pins keep the gate WIRED: removing the CI-wait step from drive-ship.md, or deleting
either script, reds here.

MUTATION-VERIFIED at authoring: deleting the `bin/drive-ci-wait.sh` reference from drive-ship.md
reds test_ship_wires_ci_wait; removing the `stop:ci-red` outcome reds test_ci_wait_maps_red_to_stop;
chmod -x either script reds test_scripts_executable.
"""
import os
import stat

from _helpers import REPO_ROOT

SHIP_MD = (REPO_ROOT / ".claude" / "commands" / "drive-ship.md").read_text(encoding="utf-8")
CI_WAIT = REPO_ROOT / "bin" / "drive-ci-wait.sh"
PLINT = REPO_ROOT / "bin" / "drive-portability-lint.sh"


def test_scripts_exist_and_executable():
    for p in (CI_WAIT, PLINT):
        assert p.is_file(), f"{p} missing"
        assert os.stat(p).st_mode & stat.S_IXUSR, f"{p} not executable (a gate script must run)"


def test_ship_wires_ci_wait():
    # the post-push gate must invoke the helper by name
    assert "bin/drive-ci-wait.sh" in SHIP_MD, "drive-ship.md no longer invokes the CI-wait gate"


def test_ci_wait_maps_red_to_stop():
    # a red CI must STOP (not silently reach done) and must surface to the human
    assert "stop:ci-red" in SHIP_MD, "drive-ship.md dropped the ci-red STOP outcome"
    assert "stop:ci-pending" in SHIP_MD, "drive-ship.md dropped the ci-pending STOP outcome"


def test_ship_pr_create_idempotency():
    # a resume after a CI-wait STOP must NOT re-create the PR (else it wedges before re-waiting)
    assert "gh pr list --head" in SHIP_MD, "drive-ship.md lost PR-create idempotency on resume"


def test_ship_wires_portability_advisory():
    assert "bin/drive-portability-lint.sh" in SHIP_MD, "drive-ship.md no longer runs the portability advisory"


def test_ci_wait_exit_contract_documented():
    txt = CI_WAIT.read_text(encoding="utf-8")
    # the 4-way exit contract the ship wiring maps against
    for token in ("0  GREEN", "1  RED", "2  NO-CI", "3  PENDING"):
        assert token in txt, f"drive-ci-wait.sh exit-code contract missing '{token}'"


def test_ci_wait_never_passes_on_empty_snapshot():
    # the P1 correctness invariant: 0 checks + workflows present must NOT proceed
    txt = CI_WAIT.read_text(encoding="utf-8")
    assert "_has_workflows" in txt, "drive-ci-wait.sh lost the workflow-presence disambiguator"
    assert "never" in txt.lower() and "empty" in txt.lower(), \
        "drive-ci-wait.sh lost the 'never pass on an empty snapshot' invariant doc"


def test_portability_lint_is_advisory():
    txt = PLINT.read_text(encoding="utf-8")
    assert "exit 0" in txt, "portability lint must be advisory (exit 0 always)"
    assert "ADVISORY" in txt, "portability lint lost its ADVISORY contract marker"
