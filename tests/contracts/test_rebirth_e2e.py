"""EXECUTABLE end-to-end rebirth-cycle harness (slice 4.1, AC1 + AC2).

Runs the REAL executable pieces of the lever-2 rebirth chain (the Stop hook,
`--mode checkpoint`, `--mode state-lint`, git ref/marker tip checks) over hermetic
git + RUN_DIR fixtures, and asserts the durable artifacts they produce are SUFFICIENT
for a fresh process to reconstruct and re-prove the run. Each chain-break negative severs
one link and proves the harness reds on the severed link's real behaviour.

Honest scope (load-bearing, per D42): the /drive coordinator is PROMPT-DRIVEN prose, not a
program, so there is no executable `/drive` resume consumer to invoke — this harness does NOT
"run the coordinator." The resume ORCHESTRATION sequence (the I1 prove-then-pause ordering,
the handoff-block presentation) is coordinator prose pinned by `test_checkpoint_contract.py` /
`test_rebirth_handshake.py`; here the test acts as the successor and performs those scriptable
acts in Python, then proves the result with the SHIPPED executables. It asserts ONLY what is
executable/checkable.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from _helpers import REPO_ROOT, _git, _rev, _commit, _review, _codex

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
# The git/review helpers (_git/_rev/_commit/_review/_codex) are shared with
# test_checkpoint_contract.py via tests/_helpers.py. Mirrors test_checkpoint_contract.py::
# _base_run (a real `drive/<runId>` branch + a `phaseInt/<runId>/1` live ref descending it)
# and test_drive_stop_hook.py's fake-HOME layout: the RUN_DIR lives at
# <home>/.claude/harness-runs/<runId>/ so the Stop hook's glob finds its state.json.
# runId = basename(RUN_DIR) so featureBranch = drive/<runId>.
# --------------------------------------------------------------------------- #
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


DEFAULT_NONCE = "00112233445566778899aabbccddeeff"  # a fixed 32-hex nonce for the handoff fixtures


def _cid(marker_path):
    """CID = `shasum -a 256` of the marker CONTENT, first 12 hex (drive.md § Durable checkpoint
    contract). Mirrors `shasum -a 256 <marker> | cut -c1-12` over the exact file bytes in Python,
    so a different nonce yields a different CID (the per-handoff identity). This is the I1-side
    per-handoff derivation: the CID is DERIVED from the content (incl. nonce), never trusted blindly."""
    return hashlib.sha256(marker_path.read_bytes()).hexdigest()[:12]


def _resume_claim(rd, claimer_sid, pending_cid, tip):
    """Mirror the drive.md rebirth-gated atomic CLAIM + loser-disambiguation (§ Run setup &
    resume, sessionId-rebind bullet). GATED by the caller (`_resume_rebirth`) on
    `waiting == "rebirth"`. Returns one of:
      ("winner", claim_target)  — this racer won the atomic `os.replace`.
      ("loser",  winner_target) — a real winner of the CURRENT checkpoint exists (a content-valid
                                  `checkpoint-claimed-*-<pending_cid>.marker`, proof.tip==tip).
      ("fail-closed", None)     — the marker-content CID MISMATCHES `pending_cid` (a stale/forged
                                  CID), OR ENOENT on the source AND no current-CID winner (or no
                                  pendingCID = a forged rebirth) → fall through to the
                                  rebirth-continue fail-closed re-prove (stop:checkpoint-unprovable).

    The CID keying the claim-target is DERIVED FROM THE MARKER CONTENT (`_cid(marker)`), NOT trusted
    blindly from `pending_cid` — the winner path claims ONLY when `_cid(marker) == pending_cid`, binding
    the routing hint to the content (a real rebirth has them equal — I1 wrote both from the same
    content). A MISMATCH (`_cid(marker) != pending_cid` — a stale/forged CID, D23) returns
    ("fail-closed", None) WITHOUT claiming, GRACEFULLY mirroring the drive.md case (b) MISMATCH STOP
    (stop:checkpoint-unprovable) — both racers hit the same mismatch and fail closed → no double-drive.
    Detection is glob-by-CID + content (NOT the tip, NOT a name rebuilt from state.sessionId); a stale
    same-tip leftover of an OLDER CID is ignored. No liveness, no wall-clock (D9/D18)."""
    marker = rd / "checkpoint-complete.marker"
    try:
        content_cid = _cid(marker)  # DERIVE the CID from the marker content (raises if absent)
    except FileNotFoundError:
        content_cid = None
    if content_cid is not None and content_cid == pending_cid:
        # MATCH: the marker-content CID equals the routing hint → claim it (winner path).
        claim_target = rd / f"checkpoint-claimed-{claimer_sid}-{content_cid}.marker"
        try:
            os.replace(marker, claim_target)  # atomic; FileNotFoundError iff a twin already claimed
            return "winner", claim_target
        except FileNotFoundError:
            pass  # lost the atomic race between hashing and replacing → loser path
    elif content_cid is not None:
        # MISMATCH (`content_cid != pending_cid`): a stale/forged/wrong-handoff marker. Do NOT
        # claim — return fail-closed GRACEFULLY (mirrors the drive.md case (b) STOP outcome,
        # stop:checkpoint-unprovable). Both racers fail closed on the same mismatch → no
        # double-drive (D23/D32).
        return "fail-closed", None
    if not pending_cid:
        return "fail-closed", None  # forged rebirth: I1 sets pendingCID with waiting=rebirth
    for t in sorted(rd.glob(f"checkpoint-claimed-*-{pending_cid}.marker")):
        content = json.loads(t.read_text(encoding="utf-8"))
        if content.get("proof", {}).get("tip") == tip:
            return "loser", t
    return "fail-closed", None


def _resume_rebirth(rd, claimer_sid, tip):
    """The ONE shared, faithful mirror of the drive.md rebirth resume GATE + claim (§ Run setup &
    resume, sessionId-rebind bullet). Reads `waiting`/`pendingCID` from the ON-DISK `state.json`
    (like the real resume) and applies the D26 gate INTERNALLY — a non-rebirth resume NEVER claims:
      ("skipped-nonrebirth", None) when `state.waiting != "rebirth"` (no claim attempted),
      else the ("winner"/"loser"/"fail-closed") result of `_resume_claim` keyed on state.pendingCID.
    AC4(d) and the other rebirth-gate tests drive THROUGH this single mirror (never an inline gate),
    so dropping the `waiting=="rebirth"` guard or the CID condition reds them (spec-pin-mutation-verify)."""
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    if st.get("waiting") != "rebirth":
        return "skipped-nonrebirth", None  # D26: a non-rebirth resume never claims
    return _resume_claim(rd, claimer_sid, st.get("pendingCID"), tip)


def _auto_trigger_proceeds(rd, cid_n):
    """The shared, faithful mirror of the drive.md auto-trigger CID gate (§ Run setup & resume,
    parent prose): an auto-resume trigger carrying payload `cid_n` proceeds to reconciliation ONLY
    IF `state.pendingCID == cid_n` AND `state.waiting == "rebirth"` (read from the ON-DISK
    state.json); otherwise it EXITS as a clean no-op (writes NO state.json, never the sole resumer).
    Returns True (proceed) / False (no-op). AC5 drives THROUGH this mirror, not an inline boolean."""
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    return st.get("pendingCID") == cid_n and st.get("waiting") == "rebirth"


def _atomic_write_json(path, obj):
    """The tmp-file + atomic-rename discipline the coordinator uses for every state.json /
    marker write (drive.md I2a) — write `<path>.tmp.$$` then `os.replace` over `path`, so a
    reader never sees a torn file. The harness uses it for the scriptable handoff/resume
    writes so the on-disk artifact is exactly what the prose mandates."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def _perform_handoff(repo, rd, *, session_id=SID_OUT, nonce=DEFAULT_NONCE):
    """The INTEGRATED both-modes handoff gate (drive.md § I1 step 3/4/5), exactly as the real
    coordinator runs it: prove BOTH `--mode checkpoint` AND `--mode state-lint`, and ONLY
    when BOTH are clean write `checkpoint-complete.marker` (carrying the checkpoint proof + an
    additive per-handoff `nonce`, step 4) and set `state.waiting="rebirth"` AND
    `state.pendingCID = CID` in ONE write (step 5). If EITHER mode is non-clean the handoff
    fails closed — NO marker, NO waiting/pendingCID set — proving state-lint genuinely gates
    the handoff in the integrated chain (not just in a separate side assertion).

    Returns (handed_off: bool, checkpoint_proof: dict). `handed_off` is False when the
    both-modes gate refused; the caller asserts the on-disk consequence either way. The written
    `state.pendingCID` equals `_cid(marker)` — the per-handoff identity the resume claim keys on."""
    rc_c, proof_c = run_conformance(repo, rd, "checkpoint")
    rc_l, _proof_l = run_conformance(repo, rd, "state-lint")
    both_clean = (rc_c == 0 and proof_c.get("clean") is True
                  and rc_l == 0 and _proof_l.get("clean") is True)
    if not both_clean:
        return False, proof_c  # fail closed: neither write happens

    # Write #1 (step 4): the durable, tip-bound proof RECORD + the per-handoff nonce (tmp+mv).
    marker = rd / "checkpoint-complete.marker"
    _atomic_write_json(marker, {"at": "now", "sessionId": session_id, "nonce": nonce,
                                "proof": proof_c})
    cid = _cid(marker)
    # Write #2 (step 5): the pause + pendingCID, set AFTER the marker is durable (fail-closed
    # ordering). A real rebirth resume ALWAYS carries pendingCID set together with waiting=rebirth.
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = "rebirth"
    st["pendingCID"] = cid
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


def _hook_payload(transcript, *, session_id):
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
        _hook_payload(OVER_WATER, session_id=SID_OUT),
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
        _hook_payload(OVER_WATER, session_id=SID_OUT),
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
        _hook_payload(UNDER_WATER, session_id=SID_IN),
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

    # (3) `waiting` was cleared to None above (this test isolates the REBIND, not the
    #     rebirth-continue), so this is the NON-rebirth path: the claim is SKIPPED (D26 — a
    #     non-rebirth resume never claims), the marker is inert. The successor removes the inert
    #     leftover; validate its tip first (D17, tip-match).
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    marker_valid = recorded.get("proof", {}).get("tip") == tip
    assert marker_valid, "the marker must validate (tip-match) before consumption"
    marker.unlink()  # remove the inert leftover (no claim happened on the non-rebirth path)

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
        _hook_payload(UNDER_WATER, session_id=SID_IN),
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
        _hook_payload(OVER_WATER, session_id=SID_IN),
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
        _hook_payload(UNDER_WATER, session_id=SID_OUT),
        home=fake_home,
    )
    assert hook_decision(cp_out) is None, \
        "waiting==rebirth is truthy -> the hook lets the OUTGOING turn END (the handoff stop)"

    # (b) The successor takes the CONTINUE branch. Rebind (D7) + CLAIM the single-use marker
    #     (the rebirth-gated atomic os.replace, D26/D18), with `waiting` STILL "rebirth" (the
    #     resume re-proves BEFORE clearing). markerValid is re-sourced FROM THE CLAIM-TARGET the
    #     winner renamed to (D18), NOT the now-moved checkpoint-complete.marker.
    st["sessionId"] = SID_IN
    st["rebirth_pending"] = False
    _atomic_write_json(rd / "state.json", st)  # waiting STILL "rebirth" + pendingCID on disk
    # Drive the claim THROUGH the shared rebirth-gate mirror (reads waiting/pendingCID from disk).
    outcome, claim_target = _resume_rebirth(rd, SID_IN, tip)
    assert outcome == "winner", "the sole rebirth resumer must WIN the atomic claim (through the gate)"
    recorded = json.loads(claim_target.read_text(encoding="utf-8"))
    assert recorded.get("proof", {}).get("tip") == tip, \
        "markerValid (re-sourced from the claim-target) must tip-match"
    assert not marker.exists(), "the claim moved checkpoint-complete.marker away (single-use)"

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

    # The re-proven CONTINUE branch clears waiting=null AND pendingCID=null (auto-clear on a
    # passing proof — the mark of a continue), and as its FINAL act removes the claim-target
    # (single-use, D18).
    st_reprove["waiting"] = None
    st_reprove["pendingCID"] = None
    _atomic_write_json(rd / "state.json", st_reprove)
    claim_target.unlink()
    assert not claim_target.exists(), "the winner removes the claim-target on completion (single-use)"

    # The successor now blocks-to-continue: the pipeline AUTO-RESUMES (no human answer was
    # ever required — that is the rebirth-continue semantics).
    cp_in = run_hook(
        _hook_payload(UNDER_WATER, session_id=SID_IN),
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
        _hook_payload(OVER_WATER, session_id=SID_OUT),
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
        _hook_payload(UNDER_WATER, session_id=SID_OUT),
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
        _hook_payload(OVER_WATER, session_id=SID_IN),
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
        _hook_payload(OVER_WATER, session_id=SID_IN),
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
        _hook_payload(UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    assert hook_decision(cp) is None, \
        "un-rebound sessionId -> the successor does NOT own the run -> hook allows (cannot resume)"
    # Control: with the rebind applied, the SAME successor session DOES block — proving the
    # allow above is caused by the missing rebind, not by something else.
    st["sessionId"] = SID_IN
    _atomic_write_json(rd / "state.json", st)
    cp2 = run_hook(
        _hook_payload(UNDER_WATER, session_id=SID_IN),
        home=fake_home,
    )
    d2 = hook_decision(cp2)
    assert d2 is not None and d2["decision"] == "block", \
        "control: with the rebind, the successor owns the run and the hook blocks-to-continue"


# =========================================================================== #
# AC4 — the rebirth-gated CID-keyed CLAIM + loser write-discipline (EXECUTABLE, NO
# liveness/wall-clock). Each scenario drives the real `_resume_claim` mirror of the drive.md
# claim + loser-disambiguation over the real handoff artifacts.
# =========================================================================== #
def test_ac4_loser_writes_nothing_cid_keyed(fake_home):
    """AC4(a): the WINNER claims (os.replace → `checkpoint-claimed-<winnerSid>-<CID>.marker`);
    a concurrent LOSER globs `checkpoint-claimed-*-<state.pendingCID>.marker` + content
    (`proof.tip==tip`) → finds the winner's target → writes NO state.json (state.sessionId
    unchanged), NO double-drive. Detection is glob-by-CID + content, NEVER a name rebuilt from
    state.sessionId, NEVER the tip. Uniformly safe for a LIVE and a DEAD winner (the loser writes
    nothing either way — drive-stop-hook `_allow()`s a run-less session; no liveness branch)."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    handed_off, _ = _perform_handoff(repo, rd, session_id=SID_OUT)
    assert handed_off
    pending_cid = json.loads((rd / "state.json").read_text(encoding="utf-8"))["pendingCID"]

    # WINNER claims (session id "winner-sess") THROUGH the shared rebirth-gate mirror; it has NOT
    # yet rebound state.sessionId (the claimed-but-not-yet-rebound skew the round-2 BLOCKING covered).
    outcome_w, winner_target = _resume_rebirth(rd, "winner-sess", tip)
    assert outcome_w == "winner"
    assert winner_target.name == f"checkpoint-claimed-winner-sess-{pending_cid}.marker", \
        "the claim-target is named by the claimer's sid + the CID (advisory sid, CID-keyed detection)"

    # LOSER (a different session) attempts the SAME claim -> ENOENT on source -> loser path.
    sid_before = json.loads((rd / "state.json").read_text(encoding="utf-8"))["sessionId"]
    outcome_l, found = _resume_rebirth(rd, "loser-sess", tip)
    assert outcome_l == "loser", "the loser must detect the winner's current-CID claim-target"
    assert found == winner_target, "detection globs the CURRENT pendingCID + content (not the tip)"
    # The loser wrote NOTHING: state.sessionId is UNCHANGED, and no loser target was created.
    assert json.loads((rd / "state.json").read_text(encoding="utf-8"))["sessionId"] == sid_before, \
        "the loser must not clobber state.sessionId (writes NOTHING and exits)"
    assert not (rd / f"checkpoint-claimed-loser-sess-{pending_cid}.marker").exists()


def test_ac4_stale_older_cid_still_fails_closed(fake_home):
    """AC4(b): a crashed prior winner left a SAME-TIP claim-target under an OLDER, different CID,
    and the current `checkpoint-complete.marker` is absent (claimed away). The CURRENT pendingCID
    has NO matching claim-target -> the loser-disambiguation finds no current-CID winner -> falls
    closed to the rebirth-continue re-prove (stop:checkpoint-unprovable). The older-CID leftover is
    IGNORED (the glob is CID-keyed, not tip-keyed) and state.sessionId is untouched (STOP, never a
    silent sole-resumer write)."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    assert _perform_handoff(repo, rd)[0]
    current_cid = json.loads((rd / "state.json").read_text(encoding="utf-8"))["pendingCID"]

    (rd / "checkpoint-complete.marker").unlink()  # current marker claimed away (absent)
    old_cid = "0000deadbeef"
    assert old_cid != current_cid
    (rd / f"checkpoint-claimed-crashed-{old_cid}.marker").write_text(
        json.dumps({"at": "then", "sessionId": "crashed", "nonce": "ff" * 16,
                    "proof": {"tip": tip}}), encoding="utf-8")

    outcome, found = _resume_rebirth(rd, SID_IN, tip)  # state waiting=rebirth, pendingCID=current_cid
    assert outcome == "fail-closed", \
        "a stale OLDER-CID same-tip leftover must NOT satisfy the current-CID loser match"
    assert found is None
    assert (rd / f"checkpoint-claimed-crashed-{old_cid}.marker").exists(), \
        "the older-CID target is IGNORED (not consumed) — no false-loser exit"
    assert json.loads((rd / "state.json").read_text(encoding="utf-8"))["sessionId"] == SID_OUT


def test_ac4_forged_rebirth_no_pendingcid_fails_closed(fake_home):
    """AC4(c): a FORGED rebirth (waiting=="rebirth" set by a bug/sibling path without I1's
    prove→marker→wait, so NO pendingCID) with the marker absent -> the rebirth-gate mirror passes
    the D26 gate (waiting is rebirth) but the loser path has no pendingCID to match -> fail-closed
    (stop:checkpoint-unprovable), never a sole-resumer write."""
    repo, rd = mid_run_fixture(fake_home)
    tip = _rev(repo, "drive/e2e-run")
    # Forge the state on disk: waiting=="rebirth" but NO pendingCID, and NO marker.
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    st["waiting"] = "rebirth"
    st.pop("pendingCID", None)
    _atomic_write_json(rd / "state.json", st)
    outcome, found = _resume_rebirth(rd, SID_IN, tip)  # gate passes (rebirth), no pendingCID/marker
    assert outcome == "fail-closed" and found is None


def test_ac_p1_mismatched_cid_marker_fails_closed_no_claim(fake_home):
    """AC-P1 (finalize, D32): a rebirth resume whose `checkpoint-complete.marker` content CID
    MISMATCHES `state.pendingCID` (a stale/forged/wrong-handoff marker — the human-paste path
    carries no CID so it never sets a matching pendingCID) is REJECTED at the winner path:
    the shared `_resume_rebirth` mirror returns "fail-closed" WITHOUT claiming, and NO
    `checkpoint-claimed-*` target is created (mismatch => no claim => no double-drive). Models the
    drive.md case (b) MISMATCH production path (stop:checkpoint-unprovable), not a raised assert."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    assert _perform_handoff(repo, rd)[0]
    pending_cid = json.loads((rd / "state.json").read_text(encoding="utf-8"))["pendingCID"]

    # Forge the MARKER content (a different nonce) so its CID no longer equals the routing hint.
    forged = json.loads((rd / "checkpoint-complete.marker").read_text(encoding="utf-8"))
    forged["nonce"] = "ff" * 16
    _atomic_write_json(rd / "checkpoint-complete.marker", forged)
    assert _cid(rd / "checkpoint-complete.marker") != pending_cid, \
        "the forged marker's content CID must MISMATCH state.pendingCID"

    outcome, target = _resume_rebirth(rd, SID_IN, tip)  # state waiting=rebirth, pendingCID unchanged
    assert outcome == "fail-closed" and target is None, \
        "a content-CID mismatch must fail closed (no claim), mirroring the drive.md case (b) STOP"
    assert (rd / "checkpoint-complete.marker").exists(), "the mismatched marker was NOT claimed"
    assert not list(rd.glob("checkpoint-claimed-*.marker")), \
        "no claim-target created on the mismatch path => no double-drive"


def test_ac4_step45_crash_window_no_claim_no_clobber(fake_home):
    """AC4(d) (round-4 BLOCKING fix, D26): the I1 step-4→step-5 crash window — marker PRESENT but
    `waiting != "rebirth"` and no pendingCID. Driven THROUGH the shared `_resume_rebirth` mirror
    (NOT an inline gate), which applies the D26 gate internally: a non-rebirth resume returns
    "skipped-nonrebirth" — NO claim attempted, the marker stays inert, no claim-target is created,
    state.sessionId is not clobbered. Dropping the `waiting=="rebirth"` guard in the mirror would
    make it attempt the claim (outcome "winner") and RED this test."""
    repo, rd = mid_run_fixture(fake_home)
    proof = run_conformance(repo, rd, "checkpoint")[1]
    _atomic_write_json(rd / "checkpoint-complete.marker",
                       {"at": "now", "sessionId": SID_OUT, "nonce": DEFAULT_NONCE, "proof": proof})
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st.get("waiting") != "rebirth" and st.get("pendingCID") is None, \
        "the crash window: marker present, waiting not rebirth, no pendingCID"

    outcome, target = _resume_rebirth(rd, SID_IN, _rev(repo, "drive/e2e-run"))
    assert outcome == "skipped-nonrebirth" and target is None, \
        "the D26 gate must SKIP the claim when waiting != rebirth (no claim attempted)"
    assert (rd / "checkpoint-complete.marker").exists(), "the leftover marker stays inert (not renamed)"
    assert not list(rd.glob("checkpoint-claimed-*.marker")), "no claim-target created on the crash-window path"
    assert json.loads((rd / "state.json").read_text(encoding="utf-8"))["sessionId"] == SID_OUT, "no clobber"


def test_ac4_manual_recovery_restore_wins(fake_home):
    """AC4(e): after a CURRENT winner crashed post-claim (its target survives, run not driven),
    the human recovers manually — `mv` the current-CID claim-target back to
    checkpoint-complete.marker — and a re-paste WINS the claim again (os.replace succeeds). The
    run is never stranded, even after auto-resume spent its one attempt."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    assert _perform_handoff(repo, rd)[0]
    cid = json.loads((rd / "state.json").read_text(encoding="utf-8"))["pendingCID"]

    outcome_w, winner_target = _resume_rebirth(rd, "crashed-winner", tip)
    assert outcome_w == "winner"
    os.replace(winner_target, rd / "checkpoint-complete.marker")  # manual restore
    outcome_r, recovered_target = _resume_rebirth(rd, "recovery-sess", tip)
    assert outcome_r == "winner", "after manual restore, the re-paste WINS the claim (never stranded)"
    assert recovered_target.exists()


# =========================================================================== #
# AC5 — the auto-trigger CID-conditional no-op AFTER a completed+cleaned resume (no clobber).
# =========================================================================== #
def test_ac5_auto_trigger_noop_after_resume_cleanup(fake_home):
    """AC5: after the WINNER completes the rebirth resume + cleans up (removes its claim-target,
    clears waiting=null AND pendingCID=null), a LATE auto-trigger carrying the now-STALE `CID_N`
    hits the § Run setup & resume CID gate `state.pendingCID == CID_N AND waiting == "rebirth"`.
    Both are cleared, so the gate is FALSE -> the trigger EXITS immediately, writing NO
    state.sessionId (no clobber, never the sole resumer)."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    assert _perform_handoff(repo, rd)[0]
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    stale_cid_n = st["pendingCID"]  # the auto-trigger was scheduled carrying THIS CID

    # BEFORE cleanup: the auto-trigger CID gate PASSES (control — proving the mirror is not a
    # constant-False), driven THROUGH the shared `_auto_trigger_proceeds` mirror.
    assert _auto_trigger_proceeds(rd, stale_cid_n) is True, \
        "control: the auto-trigger gate passes while pendingCID==CID_N AND waiting==rebirth"

    # The winner resumes + completes THROUGH the shared rebirth-gate mirror: claim, drive, then the
    # CONTINUE-branch final acts — clear waiting+pendingCID and remove the claim-target.
    outcome, claim_target = _resume_rebirth(rd, SID_IN, tip)
    assert outcome == "winner"
    st["sessionId"] = SID_IN
    st["waiting"] = None
    st["pendingCID"] = None
    _atomic_write_json(rd / "state.json", st)
    claim_target.unlink()

    # A LATE auto-trigger fires carrying CID_N == stale_cid_n. Drive it THROUGH the shared mirror
    # (NOT an inline boolean) — after cleanup pendingCID/waiting are cleared, so the gate is FALSE.
    assert _auto_trigger_proceeds(rd, stale_cid_n) is False, \
        "the stale auto-trigger must NOT pass the CID gate (pendingCID + waiting cleared)"
    # Also proven through the resume-claim mirror: even the sessionId-rebind claim gate skips
    # (waiting cleared) — a non-rebirth resume never claims.
    assert _resume_rebirth(rd, SID_IN, tip) == ("skipped-nonrebirth", None)
    # Gate false -> the trigger EXITS writing NO state.json -> state.sessionId unchanged.
    assert json.loads((rd / "state.json").read_text(encoding="utf-8"))["sessionId"] == SID_IN, "no clobber"


def test_ac5_auto_trigger_noop_on_stale_cid_during_subsequent_rebirth(fake_home):
    """AC5 (CID clause, mutation cover): a STALE auto-trigger from rebirth N arriving DURING a
    SUBSEQUENT rebirth. Here `waiting == "rebirth"` is TRUE (a later rebirth is in flight) but
    `state.pendingCID` has ADVANCED to the new rebirth's CID, while the late trigger still carries
    the OLD `CID_N`. The § Run setup & resume gate `pendingCID == CID_N AND waiting == "rebirth"`
    must therefore be a NO-OP — ONLY the `pendingCID == CID_N` clause can reject it (waiting is
    "rebirth"), so this ISOLATES the CID clause the both-true/both-false AC5 test cannot reach.
    MUTATION-VERIFIED: dropping `pendingCID == cid_n` from `_auto_trigger_proceeds` reds the stale
    assertion below (a stale trigger would then reconcile the WRONG checkpoint)."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    assert _perform_handoff(repo, rd)[0]
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    stale_cid_n = st["pendingCID"]  # rebirth N's CID — the late auto-trigger still carries THIS

    # A SUBSEQUENT rebirth re-checkpointed: `waiting` stays "rebirth", but `pendingCID` ADVANCES to
    # a new, DISTINCT CID (the gate reads pendingCID as an opaque token — same on-disk shape the
    # real subsequent handoff would leave; consistent with the cleanup-write style above).
    current_cid = "deadbeefcafe0000deadbeefcafe0000"
    assert current_cid != stale_cid_n
    st["pendingCID"] = current_cid
    st["waiting"] = "rebirth"
    _atomic_write_json(rd / "state.json", st)

    # Control: the CURRENT rebirth's trigger PASSES (waiting==rebirth AND pendingCID==current_cid) —
    # proving the mirror is not constant-False and `waiting=="rebirth"` genuinely holds here.
    assert _auto_trigger_proceeds(rd, current_cid) is True, \
        "control: the current rebirth's trigger passes the CID gate"
    # Load-bearing: the STALE CID_N trigger is a NO-OP. `waiting=="rebirth"` is TRUE, so ONLY the
    # `pendingCID == CID_N` clause can reject it — dropping that clause REDS this assertion.
    assert _auto_trigger_proceeds(rd, stale_cid_n) is False, \
        "a stale auto-trigger (old CID_N) must NOT reconcile the SUBSEQUENT rebirth's checkpoint"


# =========================================================================== #
# AC15 — CID per-handoff uniqueness via the nonce (shasum path + shasum-absent fallback).
# =========================================================================== #
def test_ac15_cid_per_handoff_uniqueness_via_nonce(tmp_path):
    """AC15: two checkpoint-complete.marker CONTENTS differing ONLY in their nonce yield DIFFERENT
    CIDs via `_cid()` — the SAME I1-side per-handoff derivation the claim uses (hash of the whole
    marker content incl. nonce, NOT a blindly-trusted state.pendingCID). The nonce is additive: the
    resume reader picks `proof.tip` only. AND the loser's glob correctly IGNORES a same-tip
    claim-target under a DIFFERENT (older) CID — the stale/forged-CID hole D23 hardened against."""
    base_proof = {"tip": "a" * 40, "clean": True, "mode": "checkpoint"}
    m1 = tmp_path / "m1.marker"
    m2 = tmp_path / "m2.marker"
    m1.write_text(json.dumps({"at": "now", "sessionId": "s",
                              "nonce": "1111111111111111aaaaaaaaaaaaaaaa", "proof": base_proof}))
    m2.write_text(json.dumps({"at": "now", "sessionId": "s",
                              "nonce": "2222222222222222bbbbbbbbbbbbbbbb", "proof": base_proof}))
    cid1, cid2 = _cid(m1), _cid(m2)
    assert cid1 != cid2, (
        "markers differing ONLY in nonce must yield DIFFERENT _cid() (the per-handoff derivation) — "
        "so two same-tip/same-second checkpoints never collide (D23)"
    )
    # shasum-absent fallback (drive.md: CID = nonce[:12]) — distinct because the nonces differ in [:12].
    assert "1111111111111111aaaaaaaaaaaaaaaa"[:12] != "2222222222222222bbbbbbbbbbbbbbbb"[:12], \
        "the shasum-absent nonce[:12] fallback CID must also differ across handoffs"
    # additive: the reader picks proof.tip only — both markers carry the SAME tip.
    assert json.loads(m1.read_text())["proof"]["tip"] == json.loads(m2.read_text())["proof"]["tip"] == "a" * 40

    # The loser glob IGNORES a same-tip claim-target under a DIFFERENT (older) CID: a resume whose
    # CURRENT pendingCID is cid2 (marker absent) must NOT match a cid1-keyed target with the same tip.
    rd = tmp_path / "rd"
    rd.mkdir()
    (rd / f"checkpoint-claimed-old-{cid1}.marker").write_text(
        json.dumps({"proof": {"tip": "a" * 40}}))  # older CID, SAME tip
    outcome, found = _resume_claim(rd, "in", cid2, "a" * 40)
    assert outcome == "fail-closed" and found is None, \
        "a same-tip claim-target under a DIFFERENT CID must be IGNORED (CID-keyed glob, D23)"
    # control: globbing for the ACTUAL cid1 DOES find it (so the ignore above is the CID-keying,
    # not a broken glob).
    outcome2, found2 = _resume_claim(rd, "in", cid1, "a" * 40)
    assert outcome2 == "loser" and found2 == rd / f"checkpoint-claimed-old-{cid1}.marker"


def test_ac15_claim_cid_is_derived_from_marker_content(fake_home):
    """AC15/P1-3 (codex MAJOR): the winner's claim CID is DERIVED from the marker CONTENT
    (`_cid(marker)`), bound to `state.pendingCID` — NOT trusted blindly. A resume whose pendingCID
    routing hint MISMATCHES the marker content (a stale/forged CID, D23) is REJECTED at the winner
    path; and the honest content-derived hint names the claim-target by `_cid(marker)`. A regression
    to "trust state.pendingCID blindly" (drop the content derivation) reds this."""
    repo, rd = mid_run_fixture(fake_home, rebirth_pending=True)
    tip = _rev(repo, "drive/e2e-run")
    assert _perform_handoff(repo, rd)[0]
    content_cid = _cid(rd / "checkpoint-complete.marker")
    st = json.loads((rd / "state.json").read_text(encoding="utf-8"))
    assert st["pendingCID"] == content_cid, "a real rebirth: the routing hint EQUALS the content CID"

    # A FORGED/stale pendingCID (NOT derived from the marker content) is REJECTED by the binding —
    # GRACEFULLY fail-closed (no claim), mirroring the drive.md case (b) MISMATCH STOP.
    st["pendingCID"] = "deadbeefdead"
    _atomic_write_json(rd / "state.json", st)
    outcome_m, target_m = _resume_rebirth(rd, SID_IN, tip)  # CID-from-content binding rejects mismatch
    assert outcome_m == "fail-closed" and target_m is None, \
        "a pendingCID that mismatches the marker content must fail closed (no claim)"
    assert (rd / "checkpoint-complete.marker").exists(), "the marker was NOT claimed under a forged CID"

    # With the honest content-derived hint, the claim-target is named by _cid(marker).
    st["pendingCID"] = content_cid
    _atomic_write_json(rd / "state.json", st)
    outcome, target = _resume_rebirth(rd, SID_IN, tip)
    assert outcome == "winner"
    assert target.name == f"checkpoint-claimed-{SID_IN}-{content_cid}.marker", \
        "the claim-target CID is DERIVED from the marker content, not a blindly-trusted hint"
