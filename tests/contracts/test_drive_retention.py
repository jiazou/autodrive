"""Contract pins for bin/drive-retention.sh — the Phase-1 REPORT-ONLY retention classifier.

Drives the script via `_helpers.run_script` against a per-test tempdir `--root`, with an
injected `--now` clock so age is deterministic. Assertions ride on the stable `--json`
schema (one object per run), not fragile human prose; the human report is smoke-checked for
the run/Tier headers only. Pins acceptance criteria 1-16 from design-phase1.md.

Closed Phase-1 skip-reason vocabulary (DP4/AC14):
    {waiting, inflight-open, not-done, not-aged, unresolvable-repo, wt-registered,
     registration-unprovable, not-drive-owned, dirty, unpushed, unreadable, not-ancestor,
     ancestry-unprovable}
"""
import json
import os
import re
import subprocess
import time

import pytest

from _helpers import REPO_ROOT, run_script

SCRIPT = REPO_ROOT / "bin" / "drive-retention.sh"

# A fixed "now" far in the future of any backdated fixture; one day = 86400s.
NOW = 4_000_000_000          # ~2096 — every backdated fixture is "aged" against it.
DAY = 86400
OLD = NOW - 60 * DAY         # 60 days old → past the 14d threshold
RECENT = NOW - 1 * DAY       # 1 day old → NOT past the 14d threshold

CLOSED_VOCAB = {
    "waiting", "inflight-open", "not-done", "not-aged", "unresolvable-repo",
    "wt-registered", "registration-unprovable", "not-drive-owned", "dirty",
    "unpushed", "unreadable", "not-ancestor", "ancestry-unprovable",
}


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #
def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )


def _backdate(path, epoch=OLD):
    """Set a path's mtime/atime to `epoch` (so the run-dir mtime input to the age union is old)."""
    os.utime(path, (epoch, epoch))


def _state(run_dir, **fields):
    """Write run_dir/state.json from the given top-level fields (omit a field to leave it absent).
    Pass waiting=None explicitly to emit JSON null; omit it to leave the key absent."""
    (run_dir / "state.json").write_text(json.dumps(fields), encoding="utf-8")


def _run_dir(root, name):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_owning_repo(tmp_path, run_id, *, base="main", make_drive_branch=True,
                      ancestor=True):
    """Create a real git repo to serve as a run's owning repo.

    make_drive_branch + ancestor=True: drive/<run_id> is an ancestor of `base` (eligible).
    ancestor=False: drive/<run_id> diverges from `base` (not an ancestor → skip:not-ancestor).
    """
    repo = tmp_path / f"repo-{run_id}"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    (repo / "a").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "branch", "-M", base)
    if make_drive_branch:
        if ancestor:
            _git(repo, "branch", f"drive/{run_id}")   # same commit ⇒ ancestor of base
        else:
            _git(repo, "checkout", "-q", "-b", f"drive/{run_id}")
            (repo / "b").write_text("b\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "diverge")     # a commit base does not contain
            _git(repo, "checkout", "-q", base)
    return repo


def _clean_pushed_checkout(child_dir):
    """Make child_dir a clean git checkout whose only commit is reachable from a remote-
    tracking ref (so W7b sees no uncommitted edits AND no unpushed commits ⇒ clean)."""
    child_dir.mkdir(parents=True, exist_ok=True)
    _git(child_dir, "init", "-q")
    (child_dir / "x").write_text("x\n")
    _git(child_dir, "add", "-A")
    _git(child_dir, "commit", "-qm", "c1")
    head = subprocess.run(
        ["git", "-C", str(child_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(child_dir, "update-ref", "refs/remotes/origin/main", head)


def _detached_unpushed_checkout(child_dir):
    """Make child_dir a CLEAN git checkout on a DETACHED HEAD whose tip commit is reachable
    only from HEAD (no branch points at it) and is NOT on any remote-tracking ref. The
    pushed commit is on `main` and on origin/main; HEAD is detached one commit AHEAD.

    `git log --branches --not --remotes` (the buggy probe) returns EMPTY here (no BRANCH
    holds the unpushed commit) ⇒ wrongly clean. `git log --all --not --remotes` (the fix)
    includes HEAD ⇒ flags the detached commit ⇒ skip:unpushed. Working tree stays clean."""
    child_dir.mkdir(parents=True, exist_ok=True)
    _git(child_dir, "init", "-q")
    (child_dir / "x").write_text("x\n")
    _git(child_dir, "add", "-A")
    _git(child_dir, "commit", "-qm", "c1-pushed")
    pushed = subprocess.run(
        ["git", "-C", str(child_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(child_dir, "update-ref", "refs/remotes/origin/main", pushed)  # c1 IS pushed
    (child_dir / "y").write_text("y\n")
    _git(child_dir, "add", "-A")
    _git(child_dir, "commit", "-qm", "c2-detached-unpushed")          # local-only commit
    # Detach HEAD at the unpushed commit, then move the only branch BACK to the pushed
    # commit so NO branch points at c2 — it is reachable solely from the detached HEAD.
    _git(child_dir, "checkout", "-q", "--detach", "HEAD")
    _git(child_dir, "branch", "-f", "main", pushed)


def _registered_pointer(child_dir, admin_dir, *, backref="self"):
    """Make child_dir/.git a worktree gitdir POINTER FILE → admin_dir, and seed admin_dir's
    `gitdir` back-reference. backref='self' (path equality holds ⇒ registered),
    'other' (a DIFFERENT path ⇒ unprovable), 'missing' (no backref file ⇒ unprovable),
    'none' (no admin dir at all ⇒ unprovable / dangling)."""
    child_dir.mkdir(parents=True, exist_ok=True)
    ptr = child_dir / ".git"
    ptr.write_text(f"gitdir: {admin_dir}\n", encoding="utf-8")
    if backref == "none":
        return
    admin_dir.mkdir(parents=True, exist_ok=True)
    if backref == "missing":
        return
    target = str(ptr) if backref == "self" else "/some/other/path/wt/elsewhere/.git"
    (admin_dir / "gitdir").write_text(f"{target}\n", encoding="utf-8")


def _scan(root, *, age_days=14, now=NOW, json_mode=True, home=None):
    """Run the script over `root` and return (CompletedProcess, list-of-json-objects)."""
    args = [str(SCRIPT), "--root", str(root), "--now", str(now), "--age-days", str(age_days)]
    if json_mode:
        args.append("--json")
    cp = run_script(args, home=home or root)
    objs = []
    if json_mode:
        for line in cp.stdout.splitlines():
            line = line.strip()
            if line:
                objs.append(json.loads(line))
    return cp, objs


def _by_id(objs):
    return {o["runId"]: o for o in objs}


def _child(obj, name):
    for c in obj["tierW"]["children"]:
        if c["name"] == name:
            return c
    raise AssertionError(f"child {name!r} not found in {obj['runId']}")


# --------------------------------------------------------------------------- #
# AC1, AC3: exit 0 always (except unknown flag), per-run isolation
# --------------------------------------------------------------------------- #
def test_exit_zero_on_normal_scan(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "ok-run")
    _state(d, stage="done", waiting=None, baseRef="main")
    _backdate(d)
    cp, _ = _scan(root)
    assert cp.returncode == 0


def test_exit_two_on_unknown_flag(tmp_path):
    cp = run_script([str(SCRIPT), "--bogus"], home=tmp_path)
    assert cp.returncode == 2


@pytest.mark.parametrize("flag", ["--root", "--age-days", "--now"])
def test_trailing_valued_flag_exits_two_not_hang(tmp_path, flag):
    """A valued flag as the TRAILING token (no value) is a CLI usage error ⇒ exit 2 promptly,
    NOT an infinite hang. `run_script` has a 30s timeout; a hang would raise TimeoutExpired
    (and would have blocked GC-at-setup)."""
    cp = run_script([str(SCRIPT), flag], home=tmp_path)
    assert cp.returncode == 2


@pytest.mark.parametrize("flag", ["--root", "--age-days", "--now"])
def test_valued_flag_followed_by_flag_exits_two(tmp_path, flag):
    """A valued flag immediately followed by ANOTHER flag (e.g. `--root --json`) is a missing
    value, NOT a swallow: the next flag must not be consumed as the value (it would silently
    scan the wrong root). ⇒ exit 2 (the bad-flag lane), no hang."""
    cp = run_script([str(SCRIPT), flag, "--json"], home=tmp_path)
    assert cp.returncode == 2


def test_non_numeric_now_falls_back_to_clock(tmp_path):
    """Edge 13: a NON-numeric (non-flag) --now value falls back to the real clock with a
    notice (exit 0) — NOT a fail-open: the real clock cannot mark a recently-touched run aged.
    A run with a RECENT mtime stays NOT aged under the wall-clock fallback."""
    root = tmp_path / "runs"
    d = _run_dir(root, "now-bad")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "codex-raw-x.log").write_text("z", encoding="utf-8")
    _backdate(d, epoch=int(time.time()))  # touched ~now ⇒ never aged vs the real clock
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", "nope", "--age-days", "14", "--json"],
        home=root,
    )
    assert cp.returncode == 0
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["now-bad"]
    assert o["pastThreshold"] is False        # real-clock fallback ⇒ recent run not aged
    assert o["tierL"]["reason"] == "not-aged"


def test_non_numeric_age_days_falls_back_to_14(tmp_path):
    """Edge 13: a NON-numeric (non-flag) --age-days value falls back to 14 with a notice
    (exit 0) — never to 0. A run RECENT (1 day) stays NOT aged under the 14d fallback."""
    root = tmp_path / "runs"
    d = _run_dir(root, "age-bad")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "codex-raw-x.log").write_text("z", encoding="utf-8")
    _backdate(d, epoch=RECENT)  # 1 day old
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "nope", "--json"],
        home=root,
    )
    assert cp.returncode == 0
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["age-bad"]
    assert o["pastThreshold"] is False        # fell back to 14d, not 0 ⇒ recent not aged
    assert o["tierL"]["reason"] == "not-aged"


def test_missing_root_exits_zero(tmp_path):
    cp = run_script([str(SCRIPT), "--root", str(tmp_path / "nope")], home=tmp_path)
    assert cp.returncode == 0


def test_torn_state_json_does_not_abort_scan(tmp_path):
    """AC3: a per-run failure (torn JSON) does not abort the scan — good runs still appear."""
    root = tmp_path / "runs"
    torn = _run_dir(root, "torn-run")
    (torn / "state.json").write_text('{"stage": "done", "wait', encoding="utf-8")  # truncated
    _backdate(torn)
    good = _run_dir(root, "good-run")
    _state(good, stage="done", waiting=None, baseRef="main")
    _backdate(good)
    cp, objs = _scan(root)
    assert cp.returncode == 0
    ids = _by_id(objs)
    assert "good-run" in ids and "torn-run" in ids
    # torn JSON ⇒ no done signal ⇒ skip:not-done on Tier-L (fail-safe)
    assert ids["torn-run"]["tierL"]["reason"] == "not-done"


# --------------------------------------------------------------------------- #
# AC2: no deletion path exists (STRUCTURAL report-only)
# --------------------------------------------------------------------------- #
def test_no_deletion_path_exists():
    """Strip trailing comments, then assert ZERO deletion tokens in the CODE text."""
    text = SCRIPT.read_text(encoding="utf-8")
    stripped = "\n".join(re.sub(r"#.*", "", line) for line in text.splitlines())
    assert not re.search(r"trash|worktree remove|--apply|(^|[^a-z])rm ", stripped), (
        "Phase-1 file must contain no deletion token in code (comments stripped)"
    )


# --------------------------------------------------------------------------- #
# AC4: owning-repo resolution order
# --------------------------------------------------------------------------- #
def test_owning_repo_from_state_reporoot(tmp_path):
    repo = _make_owning_repo(tmp_path, "rr-run")
    root = tmp_path / "runs"
    d = _run_dir(root, "rr-run")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["rr-run"]["owningRepo"] == str(repo)


def test_owning_repo_from_registered_gitdir(tmp_path):
    """No state.repoRoot, but a registered wt/<n>/.git gitdir resolves to <repo>."""
    repo = tmp_path / "repo-gd"
    admin = repo / ".git" / "worktrees" / "phase1"
    root = tmp_path / "runs"
    d = _run_dir(root, "gd-run")
    _state(d, stage="done", waiting=None, baseRef="main")  # NO repoRoot
    _registered_pointer(d / "wt" / "phase1", admin, backref="self")
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["gd-run"]["owningRepo"] == str(repo)


def test_owning_repo_unresolvable(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "unres-run")
    _state(d, stage="done", waiting=None, baseRef="main")
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["unres-run"]["owningRepo"] is None


# --------------------------------------------------------------------------- #
# AC5: Tier-L independence from repo resolution
# --------------------------------------------------------------------------- #
def test_tierL_independent_of_repo(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "logs-run")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE
    (d / "codex-raw-design.log").write_text("x" * 100, encoding="utf-8")
    (d / "codex-harden-1.log").write_text("y" * 50, encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["logs-run"]
    assert o["owningRepo"] is None
    assert o["tierL"]["eligible"] is True
    names = {x["name"] for x in o["tierL"]["logs"]}
    assert names == {"codex-raw-design.log", "codex-harden-1.log"}


# --------------------------------------------------------------------------- #
# AC6: Tier-L gates flip independently
# --------------------------------------------------------------------------- #
def test_tierL_waiting(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "w")
    _state(d, stage="done", waiting="gateB", baseRef="main")
    (d / "codex-raw-x.log").write_text("x", encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["w"]["tierL"]["reason"] == "waiting"


def test_tierL_inflight(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "inf")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "inflight-ship.marker").write_text("", encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["inf"]["tierL"]["reason"] == "inflight-open"


def test_tierL_not_done(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "nd")
    _state(d, stage="execute", waiting=None, baseRef="main")  # not done, no completedAt
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["nd"]["tierL"]["reason"] == "not-done"


def test_tierL_not_aged(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "na")
    _state(d, stage="done", waiting=None, baseRef="main")
    _backdate(d, epoch=RECENT)   # recent ⇒ not aged
    _, objs = _scan(root)
    assert _by_id(objs)["na"]["tierL"]["reason"] == "not-aged"
    assert _by_id(objs)["na"]["pastThreshold"] is False


# --------------------------------------------------------------------------- #
# AC7: Tier-W gate-order precedence (first-failing-gate-wins)
# --------------------------------------------------------------------------- #
def test_tierW_w6_ad_hoc_name_beats_unresolvable_repo(tmp_path):
    """An ad-hoc-named child of an UNRESOLVABLE run ⇒ skip:not-drive-owned (W6), NOT
    skip:unresolvable-repo — the structural per-child gate wins. A drive-owned sibling of
    the same run stops at W4 ⇒ skip:unresolvable-repo (no completedAt, no repo)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "mixed")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE, no completedAt
    (d / "wt" / "converter").mkdir(parents=True)            # ad-hoc name
    (d / "wt" / "phase1").mkdir(parents=True)               # drive-owned, no pointer
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["mixed"]
    assert _child(o, "converter")["reason"] == "not-drive-owned"
    assert _child(o, "phase1")["reason"] == "unresolvable-repo"


def test_tierW_not_done_blocks_live_quiet_fail_open(tmp_path):
    """The Wd DONE gate: a NOT-done run (stage!=done, no completedAt) that is waiting==null,
    no inflight, aged, with a CLEAN no-pointer drive-owned dir ⇒ skip:not-done, never eligible."""
    root = tmp_path / "runs"
    d = _run_dir(root, "live-quiet")
    _state(d, stage="execute", waiting=None, baseRef="main")  # NOT done
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["live-quiet"], "phase1")
    assert c["reason"] == "not-done"
    assert c["eligible"] is False


def test_tierW_completedAt_dirty_still_skips(tmp_path):
    """A parseable completedAt authorizes W4 but does NOT bypass W7b: a DIRTY existing dir
    ⇒ skip:dirty even with completedAt + unresolvable repo."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-dirty")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE repo
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    (d / "wt" / "phase1" / "dirty-edit").write_text("uncommitted\n", encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["ca-dirty"], "phase1")
    assert c["reason"] == "dirty"
    assert c["eligible"] is False


def test_tierW_sole_eligible_conjunction(tmp_path):
    """The SOLE eligible Tier-W outcome: drive-owned + no-pointer + waiting null + no inflight
    + done + aged + W4-authorized (ancestor) + W7b clean ⇒ eligible."""
    repo = _make_owning_repo(tmp_path, "elig", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "elig")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["elig"], "phase1")
    assert c["eligible"] is True
    assert c["reason"] == ""


def test_tierW_unreadable_skips(tmp_path):
    """W7b unreadable fail-safe (AC7): a drive-owned no-pointer child that is NOT a readable
    git working tree (`git -C <dir> status` fails) ⇒ skip:unreadable, NEVER eligible. The run
    is W4-authorized by a parseable completedAt (so the child reaches W7b), and the existing
    dir is a plain non-repo directory (no .git) so the cleanliness probe cannot read it."""
    root = tmp_path / "runs"
    d = _run_dir(root, "unreadable")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE repo
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # W4-authorizes
    (d / "wt" / "phase1").mkdir(parents=True)  # plain dir, no .git ⇒ not-registered, not a repo
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["unreadable"], "phase1")
    assert c["reason"] == "unreadable"
    assert c["eligible"] is False


def test_tierW_unpushed_skips(tmp_path):
    """A clean tree with a local commit not on any remote ⇒ skip:unpushed (W7b)."""
    repo = _make_owning_repo(tmp_path, "unp", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "unp")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    # clean checkout but NO remote ref ⇒ the commit is unpushed
    child = d / "wt" / "phase1"
    child.mkdir(parents=True)
    _git(child, "init", "-q")
    (child / "x").write_text("x\n")
    _git(child, "add", "-A")
    _git(child, "commit", "-qm", "c1")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["unp"], "phase1")["reason"] == "unpushed"


def test_tierW_detached_head_unpushed_skips(tmp_path):
    """BLOCKING (W7b completeness): a CLEAN checkout whose ONLY local commit is reachable
    solely from a DETACHED HEAD (no branch holds it) and is NOT on any remote ⇒ skip:unpushed,
    NEVER eligible. The run is done + W4-authorized by a parseable completedAt (so the child
    reaches W7b). The buggy `--branches` probe sees no BRANCH carrying the commit ⇒ wrongly
    reports clean ⇒ eligible ⇒ Phase 2 --apply would lose the commit (report==apply fail-open).
    The fix (`--all`, covering HEAD + stash) flags it. mutation-verified RED against
    `--branches`, GREEN against `--all`."""
    root = tmp_path / "runs"
    d = _run_dir(root, "detached")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE repo
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # W4-authorizes
    _detached_unpushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["detached"], "phase1")
    assert c["reason"] == "unpushed", (
        "a detached-HEAD-only unpushed commit must be flagged (W7b completeness)"
    )
    assert c["eligible"] is False


def test_tierW_dangling_gitdir_unreadable_or_unprovable(tmp_path):
    """Fail-safe pin: a drive-owned child whose `.git` is a DANGLING symlink (target absent)
    is never eligible — registration cannot be proven from an unreadable pointer. It resolves
    to skip:registration-unprovable (W5: a `.git` dirent exists but is not a readable pointer
    file) and never reaches W7/eligible."""
    root = tmp_path / "runs"
    d = _run_dir(root, "dangling-git")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")
    child = d / "wt" / "phase1"
    child.mkdir(parents=True)
    os.symlink(str(tmp_path / "nonexistent-target"), str(child / ".git"))  # dangling
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["dangling-git"], "phase1")
    assert c["eligible"] is False
    assert c["reason"] == "registration-unprovable"


# --------------------------------------------------------------------------- #
# AC8: wt_registered_anywhere is THREE-WAY on PATH EQUALITY (not name match)
# --------------------------------------------------------------------------- #
def test_w5_three_way_path_equality(tmp_path):
    """Two runs both own a wt/phase1: the path-matched one ⇒ wt-registered; the other (its
    pointer's admin backref points elsewhere) ⇒ registration-unprovable (NOT eligible)."""
    root = tmp_path / "runs"
    # Run A: registered (self path equality)
    a = _run_dir(root, "runA")
    _state(a, stage="done", waiting=None, baseRef="main")
    admin_a = tmp_path / "repoA" / ".git" / "worktrees" / "phase1"
    _registered_pointer(a / "wt" / "phase1", admin_a, backref="self")
    _backdate(a)
    # Run B: pointer exists but admin backref points to a DIFFERENT path
    b = _run_dir(root, "runB")
    _state(b, stage="done", waiting=None, baseRef="main")
    admin_b = tmp_path / "repoB" / ".git" / "worktrees" / "phase1"
    _registered_pointer(b / "wt" / "phase1", admin_b, backref="other")
    _backdate(b)

    _, objs = _scan(root)
    ids = _by_id(objs)
    ca = _child(ids["runA"], "phase1")
    cb = _child(ids["runB"], "phase1")
    assert ca["reason"] == "wt-registered" and ca["registered"] is True
    assert cb["reason"] == "registration-unprovable" and cb["registered"] == "unprovable"
    assert cb["eligible"] is False


def test_w5_dangling_pointer_unprovable(tmp_path):
    """A pointer file with NO admin dir at all ⇒ registration-unprovable, NOT eligible (edge 5)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "dangle")
    _state(d, stage="done", waiting=None, baseRef="main")
    admin = tmp_path / "gone" / ".git" / "worktrees" / "phase1"  # never created
    _registered_pointer(d / "wt" / "phase1", admin, backref="none")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["dangle"], "phase1")
    assert c["reason"] == "registration-unprovable"
    assert c["registered"] == "unprovable"
    assert c["eligible"] is False


def test_w5_no_pointer_is_not_registered(tmp_path):
    """A drive-owned dir with NO .git pointer at all ⇒ registered:false (the only W7 path)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "nopt")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True)  # plain dir, no .git
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["nopt"], "phase1")["registered"] is False


# --------------------------------------------------------------------------- #
# AC9: live ancestry probe (read-only) runs in Phase 1
# --------------------------------------------------------------------------- #
def test_ancestry_ancestor_eligible(tmp_path):
    repo = _make_owning_repo(tmp_path, "anc-yes", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "anc-yes")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))  # no completedAt
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["anc-yes"], "phase1")["eligible"] is True


def test_ancestry_not_ancestor_skips(tmp_path):
    repo = _make_owning_repo(tmp_path, "anc-no", ancestor=False)
    root = tmp_path / "runs"
    d = _run_dir(root, "anc-no")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["anc-no"], "phase1")["reason"] == "not-ancestor"


def test_ancestry_baseref_absent_unprovable(tmp_path):
    """baseRef absent in the owning repo ⇒ git rc>1 ⇒ skip:ancestry-unprovable."""
    repo = _make_owning_repo(tmp_path, "anc-bad", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "anc-bad")
    _state(d, stage="done", waiting=None, baseRef="nonexistent-ref", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["anc-bad"], "phase1")["reason"] == "ancestry-unprovable"


# --------------------------------------------------------------------------- #
# AC10: the ONE completedAt rule (W4 authorization only — never a W7 bypass)
# --------------------------------------------------------------------------- #
def test_completedAt_authorizes_w4_unresolvable_repo(tmp_path):
    """A parseable completedAt + W7b-clean dir ⇒ eligible even with UNRESOLVABLE repo / no
    ancestor and NO recorded child inventory."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-ok")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["ca-ok"], "phase1")
    assert c["eligible"] is True
    assert _by_id(objs)["ca-ok"]["owningRepo"] is None


def test_torn_completedAt_does_not_authorize(tmp_path):
    """An UNPARSEABLE completedAt authorizes nothing: a clean dir under an UNRESOLVABLE repo
    falls through to W4 ⇒ skip:unresolvable-repo (the marker did not flip it eligible)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-torn")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE
    (d / "completedAt").write_text("not-a-timestamp\n", encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["ca-torn"], "phase1")
    assert c["eligible"] is False
    assert c["reason"] == "unresolvable-repo"


# --------------------------------------------------------------------------- #
# AC11: drive-owned-name matching
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,owned", [
    ("1.2", True), ("4a.3", True), ("phase1", True), ("design2", True),
    ("ship", True), ("verify", True), ("verify2", True), ("finalize", True),
    ("converter", False), ("scripts", False), ("foo", False), ("test_projects", False),
])
def test_drive_owned_name_grammar(tmp_path, name, owned):
    root = tmp_path / "runs"
    d = _run_dir(root, "names")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / name).mkdir(parents=True)
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["names"], name)
    assert c["driveOwned"] is owned
    if not owned:
        assert c["reason"] == "not-drive-owned"


# --------------------------------------------------------------------------- #
# AC12: age union (most-recent-wins; completedAt one input; max over ALL event-log lines)
# --------------------------------------------------------------------------- #
def test_age_recent_mtime_beats_old_completedAt(tmp_path):
    """An OLD completedAt coexists with a RECENT mtime ⇒ the RECENT mtime wins (NOT aged)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "age-mix")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "completedAt").write_text("2020-01-01T00:00:00Z\n", encoding="utf-8")  # very old
    _backdate(d, epoch=RECENT)   # recent run-dir mtime
    _, objs = _scan(root)
    o = _by_id(objs)["age-mix"]
    assert o["pastThreshold"] is False        # recent wins ⇒ not aged
    assert o["ageAnchor"] == "mtime"


def test_age_max_over_all_eventlog_lines_not_last(tmp_path):
    """A RECENT event-log line FOLLOWED by an OLDER/backdated tail line ⇒ the RECENT earlier
    line still wins (max over all lines, not the last line) ⇒ NOT aged."""
    root = tmp_path / "runs"
    d = _run_dir(root, "age-log")
    _state(d, stage="done", waiting=None, baseRef="main")
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(RECENT))
    log = (
        json.dumps({"event": "dispatch", "at": recent_iso}) + "\n"
        + json.dumps({"event": "verdict", "at": "2020-01-01T00:00:00Z"}) + "\n"
        + "this is a torn/unparseable tail line\n"
    )
    (d / "event-log.jsonl").write_text(log, encoding="utf-8")
    _backdate(d, epoch=OLD)   # old mtime, so only the event-log can make it recent
    _, objs = _scan(root)
    o = _by_id(objs)["age-log"]
    assert o["pastThreshold"] is False        # the recent earlier line wins ⇒ not aged
    assert o["ageAnchor"] == "event-log"


def test_age_torn_line_before_recent_line_still_counts(tmp_path):
    """Robustness to a TORN line PRECEDING a valid recent line: a whole-file `jq '.at'`
    errors on the first invalid line and STOPS, dropping every timestamp after it (the recent
    line would be lost ⇒ the run looks aged ⇒ age FAIL-OPEN). With per-line tolerant parsing
    the torn line is skipped and the later recent line still makes the run NOT aged."""
    root = tmp_path / "runs"
    d = _run_dir(root, "age-torn-first")
    _state(d, stage="done", waiting=None, baseRef="main")
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(RECENT))
    log = (
        "this is a torn/unparseable leading line\n"                                  # torn FIRST
        + json.dumps({"event": "dispatch", "at": "2020-01-01T00:00:00Z"}) + "\n"     # old
        + json.dumps({"event": "verdict", "at": recent_iso}) + "\n"                  # recent, AFTER torn
    )
    (d / "event-log.jsonl").write_text(log, encoding="utf-8")
    _backdate(d, epoch=OLD)   # old mtime ⇒ only the event-log can make it recent
    _, objs = _scan(root)
    o = _by_id(objs)["age-torn-first"]
    assert o["pastThreshold"] is False        # recent line survives the torn line ⇒ NOT aged
    assert o["ageAnchor"] == "event-log"


# --------------------------------------------------------------------------- #
# AC13: KEEP history (.md/.json/.jsonl never in tierL.logs)
# --------------------------------------------------------------------------- #
def test_keep_history_files(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "hist")
    _state(d, stage="done", waiting=None, baseRef="main")
    for f in ["review-design-1.md", "state.json", "event-log.jsonl",
              "codex-review-design.md", "decisions.md"]:
        (d / f).write_text("x", encoding="utf-8")
    (d / "codex-raw-design.log").write_text("y", encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    names = {x["name"] for x in _by_id(objs)["hist"]["tierL"]["logs"]}
    assert names == {"codex-raw-design.log"}   # only the heavy log, no .md/.json/.jsonl


# --------------------------------------------------------------------------- #
# AC14: --json schema + closed vocabulary + three-valued registered
# --------------------------------------------------------------------------- #
def test_json_schema_keys(tmp_path):
    repo = _make_owning_repo(tmp_path, "schema", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "schema")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["schema"]
    assert set(o.keys()) == {
        "runId", "owningRepo", "ageDays", "ageAnchor", "pastThreshold", "tierL", "tierW",
    }
    assert set(o["tierL"].keys()) == {"eligible", "reason", "logs", "bytes"}
    c = o["tierW"]["children"][0]
    assert set(c.keys()) == {"name", "eligible", "reason", "driveOwned", "registered"}


def test_all_skip_reasons_in_closed_vocab(tmp_path):
    """Build a root exercising MANY skip reasons; assert every emitted reason ∈ the closed set,
    and that the legacy placeholder `no-completedAt-and-no-ancestry` never appears."""
    root = tmp_path / "runs"
    # waiting
    a = _run_dir(root, "r-waiting"); _state(a, stage="done", waiting="gateB", baseRef="main")
    (a / "wt" / "phase1").mkdir(parents=True); _backdate(a)
    # inflight
    b = _run_dir(root, "r-inflight"); _state(b, stage="done", waiting=None, baseRef="main")
    (b / "inflight-x.marker").write_text("", encoding="utf-8")
    (b / "wt" / "phase1").mkdir(parents=True); _backdate(b)
    # not-done
    c = _run_dir(root, "r-notdone"); _state(c, stage="execute", waiting=None, baseRef="main")
    (c / "wt" / "phase1").mkdir(parents=True); _backdate(c)
    # not-aged
    e = _run_dir(root, "r-notaged"); _state(e, stage="done", waiting=None, baseRef="main")
    (e / "wt" / "phase1").mkdir(parents=True); _backdate(e, epoch=RECENT)
    # not-drive-owned
    f = _run_dir(root, "r-adhoc"); _state(f, stage="done", waiting=None, baseRef="main")
    (f / "wt" / "converter").mkdir(parents=True); _backdate(f)
    # unresolvable-repo (drive-owned, no completedAt, unresolvable)
    g = _run_dir(root, "r-unres"); _state(g, stage="done", waiting=None, baseRef="main")
    (g / "wt" / "phase1").mkdir(parents=True); _backdate(g)
    # wt-registered + registration-unprovable
    h = _run_dir(root, "r-reg"); _state(h, stage="done", waiting=None, baseRef="main")
    _registered_pointer(h / "wt" / "phase1", tmp_path / "rh" / ".git" / "worktrees" / "p1", backref="self")
    _registered_pointer(h / "wt" / "design1", tmp_path / "rh2" / ".git" / "worktrees" / "d1", backref="other")
    _backdate(h)
    # dirty + not-ancestor + ancestry-unprovable
    repo_anc = _make_owning_repo(tmp_path, "r-dirty", ancestor=True)
    i = _run_dir(root, "r-dirty"); _state(i, stage="done", waiting=None, baseRef="main", repoRoot=str(repo_anc))
    _clean_pushed_checkout(i / "wt" / "phase1")
    (i / "wt" / "phase1" / "edit").write_text("x", encoding="utf-8"); _backdate(i)
    repo_no = _make_owning_repo(tmp_path, "r-noanc", ancestor=False)
    j = _run_dir(root, "r-noanc"); _state(j, stage="done", waiting=None, baseRef="main", repoRoot=str(repo_no))
    _clean_pushed_checkout(j / "wt" / "phase1"); _backdate(j)
    repo_bad = _make_owning_repo(tmp_path, "r-badref", ancestor=True)
    k = _run_dir(root, "r-badref"); _state(k, stage="done", waiting=None, baseRef="no-such", repoRoot=str(repo_bad))
    _clean_pushed_checkout(k / "wt" / "phase1"); _backdate(k)

    _, objs = _scan(root)
    seen = set()
    for o in objs:
        if not o["tierL"]["eligible"] and o["tierL"]["reason"]:
            seen.add(o["tierL"]["reason"])
        for ch in o["tierW"]["children"]:
            if not ch["eligible"] and ch["reason"]:
                seen.add(ch["reason"])
    assert seen <= CLOSED_VOCAB, f"reason(s) outside closed vocab: {seen - CLOSED_VOCAB}"
    assert "no-completedAt-and-no-ancestry" not in seen
    # confirm the representative reasons actually got exercised
    assert {"waiting", "inflight-open", "not-done", "not-aged", "not-drive-owned",
            "unresolvable-repo", "wt-registered", "registration-unprovable",
            "dirty", "not-ancestor", "ancestry-unprovable"} <= seen


def test_registered_field_three_valued(tmp_path):
    """All three encodings of `registered` are emitted: true, false, "unprovable"."""
    root = tmp_path / "runs"
    d = _run_dir(root, "regs")
    _state(d, stage="done", waiting=None, baseRef="main")
    _registered_pointer(d / "wt" / "phase1", tmp_path / "rA" / ".git" / "worktrees" / "p1", backref="self")     # true
    (d / "wt" / "design1").mkdir(parents=True)                                                                   # false (no pointer)
    _registered_pointer(d / "wt" / "ship", tmp_path / "rB" / ".git" / "worktrees" / "s1", backref="none")        # unprovable
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["regs"]
    assert _child(o, "phase1")["registered"] is True
    assert _child(o, "design1")["registered"] is False
    assert _child(o, "ship")["registered"] == "unprovable"


# --------------------------------------------------------------------------- #
# AC15: pinned skip-reason tokens (stable --json contract)
# --------------------------------------------------------------------------- #
def test_pinned_token_unresolvable_repo(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "t-unres"); _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True); _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["t-unres"], "phase1")["reason"] == "unresolvable-repo"


def test_pinned_token_wt_registered(tmp_path):
    root = tmp_path / "runs"
    d = _run_dir(root, "t-reg"); _state(d, stage="done", waiting=None, baseRef="main")
    _registered_pointer(d / "wt" / "phase1", tmp_path / "r" / ".git" / "worktrees" / "p1", backref="self")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["t-reg"], "phase1")["reason"] == "wt-registered"


def test_pinned_token_registration_unprovable_missing_admin(tmp_path):
    """A pointer whose admin dir exists but has NO gitdir backref ⇒ registration-unprovable."""
    root = tmp_path / "runs"
    d = _run_dir(root, "t-unp"); _state(d, stage="done", waiting=None, baseRef="main")
    _registered_pointer(d / "wt" / "phase1", tmp_path / "r" / ".git" / "worktrees" / "p1", backref="missing")
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["t-unp"], "phase1")["reason"] == "registration-unprovable"


# --------------------------------------------------------------------------- #
# AC16: --root / --now / --age-days seams
# --------------------------------------------------------------------------- #
def test_age_days_zero_passes_age_gate(tmp_path):
    """--age-days 0 makes every aged-only gate pass on age (a recent run is now 'aged')."""
    root = tmp_path / "runs"
    d = _run_dir(root, "recent")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "codex-raw-x.log").write_text("z", encoding="utf-8")
    _backdate(d, epoch=RECENT)
    # default 14d ⇒ not aged
    _, objs14 = _scan(root, age_days=14)
    assert _by_id(objs14)["recent"]["tierL"]["reason"] == "not-aged"
    # --age-days 0 ⇒ aged ⇒ Tier-L eligible
    _, objs0 = _scan(root, age_days=0)
    assert _by_id(objs0)["recent"]["tierL"]["eligible"] is True


# --------------------------------------------------------------------------- #
# LENS-2 fix 1: a present non-null `waiting` (false / 0 / string) is NOT live-quiet
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("waiting_val", [False, 0, "gateB"])
def test_waiting_false_or_zero_is_not_live_quiet(tmp_path, waiting_val):
    """LENS-2 fail-safe: `state_field` collapsed JSON false/0/null to empty, so `waiting:false`
    (and `waiting:0`) passed the liveness gate as 'not waiting' and a done+aged+clean run could
    reach `eligible` on BOTH tiers. A present-and-non-null `waiting` (false/0/string) means the
    run is NOT live-quiet ⇒ skip:waiting on BOTH tiers, never eligible.
    Mutation-verify: RED against the old `[ -z "$(state_field waiting)" ]` gate (which let
    false/0 through ⇒ Tier-L eligible / Tier-W not 'waiting')."""
    root = tmp_path / "runs"
    d = _run_dir(root, "wq")
    _state(d, stage="done", waiting=waiting_val, baseRef="main")  # present, non-null
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # would W4-authorize
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")                   # would pass W7b if reached
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["wq"]
    # BOTH tiers refuse with the waiting reason — never eligible.
    assert o["tierL"]["eligible"] is False
    assert o["tierL"]["reason"] == "waiting"
    c = _child(o, "phase1")
    assert c["eligible"] is False
    assert c["reason"] == "waiting"


def test_waiting_null_is_live_quiet(tmp_path):
    """Companion to the above: an EXPLICIT JSON null `waiting` (and an ABSENT key) IS live-quiet
    — the gate must pass for null/absent, only refuse a present non-null value."""
    root = tmp_path / "runs"
    d = _run_dir(root, "wq-null")
    _state(d, stage="done", waiting=None, baseRef="main")  # explicit JSON null
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["wq-null"]["tierL"]["eligible"] is True  # null ⇒ not 'waiting'


# --------------------------------------------------------------------------- #
# LENS-2 fix 2: an UNREADABLE event-log.jsonl is NOT conflated with empty (age fail-safe)
# --------------------------------------------------------------------------- #
def test_unreadable_eventlog_not_treated_as_aged(tmp_path):
    """LENS-2 fail-safe: a PRESENT-but-UNREADABLE event-log.jsonl (perm-denied) holding a RECENT
    timestamp was conflated with an empty log ⇒ age fell back to the stale OLD mtime ⇒ the run
    was wrongly judged aged ⇒ eligible. A read FAILURE must NOT be treated as aged: the
    unreadable log may hold a recent timestamp, so the run is treated as recent (NOT aged) and
    NEVER swept. Mutation-verify: RED against the old `eventlog_newest_epoch` that returned
    empty on a read failure (⇒ mtime fallback ⇒ aged ⇒ Tier-L eligible)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "unreadable-log")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(RECENT))
    log = d / "event-log.jsonl"
    log.write_text(json.dumps({"event": "dispatch", "at": recent_iso}) + "\n", encoding="utf-8")
    os.chmod(log, 0o000)        # present but UNREADABLE
    _backdate(d, epoch=OLD)     # old mtime — the ONLY readable age input is stale
    try:
        _, objs = _scan(root)
    finally:
        os.chmod(log, 0o644)    # restore so tmp cleanup can read it
    o = _by_id(objs)["unreadable-log"]
    # The unreadable log could hold a recent ts ⇒ fail-safe: NOT aged, NOT eligible.
    assert o["pastThreshold"] is False
    assert o["tierL"]["eligible"] is False
    assert o["tierL"]["reason"] == "not-aged"
    assert o["ageAnchor"] == "event-log"   # the unreadable log supplied the (now) anchor


# --------------------------------------------------------------------------- #
# LENS-2 fix 3: resolve_owning_repo filters ad-hoc-named registered children
# --------------------------------------------------------------------------- #
def test_resolve_owning_repo_ignores_adhoc_registered_child(tmp_path):
    """LENS-2 fail-safe: the gitdir fallback trusted the FIRST registered wt/<name>/.git with NO
    drive-owned-name filter, so an ad-hoc child (e.g. `converter`) registered into a FOREIGN repo
    resolved the owning repo to that repo ⇒ the ancestry probe ran in the WRONG repo and could
    falsely authorize a sibling drive-owned child. Only a DRIVE-OWNED-named registered child may
    resolve the owning repo. With only an ad-hoc registered child, the owning repo is UNRESOLVABLE
    ⇒ the drive-owned no-pointer child (no completedAt) is skip:unresolvable-repo, NOT eligible.
    Mutation-verify: RED against pre-fix (owningRepo == the foreign repo; phase1 eligible via the
    foreign ancestry probe)."""
    # A foreign repo where drive/<runId> IS an ancestor of main (so the WRONG-repo probe would
    # falsely say 'yes'). runId == the run-dir name below.
    foreign = _make_owning_repo(tmp_path, "adhoc-repo", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "adhoc-repo")
    _state(d, stage="done", waiting=None, baseRef="main")  # NO repoRoot ⇒ gitdir fallback
    # Ad-hoc-named child registered (path-equality) into the FOREIGN repo's admin entry.
    admin = foreign / ".git" / "worktrees" / "converter"
    _registered_pointer(d / "wt" / "converter", admin, backref="self")
    # A drive-owned no-pointer child whose ancestry the foreign repo would (wrongly) authorize.
    (d / "wt" / "phase1").mkdir(parents=True)
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["adhoc-repo"]
    assert o["owningRepo"] is None   # ad-hoc child must NOT resolve the owning repo
    # phase1 has no completedAt and no resolvable repo ⇒ unresolvable-repo, NEVER eligible.
    c = _child(o, "phase1")
    assert c["eligible"] is False
    assert c["reason"] == "unresolvable-repo"
    # the ad-hoc child itself is W6-skipped
    assert _child(o, "converter")["reason"] == "not-drive-owned"


# --------------------------------------------------------------------------- #
# LENS-2 fix 4 (codex P1): human-summary tallies — skips counted on BOTH tiers,
# bytes summed THEN converted to MB (no per-run floor)
# --------------------------------------------------------------------------- #
def test_human_summary_counts_tierW_skip_under_tierL_eligible(tmp_path):
    """Codex P1: `skipped` only incremented when Tier-L was non-eligible, so a Tier-W-skipped
    child under a Tier-L-ELIGIBLE run was omitted from the advertised skipped count. A run with
    an eligible Tier-L (would-sweep logs) AND a skipped Tier-W child must contribute the Tier-W
    skip to the count. Mutation-verify: RED against pre-fix (skipped==0 ⇒ '0 runs/items skipped')."""
    root = tmp_path / "runs"
    d = _run_dir(root, "tl-elig-tw-skip")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE repo
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")  # Tier-L eligible (aged+done)
    (d / "wt" / "converter").mkdir(parents=True)                     # Tier-W skip (not-drive-owned)
    _backdate(d)
    cp_h = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14"],
        home=root,
    )
    assert cp_h.returncode == 0
    summary = cp_h.stdout.strip().splitlines()[-1]
    assert summary.startswith("summary:")
    # Tier-L eligible (so NOT counted as a Tier-L skip), but the Tier-W child IS a skip ⇒ ≥1.
    m = re.search(r"·\s*(\d+)\s+runs/items skipped", summary)
    assert m is not None, summary
    assert int(m.group(1)) >= 1, f"Tier-W skip under Tier-L-eligible must be counted: {summary}"


def test_human_summary_bytes_summed_then_converted(tmp_path):
    """Codex P1: `tierL_mb` floored each run's bytes (`/1048576`) BEFORE summing, so several
    sub-MB reclaimable logs reported ~0 MB total. With bytes summed THEN converted once, three
    runs each holding a ~0.5 MB log sum to ~1 MB (not floor(0.5)*3 == 0). Mutation-verify: RED
    against pre-fix (reports ~0 MB)."""
    root = tmp_path / "runs"
    half_mb = "x" * (600 * 1024)   # ~0.586 MB each; three of them sum to ~1.7 MB
    for i in range(3):
        d = _run_dir(root, f"sub-mb-{i}")
        _state(d, stage="done", waiting=None, baseRef="main")
        (d / "codex-raw-x.log").write_text(half_mb, encoding="utf-8")
        _backdate(d)
    cp_h = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14"],
        home=root,
    )
    assert cp_h.returncode == 0
    summary = cp_h.stdout.strip().splitlines()[-1]
    m = re.search(r"reclaim ~(\d+) MB", summary)
    assert m is not None, summary
    assert int(m.group(1)) >= 1, f"per-run flooring lost sub-MB logs: {summary}"


# --------------------------------------------------------------------------- #
# LENS-1 missing tests: AC1 missing-jq / missing-state.json; AC4 repoRoot beats gitdir;
# AC7 Tier-W gate-order on the W tier; AC12 completedAt-anchor + future-clamp
# --------------------------------------------------------------------------- #
def test_missing_jq_exits_zero_no_classify(tmp_path):
    """AC1: jq absent ⇒ the script cannot classify; it prints a stderr notice and exits 0
    (best-effort, D3 — a missing tool must never abort a new run's setup). Simulated via a
    restricted PATH containing only the dirs needed to run bash but NOT jq."""
    root = tmp_path / "runs"
    d = _run_dir(root, "any")
    _state(d, stage="done", waiting=None, baseRef="main")
    _backdate(d)
    # Build a symlink farm exposing the real interpreters/tools the script needs at startup
    # (sh/bash/date/grep/printf-via-coreutils) but deliberately OMITTING jq.
    binshim = tmp_path / "binshim"
    binshim.mkdir()
    import shutil
    for tool in ["bash", "sh", "env", "date", "grep", "cat", "head", "stat", "sed",
                 "dirname", "git", "tr", "printf"]:
        p = shutil.which(tool)
        if p:
            try:
                os.symlink(p, binshim / tool)
            except FileExistsError:
                pass
    assert shutil.which("jq", path=str(binshim)) is None  # jq is NOT on the shim PATH
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--json"],
        home=root, env={"PATH": str(binshim)},
    )
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""          # nothing classified
    assert "jq not found" in cp.stderr


def test_missing_state_json_exits_zero_skips(tmp_path):
    """AC1: a run dir with NO state.json ⇒ exit 0, conservative skip — no done signal ⇒
    skip:not-done on Tier-L (fail-safe), reported, never crashes."""
    root = tmp_path / "runs"
    d = _run_dir(root, "no-state")  # no state.json at all
    (d / "codex-raw-x.log").write_text("z", encoding="utf-8")
    _backdate(d)
    cp, objs = _scan(root)
    assert cp.returncode == 0
    o = _by_id(objs)["no-state"]
    assert o["tierL"]["eligible"] is False
    assert o["tierL"]["reason"] == "not-done"


def test_owning_repo_reporoot_beats_conflicting_gitdir(tmp_path):
    """AC4 precedence: state.repoRoot (primary) WINS over a CONFLICTING registered gitdir
    (fallback). A run with BOTH a valid state.repoRoot AND a registered wt/<n>/.git pointing at
    a DIFFERENT repo must resolve owningRepo to the repoRoot, not the gitdir's repo."""
    primary = _make_owning_repo(tmp_path, "primary-repo", ancestor=True)
    other = tmp_path / "other-repo"
    admin = other / ".git" / "worktrees" / "phase1"
    root = tmp_path / "runs"
    d = _run_dir(root, "rr-wins")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(primary))
    _registered_pointer(d / "wt" / "phase1", admin, backref="self")  # conflicting gitdir → other
    _backdate(d)
    _, objs = _scan(root)
    assert _by_id(objs)["rr-wins"]["owningRepo"] == str(primary)     # primary beats fallback


def test_tierW_w1_waiting_wins_before_w4(tmp_path):
    """AC7 (Tier-W gate-order): W1 (waiting) wins BEFORE W4 — a waiting run with a drive-owned
    no-pointer child reports skip:waiting on the child (not unresolvable-repo / not-ancestor)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "w-order")
    _state(d, stage="done", waiting="gateB", baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True)
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["w-order"], "phase1")["reason"] == "waiting"


def test_tierW_w2_inflight_wins_before_w4(tmp_path):
    """AC7 (Tier-W gate-order): W2 (inflight-open) wins BEFORE W4 on the W tier."""
    root = tmp_path / "runs"
    d = _run_dir(root, "i-order")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "inflight-x.marker").write_text("", encoding="utf-8")
    (d / "wt" / "phase1").mkdir(parents=True)
    _backdate(d)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["i-order"], "phase1")["reason"] == "inflight-open"


def test_tierW_w3_not_aged_wins_before_w4(tmp_path):
    """AC7 (Tier-W gate-order): W3 (not-aged) wins BEFORE W4 on the W tier — a RECENT run with a
    drive-owned no-pointer child reports skip:not-aged on the child, not an authorization reason."""
    root = tmp_path / "runs"
    d = _run_dir(root, "a-order")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True)
    _backdate(d, epoch=RECENT)
    _, objs = _scan(root)
    assert _child(_by_id(objs)["a-order"], "phase1")["reason"] == "not-aged"


def test_age_anchor_completedAt_when_newest(tmp_path):
    """AC12: when a PARSEABLE completedAt is the NEWEST of the three age inputs, ageAnchor reports
    `completedAt`. (Old mtime, no event-log; a recent completedAt is the max.)"""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-anchor")
    _state(d, stage="done", waiting=None, baseRef="main")
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(RECENT))
    (d / "completedAt").write_text(recent_iso + "\n", encoding="utf-8")  # recent ⇒ the max
    _backdate(d, epoch=OLD)   # old mtime, no event-log ⇒ completedAt is newest
    _, objs = _scan(root)
    o = _by_id(objs)["ca-anchor"]
    assert o["ageAnchor"] == "completedAt"
    assert o["pastThreshold"] is False   # recent completedAt ⇒ not aged


def test_age_future_timestamp_clamps_to_zero(tmp_path):
    """AC12: a FUTURE max age input (event-log timestamp after --now) clamps age to 0 ⇒
    pastThreshold:false ⇒ a future-touched run is NEVER swept (no negative-age crash)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "future")
    _state(d, stage="done", waiting=None, baseRef="main")
    future_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW + 100 * DAY))
    (d / "event-log.jsonl").write_text(
        json.dumps({"event": "dispatch", "at": future_iso}) + "\n", encoding="utf-8")
    _backdate(d, epoch=OLD)
    _, objs = _scan(root)
    o = _by_id(objs)["future"]
    assert o["ageDays"] == 0              # clamped, no negative age
    assert o["pastThreshold"] is False


# --------------------------------------------------------------------------- #
# P2 tests: dangling inflight-*.marker symlink; W5 .git-is-a-DIRECTORY not-registered
# --------------------------------------------------------------------------- #
def test_dangling_inflight_marker_symlink_counts_as_open(tmp_path):
    """P2: a DANGLING inflight-*.marker symlink (target absent) still counts as an open marker
    (`-e || -L`), mirroring drive-conformance.sh ⇒ skip:inflight-open on both tiers."""
    root = tmp_path / "runs"
    d = _run_dir(root, "dangling-inflight")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True)
    os.symlink(str(tmp_path / "nonexistent-marker-target"),
               str(d / "inflight-finalize.marker"))  # dangling symlink
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["dangling-inflight"]
    assert o["tierL"]["reason"] == "inflight-open"
    assert _child(o, "phase1")["reason"] == "inflight-open"


def test_w5_git_is_a_directory_is_not_registered(tmp_path):
    """P2: a full-checkout `wt/<name>/.git` DIRECTORY (not a worktree gitdir pointer FILE) ⇒
    not-registered (registered:false) — the only fall-through to W7 — distinct from total .git
    absence. A clean such checkout under a W4-authorized run is therefore W7b-eligible."""
    root = tmp_path / "runs"
    d = _run_dir(root, "git-dir")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # W4-authorizes
    _clean_pushed_checkout(d / "wt" / "phase1")  # a real git checkout ⇒ wt/phase1/.git is a DIR
    assert (d / "wt" / "phase1" / ".git").is_dir()
    _backdate(d)
    _, objs = _scan(root)
    c = _child(_by_id(objs)["git-dir"], "phase1")
    assert c["registered"] is False              # .git DIRECTORY ⇒ not-registered (not unprovable)
    assert c["eligible"] is True                 # clean + W4-authorized ⇒ eligible via W7b


def test_human_report_smoke(tmp_path):
    """The default (non-JSON) report carries the run/Tier headers + summary line."""
    root = tmp_path / "runs"
    d = _run_dir(root, "smoke")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "wt" / "phase1").mkdir(parents=True)
    _backdate(d)
    cp, _ = _scan(root, json_mode=True)  # ensure scan worked
    cp_h = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14"],
        home=root,
    )
    assert cp_h.returncode == 0
    out = cp_h.stdout
    assert "run: smoke" in out
    assert "Tier-L (heavy logs):" in out
    assert "Tier-W (drive-owned worktrees):" in out
    assert out.strip().splitlines()[-1].startswith("summary:")
