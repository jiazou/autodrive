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


def _scan(root, *, age_days=14, now=NOW, json_mode=True, home=None, apply=False,
          trash_cmd=None):
    """Run the script over `root` and return (CompletedProcess, list-of-json-objects).

    apply=True adds --apply (the destructive path). trash_cmd, when given, is exported as
    RETENTION_TRASH_CMD so the destructive verb is a test-injected shim (graveyard mv /
    failing command), keeping the apply tests trash-independent and deterministic."""
    args = [str(SCRIPT), "--root", str(root), "--now", str(now), "--age-days", str(age_days)]
    if json_mode:
        args.append("--json")
    if apply:
        args.append("--apply")
    env = {"RETENTION_TRASH_CMD": trash_cmd} if trash_cmd else None
    cp = run_script(args, home=home or root, env=env)
    objs = []
    if json_mode:
        for line in cp.stdout.splitlines():
            line = line.strip()
            if line:
                objs.append(json.loads(line))
    return cp, objs


def _graveyard_shim(tmp_path):
    """Create an executable `trash`-shim that MOVES its argument into a graveyard dir (instead
    of the real Trash), so apply tests are deterministic + host-independent. Returns
    (shim_path, graveyard_dir). The shim mirrors `trash <path>` (move to a holding area)."""
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim = tmp_path / "trash-shim.sh"
    # Use a unique destination name per call (basename can collide across runs) — append the
    # source's parent dir name so wt/<name> from different runs don't clobber in the graveyard.
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'dest="{graveyard}"\n'
        'for p in "$@"; do\n'
        '  base="$(basename "$p")"; parent="$(basename "$(dirname "$p")")"\n'
        '  mv "$p" "$dest/$parent-$base" 2>/dev/null || exit 1\n'
        'done\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)
    return shim, graveyard


def _failing_shim(tmp_path):
    """An executable shim that always exits non-zero WITHOUT moving anything — simulates a
    `trash` that is absent / fails. Returns the shim path."""
    shim = tmp_path / "trash-fail.sh"
    shim.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    os.chmod(shim, 0o755)
    return shim


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
# Phase-2 AC12: deletion tokens now EXIST but are GUARDED behind APPLY=1 (report-only is
# still the default). This REPLACES the Phase-1 structural-absence test
# `test_no_deletion_path_exists` (deletion tokens are now expected by design — the phase split
# DELIBERATELY adds --apply/trash/worktree-remove). We prove report-only stays the DEFAULT:
# the destructive verbs ($TRASH_CMD, git worktree remove/prune) are reachable ONLY when
# APPLY=1, and no `rm` is ever used as a deletion verb.
# --------------------------------------------------------------------------- #
def test_deletion_tokens_are_guarded_behind_apply():
    """The destructive verbs exist (Phase 2) but the apply functions that run them are gated:
    they are invoked ONLY inside the `if [ "$APPLY" -eq 1 ]` block in classify_run, never on
    the report-only path. Structurally: (a) the apply functions exist; (b) they are called
    ONLY under the APPLY=1 guard; (c) the script still contains NO bare `rm ` deletion verb."""
    text = SCRIPT.read_text(encoding="utf-8")
    stripped = "\n".join(re.sub(r"#.*", "", line) for line in text.splitlines())
    # (a) the destructive verbs are present (Phase 2 added them) — proves the phase bit.
    assert "git -C \"$repo\" worktree remove --force" in stripped
    assert "$TRASH_CMD" in stripped
    assert "--apply" in stripped
    # (b) every call to the apply_* functions is reached ONLY through the APPLY=1 guard.
    #     The ONLY call sites of apply_tier_L / apply_tier_W_child are inside the
    #     `if [ "$APPLY" -eq 1 ]` block; assert the guard precedes them in classify_run.
    apply_guard = stripped.find('if [ "$APPLY" -eq 1 ]')
    assert apply_guard != -1, "the APPLY=1 guard must exist"
    for fn in ("apply_tier_L \"$d\"", "apply_tier_W_child \"$d\""):
        call = stripped.find(fn)
        assert call != -1, f"expected a call to {fn}"
        assert call > apply_guard, (
            f"{fn} must be called only AFTER the APPLY=1 guard (report-only default)"
        )
    # (c) NO bare `rm ` deletion verb anywhere (D4: trash, never rm — even under apply).
    assert not re.search(r"(^|[^a-z])rm ", stripped), (
        "deletion must use trash (RETENTION_TRASH_CMD), never `rm`"
    )


def test_report_only_default_performs_no_deletion(tmp_path):
    """AC1/AC12 behavioral: WITHOUT --apply, an `eligible` Tier-L/Tier-W run is NOT mutated —
    the heavy log and the eligible worktree dir both REMAIN on disk, and every `action` is
    `none`. Report-only is the default."""
    repo = _make_owning_repo(tmp_path, "ro", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "ro")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    shim, graveyard = _graveyard_shim(tmp_path)
    _, objs = _scan(root, trash_cmd=str(shim))   # NO apply
    o = _by_id(objs)["ro"]
    # Nothing moved, verdicts are eligible, all actions `none`.
    assert (d / "codex-raw-x.log").exists()
    assert (d / "wt" / "phase1").exists()
    assert list(graveyard.iterdir()) == []
    assert o["tierL"]["eligible"] is True and o["tierL"]["action"] == "none"
    assert _child(o, "phase1")["eligible"] is True
    assert _child(o, "phase1")["action"] == "none"


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


@pytest.mark.parametrize("content", [
    "2025-01-01T00:00:00 Z\n",   # interior whitespace before the Z
    "123 456\n",                 # interior whitespace between digits
    "2025-01-01T00:00:00\tZ\n",  # interior TAB
])
def test_interior_whitespace_completedAt_does_not_authorize(tmp_path, content):
    """A completedAt with INTERIOR whitespace / near-valid corruption is UNPARSEABLE ⇒ NOT a
    positive done/W4 signal (the run does not become DONE-authorized / eligible on that marker
    alone). The pre-fix code stripped ALL whitespace (`tr -d '[:space:]'`), making such
    corruption parse as a VALID timestamp ⇒ fail-open on the DONE gate AND W4 authorization.
    Here `stage != done`, so the marker is the ONLY possible done signal: it must not satisfy
    Wd/L3 (run ⇒ skip:not-done) nor W4 (child never authorized). Mutation-verify: RED against
    the `tr -d '[:space:]'` strip (which made `2025-01-01T00:00:00 Z` → a valid epoch ⇒
    not-done would have flipped to eligible / a W4-authorized clean child)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-interior-ws")
    _state(d, stage="execute", waiting=None, baseRef="main")  # NOT done; marker is the only signal
    (d / "completedAt").write_text(content, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")  # would pass W7b if W4 ever authorized
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["ca-interior-ws"]
    # The corrupt marker is no done signal ⇒ Tier-L skip:not-done (Wd/L3 fail-safe).
    assert o["tierL"]["eligible"] is False
    assert o["tierL"]["reason"] == "not-done"
    # Tier-W stops at the Wd DONE gate too — never authorized, never eligible.
    c = _child(o, "phase1")
    assert c["eligible"] is False
    assert c["reason"] == "not-done"


def test_completedAt_satisfies_done_gate_when_stage_not_done(tmp_path):
    """The DONE-gate OR-branch (Wd / L3): `state.stage != "done"` BUT a PARSEABLE completedAt
    is present ⇒ the run passes the DONE gate via the completedAt branch (is_done = parseable
    completedAt OR stage==done). Combined with waiting-null + no-inflight + aged + W4-authorized
    (completedAt also covers W4) + W7b-clean ⇒ Tier-W eligible and Tier-L eligible. Pins the
    acceptance-significant completedAt OR-branch of the DONE gate (not just the stage==done arm)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-done-branch")
    _state(d, stage="execute", waiting=None, baseRef="main")  # NOT done by stage; UNRESOLVABLE
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # parseable ⇒ done + W4
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    _, objs = _scan(root)
    o = _by_id(objs)["ca-done-branch"]
    # Tier-L: done via completedAt (stage!=done) + aged ⇒ eligible.
    assert o["tierL"]["eligible"] is True
    # Tier-W: Wd via completedAt + W4 via completedAt + W7b clean ⇒ eligible.
    c = _child(o, "phase1")
    assert c["eligible"] is True
    assert c["reason"] == ""


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
    # Phase 2 ADDS the per-tier/-child `action` field (additive apply-outcome layer).
    assert set(o["tierL"].keys()) == {"eligible", "reason", "action", "logs", "bytes"}
    c = o["tierW"]["children"][0]
    assert set(c.keys()) == {"name", "eligible", "reason", "driveOwned", "registered", "action"}
    # Under report-only the action is uniformly `none`.
    assert o["tierL"]["action"] == "none"
    assert c["action"] == "none"


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


def test_dangling_eventlog_symlink_not_treated_as_aged(tmp_path):
    """Fail-safe: a DANGLING event-log.jsonl SYMLINK (target absent) is a read failure, NOT a
    genuinely-absent log. The pre-fix `-e` test treated it as absent ⇒ age fell back to the
    stale OLD mtime ⇒ the run looked aged ⇒ Tier-L eligible (a fail-open). A dangling symlink
    may have pointed at a log with a RECENT timestamp, so it must NOW-anchor (age 0, never
    aged, never swept). Distinct from genuine absence (no symlink + no file), which legitimately
    contributes no event-log timestamp. Mutation-verify: RED against the old `[ -e ]`-only
    guard (dangling symlink ⇒ empty ⇒ mtime fallback ⇒ aged ⇒ eligible)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "dangling-log")
    _state(d, stage="done", waiting=None, baseRef="main")
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")  # would be Tier-L sweepable if aged
    os.symlink(str(tmp_path / "nonexistent-eventlog-target"),
               str(d / "event-log.jsonl"))   # dangling symlink (target absent)
    _backdate(d, epoch=OLD)                   # old mtime — the ONLY other readable age input is stale
    _, objs = _scan(root)
    o = _by_id(objs)["dangling-log"]
    # Dangling symlink ⇒ NOW anchor ⇒ NOT aged ⇒ NOT swept (fail-safe).
    assert o["pastThreshold"] is False
    assert o["tierL"]["eligible"] is False
    assert o["tierL"]["reason"] == "not-aged"
    assert o["ageAnchor"] == "event-log"   # the dangling log supplied the (NOW) anchor


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


def test_human_summary_verbs_are_apply_aware(tmp_path):
    """finding-2 (round-2, MINOR): the per-run report lines correctly switch to past tense under
    --apply, but the top-level summary stayed hypothetical ("would reclaim"/"would remove") for
    an action that ACTUALLY happened. Report mode keeps "would reclaim"/"would remove"; --apply
    uses "reclaimed"/"removed". One run with an eligible heavy log + an eligible drive-owned
    worktree exercises both Tier verbs. Mutation-verify: REDs pre-fix (apply summary said
    "would")."""
    repo = _make_owning_repo(tmp_path, "verbs", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "verbs")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")  # ~2 MB heavy log
    _clean_pushed_checkout(d / "wt" / "phase1")    # eligible drive-owned worktree
    _backdate(d)
    # Report mode: hypothetical verbs.
    cp_r = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14"],
        home=root,
    )
    sum_r = cp_r.stdout.strip().splitlines()[-1]
    assert "would reclaim" in sum_r and "would remove" in sum_r, (
        f"report mode must use hypothetical verbs: {sum_r}"
    )
    # Apply mode: past-tense verbs for an action that happened.
    shim, _ = _graveyard_shim(tmp_path)
    cp_a = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(shim)},
    )
    sum_a = cp_a.stdout.strip().splitlines()[-1]
    assert "reclaimed" in sum_a and "removed" in sum_a, (
        f"apply mode summary must use past-tense verbs: {sum_a}"
    )
    assert "would reclaim" not in sum_a and "would remove" not in sum_a, (
        f"apply mode summary must NOT use hypothetical verbs: {sum_a}"
    )


def test_apply_summary_tallies_actual_outcomes_not_eligible_verdicts(tmp_path):
    """A destructive tool MUST NOT claim it reclaimed space / removed worktrees that are still on
    disk. Under --apply the top-level summary swaps verbs to past-tense ("reclaimed"/"removed"),
    so its tallies MUST count ACTUAL action outcomes (swept/removed), NOT the pre-apply `eligible`
    verdicts. With a trash command that always fails, an eligible Tier-L log + eligible Tier-W
    worktree both stay on disk (action=trash-failed); the summary must report 0 reclaimed MB /
    0 removed worktrees and count both as skipped — NOT "reclaimed ~N MB / removed 1".

    Mutation-verify: this REDs against the pre-fix tally (which counted from `eligible` and
    over-claimed "reclaimed ~N MB · removed 1 worktrees · 0 skipped"). Per-run detail lines were
    already correct (FAILED (trash)); only the aggregate summary over-claimed."""
    repo = _make_owning_repo(tmp_path, "overclaim", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "overclaim")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")  # ~2 MB
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    fail = _failing_shim(tmp_path)
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(fail)},
    )
    assert cp.returncode == 0
    # The data really is still on disk — the summary must not say otherwise.
    assert (d / "codex-raw-x.log").exists()
    assert (d / "wt" / "phase1").exists()
    summary = cp.stdout.strip().splitlines()[-1]
    assert summary.startswith("summary:"), summary
    # Tier-L: 0 MB reclaimed across 0 runs (the trash failed).
    mL = re.search(r"Tier-L reclaimed ~(\d+) MB across (\d+) runs", summary)
    assert mL is not None, summary
    assert mL.group(1) == "0" and mL.group(2) == "0", (
        f"over-claims reclaimed bytes/runs for a trash-failed log: {summary}"
    )
    # Tier-W: 0 worktrees removed (the trash failed; the dir remains).
    mW = re.search(r"Tier-W removed (\d+) worktrees across (\d+) runs", summary)
    assert mW is not None, summary
    assert mW.group(1) == "0" and mW.group(2) == "0", (
        f"over-claims removed worktrees for a trash-failed child: {summary}"
    )
    # The not-acted-on items are accounted for as skipped, not silently dropped.
    mS = re.search(r"·\s*(\d+)\s+runs/items skipped", summary)
    assert mS is not None and int(mS.group(1)) >= 2, (
        f"trash-failed Tier-L + Tier-W items must be counted as skipped: {summary}"
    )


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


# =========================================================================== #
# PHASE 2 — --apply destructive path (AC1-6, AC12). RETENTION_TRASH_CMD graveyard
# shim keeps these trash-independent + deterministic.
# =========================================================================== #
# AC1: --apply recognized; absent ⇒ report-only (covered by
# test_report_only_default_performs_no_deletion above). Unknown flag ⇒ exit 2 (existing
# test_exit_two_on_unknown_flag). --apply itself is not a usage error:
def test_apply_flag_recognized_exit_zero(tmp_path):
    """--apply is a recognized boolean flag ⇒ a normal scan still exits 0 (not the exit-2
    unknown-flag lane)."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ok")
    _state(d, stage="done", waiting=None, baseRef="main")
    _backdate(d)
    shim, _ = _graveyard_shim(tmp_path)
    cp, _ = _scan(root, apply=True, trash_cmd=str(shim))
    assert cp.returncode == 0


# --------------------------------------------------------------------------- #
# AC2: Tier-L apply trashes ONLY heavy logs, keeps history.
# --------------------------------------------------------------------------- #
def test_apply_tierL_trashes_only_heavy_logs_keeps_history(tmp_path):
    repo = _make_owning_repo(tmp_path, "tl", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "tl")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    # heavy logs (should be swept) ...
    (d / "codex-raw-design.log").write_text("z" * 100, encoding="utf-8")
    (d / "codex-harden-1.log").write_text("y" * 50, encoding="utf-8")
    # ... history (must REMAIN)
    history = ["review-design-1.md", "event-log.jsonl", "decisions.md",
               "codex-review-design.md"]
    for f in history:
        (d / f).write_text("keep", encoding="utf-8")
    _backdate(d)
    shim, graveyard = _graveyard_shim(tmp_path)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    o = _by_id(objs)["tl"]
    # heavy logs GONE from the run dir, moved to the graveyard; action == swept.
    assert not (d / "codex-raw-design.log").exists()
    assert not (d / "codex-harden-1.log").exists()
    assert o["tierL"]["action"] == "swept"
    moved = {p.name for p in graveyard.iterdir()}
    assert any("codex-raw-design.log" in m for m in moved)
    assert any("codex-harden-1.log" in m for m in moved)
    # EVERY history file REMAINS, and state.json (always present) too.
    for f in history + ["state.json"]:
        assert (d / f).exists(), f"history file {f} must be kept"


def test_apply_tierL_snapshot_not_live_reenum_new_log_not_swept(tmp_path):
    """fix-1(a): apply_tier_L sweeps the classification-time SNAPSHOT, NOT a fresh live
    heavy_logs() re-enumeration. A heavy log that appears AFTER the snapshot is captured (so it
    was never previewed in the report) must NOT be swept — report == apply.

    Faithful injection: a `stat` wrapper that, while the snapshot stats `codex-raw-classified.log`,
    CREATES a NEW `codex-raw-late.log` in the run dir — i.e. a heavy log appears in the window
    between the snapshot's glob (already expanded, so it excludes the late log) and apply. The
    snapshot sweep iterates only the captured set ⇒ the late log survives. REDS pre-fix (the old
    `< <(heavy_logs "$d")` re-enumerated live at apply time and would have swept the late log)."""
    repo = _make_owning_repo(tmp_path, "snap", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "snap")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-classified.log").write_text("z" * 100, encoding="utf-8")  # in the snapshot
    _backdate(d)
    late = d / "codex-raw-late.log"
    # A `stat` wrapper: on a stat of codex-raw-classified.log (during the snapshot capture, whose
    # glob has already expanded), create the late log, THEN delegate to the real stat. The late
    # log thus exists for a live re-enum at apply time, but NOT in the snapshot's captured set.
    real_stat = subprocess.run(["which", "stat"], capture_output=True, text=True).stdout.strip()
    statwrap_dir = tmp_path / "statwrap"
    statwrap_dir.mkdir(parents=True, exist_ok=True)
    statwrap = statwrap_dir / "stat"
    statwrap.write_text(
        "#!/usr/bin/env bash\n"
        f'late="{late}"\n'
        f'realstat="{real_stat}"\n'
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    *codex-raw-classified.log) printf z > "$late" 2>/dev/null || true ;;\n'
        '  esac\n'
        'done\n'
        'exec "$realstat" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(statwrap, 0o755)
    shim, graveyard = _graveyard_shim(tmp_path)
    env = {"RETENTION_TRASH_CMD": str(shim),
           "PATH": f"{statwrap_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14",
         "--json", "--apply"],
        home=root, env=env,
    )
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["snap"]
    assert o["tierL"]["action"] == "swept"
    # The classified log was swept (it was in the snapshot) ...
    assert not (d / "codex-raw-classified.log").exists()
    # ... but the late log, created after the snapshot, is NOT swept (snapshot, not re-enum).
    assert late.exists(), "a heavy log created after the snapshot must NOT be swept"
    moved = {p.name for p in graveyard.iterdir()}
    assert not any("late" in m for m in moved), f"late log must not reach the graveyard: {moved}"


def test_apply_tierL_declines_run_gone_live_after_classification(tmp_path):
    """fix-1(b): apply_tier_L re-verifies run-level liveness BEFORE trashing, mirroring
    apply_tier_W_child. A run resumed (goes live) AFTER Tier-L classification but before the
    Tier-L sweep must NOT have its heavy logs swept ⇒ action=skipped-changed, logs intact.

    Faithful injection: a `stat` wrapper that, while the snapshot is being captured (it stats the
    `codex-raw-*.log`), writes an `inflight-*.marker` into the run dir — the run resumes in the
    classification→apply window. apply_tier_L's re-verify (has_open_inflight) then declines. The
    snapshot stat runs AFTER classify_tier_L's liveness check (so classification stays eligible)
    and BEFORE apply_tier_L (so the marker is present at apply time). REDS pre-fix (the old
    apply_tier_L had NO liveness recheck and would sweep the now-live run's logs)."""
    repo = _make_owning_repo(tmp_path, "tllive", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "tllive")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _backdate(d)
    # A `stat` wrapper: on a stat of a codex-raw log (the snapshot capture), the run resumes →
    # write an inflight marker, THEN delegate to the real stat. Real stat is resolved with the
    # wrapper dir stripped from PATH so we don't self-recurse.
    real_stat = subprocess.run(["which", "stat"], capture_output=True, text=True).stdout.strip()
    statwrap_dir = tmp_path / "statwrap"
    statwrap_dir.mkdir(parents=True, exist_ok=True)
    statwrap = statwrap_dir / "stat"
    statwrap.write_text(
        "#!/usr/bin/env bash\n"
        f'rundir="{d}"\n'
        f'realstat="{real_stat}"\n'
        # If any arg references a codex-raw log, the run goes LIVE (writes an inflight marker)
        # before delegating — this fires during the snapshot, after classification.
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    *codex-raw-*.log) printf x > "$rundir/inflight-implement-x.marker" 2>/dev/null || true ;;\n'
        '  esac\n'
        'done\n'
        'exec "$realstat" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(statwrap, 0o755)
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim, _ = _graveyard_shim(tmp_path)
    env = {"RETENTION_TRASH_CMD": str(shim),
           "PATH": f"{statwrap_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14",
         "--json", "--apply"],
        home=root, env=env,
    )
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["tllive"]
    # Classification still saw a quiet run (eligible); the apply-time re-verify saw the marker.
    assert o["tierL"]["eligible"] is True, "verdict must stay eligible (apply never re-classifies)"
    assert o["tierL"]["action"] == "skipped-changed", (
        "a run that went LIVE (inflight marker) after Tier-L classification must NOT be swept"
    )
    assert (d / "codex-raw-x.log").exists(), "no destructive verb on the now-live run's logs"


# --------------------------------------------------------------------------- #
# AC3: Tier-W apply removes an eligible no-pointer clean worktree (re-verify FIRST
# sequence); a skip:* child is UNTOUCHED; re-verify-ordering on a changed child.
# --------------------------------------------------------------------------- #
def test_apply_tierW_removes_eligible_leaves_skip(tmp_path):
    repo = _make_owning_repo(tmp_path, "tw", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "tw")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")          # eligible
    # a sibling skip:dirty child — must be left intact.
    _clean_pushed_checkout(d / "wt" / "design1")
    (d / "wt" / "design1" / "dirty").write_text("x", encoding="utf-8")
    _backdate(d)
    shim, graveyard = _graveyard_shim(tmp_path)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    o = _by_id(objs)["tw"]
    # eligible removed; verdict unchanged eligible:true, action removed.
    assert not (d / "wt" / "phase1").exists()
    c1 = _child(o, "phase1")
    assert c1["eligible"] is True and c1["action"] == "removed"
    # skip:dirty child untouched.
    assert (d / "wt" / "design1").exists()
    c2 = _child(o, "design1")
    assert c2["eligible"] is False and c2["reason"] == "dirty"
    assert c2["action"] == "none"


def test_apply_tierW_removes_unresolvable_completedAt_child(tmp_path):
    """Edge 7: the dominant historical reclaim path — UNRESOLVABLE repo + completedAt-authorized
    clean no-pointer child. Apply runs re-verify then trash-only (no git verbs, no repo) ⇒ dir
    gone, action removed."""
    root = tmp_path / "runs"
    d = _run_dir(root, "ca-elig")
    _state(d, stage="done", waiting=None, baseRef="main")  # UNRESOLVABLE repo
    (d / "completedAt").write_text("2025-01-01T00:00:00Z\n", encoding="utf-8")  # W4-authorizes
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    shim, graveyard = _graveyard_shim(tmp_path)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    o = _by_id(objs)["ca-elig"]
    assert o["owningRepo"] is None
    c = _child(o, "phase1")
    assert c["eligible"] is True and c["action"] == "removed"
    assert not (d / "wt" / "phase1").exists()


def _dirtying_shim(tmp_path, victim_dir):
    """A `trash`-shim that, the FIRST time it is asked to remove a dir, dirties `victim_dir`
    (writes an uncommitted file into it) BEFORE moving its own argument into the graveyard. This
    forces a REAL apply-time TOCTOU window: while child A is being trashed, sibling B (still
    pending in the apply loop) goes dirty — so B's re-verify (which the design runs BEFORE B's
    destructive verb) must DECLINE B with action=skipped-changed. Returns (shim, graveyard)."""
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim = tmp_path / "trash-dirtying.sh"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'victim="{victim_dir}"\n'
        f'dest="{graveyard}"\n'
        # Dirty the victim ONCE (idempotent: the file just needs to exist before the victim's
        # own re-verify reads `git status`).
        'printf x > "$victim/TOCTOU-dirty" 2>/dev/null || true\n'
        'for p in "$@"; do\n'
        '  base="$(basename "$p")"; parent="$(basename "$(dirname "$p")")"\n'
        '  mv "$p" "$dest/$parent-$base" 2>/dev/null || exit 1\n'
        'done\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)
    return shim, graveyard


def test_apply_reverify_declines_sibling_dirtied_in_toctou_window(tmp_path):
    """The load-bearing finding-2 guard, REALLY exercised: two eligible drive-owned children
    `1.1` (glob-first) and `9.1`. The trash shim, when it removes `1.1`, FIRST dirties `9.1` —
    a genuine TOCTOU window where `9.1` goes dirty between classification and the moment apply
    reaches it. Because re-verify runs BEFORE `9.1`'s destructive verb, `9.1` is DECLINED:
    eligible:true (verdict unchanged), action=skipped-changed, dir intact, no trash. `1.1` is
    still removed. This drives a child to action==skipped-changed (the branch no prior test
    reached). REDS pre-fix only if re-verify is removed; with re-verify present it greens."""
    repo = _make_owning_repo(tmp_path, "toctou", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "toctou")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "1.1")    # glob-first eligible child
    _clean_pushed_checkout(d / "wt" / "9.1")    # second eligible child (the victim)
    _backdate(d)
    shim, graveyard = _dirtying_shim(tmp_path, d / "wt" / "9.1")
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    o = _by_id(objs)["toctou"]
    # 1.1 removed normally.
    c1 = _child(o, "1.1")
    assert c1["eligible"] is True and c1["action"] == "removed"
    assert not (d / "wt" / "1.1").exists()
    # 9.1 went dirty in the window ⇒ re-verify declines ⇒ skipped-changed, dir intact, no trash.
    c9 = _child(o, "9.1")
    assert c9["eligible"] is True, "verdict must stay eligible (apply never re-classifies)"
    assert c9["action"] == "skipped-changed", "9.1 dirtied in the window must be skipped-changed"
    assert (d / "wt" / "9.1").exists(), "no destructive verb may run on the declined child"
    # only 1.1 reached the graveyard.
    moved = sorted(p.name for p in graveyard.iterdir())
    assert moved == ["wt-1.1"], f"only 1.1 should be trashed, got {moved}"


def test_apply_reverify_declines_run_gone_live_via_waiting(tmp_path):
    """finding-1 guard: a run classified eligible but RESUMED in the TOCTOU window — its worktree
    stays clean + not-registered, but a sibling earlier in the apply loop sets the run's
    `.waiting` (the run went LIVE). The apply-time re-verify must re-assert the FULL liveness gate
    (is_waiting_quiet), so the live run's worktree is NOT trashed ⇒ action=skipped-changed.

    Drive the window with a trash-shim that, when it removes glob-first child `1.1`, rewrites the
    run's state.json to set `waiting` (the run resumed) BEFORE child `9.1` is processed. `9.1`'s
    re-verify (fix 1) sees waiting != null ⇒ skipped-changed, dir intact. REDS pre-fix (the old
    re-verify only checked registration+cleanliness, both still holding ⇒ it would TRASH the live
    run's worktree)."""
    repo = _make_owning_repo(tmp_path, "wentlive", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "wentlive")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "1.1")    # glob-first eligible child
    _clean_pushed_checkout(d / "wt" / "9.1")    # second eligible child
    _backdate(d)
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim = tmp_path / "trash-wentlive.sh"
    sj = d / "state.json"
    # A REAL JSON OBJECT (single-encoded) written to state.json — NOT a double-encoded JSON
    # string literal (which would make jq error on `.waiting`, exercising "broken state =>
    # skipped-changed" instead of the waiting recheck). Persist it to a file the shim copies
    # so the shell never re-quotes / re-encodes the JSON.
    live_state_file = tmp_path / "wentlive-state.json"
    live_state_file.write_text(
        json.dumps({"stage": "done", "waiting": "Gate B", "baseRef": "main",
                    "repoRoot": str(repo)}),
        encoding="utf-8",
    )
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'sj="{sj}"\n'
        f'dest="{graveyard}"\n'
        f'live="{live_state_file}"\n'
        # The run RESUMES (goes live) the moment 1.1 is being torn down: set `.waiting` by
        # overwriting state.json with the real live JSON object.
        'cp "$live" "$sj" 2>/dev/null || true\n'
        'for p in "$@"; do\n'
        '  base="$(basename "$p")"; parent="$(basename "$(dirname "$p")")"\n'
        '  mv "$p" "$dest/$parent-$base" 2>/dev/null || exit 1\n'
        'done\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    o = _by_id(objs)["wentlive"]
    c1 = _child(o, "1.1")
    assert c1["eligible"] is True and c1["action"] == "removed"
    c9 = _child(o, "9.1")
    assert c9["eligible"] is True, "verdict must stay eligible"
    assert c9["action"] == "skipped-changed", (
        "a run that went LIVE (waiting set) in the window must NOT be trashed"
    )
    assert (d / "wt" / "9.1").exists(), "no destructive verb on the now-live run's worktree"
    moved = sorted(p.name for p in graveyard.iterdir())
    assert moved == ["wt-1.1"], f"only 1.1 should be trashed, got {moved}"


def test_apply_late_recheck_declines_run_gone_live_after_step1(tmp_path):
    """finding-2 (round-2) guard: the IMMEDIATELY-before-trash re-check, distinct from Step-1.

    The Step-1 full re-verify MINIMIZES but cannot CLOSE the check-then-act window: a run can go
    live AFTER its Step-1 predicates are read but BEFORE its destructive verb. This drives exactly
    that: a single eligible drive-owned child whose owning repo's `git worktree remove` (which runs
    BETWEEN Step-1 and the trash) writes an `inflight-*.marker` — the run resumes in that sub-step
    window. Step-1 saw a quiet, marker-free run (passes); the late re-check (is_waiting_quiet +
    has_open_inflight, re-run right before $TRASH_CMD) sees the open marker ⇒ skipped-changed, NO
    trash, dir intact. REDS pre-fix: with the late re-check removed the worktree is trashed even
    though the run went live.

    Injection is faithful: a `git` wrapper on PATH writes the marker on `worktree remove` then
    delegates to the real git, so the marker genuinely appears in the Step1→trash window (not
    pre-seeded). A single child guarantees Step-1 ran marker-free for THIS child."""
    repo = _make_owning_repo(tmp_path, "latelive", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "latelive")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "1.1")    # the single eligible child
    _backdate(d)
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim, _ = _graveyard_shim(tmp_path)
    # A `git` wrapper that, on `worktree remove`, writes an inflight marker into the run dir (the
    # run goes LIVE in the Step1→trash window) BEFORE delegating to the real git. Real git is
    # resolved via `command -v` with the wrapper dir stripped from PATH so we don't self-recurse.
    real_git = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
    gitwrap_dir = tmp_path / "gitwrap"
    gitwrap_dir.mkdir(parents=True, exist_ok=True)
    gitwrap = gitwrap_dir / "git"
    gitwrap.write_text(
        "#!/usr/bin/env bash\n"
        f'rundir="{d}"\n'
        f'realgit="{real_git}"\n'
        # Detect a `worktree remove` invocation in the args; on it, the run resumes → write marker.
        'for a in "$@"; do\n'
        '  if [ "$a" = "remove" ]; then\n'
        '    printf x > "$rundir/inflight-implement-1.1.marker" 2>/dev/null || true\n'
        '    break\n'
        '  fi\n'
        'done\n'
        'exec "$realgit" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(gitwrap, 0o755)
    env = {"RETENTION_TRASH_CMD": str(shim),
           "PATH": f"{gitwrap_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14",
         "--json", "--apply"],
        home=root, env=env,
    )
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["latelive"]
    c = _child(o, "1.1")
    assert c["eligible"] is True, "verdict must stay eligible (apply never re-classifies)"
    assert c["action"] == "skipped-changed", (
        "a run that went live (inflight marker) AFTER Step-1 but before trash must be "
        "caught by the late re-check ⇒ skipped-changed"
    )
    assert (d / "wt" / "1.1").exists(), "no destructive verb may run once the run went live"
    assert sorted(p.name for p in graveyard.iterdir()) == [], "nothing should be trashed"


def test_apply_tierW_dirty_child_is_skip_none_no_trash(tmp_path):
    """A child dirty AT classification ⇒ classifies skip:dirty ⇒ apply action `none`, NO trash,
    dir intact. (Pins "no destructive verb on a non-eligible child" — distinct from the TOCTOU
    skipped-changed branch above.)"""
    repo = _make_owning_repo(tmp_path, "rv", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "rv")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "phase1")
    (d / "wt" / "phase1" / "dirty").write_text("x", encoding="utf-8")  # dirty ⇒ skip
    _backdate(d)
    shim, graveyard = _graveyard_shim(tmp_path)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    c = _child(_by_id(objs)["rv"], "phase1")
    assert c["eligible"] is False and c["reason"] == "dirty"
    assert c["action"] == "none"
    assert (d / "wt" / "phase1").exists()                 # NO destructive verb ran
    assert list(graveyard.iterdir()) == []


# --------------------------------------------------------------------------- #
# AC4: report == apply parity — verdict identity + additive action layer.
# --------------------------------------------------------------------------- #
def _parity_fixture(tmp_path, root, run_id):
    """Build a mixed backlog under `root` for run `run_id`: an eligible TierL heavy log, an
    eligible TierW child, and a skip:dirty child. Returns the run dir."""
    repo = _make_owning_repo(tmp_path, run_id, ancestor=True)
    d = _run_dir(root, run_id)
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _clean_pushed_checkout(d / "wt" / "design1")
    (d / "wt" / "design1" / "dirty").write_text("x", encoding="utf-8")
    _backdate(d)
    return d


def test_report_equals_apply_verdict_partition_identity(tmp_path):
    """The eligible/reason partition is IDENTICAL between report-only and --apply over an
    equivalent backlog/clock; --apply only ADDS the `action` field (and changes report verbs).
    An eligible:true child stays eligible:true regardless of action outcome. Two independent
    roots/run-ids (since apply mutates) carry the SAME fixture shape."""
    root_ro = tmp_path / "runs-ro"
    root_ap = tmp_path / "runs-ap"
    _parity_fixture(tmp_path, root_ro, "parity-ro")     # report-only fixture
    _parity_fixture(tmp_path, root_ap, "parity-ap")     # apply fixture (same shape, fresh repo)

    _, ro = _scan(root_ro)
    ro_o = _by_id(ro)["parity-ro"]
    shim, _ = _graveyard_shim(tmp_path)
    _, ap = _scan(root_ap, apply=True, trash_cmd=str(shim))
    ap_o = _by_id(ap)["parity-ap"]

    # verdict partition identical: same tierL eligibility/reason; same children eligible/reason.
    assert ro_o["tierL"]["eligible"] == ap_o["tierL"]["eligible"]
    assert ro_o["tierL"]["reason"] == ap_o["tierL"]["reason"]
    ro_children = {c["name"]: (c["eligible"], c["reason"]) for c in ro_o["tierW"]["children"]}
    ap_children = {c["name"]: (c["eligible"], c["reason"]) for c in ap_o["tierW"]["children"]}
    assert ro_children == ap_children, "apply must NOT mutate the eligible/reason partition"
    # FULL measured-field identity (finding 2): the Tier-L log SET + total bytes must be byte-for-
    # byte identical between report and apply — apply reports the set it SWEPT from a PRE-deletion
    # snapshot, NOT an empty post-trash re-enumeration. (Would RED before the snapshot fix:
    # ap_o["tierL"]["logs"] == [] and ["bytes"] == 0 after the codex-raw-x.log was trashed.)
    ro_logs = sorted((l["name"], l["bytes"]) for l in ro_o["tierL"]["logs"])
    ap_logs = sorted((l["name"], l["bytes"]) for l in ap_o["tierL"]["logs"])
    assert ro_logs == ap_logs, "apply must report the SWEPT log set, not an empty post-trash set"
    assert ro_o["tierL"]["bytes"] == ap_o["tierL"]["bytes"] > 0, (
        "apply must report the SWEPT bytes from the pre-deletion snapshot, not 0"
    )
    # the additive delta: report-only actions are all `none`; apply records real outcomes.
    assert ro_o["tierL"]["action"] == "none"
    assert ap_o["tierL"]["action"] == "swept"
    assert _child(ap_o, "phase1")["action"] == "removed"
    # an eligible child stays eligible:true even though it was removed.
    assert _child(ap_o, "phase1")["eligible"] is True


# --------------------------------------------------------------------------- #
# AC5: apply fail-safe on trash failure + closed action-outcome enum.
# --------------------------------------------------------------------------- #
ACTION_ENUM = {"removed", "swept", "skipped-changed", "trash-failed", "none"}


def test_apply_trash_failure_is_failsafe_trash_failed(tmp_path):
    """A trash command that exits non-zero ⇒ the scan STILL exits 0, the file/dir REMAINS, the
    verdict stays eligible:true (NOT re-classified), and the action is trash-failed (no rm
    fallback)."""
    repo = _make_owning_repo(tmp_path, "tf", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "tf")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    fail = _failing_shim(tmp_path)
    cp, objs = _scan(root, apply=True, trash_cmd=str(fail))
    assert cp.returncode == 0
    o = _by_id(objs)["tf"]
    # nothing deleted (trash failed, no rm fallback).
    assert (d / "codex-raw-x.log").exists()
    # Tier-W: the worktree was git-unregistered but trash failed ⇒ trash-failed, verdict stays.
    c = _child(o, "phase1")
    assert c["eligible"] is True and c["action"] == "trash-failed"
    assert (d / "wt" / "phase1").exists()
    assert o["tierL"]["action"] == "trash-failed"
    assert o["tierL"]["eligible"] is True


def test_apply_action_values_in_closed_enum(tmp_path):
    """Every emitted `action` value (report-only AND apply, eligible AND skipped) is in the
    closed action-outcome enum {removed, swept, skipped-changed, trash-failed, none}."""
    repo = _make_owning_repo(tmp_path, "enum", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "enum")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")     # eligible ⇒ removed
    (d / "wt" / "converter").mkdir(parents=True)    # skip:not-drive-owned ⇒ none
    _backdate(d)
    shim, _ = _graveyard_shim(tmp_path)
    _, objs = _scan(root, apply=True, trash_cmd=str(shim))
    seen = set()
    for o in objs:
        seen.add(o["tierL"]["action"])
        for c in o["tierW"]["children"]:
            seen.add(c["action"])
    assert seen <= ACTION_ENUM, f"action(s) outside closed enum: {seen - ACTION_ENUM}"
    assert {"removed", "swept", "none"} <= seen   # representative outcomes exercised


# --------------------------------------------------------------------------- #
# AC6: apply never aborts the scan (per-run isolation) — a run that errors mid-apply does
# not stop the others; exit 0.
# --------------------------------------------------------------------------- #
def test_apply_never_aborts_scan_on_bad_run(tmp_path):
    """AC6 cross-run isolation: a REAL apply FAILURE on one run (a `trash` that exits non-zero,
    via _failing_shim) must NOT abort the scan — the OTHER runs are still processed and exit is 0.
    Two eligible runs share one failing trash command: the failure on the first leaves its data
    on disk (action=trash-failed) but the scan continues and the second run is still classified +
    applied. (Mutation-verify: if a per-run apply failure aborted the scan, the second run would
    be missing from the output / its action unprocessed.)

    Both runs hit the SAME failing trash, so BOTH log a trash-failed outcome — the point is that
    BOTH are PROCESSED (present in the output, classified, action recorded), not that one succeeds.
    A torn-state run is also mixed in to confirm a classification error likewise never aborts."""
    repo_a = _make_owning_repo(tmp_path, "runA", ancestor=True)
    repo_b = _make_owning_repo(tmp_path, "runB", ancestor=True)
    root = tmp_path / "runs"
    # runA: eligible heavy log + eligible worktree; its apply will hit the failing trash.
    a = _run_dir(root, "runA")
    _state(a, stage="done", waiting=None, baseRef="main", repoRoot=str(repo_a))
    (a / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(a / "wt" / "phase1")
    _backdate(a)
    # runB: a SECOND eligible run that must STILL be processed after runA's apply failure.
    b = _run_dir(root, "runB")
    _state(b, stage="done", waiting=None, baseRef="main", repoRoot=str(repo_b))
    (b / "codex-raw-y.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(b / "wt" / "phase1")
    _backdate(b)
    # a torn-state run (classification errors → skip), still must not abort
    torn = _run_dir(root, "torn")
    (torn / "state.json").write_text('{"stage": "done", "wait', encoding="utf-8")
    (torn / "codex-raw-z.log").write_text("z" * 100, encoding="utf-8")
    _backdate(torn)
    fail = _failing_shim(tmp_path)
    cp, objs = _scan(root, apply=True, trash_cmd=str(fail))
    assert cp.returncode == 0
    ids = _by_id(objs)
    # Every run was PROCESSED despite runA's apply failure (the isolation guarantee).
    assert {"runA", "runB", "torn"} <= set(ids), f"a failing apply aborted the scan: {set(ids)}"
    # runA's apply really failed (data left on disk), but did not abort the scan.
    assert ids["runA"]["tierL"]["action"] == "trash-failed"
    assert (a / "codex-raw-x.log").exists()
    # runB was STILL classified AND applied after runA's failure — the load-bearing assertion.
    assert ids["runB"]["tierL"]["eligible"] is True
    assert ids["runB"]["tierL"]["action"] == "trash-failed"
    assert _child(ids["runB"], "phase1")["eligible"] is True
    assert _child(ids["runB"], "phase1")["action"] == "trash-failed"
    # torn run classified (skip), untouched.
    assert ids["torn"]["tierL"]["eligible"] is False
    assert (torn / "codex-raw-z.log").exists()


def test_apply_human_report_verbs(tmp_path):
    """Under --apply the human report swaps verbs: WOULD-SWEEP → SWEPT, WOULD-REMOVE →
    REMOVED."""
    repo = _make_owning_repo(tmp_path, "verbs", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "verbs")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    shim, _ = _graveyard_shim(tmp_path)
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(shim)},
    )
    assert cp.returncode == 0
    out = cp.stdout
    assert "SWEPT" in out and "WOULD-SWEEP" not in out
    assert "REMOVED" in out and "WOULD-REMOVE" not in out


def test_apply_human_report_failed_trash_render_and_aggregate(tmp_path):
    """The human-output `FAILED (trash)` render branch (Tier-L AND Tier-W) plus the action-aware
    aggregate: a trash that always fails leaves both the heavy log and the worktree on disk, so
    the per-tier lines render `FAILED (trash)` (NOT SWEPT/REMOVED) and the summary counts 0
    reclaimed / 0 removed (the trash-failed items fall to skipped)."""
    repo = _make_owning_repo(tmp_path, "ftr", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "ftr")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-x.log").write_text("z" * 100, encoding="utf-8")
    _clean_pushed_checkout(d / "wt" / "phase1")
    _backdate(d)
    fail = _failing_shim(tmp_path)
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(fail)},
    )
    assert cp.returncode == 0
    lines = cp.stdout.splitlines()
    tierL_line = next(l for l in lines if "Tier-L (heavy logs):" in l)
    tierW_line = next(l for l in lines if "wt/phase1:" in l)
    assert "FAILED (trash)" in tierL_line, tierL_line
    assert "SWEPT" not in tierL_line
    assert "FAILED (trash)" in tierW_line, tierW_line
    assert "REMOVED" not in tierW_line
    # action-aware aggregate: nothing actually reclaimed/removed; both counted as skipped.
    summary = lines[-1]
    assert re.search(r"Tier-L reclaimed ~0 MB across 0 runs", summary), summary
    assert re.search(r"Tier-W removed 0 worktrees across 0 runs", summary), summary
    mS = re.search(r"·\s*(\d+)\s+runs/items skipped", summary)
    assert mS is not None and int(mS.group(1)) >= 2, summary


def test_apply_human_report_skipped_changed_render_branch(tmp_path):
    """The human-output `SKIPPED (changed)` render branch (Tier-W): a sibling child dirtied in the
    apply-time TOCTOU window is declined (action=skipped-changed) and its per-child line renders
    `SKIPPED (changed)` (NOT REMOVED). Pins the verb-render branch distinct from the JSON action
    field. The action-aware aggregate counts only the truly-removed child as removed."""
    repo = _make_owning_repo(tmp_path, "scr", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "scr")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    _clean_pushed_checkout(d / "wt" / "1.1")    # glob-first eligible child (removed)
    _clean_pushed_checkout(d / "wt" / "9.1")    # second eligible child (dirtied in window)
    _backdate(d)
    shim, _ = _dirtying_shim(tmp_path, d / "wt" / "9.1")
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(shim)},
    )
    assert cp.returncode == 0
    lines = cp.stdout.splitlines()
    l11 = next(l for l in lines if "wt/1.1:" in l)
    l91 = next(l for l in lines if "wt/9.1:" in l)
    assert "REMOVED" in l11, l11
    assert "SKIPPED (changed)" in l91, l91
    assert "REMOVED" not in l91
    # aggregate: exactly one worktree removed (1.1); the declined 9.1 falls to skipped.
    summary = lines[-1]
    assert re.search(r"Tier-W removed 1 worktrees across 1 runs", summary), summary


def _marker_on_first_trash_shim(tmp_path, run_dir):
    """A `trash`-shim that MOVES its argument into the graveyard AND, on its FIRST invocation,
    writes an `inflight-*.marker` into `run_dir` so the run goes LIVE mid-loop. Returns
    (shim, graveyard). Simulates a run resuming AFTER apply_tier_L's late pre-loop re-check has
    passed and AFTER the first heavy log was trashed — the per-iteration re-check must then STOP
    the loop (no further trash)."""
    graveyard = tmp_path / "graveyard"
    graveyard.mkdir(parents=True, exist_ok=True)
    shim = tmp_path / "trash-marker-shim.sh"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'dest="{graveyard}"\n'
        f'rundir="{run_dir}"\n'
        f'flag="{tmp_path}/.first-trash-done"\n'
        'for p in "$@"; do\n'
        '  base="$(basename "$p")"; parent="$(basename "$(dirname "$p")")"\n'
        '  mv "$p" "$dest/$parent-$base" 2>/dev/null || exit 1\n'
        '  if [ ! -e "$flag" ]; then\n'
        '    : > "$flag"\n'
        # The run resumes the instant the first log is gone: write its inflight marker.
        '    printf x > "$rundir/inflight-implement-x.marker" 2>/dev/null || true\n'
        '  fi\n'
        'done\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)
    return shim, graveyard


def test_apply_tierL_mid_loop_resume_stops_further_trashing(tmp_path):
    """fix-2(P1): apply_tier_L re-checks the cheap liveness signals at the TOP OF EACH iteration,
    mirroring apply_tier_W_child's late pre-trash re-check. A run that goes LIVE mid-loop (between
    trashing one heavy log and the next) must STOP trashing further logs ⇒ action=skipped-changed,
    the not-yet-trashed logs intact.

    Injection: a graveyard shim that, on its FIRST trash (codex-raw-a.log, glob-first), writes an
    inflight-*.marker into the run dir. The per-iteration re-check at the next iteration then sees
    the marker and declines ⇒ codex-raw-b.log survives. REDS pre-fix (the old loop trashed the
    whole snapshot unconditionally, so codex-raw-b.log would also be swept)."""
    repo = _make_owning_repo(tmp_path, "midloop", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "midloop")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-a.log").write_text("z" * 100, encoding="utf-8")  # trashed first
    (d / "codex-raw-b.log").write_text("y" * 100, encoding="utf-8")  # must survive (loop stops)
    _backdate(d)
    shim, graveyard = _marker_on_first_trash_shim(tmp_path, d)
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14",
         "--json", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(shim)},
    )
    objs = [json.loads(l) for l in cp.stdout.splitlines() if l.strip()]
    o = _by_id(objs)["midloop"]
    # Classification stayed eligible (apply never re-classifies); the mid-loop re-check declined.
    assert o["tierL"]["eligible"] is True
    assert o["tierL"]["action"] == "skipped-changed", (
        "a run that goes LIVE mid-loop must STOP — action=skipped-changed"
    )
    # The first log WAS trashed (it preceded the resume); the second log was NOT (loop stopped).
    assert not (d / "codex-raw-a.log").exists(), "first log was trashed before the resume"
    assert (d / "codex-raw-b.log").exists(), (
        "the loop must STOP after the mid-loop resume — codex-raw-b.log must survive"
    )
    moved = {p.name for p in graveyard.iterdir()}
    assert any("codex-raw-a.log" in m for m in moved)
    assert not any("codex-raw-b.log" in m for m in moved), (
        f"codex-raw-b.log must not reach the graveyard: {moved}"
    )


def test_apply_human_report_tierL_skipped_changed_render_branch(tmp_path):
    """fix-2(P2): the human-output `SKIPPED (changed)` render branch for Tier-L (only the Tier-W
    one was pinned). A run that goes LIVE in the apply-time window is declined
    (action=skipped-changed) and its Tier-L line renders `SKIPPED (changed)` (NOT SWEPT). Pins the
    Tier-L verb-render branch distinct from the JSON action field."""
    repo = _make_owning_repo(tmp_path, "tlscr", ancestor=True)
    root = tmp_path / "runs"
    d = _run_dir(root, "tlscr")
    _state(d, stage="done", waiting=None, baseRef="main", repoRoot=str(repo))
    (d / "codex-raw-a.log").write_text("z" * 100, encoding="utf-8")
    (d / "codex-raw-b.log").write_text("y" * 100, encoding="utf-8")
    _backdate(d)
    shim, _ = _marker_on_first_trash_shim(tmp_path, d)
    cp = run_script(
        [str(SCRIPT), "--root", str(root), "--now", str(NOW), "--age-days", "14", "--apply"],
        home=root, env={"RETENTION_TRASH_CMD": str(shim)},
    )
    assert cp.returncode == 0
    lines = cp.stdout.splitlines()
    tierL_line = next(l for l in lines if "Tier-L (heavy logs):" in l)
    assert "SKIPPED (changed)" in tierL_line, tierL_line
    assert "SWEPT" not in tierL_line
