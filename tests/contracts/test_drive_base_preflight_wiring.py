"""Contract pins — the ship-stage base-divergence preflight wiring.

The diverged-base trap: a /drive run branches from `baseRef` at a frozen `baseSha`; if
`baseRef` advances mid-run and both sides append to the append-only `.harness` ledgers, the
ship's ledger promotion lands on the STALE base copy and the PR CONFLICTS at merge — silently,
unless the harness CHECKS for it. The durable fix is an EXECUTABLE detector
(`bin/drive-base-preflight.sh`) that drive-ship.md runs BEFORE the ledger promotion and acts on,
NOT a behavioral memory someone must recall. These pins fail loudly if that wiring is removed:

  (a) the detector script exists and is executable;
  (b) drive-ship.md invokes it and dispatches on every `.recommendation` value
      (none/ship-as-is, manual-merge → STOP, auto-rebase → the fail-closed resolution);
  (c) the auto-rebase path carries its load-bearing gates — the merged-tree semantic suite, the
      content-preservation verify, and the sanctioned finalize `reviewed-sha` re-bind;
  (d) the detector's SHIP_LEDGER_ALLOWLIST does not drift from bin/drive-conformance.sh's.
"""

import os
import re

import pytest


@pytest.fixture
def ship_md(repo_root):
    p = repo_root / ".claude" / "commands" / "drive-ship.md"
    assert p.is_file(), f"drive-ship.md missing at {p}"
    return p.read_text(encoding="utf-8")


def test_detector_exists_and_executable(repo_root):
    pf = repo_root / "bin" / "drive-base-preflight.sh"
    assert pf.is_file(), f"bin/drive-base-preflight.sh missing at {pf}"
    assert os.access(pf, os.X_OK), "bin/drive-base-preflight.sh must be executable (gates run it as rc≠0 otherwise)"


def test_ship_md_invokes_the_detector(ship_md):
    assert "bin/drive-base-preflight.sh" in ship_md, (
        "drive-ship.md must invoke bin/drive-base-preflight.sh before the ledger promotion"
    )
    # It must run BEFORE the ledger-promotion append (so an auto-rebase lands promotion on the
    # fresh base). The preflight bullet precedes the 'Promote the run ledgers' bullet.
    i_pf = ship_md.find("bin/drive-base-preflight.sh")
    i_promote = ship_md.find("Promote the run ledgers")
    assert 0 <= i_pf < i_promote, "the base-freshness preflight must precede the ledger promotion"


def test_ship_md_dispatches_on_every_recommendation(ship_md):
    for rec in ("ship-as-is", "manual-merge", "auto-rebase"):
        assert rec in ship_md, f"drive-ship.md must handle the '{rec}' recommendation"
    # manual-merge (a non-ledger semantic conflict) must STOP, never auto-rewrite.
    assert "stop:base-diverged-conflict" in ship_md, (
        "a non-ledger conflict (manual-merge) must STOP fail-closed, not auto-resolve"
    )


def test_auto_rebase_carries_its_fail_closed_gates(ship_md):
    # 1. semantic gate: a ledger-only TEXT conflict is not proof of semantic safety → run the
    #    FULL suite on the materialized merged tree; red → STOP.
    assert "bin/run-tests.sh" in ship_md
    assert "stop:base-diverged-suite-red" in ship_md, "the merged-tree suite must gate the auto-rebase"
    # 2. content-preservation verify + abort-STOP.
    assert "content-preservation" in ship_md.lower() or "byte-identical" in ship_md.lower()
    assert "stop:base-rebase-not-clean" in ship_md
    # 3. the sanctioned finalize reviewed-sha re-bind (NOT a forge of the verdict).
    assert re.search(r"re-?bind", ship_md, re.IGNORECASE), "the finalize reviewed-sha re-bind must be described"
    assert "reviewed-sha" in ship_md
    assert "Verdict" in ship_md, "the re-bind must NOT touch the Verdict line — state that"
    # 4. re-confirm clean after the rebase.
    assert "stop:base-rebase-unresolved" in ship_md


def test_detector_predicts_the_pending_ledger_append(repo_root):
    """The P1 the merge-tree-only detector missed: at PREFLIGHT time (a fresh ship) featureBranch
    has NOT yet appended the run's ledger entries, so merge-tree on the pre-append tree sees the
    ledger as one-sided/clean and would wrongly say ship-as-is. The detector MUST additionally
    predict the pending promotion append from `git diff <baseSha>..<currentBase>` ∩ the ledgers
    the run will append to. Guard that logic so a revert to merge-tree-only reds here."""
    pf = (repo_root / "bin" / "drive-base-preflight.sh").read_text(encoding="utf-8")
    assert "pendingLedgerConflict" in pf, "the detector must predict the pending ledger-append conflict"
    assert "git diff --name-only" in pf, "the pending-append prediction diffs baseSha..currentBase"
    assert "finalize-todo.md" in pf, "TODO.md counts as a pending ledger only when finalize produced findings"
    # drive-ship.md must explain that auto-rebase can fire on a 'clean' current-tree merge.
    ship = (repo_root / ".claude" / "commands" / "drive-ship.md").read_text(encoding="utf-8")
    assert "pending" in ship.lower() and "mergeClean" in ship, (
        "drive-ship.md must note auto-rebase fires on the PENDING append even when mergeClean=true"
    )


def test_degraded_fetch_check_is_surfaced(ship_md):
    """A failed base fetch leaves the detector comparing against a possibly-stale
    `origin/<baseRef>` (the codex-found bypass) — drive-ship.md must surface `fetchOk:false`
    at Gate B regardless of the recommendation, not silently trust a clean result."""
    assert "fetchOk" in ship_md, "drive-ship.md must handle the detector's fetchOk flag"
    low = ship_md.lower()
    assert "could not fetch" in low or "possibly-stale" in low or "possibly stale" in low, (
        "the degraded (failed-fetch) check must be surfaced at Gate B"
    )


def test_ledger_allowlist_does_not_drift(repo_root):
    """The detector's LEDGER_ALLOWLIST must match bin/drive-conformance.sh's
    SHIP_LEDGER_ALLOWLIST (the append-only ledger files the single ship commit may touch).
    A drift would misclassify a conflict.

    SITE-PRECISE extraction (D-28/D-41): each capture is anchored to ITS OWN array
    DECLARATION — only the `SHIP_LEDGER_ALLOWLIST=(...)` assignment in drive-conformance.sh
    and only the `LEDGER_ALLOWLIST=(...)` assignment in drive-base-preflight.sh. A
    whole-file capture would ALSO match the ledger path inside the preflight's
    `pendingLedgers` conditional, so a one-array drift could still extract all four paths
    and stay green (default-masked vacuity). Executed probes: drift either array alone ->
    this reds; edit only the `pendingLedgers` conditional -> neither drift pin fires (that
    surface is the behavioral bash pair, check (12))."""
    def declared_paths(path, decl):
        text = path.read_text(encoding="utf-8")
        m = re.search(rf"^{decl}=\((.*?)\)\s*$", text, re.MULTILINE)
        assert m, f"{path.name}: `{decl}=(...)` declaration not found"
        return sorted(re.findall(r'"([^"]+)"', m.group(1)))

    pf = declared_paths(repo_root / "bin" / "drive-base-preflight.sh", "LEDGER_ALLOWLIST")
    cf = declared_paths(repo_root / "bin" / "drive-conformance.sh", "SHIP_LEDGER_ALLOWLIST")
    expected = sorted(
        [".harness/decisions.md", ".harness/followups.md", "TODO.md",
         ".harness/codex-refutations.md"]
    )
    assert pf == cf == expected, f"ledger allowlist drift: preflight={pf} conformance={cf}"
