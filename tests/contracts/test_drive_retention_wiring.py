"""Phase-2 prose pins (AC7-AC10, AC13) for the drive*.md retention-hygiene wiring.

These string-pin the LOAD-BEARING ordered/gated tokens the retention design requires in the
command files, so a reworded prose line that drops a safety clause reds here (memory:
"drive.md has contract-pin tests" — section-bound the assertions, AC8/AC10 ordering is
enforced by position, not bare presence):

  AC7  — drive.md fresh-run state.json carries a top-level `repoRoot` (separately pinned in
         test_state_json_shape.py for the JSON validity; here for the key presence).
  AC8  — drive-ship.md "After approval": cd-out → remove → removal-VERIFY-gate → completedAt
         → stage=done LAST, INCLUDING the cd-target `-d` validity check + checked cd +
         fail-closed branch (clause f).
  AC9  — drive.md GC-at-setup: report-only (no --apply), `|| true` swallowed, after the
         state.json write, NOT on the mkdir claim line.
  AC10 — drive.md resume "Worktrees" done-path mirrors AC8's ordered + gated tokens (incl.
         clause f).
  AC13 — drive-review.md exports TMPDIR=$RUN_DIR/tmp around codex exec with a preceding mkdir.
"""
import re

from _helpers import REPO_ROOT

CMDS = REPO_ROOT / ".claude" / "commands"
DRIVE_MD = CMDS / "drive.md"
SHIP_MD = CMDS / "drive-ship.md"
REVIEW_MD = CMDS / "drive-review.md"


def _section(text, start_marker, *, end_markers):
    """Return the substring of `text` from the line containing start_marker up to (excluding)
    the first subsequent line that starts a section in end_markers. Fails if start absent."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if start_marker in ln), None)
    assert start is not None, f"section start {start_marker!r} not found"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if any(lines[i].lstrip().startswith(m) for m in end_markers):
            end = i
            break
    return "\n".join(lines[start:end])


def _ordered(span, *tokens):
    """Assert each token appears in `span` AFTER the previous one (in order)."""
    pos = -1
    for tok in tokens:
        nxt = span.find(tok, pos + 1)
        assert nxt != -1, f"missing ordered token {tok!r}"
        assert nxt > pos, f"token {tok!r} out of order (expected after position {pos})"
        pos = nxt


# --------------------------------------------------------------------------- #
# AC7 — drive.md fresh-run state.json carries repoRoot (key presence in the prose/JSON).
# --------------------------------------------------------------------------- #
def test_drive_md_state_json_has_reporoot():
    text = DRIVE_MD.read_text(encoding="utf-8")
    assert '"repoRoot"' in text, "drive.md fresh-run state.json must carry a repoRoot key"
    # write-once-at-setup, never re-derived on resume.
    assert re.search(r"write-once.*resume|resume.*reuses the persisted", text), (
        "drive.md must state repoRoot is write-once at setup, not re-derived on resume"
    )


# --------------------------------------------------------------------------- #
# AC9 — GC-at-setup: report-only, swallowed, backgrounded, after the state.json write.
# --------------------------------------------------------------------------- #
def test_drive_md_gc_at_setup_report_only_after_state_write():
    text = DRIVE_MD.read_text(encoding="utf-8")
    span = _section(text, "GC-at-setup", end_markers=["## ", "**Autonomous"])
    assert "bin/drive-retention.sh" in span, "GC-at-setup must invoke bin/drive-retention.sh"
    assert "|| true" in span, "GC-at-setup must be swallowed (|| true)"
    assert "&" in span, "GC-at-setup must be backgrounded"
    # AFTER the first state.json write, NOT on the mkdir claim path.
    assert re.search(r"AFTER the first .{0,4}state\.json.{0,8}write", span, re.DOTALL), (
        "GC-at-setup must be sequenced AFTER the first state.json write"
    )
    assert re.search(r"mkdir|critical path", span), (
        "GC-at-setup must note it is NOT on the mkdir claim critical path"
    )
    assert "REPORT-ONLY" in span.upper()


def test_gc_at_setup_invocation_has_no_apply_flag():
    """The at-setup invocation line itself must be report-only — pin the exact swallowed
    backgrounded call shape and that it carries no --apply."""
    text = DRIVE_MD.read_text(encoding="utf-8")
    # the fenced call: ( bin/drive-retention.sh >>"..." 2>&1 || true ) &
    m = re.search(r"\(\s*bin/drive-retention\.sh[^\n)]*\)\s*&", text)
    assert m, "expected the backgrounded ( bin/drive-retention.sh ... ) & call"
    assert "--apply" not in m.group(0), "the at-setup GC call must NOT pass --apply"


# --------------------------------------------------------------------------- #
# AC8 — drive-ship.md "After approval" ordered + gated teardown (incl. clause f).
# --------------------------------------------------------------------------- #
def test_drive_ship_after_approval_ordered_gated_teardown():
    text = SHIP_MD.read_text(encoding="utf-8")
    span = _section(text, "## After approval", end_markers=["## "])
    # (a) cd OUT of wt/ship BEFORE the removal loop; (b) git worktree remove/prune of
    # drive-owned worktrees; (c) removal-success VERIFY gating the marker; (d) completedAt
    # after that verify; (e) stage="done" LAST.
    _ordered(
        span,
        "cd",                         # cd OUT first
        "wt/ship",
        "worktree remove",            # removal loop
        "[ ! -e",                     # removal-success VERIFY (proven gone on disk)
        "completedAt",                # marker AFTER the verify
        'stage="done"',               # done LAST
    )
    # (f) cd-target -d validity check (fallback on PRESENT-but-invalid, not only UNSET) +
    # checked cd + fail-closed branch refusing destructive verbs / completedAt.
    assert re.search(r"\[ -d .\$?repoRoot|\[ -d \"\$repoRoot\"", span), (
        "AC8(f): cd-target must use a `-d` validity check on repoRoot (not only UNSET)"
    )
    assert re.search(r'cd\s+"\$target"\s+\|\|', span), "AC8(f): the cd must be checked (cd || ...)"
    assert "Fail-closed" in span or "fail-closed" in span, "AC8(f): a fail-closed branch"
    # the fail-closed branch refuses completedAt + destructive verbs.
    assert re.search(r"DO NOT write .?completedAt", span), (
        "AC8(f): fail-closed must NOT write completedAt"
    )
    # (f, finding-3): a stale-but-present repoRoot must fail-closed for the WHOLE teardown — NOT
    # merely cd to a fallback and still run `git -C "<repoRoot>"` + `trash`. Pin the explicit
    # "invalid/empty repoRoot ⇒ whole teardown fail-closed (no trash)" requirement.
    assert re.search(r"fail-closed for\s+the WHOLE\s+teardown", span, re.DOTALL), (
        "AC8(f): an invalid/empty repoRoot must fail-closed the WHOLE teardown (finding 3)"
    )
    assert re.search(r"empty OR NOT", span), (
        "AC8(f): the fail-closed condition must trigger on empty OR -d-invalid repoRoot"
    )
    assert re.search(r"NO `?trash`?", span), (
        "AC8(f): the invalid-repoRoot fail-closed must run NO trash"
    )
    # the marker is GATED on proven removal, not merely sequenced.
    assert re.search(r"ONLY IF every required.*removal.*PROVEN", span, re.DOTALL), (
        "AC8(d): completedAt must be GATED on proven removal"
    )


# --------------------------------------------------------------------------- #
# AC10 — drive.md resume "Worktrees" done-path mirrors AC8 (incl. clause f).
# --------------------------------------------------------------------------- #
def test_drive_md_resume_worktrees_done_path_ordered_gated():
    text = DRIVE_MD.read_text(encoding="utf-8")
    # `_section` lstrips each line before matching, so the end-markers must ALSO be
    # leading-space-free or they never fire and the span runs to EOF (the AC10 section-bounding
    # would be dead — finding 5). These markers match the lstripped bullet lines that follow the
    # Done-via-resume teardown block (`  - **Each slice`, `  - **Phase `, `- **Fresh run`).
    span = _section(text, "Done-via-resume teardown",
                    end_markers=["- **Each slice", "- **Phase ", "- **Fresh run"])
    _ordered(
        span,
        "cd",
        "worktree remove",
        "[ ! -e",                     # removal-success VERIFY
        "completedAt",
        'stage="done"',
    )
    # clause f mirrored on the resume path.
    assert re.search(r"\[ -d .\$?repoRoot|\[ -d \"\$repoRoot\"", span), (
        "AC10(f): resume cd-target must use a `-d` validity check on repoRoot"
    )
    assert re.search(r'cd\s+"\$target"\s+\|\|', span), "AC10(f): resume cd must be checked"
    assert "Fail-closed" in span or "fail-closed" in span, "AC10(f): resume fail-closed branch"
    assert re.search(r"DO NOT write .?completedAt", span), (
        "AC10(f): resume fail-closed must NOT write completedAt"
    )
    # (f, finding-3): mirror AC8 — a stale-but-present repoRoot fail-closes the WHOLE resume
    # teardown (no `git -C "<repoRoot>"` + `trash` after a silently-failed unregister).
    assert re.search(r"fail-closed for\s+the WHOLE\s+teardown", span, re.DOTALL), (
        "AC10(f): an invalid/empty repoRoot must fail-closed the WHOLE resume teardown (finding 3)"
    )
    assert re.search(r"empty OR NOT", span), (
        "AC10(f): the fail-closed condition must trigger on empty OR -d-invalid repoRoot"
    )
    assert re.search(r"NO `?trash`?", span), (
        "AC10(f): the resume invalid-repoRoot fail-closed must run NO trash"
    )
    assert re.search(r"ONLY IF every required.*removal.*PROVEN", span, re.DOTALL), (
        "AC10: resume completedAt must be GATED on proven removal"
    )


# --------------------------------------------------------------------------- #
# AC13 — drive-review.md TMPDIR export around codex exec, with a preceding mkdir.
# --------------------------------------------------------------------------- #
def test_drive_review_exports_tmpdir_around_codex():
    text = REVIEW_MD.read_text(encoding="utf-8")
    span = _section(text, "## Step 2", end_markers=["## "])
    assert "mkdir -p" in span and "$RUN_DIR/tmp" in span, (
        "AC13: a one-time mkdir -p $RUN_DIR/tmp before the codex call"
    )
    exec_m = re.search(r'TMPDIR="?\$RUN_DIR/tmp"? codex exec', span)
    assert exec_m, "AC13: TMPDIR=$RUN_DIR/tmp must wrap the codex exec call"
    # The mkdir MUST precede the TMPDIR-wrapped codex exec — otherwise TMPDIR would
    # point at a not-yet-created dir, defeating the scratch-namespacing goal. A
    # presence-only check would still pass with the mkdir moved AFTER the exec.
    mkdir_m = re.search(r'mkdir -p "?\$RUN_DIR/tmp"?', span)
    assert mkdir_m, "AC13: a one-time mkdir -p $RUN_DIR/tmp before the codex call"
    assert mkdir_m.start() < exec_m.start(), (
        "AC13: mkdir -p $RUN_DIR/tmp must PRECEDE the TMPDIR=$RUN_DIR/tmp codex exec call"
    )
