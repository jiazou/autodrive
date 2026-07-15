"""Contract pins for the R5-R9 round-churn spec batch (run r5r9-roundchurn).

Pins the five Tier-C clauses + the refutation-ledger artifacts + the D-9 wiring:

  * R5 class-sweep fix-round contract in drive-implement / drive-finalize / drive-review
    (AC1);
  * R6 delta-focused re-review PROMPT form: eligibility + security carve-out (AC2), the
    delta-prompt composition + fail-closed deltaBase + terminal invariant (AC3), the
    suite-rerun ban bounded to eligible rounds (AC4), the zero-new-artifact-shapes
    allowlist + the D-38 forbidden-vocabulary negative (AC5 / AC3.iv);
  * R7 refutation ledger: five hard bounds, count-tags-not-prose, the no-injection clause
    at both harden/finalize read sites (AC6), the committed seed ledger with EXECUTED
    hermetic repros in both directions (AC7), the structural no-injection negative (AC17);
  * D-9 wiring: the activation-aware ship promotion step (AC11) and the 4-file
    enumeration sweep across every § C site (AC12);
  * R8 design author-verification gates (AC13);
  * R9 pin-depth mutation-survival semantics (AC14);
  * A-D21 drive-design detached-worktree guard repair (AC18).

Discipline per the batch's own R9 standard: each [M] pin is section/block-bound to the
clause it guards (a file-wide token match does not satisfy it), and each was
mutation-verified at implement (delete the clause -> red; restore -> green).
"""
import re
import subprocess

from _helpers import REPO_ROOT

CMDS = REPO_ROOT / ".claude" / "commands"

REVIEW = CMDS / "drive-review.md"
IMPLEMENT = CMDS / "drive-implement.md"
FINALIZE = CMDS / "drive-finalize.md"
HARDEN = CMDS / "drive-harden.md"
PLAN = CMDS / "drive-plan.md"
DESIGN = CMDS / "drive-design.md"
SHIP = CMDS / "drive-ship.md"
DRIVE = CMDS / "drive.md"
ENFORCE = REPO_ROOT / "docs" / "drive-enforcement.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
README = REPO_ROOT / "README.md"
LEDGER = REPO_ROOT / ".harness" / "codex-refutations.md"
CONFORMANCE = REPO_ROOT / "bin" / "drive-conformance.sh"
PREFLIGHT = REPO_ROOT / "bin" / "drive-base-preflight.sh"

BEGIN_SCOPE = "----- BEGIN SUBAGENT SCOPE -----"
END_SCOPE = "----- END SUBAGENT SCOPE -----"


def _text(p):
    return p.read_text(encoding="utf-8")


def _norm(s):
    """Collapse all whitespace to single spaces (insertion/reflow-tolerant matching)."""
    return re.sub(r"\s+", " ", s)


def _section(text, header_re, *, stop_re=r"^#{1,4}\s"):
    """The lines from the header matching `header_re` up to (excl.) the next heading."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section /{header_re}/ not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _scope_blocks(text):
    """Every `BEGIN SUBAGENT SCOPE`..`END SUBAGENT SCOPE` block (exclusive of markers)."""
    blocks, lines, cur, inside = [], text.splitlines(), [], False
    for ln in lines:
        if BEGIN_SCOPE in ln:
            inside, cur = True, []
            continue
        if END_SCOPE in ln:
            if inside:
                blocks.append("\n".join(cur))
            inside = False
            continue
        if inside:
            cur.append(ln)
    assert blocks, "no SUBAGENT SCOPE block found"
    return blocks


def _fenced_blocks(text):
    """Every ``` fenced block's content (the PROMPT-heredoc dispatch blocks live here)."""
    blocks, cur, inside = [], [], False
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            if inside:
                blocks.append("\n".join(cur))
                cur = []
            inside = not inside
            continue
        if inside:
            cur.append(ln)
    return blocks


def _review_prompt_heredoc():
    """drive-review.md's Step-1 PROMPT heredoc body (between <<'PROMPT' and PROMPT)."""
    lines = _text(REVIEW).splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if "codex-prompt-<scope>.txt" in ln and "<<'PROMPT'" in ln),
        None,
    )
    assert start is not None, "drive-review.md Step-1 PROMPT heredoc not found"
    end = next((j for j in range(start + 1, len(lines)) if lines[j] == "PROMPT"), None)
    assert end is not None, "PROMPT heredoc terminator not found"
    return "\n".join(lines[start + 1 : end])


def _r6_section():
    return _section(_text(REVIEW), r"^## Round form on eligible re-reviews")


def _r7_section():
    return _section(_text(REVIEW), r"^## Refutation ledger \(R7\)")


# =========================================================================== #
# AC1 — R5 class-sweep fix-round contract lands in all three files
# =========================================================================== #
def test_r5_class_sweep_in_implement():
    """[S] drive-implement.md's implementer scope carries the class-sweep contract:
    grep-enumerate siblings, fix ALL in-ownership members in ONE round, class boundary in
    the commit message, mutation-verify per site, and the D-12 out-of-ownership route
    (followups + STATUS note; REDESIGN only when the fix itself needs those files)."""
    scope = _norm(_scope_blocks(_text(IMPLEMENT))[0])
    assert "Class-sweep fix rounds (R5)" in scope
    assert "parser/validator/regex/classifier/reader/wording-class" in scope
    assert "grep-enumerate every sibling site" in scope
    assert "ACROSS YOUR OWNED FILES" in scope
    assert "in this one round" in scope
    assert re.search(r"class boundary.*commit message", scope), (
        "the class boundary (grep pattern + member list) must be stated in the commit message"
    )
    assert "mutation-verify per fixed site" in scope
    assert re.search(r"RECORD them to `\$RUN_DIR/followups\.md`.*STATUS line", scope), (
        "out-of-ownership members: record to followups + STATUS-line note"
    )
    assert re.search(
        r"`STATUS: REDESIGN` ONLY when your own fix requires editing those files", scope
    )
    assert "NEVER edit them" in scope


def test_r5_class_sweep_in_finalize():
    """[S] drive-finalize.md's Step-3 fix scope carries the run-diff-bounded class sweep,
    EXPLICITLY including the de-slop wording-class sweep, with the root-cause
    scope-exception / followups routing for members outside the run diff."""
    blocks = _scope_blocks(_text(FINALIZE))
    fixer = _norm(next(b for b in blocks if "Apply ONLY the fix set" in b))
    assert "Class-sweep fix rounds (R5), bounded to the run-diff scope" in fixer
    assert "scope-creep HARD GATE" in fixer
    assert "de-slop wording-class sweep" in fixer
    assert re.search(r"wording/naming P2 slop item sweeps its WHOLE class", fixer), (
        "a flagged wording/naming P2 sweeps its whole class in the same round"
    )
    assert re.search(r"ONLY when they ARE the root cause of a flagged P1", fixer)
    assert "scope-widening note" in fixer
    assert re.search(r"otherwise record them to `\$RUN_DIR/followups\.md`", fixer)


def test_r5_codex_r1_enumeration_sentence():
    """[S] the Step-1 codex round-1 prompt (heredoc BODY) instructs class-member
    enumeration — one appended sentence; the dispatch mechanics around it untouched."""
    heredoc = _norm(_review_prompt_heredoc())
    assert re.search(
        r"one instance of a class \(parser/validator/regex/classifier/reader/ ?wording\)",
        heredoc,
    ), "the codex r1 prompt must name the defect-class list"
    assert "enumerate ALL members of the class with file:line" in heredoc


def test_r5_reviewer_round_n2_checklist_retains_open_ended_hunt():
    """[S] the Step-2 reviewer scope gains the round-N>=2 class-closure checklist as an
    ADDITION to (never a replacement of) the open-ended adversarial hunt. Block-bound to
    the reviewer SUBAGENT SCOPE so the R6 section's near-verbatim codex sibling item
    cannot satisfy it (the sibling-token vacuity trap)."""
    scope = _norm(_scope_blocks(_text(REVIEW))[0])
    assert "Round-N≥2 checklist (slice/phase scopes)" in scope
    assert "VERIFY each stated class is closed" in scope
    assert "re-run its boundary grep" in scope
    assert "IN ADDITION TO, never instead of, your unchanged open-ended adversarial hunt" in scope


# =========================================================================== #
# AC2 — R6 eligibility + the any-touch security carve-out (section-bound)
# =========================================================================== #
def test_r6_eligibility_names_the_exclusions():
    """[M] the R6 section's eligibility list names the code-scope + N>=2 bound and EVERY
    exclusion: design/phasedesign, harden-regress, the recovery re-dispatch (bound at the
    recovery ADJUDICATION point, NOT bare marker existence). Mutation-verified: deleting
    the design/phasedesign exclusion sentence reds."""
    r6 = _norm(_r6_section())
    assert re.search(r"`slice <id>` or `phase <P>`.*round N≥2", r6), (
        "eligibility must bind to a CODE scope at round N>=2"
    )
    assert re.search(
        r"`design`/`phasedesign<P>` scopes are ineligible by construction", r6
    ), "design/phasedesign scopes must be excluded (audit sole-catcher §3.5)"
    assert "harden-regress` invocation is ineligible" in r6
    assert "`finalize` is not a drive-review scope" in r6
    assert "NOT a stranded-marker recovery re-dispatch" in r6
    assert "recovery ADJUDICATION point" in r6
    assert re.search(
        r"OWN `inflight-review-<scope>\.marker`.*does NOT make the round a recovery re-dispatch",
        r6,
    ), "the round's own marker must NOT classify it as a recovery re-dispatch (D-31b)"


def test_r6_security_carveout_is_any_touch():
    """[M] the security exclusion is diff-content-based and ANY-touch: one sensitive file
    in the scope's --name-only diff makes the WHOLE round ineligible (full-scope codex),
    independent of the --security-diff effort flag. Mutation-verified: deleting the
    security-exclusion sentence reds."""
    r6 = _norm(_r6_section())
    assert "touches NO security-sensitive path" in r6
    assert re.search(r"\*\*any\*\* file under `bin/`", r6)
    assert "gate-hook/installer script" in r6
    assert "settings/hook config" in r6
    assert "matcher/parser/classifier" in r6
    assert "WHOLE round is INELIGIBLE" in r6
    assert "full-scope codex every round" in r6
    assert re.search(r"independent of the `--security-diff`", r6)


# =========================================================================== #
# AC3 — R6 delta-prompt composition (descoped, D-38; multi-P1, D-40)
# =========================================================================== #
def test_r6_delta_prompt_binds_all_prior_p1s():
    """[M] AC3(i): the appended block LEADS with the delta focus and binds ALL prior-round
    P1s — per-P1 fix delta + consumer surface, class boundary only where the fix commit
    DECLARED one. Mutation-verified: deleting the lead-with-delta sentence reds."""
    r6 = _norm(_r6_section())
    assert "binds to ALL of the prior round's P1s" in r6
    assert 'never a singular "the prior finding"' in r6
    assert "LEADS with the delta focus" in r6
    assert "review FIRST the fix delta" in r6
    assert re.search(r"`git diff <deltaBase>\.\.<tip>`", r6)
    assert "FOR EACH prior-round P1" in r6
    assert "consumer surface" in r6 and "callers/readers of the changed symbols" in r6
    assert re.search(r"where that P1's fix commit DECLARED a class boundary", r6)
    assert "other fixes legitimately do not" in r6


def test_r6_conditional_class_closure_item():
    """[M] AC3(i): the class-closure checklist item is CONDITIONAL — included only when
    >=1 prior-round fix declared a boundary; an undeclared-class P1 gets NO boundary grep.
    Section-bound: the R5 Step-2 checklist sibling (same file, near-verbatim) cannot
    satisfy this. Mutation-verified: deleting the R6 item (R5 sibling intact) reds."""
    r6 = _norm(_r6_section())
    assert "CONDITIONAL class-closure checklist item" in r6
    assert "included only when ≥1 prior-round fix declared a boundary" in r6
    assert "for each declared class boundary, verify it is closed (re-run that boundary grep)" in r6
    assert re.search(r"declared no class gets the delta \+ consumer-surface treatment and NO boundary grep", r6)


def test_r6_full_scope_license_verbatim():
    """[M] AC3(i): the full-scope license lands VERBATIM, with 'scope' bound to the FULL
    reviewed diff — never the delta focus's slice (the narrow reading would revive the
    refuted settled-scope prohibition). Mutation-verified: deleting the license reds."""
    r6 = _norm(_r6_section())
    assert "you MAY flag any P1 anywhere in scope" in r6
    assert "the FULL reviewed diff of the scope" in r6
    assert "never the delta focus's slice of it" in r6
    assert "settled-scope prohibition" in r6


def test_r6_delta_base_fails_closed():
    """[M] AC3(ii): deltaBase = the reviewed-sha of review-<scope>-(N-1).md; a missing
    file or missing/non-40-hex sha makes the round NOT eligible (the stronger full-scope
    form). Mutation-verified: deleting the fail-closed sentence reds."""
    r6 = _norm(_r6_section())
    assert re.search(
        r"`deltaBase` = the `reviewed-sha:` of `review-<scope>-\(N-1\)\.md`", r6
    )
    assert re.search(r"missing/non-40-hex sha ⇒ NOT eligible", r6)
    assert "fail closed to the normal full prompt" in r6


def test_r6_claude_full_scope_and_terminal_invariant():
    """[M] AC3(iii): the Claude voice runs FULL-scope every round and carries the terminal
    pass (including the CONVERGED round); the codex voice keeps today's tier-table
    semantics, with the degraded-CONVERGED precedent cited. Mutation-verified: deleting
    the terminal-invariant sentence reds."""
    r6 = _norm(_r6_section())
    assert "The Claude voice runs FULL-scope every round" in r6
    assert "the terminal full-scope pass is the CLAUDE voice's" in r6
    assert re.search(r"including the round that records CONVERGED", r6)
    assert "tier-table semantics UNCHANGED" in r6
    assert "degraded pass contributes zero P1" in r6
    assert "degraded-round CONVERGED" in r6
    # accounting + §3.3 freshness statement ride the same section
    assert "counted INSIDE cap-8" in r6
    assert "FRESH dual-voice dispatch" in r6


def test_r6_forbidden_vocabulary_absent():
    """[M] AC3(iv) — the D-38 construction guard: the landed R6 section contains NONE of
    the retired two-pass machinery's vocabulary (case-insensitive). Mutation-verified per
    class: inserting each token into the section reds."""
    r6 = _r6_section().lower()
    for tok in (
        "conf=(",
        "tmp/codex-pass1",
        "promotion",
        "promotes",
        "widen",
        "pass 2",
        "pass-2",
        "terminal-at-pass-1",
    ):
        assert tok not in r6, f"retired two-pass vocabulary {tok!r} must not appear in the R6 section"


# =========================================================================== #
# AC4 — the suite-rerun ban, bounded to eligible rounds (section-bound)
# =========================================================================== #
def test_r6_suite_rerun_ban_bounded_to_eligible_rounds():
    """[M] the ban sentence + its eligibility bounding co-occur INSIDE the R6 section:
    eligible rounds spot-run only the pinning tests; ineligible/security rounds keep
    today's prompt with no ban. Mutation-verified: deleting the ban reds; moving it
    outside the eligibility bound reds (the co-occurrence breaks)."""
    r6 = _norm(_r6_section())
    assert "do NOT re-run the full test suites — spot-run only the tests pinning your prior findings" in r6
    assert "The ban applies ONLY on eligible rounds" in r6
    assert re.search(r"ineligible/security rounds keep today's prompt, with no ban", r6)


# =========================================================================== #
# AC5 — zero new artifact shapes (ABSOLUTE, D-38) — the allowlist check
# =========================================================================== #
# The batch's OWN new-artifact allowlist (the only filenames any landed clause may
# introduce). Pre-existing shapes the clauses reference are baseline, not introductions.
_NEW_ARTIFACT_ALLOWLIST_RE = re.compile(
    r"codex-refuted-(<scope>|\*)\.md"
    r"|codex-refutations-pending\.md"
    r"|codex-refutations\.md"
    r"|verify-design-claims-(design|phase<P>|\*)\.md"
)

# Baseline path shapes (pre-existing families) the R6 section may name.
_R6_BASELINE = {
    "codex-review-<scope>.md",
    "review-<scope>-N.md",
    "review-<scope>-(N-1).md",
    "tmp/codex-prompt-<scope>.txt",
    "tmp/codex-prior-<scope>.md",
    "inflight-review-<scope>.marker",
}


def test_new_artifact_names_stay_within_the_allowlist():
    """AC5(a): across ALL seven touched command specs, every refutation/claims-transcript
    filename any landed clause names is one of the batch's four allowlisted shapes —
    {codex-refuted-<scope>.md (family), codex-refutations-pending.md,
    verify-design-claims-*.md (family), .harness/codex-refutations.md} — no fifth shape."""
    token_re = re.compile(r"(?:codex-refut|verify-design-claims)[A-Za-z0-9<>*().-]*\.\w+")
    for md in (REVIEW, IMPLEMENT, FINALIZE, HARDEN, PLAN, DESIGN, SHIP):
        for tok in token_re.findall(_text(md)):
            assert _NEW_ARTIFACT_ALLOWLIST_RE.fullmatch(tok), (
                f"{md.name}: {tok!r} is outside the batch's new-artifact allowlist"
            )


def test_r6_section_introduces_no_new_filename():
    """AC5(b): the landed R6 section names ONLY baseline artifact shapes — every
    `<scope>`-family filename it mentions is a pre-existing family, and the review-file
    family appears only with the canonical placeholder suffixes N / (N-1) (a concrete or
    novel suffix would be a new artifact shape; the retired tmp/codex-pass1 family is
    covered by the AC3.iv forbidden set)."""
    r6 = _r6_section()
    for m in re.finditer(
        r"[A-Za-z0-9_$/.()<>*-]*<scope>[A-Za-z0-9_$/.()<>*-]*\.(?:md|txt|log|jsonl|marker)\b",
        r6,
    ):
        tok = m.group(0).lstrip("$/").removeprefix("RUN_DIR/")
        assert tok in _R6_BASELINE, (
            f"the R6 section may not introduce the artifact filename {tok!r} (zero new shapes)"
        )
    # the review-file family appears only with canonical placeholder suffixes
    for m in re.finditer(r"review-<scope>-([^\s`]+?)\.md", r6):
        assert m.group(1) in ("N", "(N-1)"), (
            f"review-<scope>-{m.group(1)}.md: non-placeholder review suffix in the R6 section"
        )


# =========================================================================== #
# AC6 — R7 five hard bounds + count-tags + the no-injection clause (3 sites)
# =========================================================================== #
def test_r7_five_bounds_present():
    """[M] the R7 section states all five bounds; bound 1 in its TWO-FORM wording
    (executable repro OR run-local doc-anchored cites-as-replay; COMMITTED entries ALWAYS
    executable). Mutations verified: deleting bound 2, bound 5, or the
    committed-always-executable half each reds."""
    r7 = _norm(_r7_section())
    # bound 1 (two-form + replay-on-re-flag + executed-red-defeats)
    assert "REPLAYABLE check" in r7
    assert "doc-anchored artifact cites" in r7 and "re-reading IS the replay" in r7
    assert "COMMITTED entries ALWAYS carry an executable hermetic `env -i` line" in r7
    assert "RE-EXECUTES the recorded check" in r7
    assert "VOIDS the entry" in r7
    assert "executed red in the faithful env ALWAYS defeats the ledger" in r7
    # bound 2 (voice independence + review-enrichment license extending the pinned rule)
    assert "NEVER injected into harden/finalize auditor prompts" in r7
    assert "prior-round enrichment" in r7
    assert "EXTENDS, and does not reword" in r7
    # bound 3
    assert "finding-specific" in r7
    assert 'never class-level "X-like findings are settled"' in r7
    # bound 4
    assert "P1→P2 downgrade requires the coordinator's OWN executed reproduction" in r7
    assert "fail-safe direction" in r7
    assert re.search(r"threat-model arm applies only to verbatim `docs/drive-enforcement\.md`", r7)
    # bound 5
    assert "repro timeout leaves the finding UN-refuted" in r7
    assert "mints nothing and voids nothing" in r7
    # the three artifacts
    assert "codex-refuted-<scope>.md" in r7
    assert "codex-refutations-pending.md" in r7
    assert ".harness/codex-refutations.md" in r7


def test_r7_count_tags_not_prose_in_step3():
    """[M] Step 3 (Combine) derives the codex verdict by COUNTING BLOCKING/MAJOR severity
    tags — never the prose summary — failing closed to the tags on conflict.
    Mutation-verified: deleting the fail-closed half reds."""
    step3 = _norm(_section(_text(REVIEW), r"^## Step 3\b"))
    assert "Count tags, not prose" in step3
    assert re.search(r"COUNTING the BLOCKING/MAJOR severity tags in `codex-review-<scope>\.md`", step3)
    assert "never its prose summary line" in step3
    assert "tag-vs-prose conflict, fail closed to the tags" in step3


def test_r7_no_injection_clause_in_harden_and_finalize():
    """[M] the D-11 no-injection clause is stated where the executing agents read — BOTH
    drive-harden.md's and drive-finalize.md's Step-1 CRITICAL BOUNDARY sentences, naming
    all three refutation paths. Mutation-verified: deleting either clause reds."""
    for md, voice in ((HARDEN, "harden's voices"), (FINALIZE, "finalize's voices")):
        step1 = _norm(_section(_text(md), r"^## Step 1\b"))
        assert "must NEVER include" in step1 and "refutation-ledger content" in step1, (
            f"{md.name}: Step 1 must carry the no-injection clause"
        )
        for path_tok in (
            "codex-refuted-*.md",
            "codex-refutations-pending.md",
            ".harness/codex-refutations.md",
        ):
            assert path_tok in step1, f"{md.name}: the ban must name {path_tok}"
        assert f"{voice} stay independent of do-not-re-raise steers" in step1


# =========================================================================== #
# AC17 — the no-injection ban is STRUCTURALLY verifiable (negative pin)
# =========================================================================== #
def test_no_refutation_tokens_inside_harden_finalize_prompts():
    """[M] within drive-harden.md's and drive-finalize.md's PROMPT heredoc fences and
    SUBAGENT SCOPE blocks, the tokens `codex-refuted` / `codex-refutations` are ABSENT
    (the D-11 ban clause naming those paths sits OUTSIDE the prompt blocks).
    Mutation-verified: pasting a refutation path into a heredoc reds."""
    for md in (HARDEN, FINALIZE):
        text = _text(md)
        for i, block in enumerate(_fenced_blocks(text) + _scope_blocks(text)):
            low = block.lower()
            assert "codex-refuted" not in low and "codex-refutations" not in low, (
                f"{md.name}: refutation-ledger content leaked into prompt/scope block {i}"
            )


# =========================================================================== #
# AC7 — the committed ledger: header, seeds, and EXECUTED hermetic repros
# =========================================================================== #
def _seed_repro_commands():
    """The two seed entries' repro lines — extracted from the `## CR-<n>` entry bodies
    (the entry-schema TEMPLATE in the header's fenced example is not a seed)."""
    text = _text(LEDGER)
    entries = re.split(r"^## CR-\d+ — ", text, flags=re.MULTILINE)[1:]
    cmds = [
        m.group(1)
        for e in entries
        for m in [re.search(r"^- repro \(hermetic\): `(env -i [^`]+)`", e, re.MULTILINE)]
        if m
    ]
    assert len(cmds) == 2, f"expected exactly the two D-27 seed repros, found {len(cmds)}"
    return cmds


def test_committed_ledger_header_and_seed_entries():
    """[M] .harness/codex-refutations.md exists with the purpose header (usage rule:
    REVIEW re-audit prompts ONLY; replay rule: re-execute verbatim, differing result =>
    VOID, executed red always defeats; timeout mints nothing) and the two D-27 seeds."""
    text = _text(LEDGER)
    norm = _norm(text)
    assert "enrich REVIEW re-audit prompts ONLY — NEVER harden/finalize auditor prompts" in norm
    assert "re-execute the recorded `env -i` line verbatim from the repo root" in norm
    assert "the entry is VOID" in norm
    assert "executed red in the faithful env ALWAYS defeats an entry" in norm
    assert "repro timeout refutes nothing and voids nothing" in norm
    assert re.search(r"^## CR-1 — ", text, re.MULTILINE), "seed CR-1 missing"
    assert re.search(r"^## CR-2 — ", text, re.MULTILINE), "seed CR-2 missing"
    assert "codex-reflags-preship-absent-ledger" in norm  # CR-1 recurrence evidence
    assert "anywhere in scope" in norm  # CR-2 anchors the landed R6 clause


def test_committed_seed_repros_execute_green():
    """[M] AC7 (green direction): each seed's recorded `env -i ... sh -c '...'` line is
    EXECUTED from the repo root and exits 0 — the entries are replayable as written, and
    a drift in any anchored token reds the suite here rather than at replay time."""
    for cmd in _seed_repro_commands():
        proc = subprocess.run(cmd, shell=True, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, (
            f"seed repro must exit 0 from the repo root: {cmd!r} "
            f"(rc={proc.returncode}, stderr={proc.stderr!r})"
        )


def test_committed_seed_repros_red_direction(tmp_path):
    """[M] AC7 (red direction — anti-vacuity): each seed's grep chain FAILS against a
    mutated tree whose guarded clause is deleted, proving the repro binds the real clause
    (green-at-HEAD is not vacuous). CR-1: strip the ship promotion clause; CR-2: strip
    the landed full-scope license."""
    mutations = {
        # seed 1: the promotion contract clause is deleted from drive-ship.md
        ".claude/commands/drive-ship.md": ("Promote the run ledgers", ""),
        # seed 2: the landed R6 full-scope license is deleted from drive-review.md
        ".claude/commands/drive-review.md": ("anywhere in scope", ""),
    }
    # mirror ONLY the repo-relative files each seed greps, mutated
    for rel, (old, new) in mutations.items():
        src = REPO_ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        assert old in _text(src), f"{rel}: expected the guarded token {old!r} at HEAD"
        dst.write_text(_text(src).replace(old, new), encoding="utf-8")
    # unmutated second halves so ONLY the guarded clause's absence can red each chain
    for rel in ("CLAUDE.md", "docs/efficiency-audit-2026-07-08.md"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(_text(REPO_ROOT / rel), encoding="utf-8")
    for cmd in _seed_repro_commands():
        proc = subprocess.run(cmd, shell=True, cwd=str(tmp_path), capture_output=True, text=True)
        assert proc.returncode != 0, (
            f"seed repro must RED once its guarded clause is deleted (vacuity probe): {cmd!r}"
        )


# =========================================================================== #
# AC11 — the activation-aware ship promotion step (both branches)
# =========================================================================== #
def test_activation_aware_promotion_step():
    """[M] drive-ship.md's promotion section: the `-s` pending check, the LIVE-gate probe
    (enforcement-worktree conformance grep), the admitted branch (same single ledger
    commit) AND the graceful-degrade branch (run-local + Gate-B surfacing, never a push
    false-block). Mutation-verified: deleting the absent-branch reds."""
    promo = _norm(_section(_text(SHIP), r"^##\s+Ship worktree \+ ledger promotion\b"))
    assert "activation-aware refutation promotion" in promo
    assert "codex-refutations-pending.md" in promo
    assert re.search(r"is non-empty \(`\[ -s", promo), "the pending check must key on `-s`"
    assert "probe the LIVE gate" in promo
    assert "grep -qF '.harness/codex-refutations.md' ~/.claude/drive-enforcement-worktree/bin/drive-conformance.sh" in promo
    assert re.search(r"Admitted.*SAME single ledger commit", promo), (
        "the admitted branch must append inside the SAME single ledger commit"
    )
    assert re.search(r"leave the entries run-local", promo), "the graceful-degrade branch"
    assert "pending-activation followup at Gate B" in promo
    assert "never a push false-block" in promo


# =========================================================================== #
# AC12 — every § C enumeration site is 4-file (and no stale 3-file wording)
# =========================================================================== #
def test_enumeration_sites_name_the_fourth_ledger():
    """[S] each D-9 wiring site's enumeration names `.harness/codex-refutations.md`:
    the two bin/ array declarations, drive-ship.md (precondition #3 + promote step +
    ship-conformance), drive.md's two enumerations, drive-finalize.md's obligation #5,
    docs/drive-enforcement.md's two sites, CLAUDE.md's committed-ledgers sentence, and
    README.md's repo-layout + committed-.harness sentences."""
    tok = ".harness/codex-refutations.md"
    # sites 1-2: the array declarations
    for sh, decl in ((CONFORMANCE, "SHIP_LEDGER_ALLOWLIST"), (PREFLIGHT, "LEDGER_ALLOWLIST")):
        m = re.search(rf"^{decl}=\((.*?)\)\s*$", _text(sh), re.MULTILINE)
        assert m and tok in m.group(1), f"{sh.name}: {decl} must contain {tok}"
    # site 3: the pendingLedgers conditional
    assert re.search(
        r'\[ -s "\$RUN_DIR/codex-refutations-pending\.md" \] && pendingLedgers\+=\("\.harness/codex-refutations\.md"\)',
        _text(PREFLIGHT),
    ), "the pendingLedgers conditional must mirror the finalize-todo form"
    # sites 4-7: drive-ship.md
    ship = _text(SHIP)
    pre = _norm(_section(ship, r"^##\s+Preconditions\b"))
    assert tok in pre, "drive-ship.md precondition #3's allowlist enumeration"
    promo = _norm(_section(ship, r"^##\s+Ship worktree \+ ledger promotion\b"))
    assert "now 4 entries" in promo and tok in promo
    conf = _norm(_section(ship, r"^##\s+Ship conformance\b"))
    assert "4-file" in conf
    # sites 8-9: drive.md's two SHIP_LEDGER_ALLOWLIST enumerations
    for ln in _text(DRIVE).splitlines():
        if "SHIP_LEDGER_ALLOWLIST` {" in ln:
            assert "codex-refutations.md" in ln, f"drive.md enumeration missing 4th entry: {ln!r}"
    assert _text(DRIVE).count("codex-refutations.md") >= 2, "both drive.md sites must update"
    # site 10: drive-finalize.md obligation #5
    assert tok in _norm(_text(FINALIZE)), "drive-finalize.md's allowlist enumeration"
    # sites 11-12: docs/drive-enforcement.md
    enforce = _norm(_text(ENFORCE))
    assert "the exact four files" in enforce and tok in enforce
    assert "single 4-file ledger commit" in enforce
    # site 13: CLAUDE.md committed cross-task ledgers
    claude_norm = _norm(_text(CLAUDE_MD))
    assert re.search(
        r"committed\*?\*? cross-task ledgers stay in the repo: `\.harness/decisions\.md`, `\.harness/followups\.md`, `\.harness/codex-refutations\.md`",
        claude_norm,
    ), "CLAUDE.md's committed-ledger enumeration must name the third .harness ledger"
    # site 14: README.md — repo layout bullet + the committed-.harness sentence
    readme_norm = _norm(_text(README))
    assert "`.harness/codex-refutations.md` -- append-only durable codex-refutation ledger" in readme_norm
    assert re.search(
        r"holds only the cross-task ledgers \(`decisions\.md`, `followups\.md`, `codex-refutations\.md`\)",
        readme_norm,
    ), "README's committed-.harness sentence must name the three ledgers"


def test_no_stale_three_file_wording_remains():
    """[S] no live-gate-describing site still says 3-file / three files / now 3 entries
    in the allowlist context (the negative half of AC12; scoped to the wiring files)."""
    for p in (SHIP, DRIVE, ENFORCE, FINALIZE):
        text = _text(p)
        assert "3-file" not in text, f"{p.name}: stale '3-file' allowlist wording"
        assert "now 3 entries" not in text, f"{p.name}: stale 'now 3 entries' wording"
        assert "exact three files" not in text, f"{p.name}: stale 'exact three files' wording"


# =========================================================================== #
# AC13 — R8 design author-verification gates
# =========================================================================== #
def test_r8_plan_transcript_always_written_and_gated():
    """[M] drive-plan.md: the planner ALWAYS writes verify-design-claims-design.md (the
    three-category no-claims declaration when none), ships calibration inputs for
    classifier/matcher rules, and the coordinator existence-checks it BEFORE round 1
    (consuming no counter). Mutation-verified: deleting the existence check reds."""
    text = _text(PLAN)
    scope = _norm(_scope_blocks(text)[0])
    assert "verify-design-claims-design.md" in scope
    assert "ARTIFACT-shaped transcript" in scope
    assert "EVERY citation, quoted snippet, and empirical claim" in scope
    assert "no citations / no quoted snippets / no empirical claims" in scope
    assert "ALWAYS written" in scope
    assert "calibration script" in scope and "imprecision budget" in scope
    assert re.search(r"Never a prose \"?verified\"? attestation", scope)
    step2 = _norm(_section(text, r"^## Step 2\b"))
    assert re.search(
        r"CHECK `\$RUN_DIR/verify-design-claims-design\.md` exists non-empty", step2
    )
    assert "send the author back" in step2
    assert "consumes no counter" in step2


def test_r8_plan_revision_leg_revalidation():
    """[M] the PLAN-path transcript cannot go stale: every post-P1 design.md revision
    re-verifies the transcript BEFORE the next round (added/changed claims verified +
    appended; coverage re-affirmed at the revised text; the pre-round check re-fires).
    Mutation-verified: deleting the revalidation sentence reds."""
    step2 = _norm(_section(_text(PLAN), r"^## Step 2\b"))
    assert "RE-VERIFIES the transcript BEFORE the next round" in step2
    assert "verified and appended" in step2
    assert "re-affirmed against the REVISED text" in step2
    assert "re-fires each round" in step2


def test_r8_design_transcript_and_revision_leg():
    """[M] drive-design.md: the author writes verify-design-claims-phase<P>.md (ALWAYS;
    rewritten in place on revision legs), the coordinator existence-checks pre-round-1,
    and a revision leg CONSUMES a phaseDesign[<P>].round tick, mints NO new artifact
    family, and re-enters as a FULL fresh dual-voice round. Mutation-verified: deleting
    the consumes-a-round-tick clause reds; deleting the existence check reds."""
    text = _text(DESIGN)
    scope = _norm(_scope_blocks(text)[0])
    assert "verify-design-claims-phase<P>.md" in scope
    assert "ALWAYS" in scope and "rewritten in place on revision legs" in scope
    assert "no citations / no quoted snippets / no empirical claims" in scope
    assert "calibration script" in scope and "imprecision budget" in scope
    step2 = _norm(_section(text, r"^## Step 2\b"))
    assert re.search(
        r"CHECK `\$RUN_DIR/verify-design-claims-phase<P>\.md` exists non-empty", step2
    )
    assert "consumes no counter" in step2
    assert "CONSUMES a `phaseDesign[<P>].round` tick" in step2
    assert "mints NO new artifact family" in step2
    assert "FULL fresh dual-voice round" in step2


def test_r8_reviewer_calibration_and_conditional_transcript_duty():
    """[M] drive-review.md (DV-2): the design/phasedesign reviewers run the author's
    calibration script (precision) PLUS their own independent recall probe, and the
    transcript duty is CONDITIONAL — claims-bearing => spot-check >=1 claim; a no-claims
    declaration => verify the declaration against the design doc (a found claim is a P1
    against the transcript). Pinned in BOTH voices' prompts. Mutation-verified: deleting
    the no-claims arm reds."""
    scope = _norm(_scope_blocks(_text(REVIEW))[0])
    assert "RUN its calibration script against its corpus (precision)" in scope
    assert "independent recall probe" in scope
    assert "the author's script inherits the rule's blind spots" in scope
    assert "claims-bearing transcript ⇒ spot-check ≥1 claim" in scope
    assert "VERIFY THAT DECLARATION against the design doc itself" in scope
    assert "any found falsifies the declaration and is a P1 against the transcript" in scope
    heredoc = _norm(_review_prompt_heredoc())
    assert "RUN its calibration script against its corpus (precision)" in heredoc
    assert "independent recall probe" in heredoc
    assert "verify-design-claims-*.md" in heredoc
    assert "spot-check >=1 claim" in heredoc
    assert "VERIFY THAT DECLARATION against the design doc itself" in heredoc


# =========================================================================== #
# AC14 — R9 pin-depth mutation-survival semantics
# =========================================================================== #
def test_r9_mutation_survival_severity_semantics():
    """[M] the Step-2 Severity block defines pin existence by MUTATION SURVIVAL (vacuous
    pin = NO pin = stays P1; could-be-stronger = P2) with the fail-closed-surface
    carve-out where exclusivity/composed-order gaps STAY P1. Mutation-verified: deleting
    the carve-out sentence reds."""
    scope = _norm(_scope_blocks(_text(REVIEW))[0])
    assert "MUTATION SURVIVAL" in scope
    assert "reds on deletion/partial-revert of the exact clause it guards" in scope
    assert "vacuous pin = NO pin = stays P1" in scope
    assert re.search(r"[\"“]Could be stronger[\"”].*= P2", scope)
    assert "permutation/exclusivity/composed-order" in scope
    assert "EXCEPT on fail-closed gate surfaces" in scope
    assert "drive-conformance contracts, gate hooks, drive-retention safety clauses" in scope
    assert "exclusivity/composed-order gaps STAY P1" in scope


def test_r9_demotion_requires_shown_red_in_step3():
    """[M] Step 3: demoting a codex BLOCKING/MAJOR on pin depth requires SHOWING the
    executed core-mutation red — an executed artifact, not an assertion (preserves
    count-tags-not-prose). Mutation-verified: deleting the rule reds."""
    step3 = _norm(_section(_text(REVIEW), r"^## Step 3\b"))
    assert "Demoting a codex BLOCKING/MAJOR on pin depth" in step3
    assert "SHOWING the executed core-mutation red" in step3
    assert "not an assertion" in step3


def test_r9_pin_depth_per_ac_required_in_design_and_flagged_by_reviewers():
    """[S] drive-design.md's write list REQUIRES the `Pin depth per AC` section
    (mutation-verified vs smoke fixed at design time; token-sweep + green-full-suite as
    the default migration pattern), and BOTH phasedesign reviewer prompts flag P2 a phase
    design whose ACs lack the assignments."""
    scope = _norm(_scope_blocks(_text(DESIGN))[0])
    assert "Pin depth per AC" in scope and "REQUIRED section" in scope
    assert "mutation-verified" in scope and "smoke" in scope
    assert "gate-adjacent / fail-closed surfaces" in scope
    assert "token-sweep + green-full-suite" in scope
    review_scope = _norm(_scope_blocks(_text(REVIEW))[0])
    assert "flag P2 a phase design whose ACs lack the `Pin depth per AC` assignments" in review_scope
    heredoc = _norm(_review_prompt_heredoc())
    assert "flag P2 when the ACs lack the 'Pin depth per AC' assignments" in heredoc


# =========================================================================== #
# AC18 — drive-design.md detached-worktree guard repaired (A-D21)
# =========================================================================== #
def test_design_guard_compares_the_frozen_tip_sha():
    """[M] the drive-design.md subagent FIRST-ACTION guard compares `git rev-parse HEAD`
    to the passed frozen tip SHA; the invocation header names the worktree DETACHED and
    the coordinator passes the SHA. Mutation-verified: restoring the branch-name form
    reds (via the negative below)."""
    text = _text(DESIGN)
    header = _norm(text.split(BEGIN_SCOPE, 1)[0])
    assert "DETACHED at the `featureBranch` tip" in header
    assert re.search(r"git worktree add ?--detach", header) or "--detach" in header
    assert "frozen 40-hex tip SHA" in header or "frozen 40-hex `featureBranch` tip SHA" in header
    scope = _norm(_scope_blocks(text)[0])
    assert re.search(r"`git rev-parse HEAD` equals the frozen tip SHA", scope), (
        "the guard must compare rev-parse HEAD to the passed tip SHA"
    )
    assert "HEAD is not that SHA" in scope


def test_design_guard_has_no_branch_name_check():
    """[M] the NEGATIVE half (bound to drive-design.md ONLY — the implement/harden/
    finalize guards legitimately keep the branch-name form on their branch-checked-out
    worktrees): drive-design.md no longer requires `--abbrev-ref HEAD` to equal
    `featureBranch` — a check a detached HEAD can NEVER pass (it prints `HEAD`)."""
    assert "abbrev-ref" not in _text(DESIGN), (
        "drive-design.md must not carry an --abbrev-ref branch-name guard (detached worktree)"
    )
