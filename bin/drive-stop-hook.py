#!/usr/bin/env python3
"""
/drive autonomous-continuation Stop hook.

Wired into ~/.claude/settings.json by bin/install-operating-rules.sh. On every Stop it
BLOCKS the turn from ending while an active /drive run owned by THIS session still has
autonomous work to do — so the pipeline keeps driving across turns — and ALLOWS the
stop the moment the run is waiting on the human (Gate A/B, a non-decision STOP, an
AskUserQuestion) or is done.

Design bias: blocking a stop is the "dangerous" action (it can push the agent past a
halt), so this hook is biased HARD toward allowing. It blocks ONLY on positive
evidence that this session owns a not-done run that is not waiting and not disabled.
Every other path — unparseable input, no session id, no matching run, kill-switch,
any exception — ALLOWS the stop. A bug here can annoy (a run stops early and you nudge
it) but must never trap a session.

Layered guards: (1) stop_hook_active loop guard, (2) session-scoped run match,
(3) per-run kill-switch (autoContinue:false), (4) fail-open on every error,
(5) Claude Code's built-in consecutive-block cap as a final backstop.

state.json contract /drive maintains (see drive.md):
  sessionId    — owning Claude session id ($CLAUDE_CODE_SESSION_ID)
  stage        — pipeline stage; "done" once the PR is open
  autoContinue — if exactly False, this hook is disabled for the run (kill-switch)
  waiting      — truthy while paused for the human (gate / STOP / question); else absent
"""
import sys
import os
import json
import glob


def _allow():
    """Let the turn end. The default for every uncertain path."""
    sys.exit(0)


def _runs_glob():
    return os.path.join(os.path.expanduser("~"), ".claude", "harness-runs", "*", "state.json")


def _override_state_paths():
    """The DRIVE_STOP_HOOK_PATHS scan-order seam: a JSON list[str], or None to fall back.
    Honored only under pytest (see _run_state_paths), so the test controls the value and the
    path shape is not re-validated. Never raises."""
    raw = os.environ.get("DRIVE_STOP_HOOK_PATHS")
    if not raw:
        return None
    try:
        paths = json.loads(raw)
    except Exception:
        return None
    if isinstance(paths, list) and all(isinstance(p, str) for p in paths):
        return paths
    return None


def _run_state_paths():
    """The state.json paths to scan, in deterministic order. Production is ALWAYS
    sorted(glob(...)); the DRIVE_STOP_HOOK_PATHS seam is honored ONLY under pytest, so a
    parent-env value can never alter production behavior (fail-open to the glob)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = _override_state_paths()
        if override is not None:
            return override
    return sorted(glob.glob(_runs_glob()))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()  # can't read the hook input -> never block

    # (1) Loop guard: if this stop is already a continuation we forced, let it end.
    if payload.get("stop_hook_active"):
        _allow()

    sid = payload.get("session_id") or ""
    if not sid:
        _allow()  # no session identity -> can't safely attribute a run

    # (2) Find a BLOCKABLE run OWNED by this session: not done, not disabled by the
    # per-run kill-switch (autoContinue:false), and not waiting on the human. We must
    # keep scanning past owned-but-non-blockable runs (a waiting/disabled one) — if it
    # short-circuited on the first owned not-done run, a non-blockable run enumerated
    # ahead of an active one would mask it and fail-OPEN past real autonomous work.
    run = None
    for path in _run_state_paths():
        try:
            st = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue  # skip an unreadable/partial run file
        if not isinstance(st, dict):
            continue  # valid JSON but not an object -> skip like any other bad file
        if st.get("sessionId") != sid or st.get("stage") == "done":
            continue  # not this session's, or already finished -> not blockable
        if st.get("autoContinue") is False:
            continue  # (3) kill-switch: this run is disabled, but keep scanning
        if st.get("waiting"):
            continue  # paused for the human on this run, but keep scanning
        run = st  # first owned, not-done, not-disabled, not-waiting run -> block on it
        break
    if run is None:
        _allow()  # no blockable owned run found in the full scan

    # Positive evidence of autonomous work remaining -> block and steer the next turn.
    # The reason explicitly defers to gates/STOPs so the agent never barrels past one.
    # `phase` is only meaningful once execution begins, so omit it for early stages rather
    # than print a bare `phase=?` next to a real stage.
    phase = run.get("phase")
    loc = f"stage={run.get('stage', '?')}" + (f", phase={phase}" if phase else "")
    reason = (
        f"/drive run {run.get('runId', '?')}: autonomous work remains ({loc}). "
        "Continue the pipeline. Do NOT stop until you reach Gate A, Gate B, a "
        "non-decision STOP, an AskUserQuestion, or the PR is open (stage=done) — "
        "and set state.waiting before pausing at any of those so this turn can end."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # _allow()/normal exits pass through
    except Exception:
        sys.exit(0)  # absolute fail-open backstop — a crash must never block
