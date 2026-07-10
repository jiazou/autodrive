"""AC11 — the /harvest ↔ /drive waiting bridge (`drive_waiting_runs` + the render section).

Read-only scan of `~/.claude/harness-runs/*/state.json` for /drive runs PARKED on a human
decision. A run qualifies iff `state.waiting` is a STRING matching the ANCHORED decision-bearing
grammar `^(gateA|gateB|stop:.+|ask:.+)$` — so `rebirth` (auto-resumes) is excluded, a `gateAfoo`
false-match is excluded, a non-str/malformed `waiting` is skipped by the isinstance guard, and an
unreadable/corrupt state.json is skipped fail-open PER FILE. The mc test monkeypatches
`harvest.HARNESS_RUNS_DIR` onto a tmp dir; the render section is asserted on the real output.
"""
import json


def _row(*, status="idle", goal="A goal", cwd="/work/repo", color=None, name=None):
    return {"pid": 123, "cwd": cwd, "status": status,
            "color": color, "name": name, "goal": goal}


def _runs_dir(mc_env, monkeypatch, tmp_path):
    runs = tmp_path / "harness-runs"
    runs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mc_env.harvest, "HARNESS_RUNS_DIR", str(runs))
    return runs


def _write_run(runs_dir, run_id, *, waiting, repo_root="/work/repo", raw=None):
    d = runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    sj = d / "state.json"
    if raw is not None:
        sj.write_text(raw, encoding="utf-8")
        return
    sj.write_text(json.dumps({"runId": run_id, "repoRoot": repo_root, "waiting": waiting}),
                  encoding="utf-8")


# --------------------------------------------------------------------------- #
# drive_waiting_runs() — the anchored, type-guarded, fail-open scan
# --------------------------------------------------------------------------- #
def test_drive_waiting_runs_matches_only_decision_bearing(mc_env, monkeypatch, tmp_path):
    """A run is surfaced iff waiting ∈ {gateA, gateB, stop:.+, ask:.+} (anchored). `rebirth`
    (auto-resumes), a null waiting, and a `gateAfoo` prefix false-match are all EXCLUDED."""
    runs = _runs_dir(mc_env, monkeypatch, tmp_path)
    _write_run(runs, "run-gateB", waiting="gateB", repo_root="/work/a")
    _write_run(runs, "run-gateA", waiting="gateA")
    _write_run(runs, "run-stop", waiting="stop:merge conflict at a/b")
    _write_run(runs, "run-ask", waiting="ask:Which base?")
    _write_run(runs, "run-rebirth", waiting="rebirth")   # auto-resumes — NEVER a human decision
    _write_run(runs, "run-none", waiting=None)            # autonomous
    _write_run(runs, "run-false", waiting="gateAfoo")     # anchored -> NOT a gateA match

    got = mc_env.harvest.drive_waiting_runs()
    assert {r["runId"] for r in got} == {"run-gateB", "run-gateA", "run-stop", "run-ask"}
    g = next(r for r in got if r["runId"] == "run-gateB")
    assert g["waiting"] == "gateB" and g["repoRoot"] == "/work/a", "carries waiting + repoRoot"


def test_drive_waiting_runs_skips_non_str_and_unreadable(mc_env, monkeypatch, tmp_path):
    """The `isinstance(w, str)` guard skips a non-str/malformed `waiting` (int/list) and the
    per-file try/except skips a corrupt state.json — fail-open, NEVER a crash (edge #10)."""
    runs = _runs_dir(mc_env, monkeypatch, tmp_path)
    _write_run(runs, "run-nonstr", waiting=123)                 # non-str -> skipped
    _write_run(runs, "run-list", waiting=["gateB"])             # non-str -> skipped
    _write_run(runs, "run-corrupt", waiting=None, raw="NOT JSON {{{")  # unreadable -> fail-open
    _write_run(runs, "run-ok", waiting="gateB")
    got = mc_env.harvest.drive_waiting_runs()  # must NOT raise
    assert {r["runId"] for r in got} == {"run-ok"}


def test_drive_waiting_runs_empty_when_no_runs(mc_env, monkeypatch, tmp_path):
    _runs_dir(mc_env, monkeypatch, tmp_path)
    assert mc_env.harvest.drive_waiting_runs() == []


# --------------------------------------------------------------------------- #
# render(..., drive_waits=...) — the conditional section
# --------------------------------------------------------------------------- #
def test_render_shows_drive_waits_section(mc_env):
    live = {"sid-a": _row()}
    drive_waits = [{"runId": "run-x", "waiting": "gateB", "repoRoot": "/work/repo"}]
    out = mc_env.harvest.render(live, {}, "now", drive_waits=drive_waits)
    assert "/drive runs waiting on you:" in out
    assert "⏸ run-x — gateB · /work/repo" in out


def test_render_absent_when_no_drive_waits(mc_env):
    live = {"sid-a": _row()}
    # empty list -> section absent
    assert "/drive runs waiting on you:" not in mc_env.harvest.render(live, {}, "now", drive_waits=[])
    # default None (existing 3-positional callers) -> section absent, still valid
    assert "/drive runs waiting on you:" not in mc_env.harvest.render(live, {}, "now")


def test_render_drive_waits_surfaces_even_with_no_live_sessions(mc_env):
    """A parked /drive run whose Claude session has already exited still surfaces (the
    no-live-sessions render path also emits the section)."""
    drive_waits = [{"runId": "run-y", "waiting": "ask:Which region?", "repoRoot": "/work/z"}]
    out = mc_env.harvest.render({}, {}, "now", drive_waits=drive_waits)
    assert "No live Claude sessions found." in out
    assert "/drive runs waiting on you:" in out
    assert "⏸ run-y — ask:Which region? · /work/z" in out


def test_render_three_positional_still_valid(mc_env):
    """Backward-compat: the existing 3-positional render(live, binds, now) call stays valid
    (drive_waits defaults to None)."""
    out = mc_env.harvest.render({}, {}, "now")
    assert "MISSION CONTROL" in out
