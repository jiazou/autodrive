"""Slice 1.2 — vault_tasks.bucket classification + ordering (AC 5) + edge #1.

Asserts the REAL behavior of vault_tasks.bucket():
- classify open tasks into overdue / due_today / due_week(<=7d) / waiting / backlog
  relative to date.today(); backlog is the CATCH-ALL — every open non-waiting task
  not overdue/due_today/due_week lands there (due >7d, or no due date), so
  open_count == sum of all bucket lengths (vault_tasks.py:170)
- open_count (over open statuses) + needs_review_count (over ALL tasks)
- ordering by (priority, due or "9999") for overdue/due_today/due_week/backlog;
  the `waiting` bucket preserves discovery order and is NOT sorted (vault_tasks.py:177)

All date-relative inputs are computed off datetime.date.today() so they never go
stale. Tasks are built through the `vault` fixture and read back via load_tasks(),
so the classification runs over real parsed dicts (not hand-built ones).
"""
import datetime


def _iso(days_from_today):
    return (datetime.date.today() + datetime.timedelta(days=days_from_today)).isoformat()


def _by_slug(rows):
    return [t["slug"] for t in rows]


# --------------------------------------------------------------------------- #
# AC 5 — classification relative to today
# --------------------------------------------------------------------------- #
def test_bucket_classifies_by_due_date(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("overdue", due=_iso(-3))
    vault.add_task("today", due=_iso(0))
    vault.add_task("this-week", due=_iso(5))      # <= 7 days ahead
    vault.add_task("backlog", due=None, scheduled=None)
    b = vt.bucket(vt.load_tasks())
    assert _by_slug(b["overdue"]) == ["overdue"]
    assert _by_slug(b["due_today"]) == ["today"]
    assert _by_slug(b["due_week"]) == ["this-week"]
    assert _by_slug(b["backlog"]) == ["backlog"]


def test_bucket_due_week_boundary_inclusive_and_exclusive(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("edge-7", due=_iso(7))    # exactly 7 days -> due_week (inclusive)
    vault.add_task("edge-8", due=_iso(8))    # 8 days -> falls past due_week into the
                                             # backlog catch-all (every open task lands
                                             # in some bucket; vault_tasks.py:170)
    b = vt.bucket(vt.load_tasks())
    assert _by_slug(b["due_week"]) == ["edge-7"]
    assert "edge-8" not in _by_slug(b["due_week"])
    # A future-but->7d task falls through every elif into the backlog catch-all.
    assert "edge-8" in _by_slug(b["backlog"])


def test_bucket_waiting_status_goes_to_waiting_regardless_of_date(mc_env, vault):
    vt = mc_env.vault_tasks
    # An overdue-dated task whose status is `waiting` lands in waiting, not overdue.
    vault.add_task("waiting-overdue", status="waiting", due=_iso(-2))
    b = vt.bucket(vt.load_tasks())
    assert _by_slug(b["waiting"]) == ["waiting-overdue"]
    assert _by_slug(b["overdue"]) == []


def test_bucket_scheduled_no_due_goes_to_backlog(mc_env, vault):
    vt = mc_env.vault_tasks
    # No due date (scheduled is ignored by bucket()) -> lands in the backlog catch-all
    # so no open task silently vanishes (vault_tasks.py:170).
    vault.add_task("scheduled-only", due=None, scheduled=_iso(2))
    b = vt.bucket(vt.load_tasks())
    assert "scheduled-only" in _by_slug(b["backlog"])


def test_bucket_excludes_non_open_statuses(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("done-task", status="done", due=_iso(-1))   # not an open status
    vault.add_task("open-task", status="todo", due=_iso(-1))
    b = vt.bucket(vt.load_tasks())
    assert _by_slug(b["overdue"]) == ["open-task"]
    assert b["open_count"] == 1


# --------------------------------------------------------------------------- #
# AC 5 — open_count + needs_review_count
# --------------------------------------------------------------------------- #
def test_bucket_counts(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("a", status="todo", needs_review=True)
    vault.add_task("b", status="doing", needs_review=False)
    vault.add_task("c", status="waiting", needs_review=True)
    # `done` is not an open status, but needs_review counts over ALL tasks.
    vault.add_task("d", status="done", needs_review=True)
    b = vt.bucket(vt.load_tasks())
    assert b["open_count"] == 3                  # todo + doing + waiting
    assert b["needs_review_count"] == 3          # a + c + d (all tasks, any status)


# --------------------------------------------------------------------------- #
# AC 5 — ordering: sorted buckets vs unsorted waiting
# --------------------------------------------------------------------------- #
def test_bucket_overdue_sorted_by_priority_then_due(mc_env, vault):
    vt = mc_env.vault_tasks
    # Same priority, different due dates -> sorted by due ascending.
    vault.add_task("late", priority="p1", due=_iso(-10))
    vault.add_task("later-due-earlier", priority="p1", due=_iso(-2))
    # Lower-priority string sorts after p1 (p1 < p2 lexicographically).
    vault.add_task("p2-most-overdue", priority="p2", due=_iso(-30))
    b = vt.bucket(vt.load_tasks())
    # p1 group first (sorted by due asc: -10 before -2), then p2.
    assert _by_slug(b["overdue"]) == ["late", "later-due-earlier", "p2-most-overdue"]


def _open_task(slug, priority, due, status="todo"):
    """A hand-built open-task dict (bypasses the glob whose order is filesystem-
    dependent) so the INPUT order is deterministic and deliberately NOT already in
    (priority, due) order — proving bucket() does the sort, not the input."""
    return {
        "slug": slug, "title": slug, "project": "P", "area": "",
        "status": status, "priority": priority, "due": due, "scheduled": "",
        "needs_review": False, "tags": [], "depends_on": [], "dod": [],
    }


def test_bucket_due_today_sorted_by_priority(mc_env):
    vt = mc_env.vault_tasks
    today = _iso(0)
    # Three tasks all due today, fed in REVERSE priority order so an unsorted bucket
    # would echo the input. bucket() must reorder to p1, p2, p3.
    tasks = [
        _open_task("today-p3", "p3", today),
        _open_task("today-p1", "p1", today),
        _open_task("today-p2", "p2", today),
    ]
    b = vt.bucket(tasks)
    # (priority, due) key; same due -> priority decides: p1 < p2 < p3
    assert _by_slug(b["due_today"]) == ["today-p1", "today-p2", "today-p3"]


def test_bucket_due_week_sorted_by_priority_then_due(mc_env):
    vt = mc_env.vault_tasks
    # All within the week window (1..7 days), hand-built in an order that is NOT the
    # expected one. Two p1s with different due dates prove the same-priority tiebreak
    # is earlier-due-first; the p2 sorts AFTER both p1s even though its due is earliest
    # — so this bites against a due-only regression (would put p2 first) AND a
    # priority-only regression (would not order the two p1s by due).
    tasks = [
        _open_task("week-p1-late", "p1", _iso(6)),
        _open_task("week-p2-soonest", "p2", _iso(1)),
        _open_task("week-p1-soon", "p1", _iso(2)),
    ]
    b = vt.bucket(tasks)
    assert _by_slug(b["due_week"]) == ["week-p1-soon", "week-p1-late", "week-p2-soonest"]


def test_bucket_backlog_sorted_by_priority(mc_env, vault):
    vt = mc_env.vault_tasks
    # No due dates -> prio key (p, "9999"); sort is by priority string.
    vault.add_task("p3-item", priority="p3", due=None)
    vault.add_task("p1-item", priority="p1", due=None)
    vault.add_task("p2-item", priority="p2", due=None)
    b = vt.bucket(vt.load_tasks())
    assert _by_slug(b["backlog"]) == ["p1-item", "p2-item", "p3-item"]


def test_bucket_waiting_is_unsorted_preserves_input_order(mc_env):
    vt = mc_env.vault_tasks
    # Feed bucket() a hand-ordered list (bypassing glob, whose order is
    # filesystem-dependent) so the input order is DETERMINISTIC and deliberately
    # NOT in priority order. bucket() must leave `waiting` in this exact order —
    # it does not sort it (vault_tasks.py:177), unlike the other buckets.
    def _wt(slug, priority):
        return {
            "slug": slug, "title": slug, "project": "P", "area": "",
            "status": "waiting", "priority": priority, "due": "", "scheduled": "",
            "needs_review": False, "tags": [], "depends_on": [], "dod": [],
        }
    input_order = ["w-p1", "w-p3", "w-p2"]   # NOT sorted by priority
    tasks = [_wt("w-p1", "p1"), _wt("w-p3", "p3"), _wt("w-p2", "p2")]
    b = vt.bucket(tasks)
    assert _by_slug(b["waiting"]) == input_order   # untouched (no sort)
    # Prove the guard is non-vacuous: a priority sort WOULD reorder this input.
    sorted_order = [t["slug"] for t in sorted(tasks, key=lambda t: t["priority"])]
    assert sorted_order != input_order


# --------------------------------------------------------------------------- #
# Edge case #1 — empty input
# --------------------------------------------------------------------------- #
def test_bucket_empty_input_all_empty(mc_env):
    vt = mc_env.vault_tasks
    b = vt.bucket([])
    assert b["overdue"] == []
    assert b["due_today"] == []
    assert b["due_week"] == []
    assert b["waiting"] == []
    assert b["backlog"] == []
    assert b["open_count"] == 0
    assert b["needs_review_count"] == 0


def test_bucket_on_missing_vault_all_empty(mc_env):
    vt = mc_env.vault_tasks
    # load_tasks() returns [] on a missing vault dir; bucket of that is all-empty.
    b = vt.bucket(vt.load_tasks())
    assert b["open_count"] == 0
    assert b["needs_review_count"] == 0
