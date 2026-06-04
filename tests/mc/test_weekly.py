"""Slice 1.5 — weekly review agenda (AC 17).

Asserts mission-control/bin/weekly.py:gather groups open tasks by project and
surfaces needs_review/overdue, plus ONE subprocess check of `weekly --json` shape
(the only subprocess in this slice) via _helpers.run_script.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _helpers  # noqa: E402

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


# --------------------------------------------------------------------------- #
# AC 17 — weekly.gather (import path)
# --------------------------------------------------------------------------- #
def test_gather_groups_open_by_project(mc_env, vault):
    vault.add_task("a1", project="Alpha", status="todo")
    vault.add_task("a2", project="Alpha", status="doing")
    vault.add_task("b1", project="Beta", status="todo")
    # a closed task is NOT open -> excluded from by_project / open_count
    vault.add_task("a3", project="Alpha", status="done")

    d = mc_env.weekly.gather()

    assert d["open_count"] == 3
    assert {t["slug"] for t in d["by_project"]["Alpha"]} == {"a1", "a2"}
    assert {t["slug"] for t in d["by_project"]["Beta"]} == {"b1"}
    assert "a3" not in {t["slug"] for t in d["by_project"]["Alpha"]}


def test_gather_surfaces_needs_review_and_overdue(mc_env, vault):
    vault.add_task("nr", project="Alpha", status="todo", needs_review=True)
    vault.add_task("od", project="Beta", status="todo", due=YESTERDAY)
    vault.add_task("plain", project="Beta", status="todo")

    d = mc_env.weekly.gather()

    assert [t["slug"] for t in d["needs_review"]] == ["nr"]
    assert "od" in {t["slug"] for t in d["overdue"]}
    assert "plain" not in {t["slug"] for t in d["overdue"]}


def test_gather_empty_vault_is_all_empty(mc_env):
    """Missing vault dir -> load_tasks returns [] -> no crash, empty agenda."""
    d = mc_env.weekly.gather()
    assert d["open_count"] == 0
    assert d["needs_review"] == []
    assert d["overdue"] == []
    assert dict(d["by_project"]) == {}


def test_gather_no_project_bucketed_under_placeholder(mc_env, vault):
    """A task whose `project:` frontmatter is empty groups under '(no project)'
    (weekly.py:26). The directory component stays non-empty so the TASKS_GLOB still
    matches; only the parsed project FIELD is blank — set via extra_frontmatter that
    overrides the builder's `project:` line read order (last top-level wins is N/A;
    _parse_frontmatter keeps the first, so we suppress the builder's project key)."""
    # add_task always emits `project: <dir>`; to get an empty parsed project we write
    # the note directly with a non-empty dir but an empty project field.
    vault.add_raw(
        "01 Projects/Holder/Tasks/orphan.md",
        "---\ntype: task\nproject:\nstatus: todo\npriority: p2\nneeds_review: false\n---\n\n# orphan\n",
    )
    d = mc_env.weekly.gather()
    assert "(no project)" in d["by_project"]
    assert {t["slug"] for t in d["by_project"]["(no project)"]} == {"orphan"}


# --------------------------------------------------------------------------- #
# AC 17 — weekly --json shape (subprocess, the only one in this slice)
# --------------------------------------------------------------------------- #
def test_weekly_json_cli_shape(mc_env, vault, repo_root):
    vault.add_task("a1", project="Alpha", status="todo")
    vault.add_task("nr", project="Alpha", status="todo", needs_review=True)
    vault.add_task("od", project="Beta", status="todo", due=YESTERDAY)
    # an unscheduled open task with no due date -> lands in the CATCH-ALL backlog
    # bucket (vault_tasks.bucket). Lets us assert backlog CONTENTS, not just the key.
    vault.add_task("bk", project="Beta", status="todo")

    script = repo_root / "mission-control" / "bin" / "weekly.py"
    cp = _helpers.run_script(
        ["python3", str(script), "--json"],
        home=mc_env.home,
        env={"MC_VAULT": str(mc_env.vault), "MC_VAULT_NAME": "TestVault"},
    )

    assert cp.returncode == 0, cp.stderr
    data = json.loads(cp.stdout)  # valid JSON

    # shape: scalar count + slug lists + project->slug-list map (weekly.py:41-48)
    assert data["open_count"] == 4
    assert data["needs_review"] == ["nr"]
    assert "od" in data["overdue"]
    assert isinstance(data["by_project"], dict)
    assert set(data["by_project"]["Alpha"]) == {"a1", "nr"}
    assert set(data["by_project"]["Beta"]) == {"od", "bk"}
    # backlog CONTENTS pass through the --json projection. backlog is the CATCH-ALL
    # bucket: every open non-waiting task with no due in the next 7d -> bk, a1 and nr
    # (all undated) land here; the overdue `od` does NOT (it has a past due date).
    # A dropped or miswired backlog pass-through (weekly.py:46) FAILS here.
    assert set(data["backlog"]) == {"bk", "a1", "nr"}
    assert "od" not in data["backlog"]
    # every documented key present
    for key in ("open_count", "needs_review", "overdue", "waiting", "backlog", "by_project"):
        assert key in data
