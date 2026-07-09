"""Contract pins for the R2/R4 codex-dispatch work (slice 1.1):

  * the closed helper contract in `bin/drive-codex.sh` (tokens, sandbox rungs, effort mechanism);
  * the codex-FIRST reorder position in all three review specs (AC1);
  * the single outcome tier TABLE + its cross-references (AC3/AC4);
  * the `CODEX_KILLED_TIMEOUT` tier at EVERY enumerated consumer (AC8);
  * the enrichment clause (AC6), `--scope-class` per spec + helper `--sandbox` (AC7);
  * the broken-helper STOP (AC-P1), snapshot→quarantine→dispatch ordering (AC-P2), post-OK
    completion contract (AC-P3), atomic post-process write (AC-P4), and the branch-specific
    re-dispatch⇒full-effort conditional (AC-H12c).

UNIFORM anti-vacuity discipline (§I): every pin is a BOUNDED slice anchored to a STABLE, UNIQUE
anchor — the actual `bin/drive-codex.sh … --mode dispatch` line, a bounded degradation-paragraph
slice, or a per-bullet/subsection slice — NEVER a whole-`## Step`/`###` section grep (the tier
table + prose recur those tokens). Each carries an explicit MUTATION-VERIFY in its docstring.
"""
import re

from _helpers import REPO_ROOT

CMDS = REPO_ROOT / ".claude" / "commands"
BIN = REPO_ROOT / "bin"
DOCS = REPO_ROOT / "docs"

REVIEW = CMDS / "drive-review.md"
HARDEN = CMDS / "drive-harden.md"
FINALIZE = CMDS / "drive-finalize.md"
DRIVE = CMDS / "drive.md"
RETRO = CMDS / "drive-retro.md"
SHIP = CMDS / "drive-ship.md"
ENFORCE = DOCS / "drive-enforcement.md"
CLAUDE = REPO_ROOT / "CLAUDE.md"
README = REPO_ROOT / "README.md"
HELPER = BIN / "drive-codex.sh"

TOKENS = ("OK", "CODEX_KILLED_TIMEOUT", "CODEX_UNAVAILABLE", "HELPER_ERROR")
DISPATCH_RE = r"bin/drive-codex\.sh.*--mode\s+dispatch"
BEGIN_SCOPE = "----- BEGIN SUBAGENT SCOPE -----"


def _text(p):
    return p.read_text(encoding="utf-8")


def _lines(p):
    return _text(p).splitlines()


def _idx(lines, pattern):
    """First line index whose text matches the regex `pattern`, or None."""
    return next((i for i, ln in enumerate(lines) if re.search(pattern, ln)), None)


def _idx_sub(lines, *subs):
    """First line index containing ALL of the literal substrings `subs`, or None."""
    return next((i for i, ln in enumerate(lines) if all(s in ln for s in subs)), None)


def _section(lines, header_re, *, stop_re=r"^#{1,4}\s"):
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section /{header_re}/ not found"
    end = next((j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])), len(lines))
    return "\n".join(lines[start:end])


def _slice(lines, start_re, stop_re, *, inclusive=True):
    start = next((i for i, ln in enumerate(lines) if re.search(start_re, ln)), None)
    assert start is not None, f"slice start /{start_re}/ not found"
    end = next((j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])), None)
    assert end is not None, f"slice stop /{stop_re}/ not found after /{start_re}/"
    return "\n".join(lines[start : end + 1 if inclusive else end])


# =========================================================================== #
# Helper closed contract — bin/drive-codex.sh
# =========================================================================== #
def test_helper_declares_the_closed_token_set():
    """The supervisor names the EXACTLY-four closed outcome tokens in its Usage/contract
    header. Mutation-verify: drop CODEX_KILLED_TIMEOUT from the header → reds."""
    txt = _text(HELPER)
    header = txt.split("set -m", 1)[0]  # the leading comment block, before any launch logic
    for tok in TOKENS:
        assert tok in header, f"bin/drive-codex.sh contract header must name the token {tok}"
    assert "OK | CODEX_KILLED_TIMEOUT | CODEX_UNAVAILABLE | HELPER_ERROR" in header, (
        "the closed token set must be documented as a single ordered contract line"
    )


def test_helper_sandbox_rungs_match_spike_evidence():
    """AC13: the helper's rung constants are the RESOLVED spike fail-branch values —
    SANDBOX_RUNG_DESIGN=read-only, SANDBOX_RUNG_CODE=workspace-write. Mutation-verify: flip
    a constant → reds (and it would diverge from sandbox-spike-evidence.md)."""
    txt = _text(HELPER)
    assert re.search(r'SANDBOX_RUNG_DESIGN="read-only"', txt), "design scope rung must be read-only"
    assert re.search(r'SANDBOX_RUNG_CODE="workspace-write"', txt), "code scope rung must be workspace-write"


def test_helper_composes_sandbox_and_effort_flags():
    """AC7 (helper half) + §F: the single codex-exec construction composes `--sandbox <rung>` and
    the effort down-tier is `-c model_reasoning_effort=<low>` (codex has no first-class effort
    flag). Mutation-verify: delete the `--sandbox` cmd += line → reds."""
    txt = _text(HELPER)
    assert re.search(r'cmd\+=\(--sandbox "\$RUNG"\)', txt), (
        "the helper must compose `--sandbox \"$RUNG\"` on its ONE codex exec construction"
    )
    assert re.search(r'model_reasoning_effort=\$EFFORT_TIER_LOW', txt), (
        "the effort down-tier must be `-c model_reasoning_effort=<low>` (§F mechanism)"
    )


# =========================================================================== #
# AC1 — codex dispatch precedes the FIRST (Step-1) reviewer subagent scope
# =========================================================================== #
def test_codex_first_position_drive_review():
    """AC1: in drive-review the `bin/drive-codex.sh --mode dispatch` block (Step 1) precedes the
    reviewer `BEGIN SUBAGENT SCOPE` (Step 2). Mutation-verify: swap the blocks back → reds."""
    lines = _lines(REVIEW)
    d = _idx(lines, DISPATCH_RE)
    b = _idx(lines, re.escape(BEGIN_SCOPE))
    assert d is not None and b is not None, "both the dispatch line and a reviewer scope must exist"
    assert d < b, "codex dispatch must precede the FIRST reviewer BEGIN SUBAGENT SCOPE"


def test_codex_first_position_harden_and_finalize():
    """AC1: harden + finalize — WITHIN `## Step 1`, the dispatch precedes the Step-1 reviewer
    scope (section-scoped so the Step-3 fixer BEGIN SCOPE can't satisfy it). Mutation-verify:
    swap → reds."""
    for md in (HARDEN, FINALIZE):
        step1 = _section(_lines(md), r"^##\s+Step 1\b").splitlines()
        d = _idx(step1, DISPATCH_RE)
        b = _idx(step1, re.escape(BEGIN_SCOPE))
        assert d is not None, f"{md.name}: Step 1 must contain the dispatch"
        assert b is not None, f"{md.name}: Step 1 must contain the reviewer BEGIN SCOPE"
        assert d < b, f"{md.name}: codex dispatch must precede the Step-1 reviewer scope"


# =========================================================================== #
# AC2 — each spec invokes the helper in dispatch mode and post-processes ONLY on OK
# =========================================================================== #
def test_each_spec_invokes_dispatch_and_post_process_on_ok():
    """AC2: each block invokes `bin/drive-codex.sh --mode dispatch` and post-processes ONLY on
    `OK`. Mutation-verify: drop the ONLY-on-OK clause → reds."""
    for md in (REVIEW, HARDEN, FINALIZE):
        lines = _lines(md)
        assert _idx(lines, DISPATCH_RE) is not None, f"{md.name}: must invoke --mode dispatch"
        assert re.search(r"post-process.*ONLY on `OK`|ONLY on `OK`", _text(md)), (
            f"{md.name}: must post-process ONLY on OK"
        )


# =========================================================================== #
# AC3 / AC4 — the single tier TABLE (drive-review) + REFERENCE in harden/finalize
# =========================================================================== #
def test_tier_table_outcome_column_is_token_only():
    """AC3: drive-review's tier TABLE outcome column is TOKEN-ONLY — the four closed tokens, no
    out-of-band rc126/rc127 cell. BOUNDED to the table ROWS (from the header row to the first
    non-`|` line). Mutation-verify: add an `rc126,127` cell to the outcome column → reds."""
    lines = _lines(REVIEW)
    start = _idx(lines, r"^\| helper outcome \| marker 1st line \|")
    assert start is not None, "the tier TABLE header row must exist in drive-review.md"
    rows = []
    for ln in lines[start:]:
        if not ln.lstrip().startswith("|"):
            break
        rows.append(ln)
    table = "\n".join(rows)
    for tok in TOKENS:
        assert tok in table, f"the tier table must carry the {tok} outcome row"
    assert "rc126" not in table and "rc127" not in table, (
        "the outcome column is token-only — no out-of-band rc126/rc127 cell (AC3)"
    )


def test_harden_and_finalize_reference_the_tier_table():
    """AC4: harden + finalize REFERENCE drive-review's tier TABLE (prose), not host a second
    copy. Mutation-verify: drop the `outcome tier TABLE` reference → reds."""
    for md in (HARDEN, FINALIZE):
        assert "outcome tier TABLE" in _text(md), (
            f"{md.name} must REFERENCE drive-review's outcome tier TABLE"
        )
    # and there is only ONE authoritative table (its header row lives in drive-review only).
    assert _idx(_lines(HARDEN), r"^\| helper outcome \|") is None, "harden must NOT host the table"
    assert _idx(_lines(FINALIZE), r"^\| helper outcome \|") is None, "finalize must NOT host the table"


# =========================================================================== #
# AC6 — enrichment clause (prior rounds only) in all three specs
# =========================================================================== #
def test_enrichment_clause_present_in_all_three_specs():
    """AC6: each spec carries the codex-independence clause. Mutation-verify: delete it → reds."""
    for md in (REVIEW, HARDEN, FINALIZE):
        blob = re.sub(r"\s+", " ", _text(md))  # the clause wraps across lines in harden/finalize
        assert "prompt enrichment may reference PRIOR rounds only" in blob, (
            f"{md.name} must carry the 'prior rounds only' enrichment clause"
        )


# =========================================================================== #
# AC7 (spec half) — each spec passes --scope-class
# =========================================================================== #
def test_scope_class_passed_per_spec():
    """AC7: drive-review passes `--scope-class <design|slice|phase>`, harden `--scope-class phase`,
    finalize `--scope-class finalize`. Mutation-verify: drop `--scope-class` → reds."""
    assert re.search(r"--scope-class <design\|slice\|phase>", _text(REVIEW)), "drive-review --scope-class"
    assert re.search(r"--scope-class phase\b", _text(HARDEN)), "harden --scope-class phase"
    assert re.search(r"--scope-class finalize\b", _text(FINALIZE)), "finalize --scope-class finalize"


# =========================================================================== #
# AC-P1 — broken-helper STOP (no codex launched, no marker, no fallback) in each block
# =========================================================================== #
def test_broken_helper_stop_in_each_block():
    """AC-P1: each spec routes `HELPER_ERROR`/rc 126/127 to a broken-helper NON-DECISION STOP with
    NO codex launched, NO marker, and NO `codex exec` fallback. Mutation-verify: replace the STOP
    with a codex-exec fallback → reds (`NO ... fallback` gone)."""
    for md in (REVIEW, HARDEN, FINALIZE):
        blob = re.sub(r"\s+", " ", _text(md))
        assert re.search(r"HELPER_ERROR.*shell rc 126/127.*broken-helper NON-DECISION STOP", blob), (
            f"{md.name} must route HELPER_ERROR / rc 126,127 to a broken-helper STOP"
        )
        assert "NO `codex exec` fallback" in _text(md), (
            f"{md.name}: the broken-helper STOP must state there is NO codex exec fallback"
        )


# =========================================================================== #
# AC-P2 — snapshot (cp) → quarantine (mv sibling) → dispatch, in that ORDER
# =========================================================================== #
def _ac_p2_anchors(md):
    if md is REVIEW:
        sib = "codex-review-<scope>.md"
        prior = "codex-prior-<scope>.md"
    elif md is HARDEN:
        sib = "codex-harden-<P>.md"
        prior = "codex-prior-<scope>.md"
    else:
        sib = "codex-review-finalize.md"
        prior = "codex-prior-finalize.md"
    return sib, prior


def test_snapshot_then_quarantine_then_dispatch_order():
    """AC-P2: each block `cp`s the prior codex sibling to a stable snapshot BEFORE it `mv`s the
    stale sibling aside, BEFORE the dispatch. Mutation-verify: delete the sibling `mv` → reds;
    move the `cp` AFTER the `mv` → the ordering reds."""
    for md in (REVIEW, HARDEN, FINALIZE):
        sib, prior = _ac_p2_anchors(md)
        lines = _lines(md)
        cp_i = _idx_sub(lines, "cp ", prior)
        mv_i = _idx_sub(lines, "mv ", sib, ".stranded")
        disp_i = _idx(lines, DISPATCH_RE)
        assert cp_i is not None, f"{md.name}: missing snapshot `cp … {prior}`"
        assert mv_i is not None, f"{md.name}: missing sibling quarantine `mv … {sib} … .stranded`"
        assert disp_i is not None, f"{md.name}: missing the dispatch line"
        assert cp_i < mv_i < disp_i, (
            f"{md.name}: ordering must be snapshot(cp) < quarantine(mv) < dispatch"
        )


# =========================================================================== #
# AC-P3 — post-OK completion contract (require a non-empty marker or fail-closed STOP)
# =========================================================================== #
def test_post_ok_completion_contract_in_each_block():
    """AC-P3: after `OK` + post-process each block REQUIRES a non-empty file at the `--marker`
    path, else fail-closed STOP. Mutation-verify: delete the require-marker clause → reds."""
    for md in (REVIEW, HARDEN, FINALIZE):
        blob = re.sub(r"\s+", " ", _text(md))
        assert re.search(
            r"require a non-empty.{0,220}fail-closed non-decision STOP",
            blob,
        ), f"{md.name}: OK branch must require a non-empty marker or fail-closed STOP"


# =========================================================================== #
# AC-P4 — the post-process writes the marker ATOMICALLY (tmp+mv)
# =========================================================================== #
def test_atomic_post_process_write_in_each_block():
    """AC-P4: each post-process writes to `<marker>.tmp.$$` then `mv`s into the --marker path (never
    a direct in-place write). BOUNDED-SLICE on the post-process prose. Mutation-verify: replace the
    tmp+mv with a direct write → reds."""
    specs = {
        REVIEW: "codex-review-<scope>.md.tmp.$$",
        HARDEN: "codex-harden-<P>.md.tmp.$$",
        FINALIZE: "codex-review-finalize.md.tmp.$$",
    }
    for md, tmp in specs.items():
        blob = re.sub(r"\s+", " ", _text(md))
        assert "ATOMICALLY" in blob and tmp.replace("$", r"$") in _text(md), (
            f"{md.name}: post-process must write ATOMICALLY to {tmp} then mv into place"
        )
        assert re.search(r"then `mv` into the `--marker` path", blob), (
            f"{md.name}: the atomic write must tmp+mv into the --marker path"
        )


# =========================================================================== #
# AC-H12c — re-dispatch ⇒ FULL effort is a CONDITIONAL BRANCH (not prose-only)
# =========================================================================== #
def test_redispatch_full_effort_is_a_conditional_branch():
    """AC-H12c: each block builds `--confirmation-class` in a CONDITIONAL branch — the
    clean-first-dispatch branch INCLUDES `CONF=(--confirmation-class …)`, the re-dispatch
    else-branch sets `CONF=()` and LACKS `--confirmation-class`; the invocation expands
    `"${CONF[@]}"`. Mutation-verify: make `--confirmation-class` unconditional (move it into the
    else / drop the guard) → the re-dispatch pin reds."""
    for md in (REVIEW, HARDEN, FINALIZE):
        lines = _lines(md)
        clean_i = _idx(lines, r"CONF=\(--confirmation-class")
        redis_i = _idx(lines, r"CONF=\(\)")
        assert clean_i is not None, f"{md.name}: clean-first branch must set CONF=(--confirmation-class …)"
        assert redis_i is not None, f"{md.name}: re-dispatch branch must set CONF=()"
        # the CODE of the re-dispatch branch (before any trailing `# comment`) must LACK the flag.
        redis_code = lines[redis_i].split("#", 1)[0]
        assert "--confirmation-class" not in redis_code, (
            f"{md.name}: the re-dispatch (CONF=()) branch must LACK --confirmation-class ⇒ FULL effort"
        )
        assert re.search(r'"\$\{CONF\[@\]\}"', _text(md)), (
            f"{md.name}: the invocation must expand \"${{CONF[@]}}\" (not a literal flag)"
        )
        # the re-dispatch signal is the OPEN inflight marker, NOT prior-round review-<scope>-N.md
        assert "inflight-review-" in _text(md), (
            f"{md.name}: re-dispatch must be signalled by a pre-existing open inflight-review marker"
        )


# =========================================================================== #
# AC8 — the CODEX_KILLED_TIMEOUT tier at EVERY enumerated consumer
# =========================================================================== #
def test_kill_tier_in_three_specs_degradation_paragraphs():
    """AC8: each spec's OWN inline `Degradation (do NOT hard-fail):` paragraph names BOTH tokens.
    BOUNDED to the paragraph (stop on the retained convention clause), NOT the section (which
    hosts/references the tier table). Mutation-verify: delete CODEX_KILLED_TIMEOUT from the
    paragraph → THAT pin reds (the tier-table copy is outside the slice)."""
    stops = {
        REVIEW: r"does NOT parse the marker",
        HARDEN: r"uniform across review and harden",
        FINALIZE: r"inspects existence \+ non-emptiness only",
    }
    for md, stop in stops.items():
        para = _slice(_lines(md), r"Degradation \(do NOT hard-fail\)", stop, inclusive=True)
        assert "CODEX_UNAVAILABLE" in para, f"{md.name} degradation paragraph must name CODEX_UNAVAILABLE"
        assert "CODEX_KILLED_TIMEOUT" in para, f"{md.name} degradation paragraph must name CODEX_KILLED_TIMEOUT"


def test_kill_tier_at_drive_md_four_sites():
    """AC8: drive.md's four tier sites each render the new token — per-anchor (per-bullet for the
    :891/:900 pair that share `### Data sources`, per-subsection for the others). Mutation-verify:
    delete the token at ONE anchor → THAT anchor's pin reds, not another's."""
    lines = _lines(DRIVE)
    # :641 stranded-adopt bullet
    adopt = _slice(lines, r"\*\*Adopt\*\* only if", r"unfinished dual-voice chain")
    assert "CODEX_KILLED_TIMEOUT" in adopt, "drive.md stranded-adopt bullet must name CODEX_KILLED_TIMEOUT"
    # :891 review-<scope>-N.md data-source bullet (bounded to that bullet)
    ds = _slice(lines, r"`review-<scope>-N\.md` \(", r"`design-phase<P>\.md`")
    assert "CODEX_KILLED_TIMEOUT" in ds, "drive.md data-source codex-sibling bullet must name the token"
    # :900 Finalize-node bullet
    fin = _slice(lines, r"`review-finalize-<N>\.md`", r"The slice scope token is the BARE id")
    assert "CODEX_KILLED_TIMEOUT" in fin, "drive.md Finalize-node bullet must name the token"
    # :997 Combined dual-voice round verdict subsection
    comb = _section(lines, r"^### Combined \(dual-voice\) round verdict")
    assert "CODEX_KILLED_TIMEOUT" in comb, "drive.md combined-verdict subsection must name the token"


def test_kill_tier_at_retro_two_sites():
    """AC8/AC9: drive-retro.md's degraded-scope stat (§5) and Rule-U E7 stub both name the token.
    Mutation-verify: delete either → that section's pin reds."""
    lines = _lines(RETRO)
    stats = _section(lines, r"^## 5 — Derive stats", stop_re=r"^##\s")
    assert "CODEX_KILLED_TIMEOUT" in stats, "drive-retro §5 degraded-scope stat must name the token"
    ruleu = _section(lines, r"^## 6 — Mine findings: Rule U", stop_re=r"^##\s")
    assert "CODEX_KILLED_TIMEOUT" in ruleu, "drive-retro Rule-U E7 stub must name the token"


def test_kill_tier_at_ship_enforcement_claude_readme():
    """AC8: the doc/config consumers (drive-enforcement operator note, CLAUDE.md inventory, README
    codex row) each name the new token — each BOUNDED to its region. (The ship Gate-B killed tier
    is pinned by `test_ship_gate_b_degraded_line_counts_both_tiers` via its `killed-timeout` count
    label.) Mutation-verify: delete the token in a region → that region's pin reds."""
    # drive-enforcement operator note (the blockquote paragraph)
    op = _slice(_lines(ENFORCE), r"Operator note — codex degradation tiers", r"killed-N\.log", inclusive=True)
    assert "CODEX_KILLED_TIMEOUT" in op, "drive-enforcement operator note must name the token"
    # CLAUDE.md $RUN_DIR inventory (the codex family lines)
    inv = _slice(_lines(CLAUDE), r"codex-review-<scope>\.md\s+-- codex findings", r"sandbox-spike-evidence\.md", inclusive=True)
    assert "CODEX_KILLED_TIMEOUT" in inv, "CLAUDE.md inventory must name the killed token"
    # README codex CLI row
    readme_row = _slice(_lines(README), r"\[codex CLI\]", r"No third-party libraries", inclusive=False)
    assert "CODEX_KILLED_TIMEOUT" in readme_row, "README codex row must name the token"


def test_ship_gate_b_degraded_line_counts_both_tiers():
    """AC11: drive-ship.md's Gate-B degraded-codex line reports per-tier counts (killed-timeout +
    unavailable) across scopes, computed from the final-round codex files + the attempt log.
    Mutation-verify: drop `killed-timeout` from the line → reds."""
    gateb = re.sub(r"\s+", " ", _section(_lines(SHIP), r"^## Gate B", stop_re=r"^##\s"))
    assert "killed-timeout" in gateb and "unavailable" in gateb, (
        "Gate-B must report per-tier degraded-codex counts (killed-timeout + unavailable)"
    )
    assert "codex-attempts-<runId>.jsonl" in gateb, (
        "the Gate-B degraded line must be computed from the attempt log"
    )


# =========================================================================== #
# AC10 — tier-table prose-consistency across the consumer docs
# =========================================================================== #
def test_tier_table_prose_consistency():
    """AC10: the codex-n/a / codex-killed rendering is described consistently — drive.md renders
    `Codex n/a` (unavailable) AND `Codex killed` (killed-timeout). Mutation-verify: drop the
    `Codex killed` rendering → reds."""
    drive = _text(DRIVE)
    assert "Codex n/a" in drive, "drive.md must render `Codex n/a` for CODEX_UNAVAILABLE"
    assert "Codex killed" in drive, "drive.md must render `Codex killed` for CODEX_KILLED_TIMEOUT"
