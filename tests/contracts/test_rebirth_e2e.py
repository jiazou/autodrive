"""EXECUTABLE end-to-end rebirth-cycle harness (slice 4.1, AC1 + AC2).

This harness runs the REAL executable pieces of the lever-2 rebirth chain over hermetic
git + RUN_DIR fixtures and asserts the detect -> prove -> handoff -> fresh-process-resume
chain composes. It is the answer to the codex P1 "detect->handoff chain is advisory /
unproven E2E": each link below is exercised by running the real script and asserting on
its real output, and each chain-break negative SEVERS one link and proves the harness reds.

===========================================================================
WHAT THIS HARNESS CAN AND CANNOT PROVE (honest scope — load-bearing, per D42)
===========================================================================
The /drive coordinator is PROMPT-DRIVEN: `.claude/commands/drive.md` is INSTRUCTIONS
executed by Claude, not a program. A literal "run the coordinator end-to-end" is therefore
NOT a unit test — the prove-then-pause sequencing, the I1 handler ordering, and the resume
reconciliation are PROSE contracts pinned by the slice-1.3 / 3.3 string/structural suites
(`test_checkpoint_contract.py`, `test_rebirth_handshake.py`). This harness does NOT re-prove
those (it would only re-grep the same prose) and does NOT "run the coordinator."

What IS executable and what this harness DOES prove — the STATE-RECONSTRUCTION half of the
cycle, run against the REAL scripts over REAL git + RUN_DIR artifacts:
  1. DETECT/STEER  — the REAL `bin/drive-stop-hook.py` over a mid-run RUN_DIR + over-water
     transcript emits the set-flag steer (pre-flag) and the ESCALATION steer (rebirth_pending
     set). The detection->steer link actually fires on real input.
  2. PROVE         — the REAL `bin/drive-conformance.sh --mode checkpoint` AND `--mode
     state-lint` both report clean on a checkpoint-complete (quiescent + well-formed) state,
     and BOTH fail closed on a deliberately-unresumable state (open in-flight marker /
     malformed routing state.json). The fail-closed gate actually gates.
  3. HANDOFF       — the SCRIPTABLE prove-then-pause writes (write `checkpoint-complete.marker`
     from the proof stdout via tmp+mv; set `state.waiting="rebirth"` via the same atomic
     jq|mv the coordinator uses) produce a consistent on-disk pair: marker parses, its
     `proof.tip` == the `drive/<runId>` tip, BEFORE `waiting=="rebirth"`.
  4. RECONSTRUCT   — a FRESH read (the test, as the successor) performs the SCRIPTABLE resume
     acts (rebind `sessionId`, reset `rebirth_pending`, validate+DELETE the single-use marker,
     clear `waiting`) and asserts the run is continuable: the Stop hook now RE-ATTRIBUTES the
     run to the successor session (blocks-to-continue), `--mode checkpoint` STILL passes, the
     marker is consumed, and `--mode state-lint` is clean.

The prompt-driven coordinator STEPS (I1 prove-then-pause sequencing, the handoff-block
presentation, the I1 handler ordering) are NOT executable and are NOT faked here — they stay
pinned by `test_checkpoint_contract.py` / `test_rebirth_handshake.py`. This harness asserts
ONLY what is executable/checkable.
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
    assert "--mode checkpoint" in d["reason"]


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
def test_step3_handoff_writes_consistent_marker_then_waiting(fake_home):
    """The harness performs the SCRIPTABLE coordinator handoff writes — write
    `checkpoint-complete.marker` (tmp+mv) carrying the step-2 proof JSON, THEN set
    `state.waiting="rebirth"` (atomic jq|mv-equivalent) — and asserts the on-disk pair is
    consistent: the marker exists, parses, and its `proof.tip` == the drive/<runId> tip
    BEFORE waiting=="rebirth" is asserted present. (The prose ORDERING rule is pinned by
    test_rebirth_handshake.py; here the harness proves the WRITES produce a consistent pair.)"""
    repo, rd = mid_run_fixture(fake_home)
    tip = _rev(repo, "drive/e2e-run")

    _rc, proof = run_conformance(repo, rd, "checkpoint")
    assert proof["clean"] is True

    # Coordinator write #1: the durable proof RECORD, tip-bound (D11/D17).
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": SID_OUT, "proof": proof})

    # Ordering on disk: the marker must be a valid, tip-matching proof record BEFORE we
    # assert the pause is set (the fail-closed handoff sequence).
    assert marker.is_file(), "marker must be written before the pause is set"
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    assert recorded["proof"]["tip"] == tip, "marker.proof.tip must equal the drive/<runId> tip"

    # Coordinator write #2: set the pause AFTER the marker is durable.
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = "rebirth"
    _atomic_write_json(rd / "state.json", st)

    st_after = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st_after["waiting"] == "rebirth", "the pause must be set once the marker is durable"


# --- Step 4: RECONSTRUCT — a fresh process resumes from the durable artifacts. - #
def test_step4_fresh_process_reconstructs_and_continues(fake_home):
    """The load-bearing E2E claim (AC1): after a simulated handoff, the durable artifacts
    (git refs + RUN_DIR marker + state.json) are SUFFICIENT for a fresh process to
    reconstruct and continue. The test, acting as the successor, performs the SCRIPTABLE
    resume acts and asserts the reconstructed run is continuable."""
    repo, rd = mid_run_fixture(fake_home)
    tip = _rev(repo, "drive/e2e-run")

    # --- simulate the outgoing handoff (step 3) -----------------------------
    _rc, proof = run_conformance(repo, rd, "checkpoint")
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": SID_OUT, "proof": proof})
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = "rebirth"
    _atomic_write_json(rd / "state.json", st)

    # BEFORE the rebind: the successor (incoming-sess) is NOT yet attributed the run, so
    # the Stop hook must ALLOW for it (the run is owned by outgoing-sess + waiting set).
    cp_before = run_hook(
        _hook_payload(fake_home, "e2e-run", UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    assert hook_decision(cp_before) is None, \
        "pre-rebind: the run is not yet attributed to the successor -> hook allows"

    # --- the SCRIPTABLE resume acts (drive.md I4/I7/D7/D17/D36) --------------
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    # (1) sessionId rebind FIRST (D7): re-attribute the run to the live session.
    st["sessionId"] = SID_IN
    # (2) re-arm: reset rebirth_pending (D36).
    st["rebirth_pending"] = False
    _atomic_write_json(rd / "state.json", st)

    # (3) validate + DELETE the single-use marker (D17, tip-match).
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    marker_valid = recorded.get("proof", {}).get("tip") == tip
    assert marker_valid, "the marker must validate (tip-match) before consumption"
    marker.unlink()  # single-use consumption — the resume's first act after rebind

    # (4) RE-PROVE both modes (the resume re-prove gate), THEN clear waiting.
    rc_c, obj_c = run_conformance(repo, rd, "checkpoint")
    rc_l, obj_l = run_conformance(repo, rd, "state-lint")
    assert rc_c == 0 and obj_c["clean"] is True, "re-prove checkpoint must still pass"
    assert rc_l == 0 and obj_l["clean"] is True, "re-prove state-lint must still pass"
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = None
    _atomic_write_json(rd / "state.json", st)

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


# --- Break RESUME (marker consumption): a stale checkpoint marker whose proof.tip
#     no longer matches the moved tip -> the marker does NOT validate, so a
#     re-attribution that trusted the marker would be refused. ------------------ #
def test_chainbreak_resume_severed_stale_marker_fails_validation(fake_home):
    """RESUME severed (the single-use marker stale-detection): the handoff writes a
    tip-bound marker, then work advances drive/<runId> (the tip MOVES). On resume the
    marker's `proof.tip` no longer equals the current tip, so the tip-match validation
    FAILS — the resume must re-prove from scratch, never replay the stale marker (D17)."""
    repo, rd = mid_run_fixture(fake_home)
    tip_then = _rev(repo, "drive/e2e-run")
    _rc, proof = run_conformance(repo, rd, "checkpoint")
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": SID_OUT, "proof": proof})
    assert proof["tip"] == tip_then

    # Work advances the feature branch AFTER the marker was written.
    _commit(repo, "more.sh", "echo more", "post-checkpoint work")
    tip_now = _rev(repo, "drive/e2e-run")
    assert tip_now != tip_then, "the tip must move so the marker goes stale"

    recorded = json.loads(marker.read_text(encoding="utf-8"))
    marker_valid = recorded.get("proof", {}).get("tip") == tip_now
    assert not marker_valid, \
        "RESUME severed: a stale-tip marker must FAIL tip-match validation (no replay, D17)"


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
