"""Slice 1.4 — standup data layer (AC 12, 13, 14, 15).

Asserts the REAL behavior of standup.classify_ready / gather / focus_slugs /
_replace_or_append_section / draft against fixtures built via vault + claude_state.
Due dates are computed relative to date.today() so the bucket math is deterministic.
"""
from datetime import date, timedelta


def _iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------- #
# AC 12 — classify_ready: BLOCKED iff a depends_on slug is still open
# --------------------------------------------------------------------------- #
def test_classify_ready_blocks_on_open_dependency(mc_env, vault):
    # dep is open (todo) -> the dependent task is BLOCKED
    vault.add_task("dep", status="todo")
    vault.add_task("downstream", depends_on=["dep"])

    tasks = mc_env.vault_tasks.load_tasks()
    ready, blocked = mc_env.standup.classify_ready(tasks)

    ready_slugs = {t["slug"] for t in ready}
    blocked_slugs = {t["slug"] for t in blocked}
    assert "downstream" in blocked_slugs
    assert "downstream" not in ready_slugs
    # the open dep itself has no unmet deps -> it is READY
    assert "dep" in ready_slugs
    # blocked entry carries the unmet slug
    bd = next(t for t in blocked if t["slug"] == "downstream")
    assert bd["_unmet"] == ["dep"]


def test_classify_ready_unblocks_when_dependency_closed(mc_env, vault):
    # dep is done (not in OPEN_STATUSES) -> the dependent task is READY
    vault.add_task("dep", status="done")
    vault.add_task("downstream", depends_on=["dep"])

    tasks = mc_env.vault_tasks.load_tasks()
    ready, blocked = mc_env.standup.classify_ready(tasks)

    ready_slugs = {t["slug"] for t in ready}
    blocked_slugs = {t["slug"] for t in blocked}
    assert "downstream" in ready_slugs
    assert "downstream" not in blocked_slugs
    # a closed task is neither ready nor blocked (it is not open)
    assert "dep" not in ready_slugs and "dep" not in blocked_slugs


# --------------------------------------------------------------------------- #
# AC 13 — gather: LEFT JOIN sessions+bindings; spare_capacity = idle/shell,
#         unbound, NOT self
# --------------------------------------------------------------------------- #
def test_gather_left_join_and_buckets(mc_env, vault, claude_state):
    # one bound session, one unbound idle session
    vault.add_task("dep", status="todo")
    vault.add_task("downstream", depends_on=["dep"])
    vault.add_task("overdue-task", due=_iso(-1))

    # aaaaaaaa: busy + BOUND -> not spare (bound, and not idle/shell)
    claude_state.add_session("aaaaaaaa-1111-2222-3333-444444444444", status="busy")
    claude_state.add_binding("aaaaaaaa-1111-2222-3333-444444444444",
                             project="ProjX", task="some-task")
    # bbbbbbbb: idle + UNBOUND + not-self -> COUNTS toward spare_capacity
    claude_state.add_session("bbbbbbbb-1111-2222-3333-444444444444", status="idle")
    # eeeeeeee: shell + UNBOUND + not-self -> POSITIVE shell case; MUST count
    claude_state.add_session("eeeeeeee-1111-2222-3333-444444444444", status="shell")
    # ffffffff: busy + UNBOUND -> NEGATIVE case; status is not idle/shell so it MUST
    # NOT count even though it is unbound (guards against an "all unbound" regression)
    claude_state.add_session("ffffffff-1111-2222-3333-444444444444", status="busy")

    d = mc_env.standup.gather()

    # LEFT JOIN: bound session carries its project/task; unbound carries None
    by_id = {s["id"]: s for s in d["sessions"]}
    assert by_id["aaaaaaaa"]["project"] == "ProjX"
    assert by_id["aaaaaaaa"]["task"] == "some-task"
    assert by_id["bbbbbbbb"]["project"] is None
    assert by_id["bbbbbbbb"]["task"] is None
    assert by_id["eeeeeeee"]["status"] == "shell"
    assert by_id["ffffffff"]["status"] == "busy"

    # buckets/ready/blocked filled
    assert "overdue-task" in d["buckets"]["overdue"]
    assert "downstream" in [b["slug"] for b in d["blocked"]]
    assert "dep" in [r["slug"] for r in d["ready"]]

    # spare_capacity counts ONLY (idle OR shell) + unbound + not-self:
    #   bbbbbbbb (idle, unbound)  ✓
    #   eeeeeeee (shell, unbound) ✓   <- positive shell case
    #   aaaaaaaa (busy, BOUND)    ✗
    #   ffffffff (busy, unbound)  ✗   <- negative busy+unbound case
    assert d["spare_capacity"] == 2


def test_gather_spare_capacity_counts_shell_unbound(mc_env, claude_state):
    # ISOLATED positive for the shell branch of (status in idle/shell): a single
    # shell + unbound + not-self session, nothing else countable. Pins "shell counts"
    # independently of the combined test (== 1 is not gameable by a stray idle/busy).
    claude_state.add_session("eeeeeeee-1111-2222-3333-444444444444", status="shell")

    d = mc_env.standup.gather()

    assert d["spare_capacity"] == 1


def test_gather_spare_capacity_excludes_busy_even_unbound(mc_env, claude_state):
    # ISOLATED negative for the status predicate: a single busy + unbound session.
    # It is unbound and not-self, so ONLY the (idle/shell) status gate keeps it out.
    # Pins "busy doesn't count even when unbound" — bites an "all unbound count"
    # regression that the == 2 combined assertion alone could be gamed past.
    claude_state.add_session("ffffffff-1111-2222-3333-444444444444", status="busy")

    d = mc_env.standup.gather()

    assert d["spare_capacity"] == 0


def test_gather_spare_capacity_excludes_self(mc_env, vault, claude_state, monkeypatch):
    sid = "cccccccc-1111-2222-3333-444444444444"
    claude_state.add_session(sid, status="idle")
    # the self session is idle + unbound but must NOT count as spare capacity.
    # SELF_ID is frozen to "" at import; set it on the reloaded harvest module
    # directly (env alone won't take effect post-reload).
    monkeypatch.setattr(mc_env.harvest, "SELF_ID", sid)

    d = mc_env.standup.gather()

    by_id = {s["id"]: s for s in d["sessions"]}
    assert by_id[sid[:8]]["is_self"] is True
    assert d["spare_capacity"] == 0


def test_gather_bound_session_not_spare(mc_env, vault, claude_state):
    # idle but bound to a project -> not spare capacity
    sid = "dddddddd-1111-2222-3333-444444444444"
    claude_state.add_session(sid, status="idle")
    claude_state.add_binding(sid, project="ProjY")

    d = mc_env.standup.gather()
    assert d["spare_capacity"] == 0


# --------------------------------------------------------------------------- #
# AC 14 — focus_slugs: overdue + due_today capped at 10, due_today never truncated
# --------------------------------------------------------------------------- #
def test_focus_slugs_caps_overdue_keeps_all_due_today(mc_env, vault):
    # 8 overdue + 5 due-today = 13 candidates; cap=10 -> drop overdue to fit
    for i in range(8):
        vault.add_task(f"overdue-{i}", due=_iso(-(i + 1)))
    for i in range(5):
        vault.add_task(f"today-{i}", due=_iso(0))

    d = mc_env.standup.gather()
    picks = mc_env.standup.focus_slugs(d)

    assert len(picks) == 10
    # all 5 due-today survive (never truncated)
    due_today = set(d["buckets"]["due_today"])
    assert due_today.issubset(set(picks))
    # exactly cap - len(due_today) = 5 overdue kept
    overdue_in_picks = [s for s in picks if s.startswith("overdue-")]
    assert len(overdue_in_picks) == 5


def test_focus_slugs_pins_ordered_result(mc_env, vault):
    """AC 14 ORDER: focus_slugs returns `overdue[:cap-len(due_today)] + due_today`,
    in that exact sequence — overdue (priority-sorted) first, trimmed to fit, then
    ALL due-today appended. Pin the full ordered LIST so a reorder (due-today first,
    or trimming due-today instead of overdue) or a wrong-trim FAILS, not just a count.

    cap=5. 6 overdue with distinct priorities p0..p5 (so the bucket's (priority,due)
    sort gives a deterministic order) + 2 due-today p0/p1. keep = 5-2 = 3 overdue:
    the three lowest-priority strings p0,p1,p2. Result must be exactly
    [overdue-p0, overdue-p1, overdue-p2, today-p0, today-p1]."""
    # overdue, distinct priorities + distinct (older) due dates so the sort is total
    for i in range(6):
        vault.add_task(f"overdue-p{i}", priority=f"p{i}", due=_iso(-(i + 1)))
    # due-today, two of them with their own priorities
    vault.add_task("today-p0", priority="p0", due=_iso(0))
    vault.add_task("today-p1", priority="p1", due=_iso(0))

    d = mc_env.standup.gather()
    picks = mc_env.standup.focus_slugs(d, cap=5)

    # exact ordered list: 3 trimmed overdue (priority-sorted) THEN both due-today
    assert picks == ["overdue-p0", "overdue-p1", "overdue-p2", "today-p0", "today-p1"]


def test_focus_slugs_due_today_overflow_never_truncated(mc_env, vault):
    # 12 due-today alone (> cap) — due_today is never trimmed, so all 12 survive
    for i in range(12):
        vault.add_task(f"today-{i}", due=_iso(0))

    d = mc_env.standup.gather()
    picks = mc_env.standup.focus_slugs(d)

    assert len(picks) == 12
    assert set(d["buckets"]["due_today"]) == set(picks)


# --------------------------------------------------------------------------- #
# AC 15 — _replace_or_append_section + draft non-destructiveness
# --------------------------------------------------------------------------- #
def test_replace_or_append_replaces_in_place(mc_env):
    text = ("# Daily\n\n"
            "## Today's Focus\n"
            "old focus body\n\n"
            "## Notes\n"
            "keep me\n")
    out = mc_env.standup._replace_or_append_section(text, "Today's Focus", "NEW BODY\n")

    assert "NEW BODY" in out
    assert "old focus body" not in out
    # sibling section untouched
    assert "## Notes\nkeep me" in out
    # heading itself preserved (replaced body in place, not the header)
    assert out.count("## Today's Focus") == 1


def test_replace_or_append_appends_when_absent(mc_env):
    text = "# Daily\n\n## Notes\nkeep me\n"
    out = mc_env.standup._replace_or_append_section(text, "Parallel Plan", "PLAN BODY\n")

    assert "## Parallel Plan\nPLAN BODY" in out
    # pre-existing section preserved
    assert "## Notes\nkeep me" in out


def test_draft_populates_section_bodies(mc_env, vault, claude_state):
    """AC 15 BODIES: draft() must write NON-EMPTY, real content into both sections,
    not just the headings. Today's Focus carries the focused task (slug link via
    _focus_md), and Parallel Plan carries the capacity line + the Ready-to-start
    task. Asserting the BODY text (not just the `##` heading) bites a regression that
    emits empty/stale sections."""
    # one overdue task -> shows up in Today's Focus AND (no blocking dep) in Ready
    vault.add_task("focus-task", project="ProjZ", due=_iso(-1), title="Focus Task")
    # an idle spare session so the Parallel Plan capacity line is meaningful
    claude_state.add_session("bbbbbbbb-1111-2222-3333-444444444444", status="idle")

    d = mc_env.standup.gather()
    path = mc_env.standup.draft(d)
    out = path.read_text(encoding="utf-8") if hasattr(path, "read_text") \
        else open(path).read()

    # locate the body of each section (text after its heading, up to the next ## / EOF)
    focus_body = mc_env.standup.SECTION_RE("Today's Focus").search(out).group(2)
    plan_body = mc_env.standup.SECTION_RE("Parallel Plan").search(out).group(2)

    # Today's Focus body is non-empty and names the focused task (not the "no tasks" stub)
    assert focus_body.strip()
    assert "Focus Task" in focus_body
    assert "_No overdue or due-today tasks." not in focus_body
    # the obsidian link for the slug is in the focus body
    assert mc_env.vault_tasks.obsidian_href("focus-task") in focus_body

    # Parallel Plan body carries the capacity line and the Ready-to-start task
    assert plan_body.strip()
    assert "Capacity:" in plan_body
    assert "Ready to start now" in plan_body
    assert "Focus Task" in plan_body


def test_draft_creates_daily_note_from_template_when_absent(mc_env, vault, claude_state):
    """AC 15 template-creation: when no daily note exists yet, draft() ->
    harvest.ensure_daily_note() must CREATE it from the template
    (03 Resources/Templates/daily-note-template.md), substituting {{date}}, THEN
    write the two sections into it. Exercises the `if os.path.exists(DAILY_TEMPLATE)`
    branch in harvest.ensure_daily_note (vs the minimal-frontmatter fallback)."""
    vault.add_task("focus-task", due=_iso(-1), title="Focus Task")
    # a template with a marker line + {{date}} placeholder + a sibling section
    vault.add_daily_template(
        "---\ndate: {{date}}\ntype: daily-note\n---\n\n"
        "# {{date}} — Daily\n\n"
        "## Journal\nTEMPLATE-MARKER journal seed\n"
    )

    d = mc_env.standup.gather()
    date_str = d["generated_at"].split(" ")[0]
    daily = mc_env.daily_dir / f"{date_str}.md"
    assert not daily.exists()  # nothing pre-existing -> must be created from template

    path = mc_env.standup.draft(d)
    out = path.read_text(encoding="utf-8") if hasattr(path, "read_text") \
        else open(path).read()

    # the note was created from the TEMPLATE (marker present, {{date}} substituted)
    assert "TEMPLATE-MARKER journal seed" in out
    assert "{{date}}" not in out
    assert date_str in out
    # ...and the two drafted sections were written into the freshly created note
    assert "## Today's Focus" in out
    assert "## Parallel Plan" in out
    assert "Focus Task" in out
    # the template's own sibling section survives the in-place section write
    assert "## Journal" in out


def test_draft_is_non_destructive_to_siblings(mc_env, vault, claude_state):
    # seed the daily note with a sibling section the draft must preserve
    vault.add_task("overdue-task", due=_iso(-1))
    d = mc_env.standup.gather()
    date_str = d["generated_at"].split(" ")[0]

    daily = mc_env.daily_dir / f"{date_str}.md"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text("# Daily\n\n## Journal\nmy private journal entry\n",
                     encoding="utf-8")

    path = mc_env.standup.draft(d)
    out = path.read_text(encoding="utf-8") if hasattr(path, "read_text") \
        else open(path).read()

    # the two drafted sections were written
    assert "## Today's Focus" in out
    assert "## Parallel Plan" in out
    # the pre-existing sibling section survived untouched
    assert "## Journal\nmy private journal entry" in out
