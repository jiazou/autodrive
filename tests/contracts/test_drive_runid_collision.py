"""Contract pin for the fresh-run runId collision claim in drive.md.

`runId = <branch>-<timestamp>` is minted at second resolution, so it is not unique by
construction: two fresh runs with the same slug in the same second collide. A non-atomic
"does state.json exist?" check does NOT close this — `state.json` is written LAST (after
the `drive/<runId>` branch), so it misses both the crash-window (a run that died before
its first state.json write) and the same-second concurrency race. The real fix claims the
id ATOMICALLY: plain `mkdir` (not `mkdir -p`) of the leaf RUN_DIR as the first setup step
— an atomic test-and-create that fails on EEXIST — and disambiguates the runId on failure.

These pins assert that SAFETY PROPERTY (not just that the word "collision" appears), and
are SECTION-BOUNDED to the run-setup region (the `## Run setup & resume` header up to the
first `- **Resume:**` bullet) so a token recurring in the resume/recovery prose cannot
pass them vacuously. Verified RED by reverting to the non-atomic state.json-check wording.
"""
import re

from _helpers import REPO_ROOT

DRIVE_MD = REPO_ROOT / ".claude" / "commands" / "drive.md"


def _setup_region():
    """The run-setup prose where the fresh-run claim lives: from the
    `## Run setup & resume` header up to the first `- **Resume:**` bullet."""
    text = DRIVE_MD.read_text(encoding="utf-8")
    start = text.index("## Run setup & resume")
    try:
        end = text.index("- **Resume:**", start)
    except ValueError:  # bullet renamed — fail loud with a clear message, not a stack trace
        raise AssertionError("run-setup region anchor '- **Resume:**' not found in drive.md")
    region = text[start:end]
    return re.sub(r"\s+", " ", region)  # collapse wrap so phrases match across line breaks


def test_claim_is_atomic_plain_mkdir_not_mkdir_p():
    """The id is claimed with a PLAIN `mkdir` (atomic test-and-create), explicitly NOT
    `mkdir -p` — the property that closes the same-second concurrency race. A non-atomic
    check-then-create cannot satisfy this."""
    region = _setup_region()
    assert "atomic" in region.lower(), "the claim must be described as atomic"
    # plain `mkdir "$RUN_DIR"` is required, and `mkdir -p` of the LEAF is forbidden
    assert re.search(r"plain\s+`?mkdir", region), "must claim the leaf with a plain `mkdir`"
    assert re.search(r"NOT\s+`?mkdir -p`?", region), (
        "must forbid `mkdir -p` for the leaf claim (it is not an exclusive create)"
    )


def test_claim_precedes_branch_and_state_json():
    """The claim must PRECEDE both `featureBranch` creation and the first state.json write
    — pinning the full ordering, not just state.json. A claim that ran after branch
    creation would reopen the orphan-ref window, so `featureBranch` must be named here."""
    region = _setup_region()
    assert re.search(r"precede[s]?\b", region), "the claim must be stated to precede setup"
    assert "featureBranch" in region, "ordering must name featureBranch (orphan-ref window)"
    assert "state.json" in region, "ordering must name the first state.json write"


def test_failed_claim_disambiguates_only_on_eexist_else_stops():
    """A failed claim must disambiguate ONLY on the dir-already-exists error (EEXIST); any
    OTHER mkdir error (permissions, bad path) must STOP, not spin or keep mutating the id."""
    region = _setup_region()
    assert "disambiguator" in region.lower() or "disambiguate" in region.lower(), (
        "a colliding claim must disambiguate the runId"
    )
    assert "EEXIST" in region, "retry must be scoped to the already-exists error (EEXIST)"
    assert re.search(r"other\b.{0,40}\berror", region, re.I) and "STOP" in region, (
        "any non-EEXIST mkdir error must STOP, not retry"
    )
