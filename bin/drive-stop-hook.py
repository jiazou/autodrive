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
  rebirth_pending — truthy once context-pressure has been signalled (set by the
                    coordinator, NOT this hook); suppresses the re-steer (idempotent)

Context-pressure detection (signal-only, design phase 2 / I2 / D28): when the owned
run's transcript token sum crosses the hard high-water mark, this hook APPENDS a
signal-only steer to its block reason instructing the coordinator to set
state.rebirth_pending=true. It NEVER writes state.json itself and NEVER hands off /
checkpoints / pauses (that is Phase 3, at a safe boundary). The detection is fully
fail-open: any error degrades to "no steer this turn", leaving the original
continue-only reason unchanged.
"""
import sys
import os
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for rebirth_thresholds


def _allow():
    """Let the turn end. The default for every uncertain path."""
    sys.exit(0)


def _runs_glob():
    return os.path.join(os.path.expanduser("~"), ".claude", "harness-runs", "*", "state.json")


def _override_state_paths():
    """Parse + validate the DRIVE_STOP_HOOK_PATHS test seam, or None to fall back.

    Returns the override path list ONLY when it is genuinely a test pin: a JSON
    list[str] whose every entry sits under ~/.claude/harness-runs/*/state.json (the
    same shape _runs_glob() produces). Any other value — unset, not JSON, not a
    list, a non-str element, or a path outside that root — returns None so the
    caller falls back to sorted(glob(...)). Never raises."""
    raw = os.environ.get("DRIVE_STOP_HOOK_PATHS")
    if not raw:
        return None
    try:
        paths = json.loads(raw)
    except Exception:
        return None
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return None
    runs_root = os.path.join(os.path.expanduser("~"), ".claude", "harness-runs")
    for p in paths:
        # Must be <runs_root>/<run>/state.json — directly under runs_root, one dir deep.
        if os.path.basename(p) != "state.json":
            return None
        rundir = os.path.dirname(p)
        if os.path.dirname(rundir) != runs_root:
            return None
    return paths


def _run_state_paths():
    """The state.json paths to scan, in deterministic order.

    Production: ALWAYS sorted(glob(...)) — a stable order that never depends on the
    filesystem's incidental glob order, and never on the parent environment. The
    DRIVE_STOP_HOOK_PATHS env var is a TEST-ONLY scan-order seam: it is honored ONLY
    when running under pytest (PYTEST_CURRENT_TEST is set) AND its value validates as
    a JSON list[str] of run-glob-shaped paths (see _override_state_paths). Outside a
    test, or for any invalid value, it is a complete no-op — production behavior is
    identical to sorted(glob(...)), so a foreign/empty parent-env value can never
    suppress a real block (fail-open)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        override = _override_state_paths()
        if override is not None:
            return override
    return sorted(glob.glob(_runs_glob()))


def _rebirth_steer(run, payload):
    """A signal-only CONTEXT-PRESSURE sentence to APPEND to the block reason when the
    owned run has crossed the hard high-water mark — or "" when it has not, or on ANY
    error (fully fail-open, per I2). Never writes state.json, never inspects markers.

    Steers ONLY when all hold (I2): the transcript token sum >= window * hard fraction,
    run.rebirth_pending is not already truthy (idempotent — don't re-steer; the
    coordinator may have already set it), and (already guaranteed by the caller's scan)
    the run is not waiting. The wording is signal-only: "set the flag", never "hand off".
    """
    try:
        if run.get("rebirth_pending"):
            return ""  # idempotent: already signalled, don't re-steer
        transcript_path = payload.get("transcript_path")
        if not transcript_path or not os.path.isfile(transcript_path):
            return ""  # no transcript -> no token sum -> skip (fail-open)

        import rebirth_thresholds  # sibling bin/ module (slice 2.1 resolver)

        tokens = rebirth_thresholds.latest_usage_tokens(transcript_path)
        if not tokens or tokens <= 0:
            return ""  # no usage line yet -> skip (a fresh transcript hits this)
        model = rebirth_thresholds.latest_model(transcript_path)
        thresholds = rebirth_thresholds.load_thresholds()
        window, hard, _soft = rebirth_thresholds.resolve_thresholds(model, thresholds)
        if tokens < hard:
            return ""  # below the hard high-water mark -> no steer

        pct = tokens * 100 // window
        return (
            f" CONTEXT-PRESSURE: this run has crossed the rebirth high-water mark "
            f"(context ~{pct}% of the {window}-token window). Set "
            f"state.rebirth_pending=true now (a plain field write — do NOT hand off, "
            f"do NOT checkpoint, do NOT pause here). The handoff happens later at your "
            f"next safe boundary per the rebirth contract; until then, keep driving the "
            f"pipeline normally."
        )
    except Exception:
        return ""  # any detection failure degrades to no steer this turn (fail-open)


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
    reason = (
        f"/drive run {run.get('runId', '?')}: autonomous work remains "
        f"(stage={run.get('stage', '?')}, phase={run.get('phase', '?')}). "
        "Continue the pipeline. Do NOT stop until you reach Gate A, Gate B, a "
        "non-decision STOP, an AskUserQuestion, or the PR is open (stage=done) — "
        "and set state.waiting before pausing at any of those so this turn can end."
    )
    # Additive, signal-only context-pressure steer (fail-open; "" on any error).
    reason += _rebirth_steer(run, payload)
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # _allow()/normal exits pass through
    except Exception:
        sys.exit(0)  # absolute fail-open backstop — a crash must never block
