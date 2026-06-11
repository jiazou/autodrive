"""EXECUTABLE end-to-end rebirth-cycle harness (slice 4.1, AC1 + AC2).

This harness runs the REAL executable pieces of the lever-2 rebirth chain over hermetic
git + RUN_DIR fixtures and asserts the detect -> prove -> handoff -> fresh-process-resume
chain composes over real artifacts. Each chain-break negative SEVERS one link and proves
the harness reds on the severed link's REAL executable behaviour.

===========================================================================
WHAT THIS HARNESS CAN AND CANNOT PROVE (honest scope — load-bearing, per D42)
===========================================================================
The /drive coordinator is PROMPT-DRIVEN: `.claude/commands/drive.md` is INSTRUCTIONS
executed by Claude, not a program. There is NO executable `/drive` resume consumer to
invoke, so a literal "run the coordinator end-to-end" is NOT possible here. What the harness
proves is precise: it runs the REAL EXECUTABLE artifacts at each step (the Stop hook,
`--mode checkpoint`, `--mode state-lint`, git ref/marker tip checks) and proves the durable
artifacts those produce are SUFFICIENT for a fresh process to reconstruct and re-prove the
run. The resume ORCHESTRATION — the SEQUENCE of rebind -> consume-marker -> re-prove ->
clear-waiting, plus the I1 prove-then-pause sequencing / handler ordering — is coordinator
PROSE pinned by `test_checkpoint_contract.py` / `test_rebirth_handshake.py`; this harness
does NOT re-prove that prose (it would only re-grep the same strings) and does NOT "run the
coordinator." It executes that sequence's individual scriptable acts and proves the REAL
proof passes on the result.

Per step, what is REAL (a shipped executable runs) vs PROSE-pinned (sequenced in Python here,
its ordering pinned by the sibling suites):
  1. DETECT/STEER  — REAL. `bin/drive-stop-hook.py` over a mid-run RUN_DIR + over-water
     transcript emits the set-flag steer (pre-flag) and the ESCALATION steer (rebirth_pending
     set). The detection->steer link actually fires on real input.
  2. PROVE         — REAL. `bin/drive-conformance.sh --mode checkpoint` AND `--mode
     state-lint` both report clean on a checkpoint-complete (quiescent + well-formed) state,
     and the TWO-MODE GATE (proven-resumable = BOTH clean) fails closed on a
     deliberately-unresumable state: an OPEN in-flight marker reds `--mode checkpoint`; a
     malformed routing state.json reds `--mode state-lint` while `--mode checkpoint` stays
     CLEAN (D8 — checkpoint never reads state.json), so it is state-lint that catches it.
     Either way one mode fails, so the both-clean gate fails closed.
  3. HANDOFF       — REAL artifacts, PROSE ordering. The marker/`waiting` WRITES use the real
     proof stdout + the atomic tmp+mv discipline; the marker's `proof.tip` == the
     `drive/<runId>` tip is checked against real `git rev-parse`. The marker-then-waiting
     ORDER is pinned by test_rebirth_handshake.py, not enforced by a shipped resume program.
  4. RECONSTRUCT   — REAL proof over a PROSE-sequenced resume. The test, acting as the
     successor, performs the scriptable resume acts (rebind `sessionId`, reset
     `rebirth_pending`, validate+DELETE the single-use marker, clear `waiting`) IN PYTHON —
     their SEQUENCE is the prose contract — then proves the result with SHIPPED executables:
     the REAL `--mode checkpoint` AND `--mode state-lint` both re-prove clean on the
     post-handoff state, the REAL Stop hook RE-ATTRIBUTES the run to the successor
     (blocks-to-continue) and, after the re-arm, emits the PRE-FLAG (not escalation) steer on
     the next over-water crossing. The marker stale-detection negative moves the tip with a
     REAL git commit and fails the marker against the REAL proof's emitted live tip — not a
     python `tip == tip` self-compare.

The prompt-driven coordinator STEPS (the resume act SEQUENCE, the I1 prove-then-pause
sequencing, the handoff-block presentation, the handler ordering) are NOT executable and are
NOT faked here — they stay pinned by `test_checkpoint_contract.py` / `test_rebirth_handshake.py`.
This harness asserts ONLY what is executable/checkable; it does NOT claim each orchestration
link runs a shipped program.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from _helpers import REPO_ROOT

CONFORMANCE = REPO_ROOT / "bin" / "drive-conformance.sh"
STOP_HOOK = REPO_ROOT / "bin" / "drive-stop-hook.py"
FIXTURES = REPO_ROOT / "tests" / "hooks" / "fixtures"
OVER_WATER = FIXTURES / "transcript-over-water.jsonl"    # Opus-4.8, sum 909200 (>= 850000)
UNDER_WATER = FIXTURES / "transcript-under-water.jsonl"  # Opus-4.8, sum 315000 (< 850000)

# The hook steer anchors (reused verbatim from test_drive_stop_hook.py — the shipped wording).
SET_FLAG_ANCHOR = "CONTEXT-PRESSURE: this run has crossed the rebirth high-water mark"
ESCALATION_ANCHOR = (
    "this run is over the rebirth high-water mark and state.rebirth_pending is already set"
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None or shutil.which("jq") is None,
    reason="needs git + bash + jq to exercise the real rebirth scripts",
)


# --------------------------------------------------------------------------- #
# Hermetic git + RUN_DIR fixture builder (real git, fake HOME).
# Mirrors test_checkpoint_contract.py::_base_run (a real `drive/<runId>` branch + a
# `phaseInt/<runId>/1` live ref descending it) and test_drive_stop_hook.py's fake-HOME
# layout: the RUN_DIR lives at <home>/.claude/harness-runs/<runId>/ so the Stop hook's
# glob finds its state.json. runId = basename(RUN_DIR) so featureBranch = drive/<runId>.
# --------------------------------------------------------------------------- #
def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )


def _rev(repo, ref):
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(repo, path, content, msg):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _review(rd, scope, n, sha="0" * 40, verdict="CONVERGED"):
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n\n## Verdict: {verdict}\n\nreviewed-sha: {sha}\n",
        encoding="utf-8",
    )


def _codex(rd, scope):
    (rd / f"codex-review-{scope}.md").write_text(
        f"codex review for {scope}\nlooks fine\n", encoding="utf-8"
    )


SID_OUT = "outgoing-sess"
SID_IN = "incoming-sess"


def _canonical_state(run_id, *, session_id=SID_OUT, **overrides):
    """The canonical mid-run state.json (the drive.md template / mkfixture.sh `clean`
    shape): stage=execute, a non-empty routable phaseList + slices, well-formed
    verify/ship. This is what `--mode state-lint` accepts as clean and what the Stop hook
    reads (sessionId/stage/autoContinue/waiting/rebirth_pending)."""
    st = {
        "runId": run_id,
        "sessionId": session_id,
        "stage": "execute",
        "phase": 1,
        "phaseList": ["1", "2"],
        "phaseBaseSha": None,
        "concurrencyCap": 4,
        "slices": {
            "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []},
            "1.2": {"step": "implementing", "owns": ["bin/y.sh", "test/y.test.sh"],
                    "deps": ["1.1"]},
        },
        "phaseDesign": {}, "phaseReview": {},
        "verify": {"attempts": []},
        "ship": {"suite": None, "conformance": None, "prUrl": None},
        "autoContinue": True,
        "waiting": None,
        "rebirth_pending": False,
    }
    st.update(overrides)
    return st


def _atomic_write_json(path, obj):
    """The tmp-file + atomic-rename discipline the coordinator uses for every state.json /
    marker write (drive.md I2a) — write `<path>.tmp.$$` then `os.replace` over `path`, so a
    reader never sees a torn file. The harness uses it for the scriptable handoff/resume
    writes so the on-disk artifact is exactly what the prose mandates."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def _perform_handoff(repo, rd, *, session_id=SID_OUT):
    """The INTEGRATED both-modes handoff gate (drive.md § I1 step 3/4), exactly as the real
    coordinator runs it: prove BOTH `--mode checkpoint` AND `--mode state-lint`, and ONLY
    when BOTH are clean write `checkpoint-complete.marker` (carrying the checkpoint proof)
    and set `state.waiting="rebirth"`. If EITHER mode is non-clean the handoff fails closed
    — NO marker, NO waiting set — proving state-lint genuinely gates the handoff in the
    integrated chain (not just in a separate side assertion).

    Returns (handed_off: bool, checkpoint_proof: dict). `handed_off` is False when the
    both-modes gate refused; the caller asserts the on-disk consequence either way."""
    rc_c, proof_c = run_conformance(repo, rd, "checkpoint")
    rc_l, _proof_l = run_conformance(repo, rd, "state-lint")
    both_clean = (rc_c == 0 and proof_c.get("clean") is True
                  and rc_l == 0 and _proof_l.get("clean") is True)
    if not both_clean:
        return False, proof_c  # fail closed: neither write happens

    # Write #1: the durable, tip-bound proof RECORD (tmp+mv).
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": session_id, "proof": proof_c})
    # Write #2: the pause, set AFTER the marker is durable (fail-closed ordering).
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = "rebirth"
    _atomic_write_json(rd / "state.json", st)
    return True, proof_c


def mid_run_fixture(home, *, run_id="e2e-run", inflight=False, rebirth_pending=False):
    """Build a realistic coordinator mid-run under the fake HOME:

      <home>/.claude/harness-runs/<run_id>/      = RUN_DIR
        state.json                               = canonical mid-run state
        review-*.md / codex-review-*.md          = CONVERGED dual-voice artifacts (counters
                                                   are non-trivial)
        inflight-review-phase1.marker            = present ONLY when inflight=True
      <home>/.claude/harness-runs/<run_id>-repo/ = a real git repo with drive/<run_id> +
                                                   phaseInt/<run_id>/1 (live phase) descending it

    Returns (repo, run_dir). The repo is a SIBLING of the RUN_DIR (not under it) so the
    Stop hook's `harness-runs/*/state.json` glob does not pick up the repo's own files.
    """
    runs = home / ".claude" / "harness-runs"
    rd = runs / run_id
    repo = runs / f"{run_id}-repo"
    rd.mkdir(parents=True)
    repo.mkdir(parents=True)

    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README", "base", "base")
    _git(repo, "checkout", "-q", "-b", f"drive/{run_id}")
    _commit(repo, "drive.sh", "echo drive", "drive work")
    # A live phase: phaseInt tip descends from drive/<runId> (the D18 live-phase shape the
    # checkpoint proof's ancestry check classifies as live, not divergent).
    _git(repo, "checkout", "-q", "-b", f"phaseInt/{run_id}/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    _git(repo, "checkout", "-q", f"drive/{run_id}")

    # CONVERGED dual-voice artifacts so the checkpoint proof's counters are non-trivial.
    _review(rd, "phase1", 1)
    _codex(rd, "phase1")
    _review(rd, "1.1", 1)

    _atomic_write_json(
        rd / "state.json",
        _canonical_state(run_id, rebirth_pending=rebirth_pending),
    )
    if inflight:
        (rd / "inflight-review-phase1.marker").write_text(
            json.dumps({"kind": "review", "scope": "phase1", "runId": run_id,
                        "sessionId": SID_OUT, "startedAt": "now"}) + "\n",
            encoding="utf-8",
        )
    return repo, rd


# --------------------------------------------------------------------------- #
# Real-script drivers.
# --------------------------------------------------------------------------- #
def run_hook(payload, *, home, bindir=None):
    """Invoke the REAL drive-stop-hook.py with `payload` on stdin, HOME=home. Mirrors
    test_drive_stop_hook.run_hook. `bindir` overrides which bin/ to run (a mutated copy
    for the threshold-mutation chain-break)."""
    hook = (bindir / "drive-stop-hook.py") if bindir else STOP_HOOK
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        env={**os.environ, "HOME": str(home)},
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=30,
    )


def hook_decision(cp):
    """The parsed stdout block decision, or None when the hook allowed (printed nothing)."""
    out = cp.stdout.strip()
    return json.loads(out) if out else None


def run_conformance(repo, rd, mode):
    """Run the REAL drive-conformance.sh <RUN_DIR> --mode <mode> from inside the repo
    (it resolves drive/<runId> refs relative to cwd). Returns (returncode, parsed-json)."""
    proc = subprocess.run(
        ["bash", str(CONFORMANCE), str(rd), "--mode", mode],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.stdout.strip(), f"no JSON on stdout for --mode {mode} (stderr={proc.stderr!r})"
    return proc.returncode, json.loads(proc.stdout)


def _hook_payload(home, run_id, transcript, *, session_id):
    return {"session_id": session_id, "transcript_path": str(transcript)}


# =========================================================================== #
# THE FORWARD CHAIN — each step runs a real executable and asserts the link fires.
# =========================================================================== #

# --- Step 1: DETECT/STEER — the real Stop hook emits the rebirth steer. ------ #
def test_step1_detect_emits_set_flag_steer_over_water(fake_home):
    """The REAL Stop hook over a mid-run RUN_DIR + over-water transcript, rebirth_pending
    UNSET -> BLOCKS with the pre-flag SET-FLAG steer (the detection->steer link fires)."""
    mid_run_fixture(fake_home, rebirth_pending=False)
    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_OUT),
        home=fake_home,
    )
    assert cp.returncode == 0
    d = hook_decision(cp)
    assert d is not None and d["decision"] == "block", "expected a block+steer, got allow"
    assert SET_FLAG_ANCHOR in d["reason"], "the over-water set-flag steer must fire"
    assert "state.rebirth_pending=true" in d["reason"]
    assert ESCALATION_ANCHOR not in d["reason"], "pre-flag must NOT emit the escalation steer"


def test_step1_detect_emits_escalation_steer_when_pending(fake_home):
    """With rebirth_pending ALREADY set + over water, the REAL hook emits the ESCALATION
    steer (checkpoint + set waiting=rebirth at the next safe boundary), not the set-flag
    one — the over-the-hard-water handoff steer the rebirth is due on."""
    mid_run_fixture(fake_home, rebirth_pending=True)
    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_OUT),
        home=fake_home,
    )
    assert cp.returncode == 0
    d = hook_decision(cp)
    assert d is not None and d["decision"] == "block"
    assert ESCALATION_ANCHOR in d["reason"], "the post-flag escalation steer must fire"
    assert SET_FLAG_ANCHOR not in d["reason"], "must not re-emit the set-flag steer"
    assert 'state.waiting="rebirth"' in d["reason"]
    # The steer names the BOTH-modes proof (per drive.md § I1), not a checkpoint-only surface.
    assert "--mode checkpoint AND --mode state-lint" in d["reason"]


# --- Step 2: PROVE — both modes clean on a checkpoint-complete state. -------- #
def test_step2_prove_both_modes_clean_on_resumable_state(fake_home):
    """The REAL proof: `--mode checkpoint` AND `--mode state-lint` BOTH report clean on a
    quiescent + well-formed mid-run state (the proof the rebirth handoff gates on). This is
    the both-modes proof (D40): proven-resumable means BOTH clean."""
    repo, rd = mid_run_fixture(fake_home)

    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    assert rc_c == 0 and obj_c["clean"] is True, obj_c
    assert obj_c["mode"] == "checkpoint"
    assert obj_c["tip"] == _rev(repo, "drive/e2e-run"), "tip must be the live featureBranch tip"
    assert "counters" in obj_c, "checkpoint must emit artifact-derived counters"

    rc_l, obj_l = run_conformance(repo, rd, "state-lint")
    assert rc_l == 0 and obj_l["clean"] is True, obj_l
    assert obj_l["mode"] == "state-lint"


# --- Step 3: HANDOFF — the scriptable prove-then-pause writes are consistent. -- #
def test_step3_handoff_gates_on_both_modes_then_writes_marker_and_waiting(fake_home):
    """The harness performs the INTEGRATED both-modes handoff (drive.md § I1 step 3/4): it
    proves BOTH `--mode checkpoint` AND `--mode state-lint` and ONLY then writes
    `checkpoint-complete.marker` (tmp+mv, carrying the proof JSON) and sets
    `state.waiting="rebirth"`. This proves the integrated gate end-to-end — the marker +
    pause appear iff BOTH modes were clean — not just that the two modes each pass in
    isolation. The prose ORDERING rule is pinned by test_rebirth_handshake.py; here the
    harness proves the WRITES are produced by the both-modes gate."""
    repo, rd = mid_run_fixture(fake_home)
    tip = _rev(repo, "drive/e2e-run")

    handed_off, proof = _perform_handoff(repo, rd)
    assert handed_off, "both modes clean -> the handoff must proceed"

    # The both-modes gate produced a consistent, tip-bound marker (D11/D17) …
    marker = rd / "checkpoint-complete.marker"
    assert marker.is_file(), "marker must be written once both modes are clean"
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    assert recorded["proof"]["tip"] == tip, "marker.proof.tip must equal the drive/<runId> tip"
    assert proof["tip"] == tip
    # … and the pause set AFTER it.
    st_after = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st_after["waiting"] == "rebirth", "the pause must be set once both modes are clean"


# --- Step 4: RECONSTRUCT — a fresh process resumes from the durable artifacts. - #
def test_step4_fresh_process_reconstructs_and_continues(fake_home):
    """The load-bearing E2E claim (AC1): after a simulated handoff, the durable artifacts
    (git refs + RUN_DIR marker + state.json) are SUFFICIENT for a fresh process to
    reconstruct and continue. The test, acting as the successor, performs the SCRIPTABLE
    resume acts and asserts the reconstructed run is continuable."""
    # The realistic handoff state: rebirth_pending is ALREADY set (the escalation steer fired
    # because it was set, then the boundary checkpoint+pause ran). The resume re-arm must
    # CLEAR it — so building the fixture with rebirth_pending=True makes the step-(2) reset
    # below load-bearing (removing it leaves the field true and reds guard (v)).
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")

    # --- simulate the outgoing handoff (step 3) — the INTEGRATED both-modes gate ---
    handed_off, proof = _perform_handoff(repo, rd)
    assert handed_off, "the outgoing handoff must gate on BOTH modes clean before writing"
    marker = rd / "checkpoint-complete.marker"

    # BEFORE the rebind: prove the sessionId rebind (D7) is the load-bearing variable, with
    # `waiting` controlled OUT of the picture. The continuation hook keeps a run driving only
    # for the session whose id == state.sessionId AND only when waiting is empty (see
    # drive-stop-hook.py main(): it `continue`s past any waiting run, so a still-set
    # waiting=="rebirth" would make the hook allow for ANY session regardless of ownership —
    # which would NOT isolate the rebind). So CLEAR waiting here, leave sessionId at SID_OUT,
    # and assert the sessionId-MATCH branch: the successor (SID_IN) does NOT own the run, so
    # the hook does NOT keep THIS run driving for it -> allows. (Removing the rebind below —
    # i.e. leaving sessionId at SID_OUT — reds the post-rebind block assertion; this is the
    # executable form of test_chainbreak_resume_severed_unrebound_session_does_not_block.)
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = None
    _atomic_write_json(rd / "state.json", st)
    cp_before = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    assert hook_decision(cp_before) is None, \
        "pre-rebind (waiting cleared): sessionId still SID_OUT -> the successor does NOT own " \
        "the run -> the hook does not keep it driving for SID_IN (allows). The rebind, not " \
        "waiting, is the variable under test."

    # --- the SCRIPTABLE resume acts (drive.md I4/I7/D7/D17/D36) --------------
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    # (1) sessionId rebind FIRST (D7): re-attribute the run to the live session. With waiting
    # already cleared above, this rebind is the SOLE difference from the pre-rebind allow —
    # so the post-rebind block below isolates the rebind's real consequence.
    st["sessionId"] = SID_IN
    # (2) re-arm: reset rebirth_pending (D36).
    st["rebirth_pending"] = False
    _atomic_write_json(rd / "state.json", st)

    # (3) validate + DELETE the single-use marker (D17, tip-match).
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    marker_valid = recorded.get("proof", {}).get("tip") == tip
    assert marker_valid, "the marker must validate (tip-match) before consumption"
    marker.unlink()  # single-use consumption — the resume's first act after rebind

    # (4) RE-PROVE both modes (the resume re-prove gate). `waiting` was already cleared in the
    # pre-rebind control above; the re-prove confirms BOTH modes stay clean on the
    # reconstructed (rebound + re-armed + marker-consumed) state.
    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    rc_l, obj_l = run_conformance(repo, rd, "state-lint")
    assert rc_c == 0 and obj_c["clean"] is True, "re-prove checkpoint must still pass"
    assert rc_l == 0 and obj_l["clean"] is True, "re-prove state-lint must still pass"
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st["waiting"] is None, "waiting was cleared in the pre-rebind control (CONTINUE semantics)"

    # --- the reconstructed run is continuable -------------------------------
    # (i) the Stop hook now RE-ATTRIBUTES the run to the successor and blocks-to-continue
    #     (the D7 multi-rebirth rebind, proven executably).
    cp_after = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d_after = hook_decision(cp_after)
    assert d_after is not None and d_after["decision"] == "block", \
        "post-rebind: the successor owns a not-waiting run -> hook blocks-to-continue"
    assert "e2e-run" in d_after["reason"]
    # (ii) the marker is consumed (single-use).
    assert not marker.exists(), "the checkpoint-complete.marker must be consumed (single-use)"
    # (iii) --mode checkpoint still passes (already asserted above as the re-prove).
    # (iv) --mode state-lint is clean on the reconstructed state.
    rc_l2, obj_l2 = run_conformance(repo, rd, "state-lint")
    assert rc_l2 == 0 and obj_l2["clean"] is True, obj_l2

    # (v) the rebirth_pending RE-ARM (D36) actually fired: the on-disk reconstructed state
    #     has rebirth_pending cleared, AND the REAL Stop hook proves the consequence — when
    #     the successor next crosses hard water, the hook emits the PRE-FLAG set-flag steer
    #     (rebirth_pending unset), NOT the escalation steer. If step (2) above left
    #     rebirth_pending true, the hook would spuriously re-fire the ESCALATION steer as if
    #     a handoff were already signalled. (Removing the `rebirth_pending=False` reset above
    #     reds this guard — see test_chainbreak_resume_severed_missing_rearm_refires.)
    st_recon = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st_recon["rebirth_pending"] is False, \
        "the resume re-arm must clear rebirth_pending (D36) so the next cycle starts fresh"
    cp_rearm = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d_rearm = hook_decision(cp_rearm)
    assert d_rearm is not None and d_rearm["decision"] == "block"
    assert SET_FLAG_ANCHOR in d_rearm["reason"], \
        "re-armed: a fresh over-water crossing must emit the PRE-FLAG set-flag steer"
    assert ESCALATION_ANCHOR not in d_rearm["reason"], \
        "re-armed: rebirth_pending was cleared, so the hook must NOT re-fire the escalation steer"


def test_step4b_waiting_rebirth_is_a_continue_not_a_human_pause(fake_home):
    """The rebirth-CONTINUE branch, exercised directly (AC1 — the resume-as-continue this
    feature exists for). DISTINCT from test_step4's rebind-isolation control, which CLEARS
    `waiting` before the resume so the rebind is the only variable: there the
    `waiting=="rebirth"` continue branch is never actually taken. Here `waiting` STAYS
    "rebirth" through the handoff and the hook is exercised against it, proving:

      (a) the OUTGOING session's Stop hook ALLOWS the turn to END on a `waiting=="rebirth"`
          run — the hook acts on `waiting`'s TRUTHINESS only (drive-stop-hook main(): it
          `continue`s past any waiting run), so a rebirth pause lets the outgoing turn end
          exactly like a human pause would. This is what makes the handoff a clean stop.
      (b) the CONTINUE semantics (NOT a human-answer wait): a fresh successor, after the D7
          rebind, RE-PROVES BOTH modes clean on the still-`waiting=="rebirth"` reconstructed
          state — i.e. the run is resumable WITHOUT any human answer — and only THEN clears
          `waiting=null` in the re-proven CONTINUE branch (drive.md L84-87: clear in the
          re-proven CONTINUE branch, never before). After that clear the REAL hook
          blocks-to-continue for the successor, i.e. the pipeline auto-resumes. A human pause
          (gateA/gateB/stop:/ask:) would instead require a human answer, never an auto-clear
          on a passing proof.
    """
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")

    # The outgoing handoff: both modes gate -> marker + waiting="rebirth" (NOT cleared here).
    handed_off, _proof = _perform_handoff(repo, rd)
    assert handed_off, "the outgoing handoff must gate on BOTH modes clean"
    marker = rd / "checkpoint-complete.marker"
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st["waiting"] == "rebirth", "the handoff set the rebirth pause"

    # (a) The OUTGOING session's Stop hook ALLOWS the turn to end *because* waiting is truthy:
    #     a rebirth pause ends the outgoing turn just like a human pause. (Same session id
    #     SID_OUT that owns the run — the allow is driven by `waiting`, not by ownership.)
    cp_out = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_OUT),
        home=fake_home,
    )
    assert hook_decision(cp_out) is None, \
        "waiting==rebirth is truthy -> the hook lets the OUTGOING turn END (the handoff stop)"

    # (b) The successor takes the CONTINUE branch. Rebind (D7) + consume the single-use marker,
    #     with `waiting` STILL "rebirth" (the resume re-proves BEFORE clearing — L84-87).
    st["sessionId"] = SID_IN
    st["rebirth_pending"] = False
    _atomic_write_json(rd / "state.json", st)
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    assert recorded.get("proof", {}).get("tip") == tip, "marker must validate (tip-match)"
    marker.unlink()

    # The re-prove gate runs while waiting is STILL "rebirth" — proving resumability needs NO
    # human answer (the rebirth-continue distinction). state-lint must ALSO accept rebirth as
    # a clean waiting value (the per-field guard added this round must not over-reject it).
    st_reprove = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st_reprove["waiting"] == "rebirth", "waiting is re-proven BEFORE it is cleared"
    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    rc_l, obj_l = run_conformance(repo, rd, "state-lint")
    assert rc_c == 0 and obj_c["clean"] is True, "re-prove checkpoint must pass on a rebirth-waiting run"
    assert rc_l == 0 and obj_l["clean"] is True, \
        "re-prove state-lint must pass: rebirth is a VALID waiting value (no over-reject)"

    # The re-proven CONTINUE branch clears waiting=null (auto-clear on a passing proof — the
    # mark of a continue, not a human-answer wait).
    st_reprove["waiting"] = None
    _atomic_write_json(rd / "state.json", st_reprove)

    # The successor now blocks-to-continue: the pipeline AUTO-RESUMES (no human answer was
    # ever required — that is the rebirth-continue semantics).
    cp_in = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d_in = hook_decision(cp_in)
    assert d_in is not None and d_in["decision"] == "block", \
        "after the re-proven CONTINUE clears waiting, the successor auto-resumes (blocks-to-continue)"
    assert "e2e-run" in d_in["reason"]


# =========================================================================== #
# CHAIN-BREAK NEGATIVES (AC2, load-bearing) — sever ONE link, prove the harness FAILS.
# A harness that cannot red on a broken chain is worthless; each negative below is a real
# assertion that the SEVERED link's executable behaves as a failure.
# =========================================================================== #

# --- Break DETECTION: over-water transcript but the thresholds are mutated so it
#     reads as UNDER water -> NO steer. Proves the steer is genuinely threshold-gated
#     (a hook that always steers would pass step 1 vacuously). ------------------ #
def test_chainbreak_detection_severed_no_steer(fake_home, tmp_path):
    """DETECTION severed: run a COPY of bin/ whose rebirth-thresholds.json hard fraction is
    raised above 1.0 so the 909200-token over-water transcript no longer crosses the hard
    mark (909200 < 1000000 * 2.0) -> the hook emits NO rebirth steer. If the detection link
    were a no-op (always steers), this would still steer and the negative would (correctly) fail."""
    mid_run_fixture(fake_home, rebirth_pending=False)
    bindir = tmp_path / "bin"
    shutil.copytree(REPO_ROOT / "bin", bindir)
    data = json.loads((bindir / "rebirth-thresholds.json").read_text(encoding="utf-8"))
    # Raise the hard fraction above 1.0 so no token sum can cross window*fraction.
    data["hardHighWaterFraction"] = 2.0
    (bindir / "rebirth-thresholds.json").write_text(json.dumps(data), encoding="utf-8")

    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_OUT),
        home=fake_home, bindir=bindir,
    )
    assert cp.returncode == 0
    d = hook_decision(cp)
    # The hook STILL blocks-to-continue (autonomous work remains) but with NO rebirth steer.
    assert d is not None and d["decision"] == "block"
    assert SET_FLAG_ANCHOR not in d["reason"], "detection severed -> the set-flag steer must NOT fire"
    assert ESCALATION_ANCHOR not in d["reason"], "detection severed -> no escalation steer either"


def test_chainbreak_detection_severed_under_water_no_steer(fake_home):
    """DETECTION severed (the simple form): a genuinely UNDER-water transcript -> the real
    hook emits no rebirth steer. The detect link only fires over the hard mark."""
    mid_run_fixture(fake_home, rebirth_pending=True)
    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_OUT),
        home=fake_home,
    )
    d = hook_decision(cp)
    assert d is not None and d["decision"] == "block"
    assert SET_FLAG_ANCHOR not in d["reason"]
    assert ESCALATION_ANCHOR not in d["reason"], "below water -> no escalation steer (hard-water gated)"


# --- Break PROOF (checkpoint): an open in-flight marker -> checkpoint fails closed. - #
def test_chainbreak_proof_severed_inflight_open_checkpoint_fails(fake_home):
    """PROOF severed: a quiescent fixture with an OPEN inflight-*.marker -> the REAL
    `--mode checkpoint` exits 1 with `inflight-open`. The proof refuses to declare the run
    resumable while work is in flight (fail-closed), so the handoff gate would not proceed."""
    repo, rd = mid_run_fixture(fake_home, inflight=True)
    rc, obj = run_conformance(repo, rd, "checkpoint")
    assert rc == 1 and obj["clean"] is False, obj
    reasons = {v["reason"] for v in obj["violations"]}
    assert "inflight-open" in reasons, obj["violations"]


# --- Break PROOF (state-lint): a malformed routing state.json -> state-lint fails. - #
@pytest.mark.parametrize(
    "mutate, expect_reason",
    [
        (lambda st: st.update(slices={"1.1": {"step": "bogus", "owns": ["x"], "deps": []}}),
         "slice-routing-malformed"),
        (lambda st: st.update(phaseList=[]),
         "phaselist-malformed"),
        ("corrupt", "unparseable-state"),
    ],
    ids=["bad-slice-step", "empty-phaselist-executing", "corrupt-json"],
)
def test_chainbreak_proof_severed_state_lint_fails(fake_home, mutate, expect_reason):
    """PROOF severed (the routing-hint half): a deliberately-unresumable state.json (an
    out-of-enum slice step, an empty phaseList while executing, or corrupt JSON) -> the
    REAL `--mode state-lint` exits 1 with the matching violation. BOTH modes must be clean
    for the handoff to proceed, so a state-lint failure fails the proof closed exactly like
    a checkpoint failure."""
    repo, rd = mid_run_fixture(fake_home)
    sj = rd / "state.json"
    if mutate == "corrupt":
        sj.write_text("CORRUPT-NOT-JSON{{{\n", encoding="utf-8")
    else:
        st = json.loads(sj.read_text(encoding="utf-8"))
        mutate(st)
        _atomic_write_json(sj, st)

    rc, obj = run_conformance(repo, rd, "state-lint")
    assert rc == 1 and obj["clean"] is False, obj
    reasons = {v["reason"] for v in obj["violations"]}
    assert expect_reason in reasons, obj["violations"]

    # And the SAME unresumable state.json STILL passes --mode checkpoint (D8: checkpoint
    # NEVER reads state.json) — proving state-lint is the link that catches it, and that
    # the two-mode proof is what makes the gate honest (checkpoint alone would pass).
    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    assert rc_c == 0 and obj_c["clean"] is True, \
        "checkpoint must stay clean on a bad state.json (it never reads it) — state-lint is the gate"


# --- Break HANDOFF GATE (integrated): state-lint fails -> the both-modes handoff does
#     NOT proceed (no marker, no waiting=rebirth) even though checkpoint is clean. ---- #
def test_chainbreak_handoff_state_lint_failure_blocks_marker_and_waiting(fake_home):
    """The INTEGRATED both-modes gate, severed at the state-lint link: on a malformed routing
    state.json `--mode checkpoint` STAYS clean (D8 — never reads state.json) but `--mode
    state-lint` fails, so the integrated `_perform_handoff` refuses — NO
    `checkpoint-complete.marker` is written and `state.waiting` is NEVER set to "rebirth".
    This proves state-lint genuinely gates the handoff in the integrated chain, not merely in
    a side assertion: checkpoint-alone would have written the marker."""
    repo, rd = mid_run_fixture(fake_home)
    sj = rd / "state.json"
    st = json.loads(sj.read_text(encoding="utf-8"))
    st.update(slices={"1.1": {"step": "bogus", "owns": ["x"], "deps": []}})  # state-lint reds
    _atomic_write_json(sj, st)

    # Sanity: checkpoint is clean, state-lint fails — exactly the divergence the gate exists for.
    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    assert rc_c == 0 and obj_c["clean"] is True, "checkpoint clean (never reads state.json)"
    rc_l, obj_l = run_conformance(repo, rd, "state-lint")
    assert rc_l == 1 and obj_l["clean"] is False, "state-lint must red on the malformed routing"

    handed_off, _proof = _perform_handoff(repo, rd)
    assert handed_off is False, "a state-lint failure must fail the both-modes handoff closed"
    # The fail-closed consequence: NEITHER write happened.
    assert not (rd / "checkpoint-complete.marker").exists(), \
        "no marker may be written when the both-modes gate refuses"
    st_after = json.loads(sj.read_text(encoding="utf-8"))
    assert st_after.get("waiting") != "rebirth", \
        "waiting must NOT be set to rebirth when state-lint fails the handoff gate"


# --- Break RESUME (marker consumption): a stale checkpoint marker whose proof.tip
#     no longer matches the moved tip -> the marker does NOT validate, so a
#     re-attribution that trusted the marker would be refused. ------------------ #
def test_chainbreak_resume_severed_stale_marker_fails_validation(fake_home):
    """RESUME severed (the single-use marker stale-detection): the handoff writes a
    tip-bound marker, then work advances drive/<runId> with a REAL git commit (the tip
    MOVES). On resume the live tip is re-derived by the REAL proof — `--mode checkpoint`'s
    emitted `tip` (and, independently, `git rev-parse drive/<runId>`) — and the marker's
    bound `proof.tip` no longer equals it, so the tip-match validation FAILS. The resume
    must re-prove from scratch, never replay the stale marker (D17). The staleness here is
    detected by the SHIPPED tip source (the real conformance proof + real git), not a
    python `tip == tip` self-compare."""
    repo, rd = mid_run_fixture(fake_home)
    tip_then = _rev(repo, "drive/e2e-run")
    _rc, proof = run_conformance(repo, rd, "checkpoint")
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": SID_OUT, "proof": proof})
    assert proof["tip"] == tip_then

    # Work advances the feature branch AFTER the marker was written (a REAL git commit). The
    # phase integration ref is fast-forwarded onto the new tip too, so the run stays a
    # well-formed, resumable D18 live-phase shape (drive/<runId> remains an ancestor of the
    # phaseInt tip) — the marker is stale, but the RUN is not corrupt.
    _commit(repo, "more.sh", "echo more", "post-checkpoint work")
    _git(repo, "branch", "-f", "phaseInt/e2e-run/1", "drive/e2e-run")

    # Re-derive the LIVE tip the way the resume consumer does: from the REAL proof's emitted
    # `tip` (re-run `--mode checkpoint`), cross-checked against real `git rev-parse` — the
    # SHIPPED tip source, not a python `tip == tip` self-compare.
    _rc2, proof_now = run_conformance(repo, rd, "checkpoint")
    assert proof_now["clean"] is True, "post-advance state is still resumable (re-prove passes)"
    live_tip = proof_now["tip"]
    assert live_tip == _rev(repo, "drive/e2e-run"), \
        "the proof's emitted tip must equal the real git tip (the shipped tip source)"
    assert live_tip != proof["tip"], "the real commit must have moved the live tip"

    # The marker's bound proof.tip is validated against the LIVE tip from the real proof —
    # it no longer matches, so the single-use marker fails tip-match validation.
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    marker_valid = recorded.get("proof", {}).get("tip") == live_tip
    assert not marker_valid, \
        "RESUME severed: a stale-tip marker must FAIL tip-match validation against the " \
        "real proof's live tip (no replay, D17)"


def test_chainbreak_resume_severed_missing_rearm_refires(fake_home):
    """RESUME severed (the rebirth_pending re-arm, D36): a successor that rebinds + clears
    waiting but FORGETS to reset rebirth_pending leaves the run mis-armed. The detectable
    wrong consequence — proven by the REAL Stop hook — is that the successor's next hard-water
    crossing spuriously re-fires the ESCALATION steer (checkpoint + set waiting=rebirth) as if
    a handoff were already signalled, instead of the fresh PRE-FLAG set-flag steer. This is the
    chain-break that reds when the `rebirth_pending=False` reset in the resume acts is removed."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    # Resume that rebinds + clears waiting but SKIPS the rebirth_pending reset.
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["sessionId"] = SID_IN
    st["waiting"] = None
    # st["rebirth_pending"] is left True (the re-arm was skipped).
    _atomic_write_json(rd / "state.json", st)

    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d = hook_decision(cp)
    assert d is not None and d["decision"] == "block"
    assert ESCALATION_ANCHOR in d["reason"], \
        "missing re-arm: a still-set rebirth_pending makes the hook spuriously re-fire the " \
        "ESCALATION steer on the successor's first over-water crossing"
    assert SET_FLAG_ANCHOR not in d["reason"]

    # Control: WITH the re-arm applied, the SAME over-water crossing emits the PRE-FLAG
    # set-flag steer instead — proving the spurious escalation above is caused by the
    # missing reset, not by something else.
    st["rebirth_pending"] = False
    _atomic_write_json(rd / "state.json", st)
    cp2 = run_hook(
        _hook_payload(fake_home, "e2e-run", OVER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d2 = hook_decision(cp2)
    assert d2 is not None and d2["decision"] == "block"
    assert SET_FLAG_ANCHOR in d2["reason"], \
        "control: with the re-arm, the fresh crossing emits the set-flag steer"
    assert ESCALATION_ANCHOR not in d2["reason"]


def test_chainbreak_resume_severed_unrebound_session_does_not_block(fake_home):
    """RESUME severed (the sessionId rebind, D7): if the successor SKIPS the rebind, the run
    is still attributed to the OUTGOING session, so the Stop hook does NOT block for the
    incoming session -> auto-continue cannot resume. Proves the rebind is load-bearing for
    re-attribution (the multi-rebirth fix)."""
    repo, rd = mid_run_fixture(fake_home)
    # Simulate a resume that cleared waiting but FORGOT the sessionId rebind.
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = None  # the run is no longer waiting...
    # ...but st["sessionId"] is left at SID_OUT (the rebind was skipped).
    _atomic_write_json(rd / "state.json", st)

    cp = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    assert hook_decision(cp) is None, \
        "un-rebound sessionId -> the successor does NOT own the run -> hook allows (cannot resume)"
    # Control: with the rebind applied, the SAME successor session DOES block — proving the
    # allow above is caused by the missing rebind, not by something else.
    st["sessionId"] = SID_IN
    _atomic_write_json(rd / "state.json", st)
    cp2 = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d2 = hook_decision(cp2)
    assert d2 is not None and d2["decision"] == "block", \
        "control: with the rebind, the successor owns the run and the hook blocks-to-continue"
