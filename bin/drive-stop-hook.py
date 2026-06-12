#!/usr/bin/env python3
"""
/drive autonomous-continuation Stop hook.

Wired into ~/.claude/settings.json by bin/install-operating-rules.sh. On every Stop it
BLOCKS the turn from ending while an active /drive run owned by THIS session still has
autonomous work to do — so the pipeline keeps driving across turns — and ALLOWS the
stop the moment the run is waiting on the human (Gate A/B, a non-decision STOP, an
AskUserQuestion) or is done. A `rebirth` pause (context-pressure handoff) ALSO has
`waiting` truthy, so the hook ALLOWS its stop identically — but its semantics are
continue-on-resume, not a human pause: the outgoing session sets `waiting="rebirth"`
to hand off and the resume path auto-clears it as a CONTINUE (see the coordinator's
I1/I4 in drive.md). The hook acts on `waiting`'s truthiness only and does not
distinguish it.

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
  waiting      — truthy while paused for the human (gate / STOP / question); else absent.
                 `rebirth` is ALSO a truthy `waiting` value but NOT a human pause: the
                 outgoing session sets it to checkpoint-and-hand-off and the resume path
                 auto-clears it as a CONTINUE (dual nature). The hook does not distinguish
                 it — it acts on truthiness only.
  rebirth_pending — truthy once context-pressure has been signalled (set by the
                    coordinator, NOT this hook); selects the ESCALATION steer over the
                    set-flag steer (I7), never suppresses both

Context-pressure detection (signal-only, design phase 2/3 / I2 / I7 / D28/D32): when the
owned run's transcript token sum crosses the hard high-water mark, this hook APPENDS a
steer to its block reason. The steer is keyed on state.rebirth_pending: when it is NOT
yet set, the set-flag steer (instruct the coordinator to set state.rebirth_pending=true);
when it is ALREADY set, the ESCALATION steer (instruct the coordinator to checkpoint and
set state.waiting="rebirth" at its next safe boundary). BOTH are advisory — the hook NEVER
writes state.json itself and NEVER hands off / checkpoints / pauses / inspects markers
(that is Phase 3's coordinator handler, at a safe boundary). The detection is fully
fail-open: any error degrades to "no steer this turn", leaving the original continue-only
reason unchanged.
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


def _rebirth_steer(run, payload):
    """A CONTEXT-PRESSURE sentence to APPEND to the block reason when the owned run has
    crossed the hard high-water mark — or "" when it has not, or on ANY error (fully
    fail-open, per I2/I7). Never writes state.json, never inspects markers, never enacts
    the handoff (D28 — advisory only; the coordinator's I1 handler acts at a boundary).

    Both steers are hard-water gated (`tokens >= window * hard fraction`); below water ->
    "" in either case. The branch is keyed on `run.rebirth_pending` (I7):
      - falsy  -> the phase-2 SET-FLAG steer ("set state.rebirth_pending=true now; do NOT
        hand off"). Signal-only: "set the flag", never "hand off".
      - truthy -> the ESCALATION steer ("you have already signalled; perform the rebirth
        checkpoint + handoff per the drive.md § I1 routine — proof = `--mode checkpoint`
        AND `--mode state-lint`, both clean — and set waiting=rebirth at your NEXT safe
        boundary"). It steers the OUTGOING session to hand off later; it does NOT itself
        checkpoint, write state, or pause.
    """
    try:
        transcript_path = payload.get("transcript_path")
        if not transcript_path or not os.path.isfile(transcript_path):
            return ""  # no transcript -> no token sum -> skip (fail-open)

        import rebirth_thresholds  # sibling bin/ module (slice 2.1 resolver)

        # Model + tokens MUST come from the SAME usage-bearing line: the model picks the
        # window the tokens are measured against, so a usage-less/synthetic line after the
        # last usage line (different/absent model) would otherwise split window from tokens.
        model, tokens = rebirth_thresholds.latest_usage_model_and_tokens(transcript_path)
        if not tokens or tokens <= 0:
            return ""  # no usage line yet -> skip (a fresh transcript hits this)
        thresholds = rebirth_thresholds.load_thresholds()
        window, hard, _soft = rebirth_thresholds.resolve_thresholds(model, thresholds)
        if tokens < hard:
            return ""  # below the hard high-water mark -> no steer (either branch)

        pct = tokens * 100 // window
        if run.get("rebirth_pending"):
            # ESCALATION: the flag is set but no boundary has been reached yet — steer the
            # outgoing session to perform the handoff at its NEXT safe boundary (I7/D32).
            return (
                f" CONTEXT-PRESSURE: this run is over the rebirth high-water mark and "
                f"state.rebirth_pending is already set (context ~{pct}% of the "
                f"{window}-token window). At your NEXT safe boundary (no open "
                f"inflight-*.marker), perform the rebirth checkpoint + handoff per the "
                f"drive.md § I1 routine (proof = bin/drive-conformance.sh "
                f"--mode checkpoint AND --mode state-lint, both clean), write "
                f"checkpoint-complete.marker, set state.waiting=\"rebirth\", and present "
                f"the handoff block. Until that boundary, keep driving — do NOT hand off "
                f"mid-dispatch."
            )
        # PRE-FLAG: the phase-2 signal-only set-flag steer (unchanged wording).
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
