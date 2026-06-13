"""Cross-file contract for the FINALIZE stage (Stage 4c) of /drive.

Phase 1 added `drive-finalize.md` + narrowed `drive-harden.md`; Phase 2 wired the
stage into drive.md, drive-ship.md, bin/drive-conformance.sh, bin/drive-merge-gate.sh,
and CLAUDE.md. These are PURE SPEC-PROSE pins (the script BEHAVIOR is covered by the
bash conformance suite, slice 3.1) so a later edit cannot silently drop the wiring.

Two anti-vacuity disciplines run throughout (per design D-P3-7):

1. SECTION-BOUNDED pins. `/drive-finalize` and `stage = finalize` also appear in
   drive.md's resume/recovery prose (drive.md:128/133/399-402), so a loose "appears
   somewhere" assertion passes vacuously even if the real Stage-4c dispatch / the
   Execute→Finalize transition is deleted. The Stage-4c tests therefore slice the
   `### Stage 4c — Finalize` section by its header anchor and the transition by its
   real line, and assert the token THERE.

2. PER-TOKEN REQUIRED-PRESENCE for cross-file token consistency (NOT exact-set-
   equality): each token must appear in its REQUIRED carrier files; extra occurrences
   elsewhere are tolerated (so a token legitimately gaining one more carrier never
   false-reds). Grounded by `grep -rln '<token>' .claude/commands/ bin/ CLAUDE.md`
   on the real worktree.

Each assertion PASSES on the current correct worktree and reds only on a real
regression — a dropped dispatch/transition, a re-applied harden de-slop lens, a
dropped artifact-contract clause, or a token drop/spelling-drift in a required carrier.
"""
import re

from _helpers import REPO_ROOT

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
COMMANDS = REPO_ROOT / ".claude" / "commands"
BIN = REPO_ROOT / "bin"

DRIVE_MD = COMMANDS / "drive.md"
DRIVE_HARDEN = COMMANDS / "drive-harden.md"
DRIVE_FINALIZE = COMMANDS / "drive-finalize.md"
DRIVE_SHIP = COMMANDS / "drive-ship.md"
CONFORMANCE = BIN / "drive-conformance.sh"
MERGE_GATE = BIN / "drive-merge-gate.sh"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# A genuine `/drive-<word>` SLASH-COMMAND token (NOT a `bin/drive-*` path substring).
# Mirrors test_drive_command_refs.py's proven negative-lookbehind so a buried path or
# code-fence path cannot false-pass.
_DRIVE_REF = re.compile(r"(?<![\w/])/drive-[a-z]+")


# --------------------------------------------------------------------------- #
# File-text accessors + helpers
# --------------------------------------------------------------------------- #
def _text(path):
    assert path.is_file(), f"expected file at {path}"
    return path.read_text(encoding="utf-8")


def _norm(text):
    """Collapse whitespace runs (incl. newlines) to a single space — robust to wrap/
    reflow but still load-bearing on the words."""
    return re.sub(r"\s+", " ", text)


def _section(text, header_re, *, stop_re=r"^#{1,4}\s"):
    """Slice the lines from the FIRST line matching `header_re` up to (excluding) the
    next line matching `stop_re` (another `#`..`####` markdown header) or EOF. Returns
    the section's text. Asserts the header exists so a renamed/removed header reds."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section header /{header_re}/ not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _slice_between(text, start_re, stop_re, *, inclusive_stop=False):
    """Slice from the FIRST line matching `start_re` up to the line matching `stop_re`
    (excluded by default; included when `inclusive_stop`). Asserts BOTH markers exist so
    deleting the start marker (e.g. the `Write ...:` schema header) OR the stop boundary
    reds. Used to pin a sub-block WITHIN an already-sliced section."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(start_re, ln)), None)
    assert start is not None, f"sub-block start /{start_re}/ not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        None,
    )
    assert end is not None, f"sub-block stop /{stop_re}/ not found after /{start_re}/"
    return "\n".join(lines[start : (end + 1 if inclusive_stop else end)])


# =========================================================================== #
# AC39 — finalize command exists with frontmatter; dispatched IN Stage 4c
# =========================================================================== #
def test_drive_finalize_command_exists_with_frontmatter():
    """`drive-finalize.md` exists, opens with a `---` frontmatter fence, and has a
    non-empty `description:` naming the finalize/aggregate stage. The FEATURE's own
    pin (belt-and-braces over test_drive_command_refs.py's generic frontmatter scan)."""
    assert DRIVE_FINALIZE.is_file(), f"drive-finalize.md missing at {DRIVE_FINALIZE}"
    lines = _text(DRIVE_FINALIZE).splitlines()
    assert lines and lines[0].strip() == "---", "drive-finalize.md must open with `---`"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    assert end is not None, "drive-finalize.md frontmatter not closed with `---`"
    desc = next((ln for ln in lines[1:end] if ln.startswith("description:")), None)
    assert desc is not None, "drive-finalize.md frontmatter has no `description:`"
    value = desc[len("description:"):].strip().lower()
    assert value, "drive-finalize.md `description:` is empty"
    assert "finalize" in value or "aggregate" in value, (
        f"description should name the finalize/aggregate stage; got: {value!r}"
    )


def test_drive_md_dispatches_drive_finalize_in_stage_4c():
    """`/drive-finalize` is wired as the actual Stage-4c DISPATCH, not merely mentioned
    in resume/recovery prose OR in the three OTHER in-section `/drive-finalize` mentions
    (the LEADS-with-de-slop wiring prose drive.md:985, the inflight-marker prose :994,
    and the FINDINGS re-invoke :1020). SECTION-BOUNDED to `### Stage 4c — Finalize`, then
    pin the DISTINCTIVE imperative dispatch construct: the initial `invoke /drive-finalize`
    that hands the stage its `cwd = $RUN_DIR/wt/finalize` AND `passing` the run args
    (drive.md:1011). The other three in-section mentions lack this `invoke ... cwd ...
    passing` shape — the re-invoke at :1020 is `re-invoke ... on the SAME ... worktree`
    with no `passing` clause — so deleting/rewording ONLY the real dispatch at :1011 reds
    this, while the prose mentions alone do NOT satisfy it. Pins AC39."""
    section = _section(_drive_md_text(), r"^###\s+Stage 4c\b")
    # Sanity: the section must NOT be satisfiable by the bare token alone — there are
    # multiple in-section `/drive-finalize` mentions, so a loose token check is vacuous.
    refs = _DRIVE_REF.findall(section)
    assert "/drive-finalize" in refs, (
        "the Stage 4c section must reference /drive-finalize; found refs in section: "
        f"{sorted(set(refs))}"
    )
    # The load-bearing pin: the initial dispatch construct. `invoke /drive-finalize`
    # (NOT `re-invoke`) ... `cwd = $RUN_DIR/wt/finalize` ... `passing` the run args, all
    # on one normalized stretch. Negative-lookbehind `(?<!re-)` excludes the :1020
    # re-invoke; the `passing` clause excludes the prose mentions at :985/:994.
    norm = _norm(section)
    dispatch = re.compile(
        r"(?<!re-)invoke\s+`?/drive-finalize`?\b.*?cwd\s*=\s*`?\$RUN_DIR/wt/finalize"
        r".*?\bpassing\b",
        re.IGNORECASE,
    )
    assert dispatch.search(norm), (
        "the Stage 4c section must carry the real DISPATCH of /drive-finalize "
        "(`invoke /drive-finalize ... with cwd = $RUN_DIR/wt/finalize ... passing "
        "<runId>, $RUN_DIR, baseRef, featureBranch`); the LEADS/inflight prose mentions "
        "and the FINDINGS `re-invoke` do NOT satisfy this — the initial dispatch was "
        "deleted or reworded"
    )


def _drive_md_text():
    return _text(DRIVE_MD)


# =========================================================================== #
# AC40 — Stage-4c placement: header, Execute→Finalize transition, run-graph order
# =========================================================================== #
def test_finalize_stage_4c_placement():
    """Three SECTION/LINE-BOUNDED pins so a regression that removes the real wiring
    reds even though the bare token survives in resume prose. Pins AC40."""
    text = _drive_md_text()

    # (a) the section header exists.
    assert re.search(r"^###\s+Stage 4c\b.*Finalize", text, re.MULTILINE), (
        "drive.md must have a `### Stage 4c — Finalize` section header"
    )

    # (b) the Execute->Finalize transition exists at its real site: a single line that
    # co-locates `all phases`, `hardened`, and `stage = finalize`. `stage = finalize`
    # alone also appears in the resume routing prose (drive.md:128/133) and step-6
    # (drive.md:974), so anchor on the transition's distinctive co-occurrence.
    transition = re.compile(
        r"all phases.*hardened.*stage\s*=\s*`?\s*finalize", re.IGNORECASE
    )
    assert any(transition.search(ln) for ln in text.splitlines()), (
        "drive.md must carry the Execute->Finalize transition on one line "
        "(`all phases ... hardened -> stage = finalize`); the bare `stage = finalize` "
        "token in resume prose does not satisfy this"
    )

    # (c) the run-graph stage-order line places Finalize between Execute and Verify.
    # Assert INDEX order on the rendered line, not a verbatim glyph match.
    order_line = next(
        (
            ln for ln in text.splitlines()
            if "Execute" in ln and "Finalize" in ln and "Verify" in ln
            and "Plan" in ln and "Ship" in ln
        ),
        None,
    )
    assert order_line is not None, (
        "drive.md must have the run-graph stage-order line "
        "(Premises ... Execute ... Finalize ... Verify ... Ship)"
    )
    i_exec = order_line.index("Execute")
    i_fin = order_line.index("Finalize")
    i_ver = order_line.index("Verify")
    assert i_exec < i_fin < i_ver, (
        f"run-graph order must be Execute < Finalize < Verify; got line: {order_line!r}"
    )


# =========================================================================== #
# AC41 — drive-harden narrowed to two correctness lenses; de-slop DEFERRED
# =========================================================================== #
def test_harden_narrowed_to_two_lenses():
    """drive-harden.md is narrowed: it DEFERS de-slop to `/drive-finalize`, keeps the
    two correctness lenses (add missing tests / fix logic bugs), and no longer instructs
    APPLYING a de-slop edit within harden. Anchors on stable directive tokens, not exact
    prose (OPERATING: structural over brittle-regex). Pins AC41."""
    text = _text(DRIVE_HARDEN)
    norm = _norm(text)

    # The lens DEFINITIONS are SECTION-BOUNDED to `## The two hardening lenses (+ a
    # deferred slop NOTE)` (drive-harden.md:45-62). The bare tokens (`/drive-finalize`,
    # `defer`, `add missing tests`, `fix logic`, `do NOT remove any slop`) all recur
    # elsewhere in the file (frontmatter/intro/Step-1 prompt/triage prose), so a
    # file-wide check stays GREEN even if the real lens defs are deleted. Slice the
    # section and pin the deferral NOTE + the two numbered correctness lenses THERE.
    lenses = _norm(_section(text, r"^##\s+The two hardening lenses\b"))

    # Deferral NOTE (lens-0): harden DEFERS slop to /drive-finalize, not a fix lens here.
    assert "/drive-finalize" in lenses, (
        "the two-lenses section must DEFER slop to /drive-finalize (the deferral NOTE)"
    )
    assert re.search(r"\bDEFER\b", lenses, re.IGNORECASE), (
        "the two-lenses section's slop NOTE must carry a `DEFER` directive to finalize"
    )

    # The two NUMBERED correctness lenses are defined THERE (stable directive tokens).
    assert re.search(r"1\.\s*\*?\*?[Aa]dd missing tests", lenses), (
        "harden lens 1 (`1. Add missing tests`) must be defined in the two-lenses section"
    )
    assert re.search(r"2\.\s*\*?\*?[Ff]ix logic", lenses), (
        "harden lens 2 (`2. Fix logic issues & bugs`) must be defined in the section"
    )

    # The narrowing directive: harden no longer REMOVES slop in-stage. The pre-narrowing
    # version applied slop as an active numbered lens; the narrowing replaced it with the
    # `no longer REMOVES slop` deferral. Pinned WITHIN the section so a re-introduced
    # active de-slop lens (which would rewrite this section) reds. The note literally
    # reads "no longer REMOVES slop".
    assert re.search(r"no longer\b.*\bREMOVES?\b.*slop", lenses, re.IGNORECASE) or re.search(
        r"do not remove any slop", lenses, re.IGNORECASE
    ), (
        "the two-lenses section must state harden no longer REMOVES slop in-stage "
        "(de-slop is deferred to finalize); a re-applied de-slop lens would drop this"
    )

    # ABSENCE check — the OLD active de-slop FIX-lens must be GONE (not merely deferred).
    # The pre-narrowing version carried slop as an active numbered apply-lens
    # (`## The three hardening lenses` / `1. **Reduce AI slop**` / a `3-lens` audit), all
    # of which the narrowing replaced with `## The two hardening lenses (+ a deferred slop
    # NOTE)` / a `2-lens` audit / a slop NOTE. Reintroducing the slop-as-a-fix lens while
    # KEEPING the `do NOT remove any slop` deferral sentence (which the presence checks
    # above accept) must RED here. These phrases were ACTIVE-APPLY constructs, NOT the
    # deferral mentions (`do NOT remove any slop`, `DEFER to /drive-finalize`, `## slop
    # (deferred to finalize)`), so this targets only the regressed active lens.
    assert not re.search(r"\bReduce AI slop\b", norm, re.IGNORECASE), (
        "drive-harden.md must NOT carry the OLD active de-slop fix-lens "
        "(`**Reduce AI slop**`); de-slop is DEFERRED to /drive-finalize, not applied "
        "in-stage — this is a re-introduced slop-as-a-fix lens"
    )
    assert not re.search(r"\bthree hardening lenses\b", norm, re.IGNORECASE), (
        "drive-harden.md must NOT advertise THREE hardening lenses (the narrowed stage "
        "has TWO correctness lenses + a deferred slop NOTE); a third active lens is the "
        "regressed de-slop lens"
    )
    assert not re.search(r"\b3-lens\b", norm, re.IGNORECASE), (
        "drive-harden.md's audit must be a 2-lens (+ slop-note) audit, not the OLD "
        "`3-lens` audit that applied de-slop in-stage"
    )


# =========================================================================== #
# AC42 — drive-finalize artifact + scope-gate + cap + regression-guard contract
# =========================================================================== #
def test_finalize_emits_shipgate_artifact_contract():
    """drive-finalize.md states the ship-gate artifact contract: `review-finalize-N.md`
    + `## AppliedEdits:` marker + a `reviewed-sha` bound to the featureBranch tip + the
    `codex-review-finalize.md` sibling + `codex-raw-finalize.log` per-scope log + the
    `CODEX_UNAVAILABLE` degradation + `FINALIZE_CAP = 3` / `finalizeRound` + the full-suite
    regression guard with REVERT-on-red. Pins AC42 (artifact half)."""
    text = _text(DRIVE_FINALIZE)
    norm = _norm(text)

    # ---- artifact SCHEMA, SECTION-BOUNDED to `## Step 1 — Audit`. -------------------- #
    # The real artifact-schema block (the `Write $RUN_DIR/review-finalize-N.md:` listing,
    # the `## AppliedEdits:` marker, the reviewed-sha binding paragraph, the codex sibling
    # + raw log + CODEX_UNAVAILABLE degradation) all live in Step 1 (drive-finalize.md:
    # 152-238). The same tokens recur file-wide (the Loop-counter §128-149, the three-lenses
    # §, Step-4 §339-347), so a file-wide check stays GREEN if the real Step-1 schema is
    # deleted. Slice Step 1 and assert the schema THERE.
    step1 = _section(text, r"^##\s+Step 1\b.*Audit")
    step1_norm = _norm(step1)

    # The schema-block tokens (`review-finalize-N.md`, the `## AppliedEdits:` marker, the
    # `reviewed-sha: <40-hex>` line, the codex sibling/raw-log/CODEX_UNAVAILABLE) recur ELSE-
    # WHERE within Step 1 itself — the binding paragraph (:208-219), the degradation paragraph
    # (:232-237), and the post-process prose — so a Step-1-wide check stays GREEN even if the
    # real artifact-SCHEMA listing / exec command block is deleted. Slice the two distinctive
    # sub-blocks WITHIN Step 1 and pin each token THERE:
    #   (a) the `Write $RUN_DIR/review-finalize-N.md:` schema enumeration (:197-203), and
    #   (b) the codex `codex exec ... > $RUN_DIR/codex-raw-finalize.log` command + its post-
    #       process target `codex-review-finalize.md` (:224-230).
    schema = _norm(_slice_between(step1, r"Write\s+`?\$RUN_DIR/review-finalize-N\.md", r"^CONVERGED\b"))
    codex_block = _norm(
        _slice_between(step1, r"^```\s*$", r"codex-review-finalize\.md", inclusive_stop=True)
    )

    assert "review-finalize-N.md" in schema, (
        "Step 1's artifact-SCHEMA block (`Write $RUN_DIR/review-finalize-N.md:`) must name "
        "the review-finalize-N.md artifact it WRITES; the binding/degradation prose elsewhere "
        "in Step 1 does NOT satisfy this"
    )
    assert "## AppliedEdits:" in schema, (
        "Step 1's artifact SCHEMA block must carry the `## AppliedEdits:` marker line"
    )
    # The schema's literal `reviewed-sha: <40-hex>` line (NOT the binding-paragraph prose,
    # which the section-wide check accepted vacuously). Pin the schema-line form.
    assert re.search(r"reviewed-sha:\s*<40-hex>", schema), (
        "Step 1's artifact SCHEMA block must carry the `reviewed-sha: <40-hex>` line "
        "(the per-round binding line the ship gate reads); the binding-paragraph prose "
        "elsewhere in Step 1 does NOT satisfy this"
    )
    # reviewed-sha bound to the featureBranch tip — the LOAD-BEARING binding clause in Step 1
    # is the `git rev-parse <featureBranch>` COMMAND that produces the sha. The prose phrase
    # "featureBranch tip" recurs incidentally in Step 1 (a benign-prose match would make this
    # vacuous), so pin ONLY the rev-parse-featureBranch construct — deleting the binding
    # paragraph's `git rev-parse <featureBranch>` then reds.
    assert re.search(r"rev-parse\s+<?\s*`?featureBranch", step1_norm), (
        "Step 1's reviewed-sha must bind to `git rev-parse <featureBranch>` (the binding "
        "command that yields the post-fix tip the ship gate reads)"
    )
    # The codex command block (the `codex exec ... > $RUN_DIR/codex-raw-finalize.log` exec
    # redirection) + its post-process target `codex-review-finalize.md`, pinned to the fenced
    # command block + its immediate post-process sentence, so deleting the exec redirection
    # path or the post-process target reds (the degradation paragraph's mentions do NOT).
    assert "codex-raw-finalize.log" in codex_block, (
        "Step 1's codex exec command must redirect to `$RUN_DIR/codex-raw-finalize.log` "
        "(the per-scope raw codex log); the degradation prose mention does NOT satisfy this"
    )
    assert "codex-review-finalize.md" in codex_block, (
        "Step 1's codex post-process must write `$RUN_DIR/codex-review-finalize.md` (the "
        "codex sibling); the degradation prose mention does NOT satisfy this"
    )
    assert "CODEX_UNAVAILABLE" in step1_norm, (
        "Step 1's codex degradation must emit the CODEX_UNAVAILABLE token"
    )

    # FINALIZE_CAP / finalizeRound are defined in `## Loop counter & cap`, not Step 1 — pin
    # them there (section-bounded), so deleting the cap section reds.
    cap = _norm(_section(text, r"^##\s+Loop counter\b"))
    assert re.search(r"FINALIZE_CAP\s*=\s*3", cap), "the cap section must define FINALIZE_CAP = 3"
    assert "finalizeRound" in cap, "the cap section must define the finalizeRound counter"

    # Full-suite regression guard with revert-on-red — SECTION-BOUNDED to `## Step 4 —
    # Regression guard & converge`. A loose file-wide `full...suite` + `REVERT` is vacuous:
    # `full suite` appears in Step-3's prose and `REVERT` in the lens-1 de-slop prose, so
    # deleting the REAL Step-4 guard clause (the post-fix full-suite re-run that REVERTs a
    # de-slop edit which reds a test) would stay green. Slice Step 4 and assert the guard's
    # load-bearing co-occurrence THERE: the FULL suite re-run AS the regression guard, and
    # the revert-on-red rule (a reddened test → REVERT the edit, do NOT edit the test).
    step4 = _norm(_section(text, r"^##\s+Step 4\b.*Regression guard"))
    # The full-suite re-run that IS the regression guard (not Step-3's plain "run the suite").
    assert re.search(r"FULL\s+suite\b.*\bregression guard", step4, re.IGNORECASE), (
        "Step 4 must run the driven project's FULL suite AS the regression guard after a "
        "fix round; deleting/weakening this Step-4 clause must red (a file-wide `full "
        "suite` mention elsewhere does NOT satisfy it)"
    )
    # The revert-on-red rule, co-located in Step 4: a de-slop edit that reds a test is a
    # REAL REGRESSION → REVERT it, and explicitly NOT reconcile by editing the test.
    assert re.search(r"reddened\b.*\bREVERT\b", step4), (
        "Step 4's regression guard must REVERT the offending edit when a test reds "
        "(a real regression), not reconcile by editing the test"
    )
    assert re.search(r"do not reconcile by editing the test", step4, re.IGNORECASE), (
        "Step 4 must forbid reconciling a reddened test by editing the test "
        "(the load-bearing revert-on-red discipline)"
    )


def test_finalize_scope_creep_gate_and_arch_todo():
    """drive-finalize.md states: the diff scope `baseRef..featureBranch`, the edit-scope
    HARD GATE (run diff + test-support + flagged-P1 root cause), the three lenses (de-slop
    LED + aggregate tests + aggregate bugs), and the `$RUN_DIR/finalize-todo.md` ->
    repo-root `TODO.md` architectural route (NOT a `wt/finalize/TODO.md`). Pins AC42
    (scope/gate/arch half)."""
    text = _text(DRIVE_FINALIZE)
    norm = _norm(text)

    # The diff-scope clause, SECTION-BOUNDED to `## Scope (READ vs EDIT)` (drive-finalize.md:
    # 47-52). `baseRef..featureBranch` recurs later (the HARD GATE §, Step 1's audit prompt),
    # so a file-wide check stays GREEN even if the real `## Scope` section is deleted. Slice
    # it and pin the diff-scope definition + its "derive from git, never an implementer list"
    # discipline THERE.
    scope = _norm(_section(text, r"^##\s+Scope\b.*READ vs EDIT"))
    assert "baseRef..featureBranch" in scope or re.search(
        r"git diff\s+<?baseRef>?\.\.<?featureBranch", scope
    ), "the Scope section must define the diff scope as `git diff baseRef..featureBranch`"
    assert re.search(r"never an implementer list", scope, re.IGNORECASE) or re.search(
        r"authoritatively from git", scope, re.IGNORECASE
    ), (
        "the Scope section must derive the diff authoritatively from git "
        "(never an implementer list) — the load-bearing diff-scope discipline"
    )
    assert "HARD GATE" in text, "the edit-scope HARD GATE"

    # ---- LOAD-BEARING scope-creep clauses (section-bounded to the HARD GATE). --------- #
    # Not the bare `HARD GATE` heading: pin the actual edit-scope allowances/exceptions
    # that make the gate load-bearing, so dropping them reds. Slice the gate section so a
    # match elsewhere can't false-pass.
    gate = _norm(_section(text, r"^##\s+Scope-creep HARD GATE\b"))
    # Allowed: the run's own diff surface.
    assert re.search(r"files in `?git diff", gate), (
        "the gate must allow editing the run's own diff surface (git diff baseRef..featureBranch)"
    )
    # Allowed: existing test-support (fixtures/harnesses) — a load-bearing allowance.
    assert re.search(r"test-support\b.*\(.*fixtures", gate, re.IGNORECASE) or re.search(
        r"existing\b.*\btest-support", gate, re.IGNORECASE
    ), "the gate must allow EXISTING test-support (fixtures/harnesses) for coverage"
    # Exception: a file JUST OUTSIDE the diff iff it is the true root cause of a flagged P1.
    assert re.search(r"just outside\b.*diff", gate, re.IGNORECASE), (
        "the gate must carry the `just outside the diff` exception"
    )
    assert re.search(r"flagged\b[^.]*\bP1\b", gate, re.IGNORECASE), (
        "the out-of-diff exception must be gated on a FLAGGED P1 root cause"
    )
    assert re.search(r"log it to\b.*decisions\.md", gate, re.IGNORECASE) or re.search(
        r"\$RUN_DIR/decisions\.md", gate
    ), "widening scope for the flagged-P1 exception must be LOGGED to $RUN_DIR/decisions.md"
    # Forbidden: a refactor/taste edit without a flagged P1, and editing untouched user code.
    assert re.search(r"[Ff]orbidden", gate), "the gate must state what is FORBIDDEN"
    assert re.search(r"refactor\b.*without a flagged\b[^.]*\bP1", gate, re.IGNORECASE), (
        "forbidden: a refactor/taste edit WITHOUT a flagged P1"
    )

    # Three lenses, de-slop LED — SECTION-BOUNDED to `## The three lenses`. The bare
    # tokens `de-slop` (x14), `missing test`, `logic bug` are spread file-wide (Step-1/
    # Step-2 prose), so a norm-wide check stays green even if the real `## The three lenses`
    # section is deleted. Slice the section and pin the three NUMBERED lens definitions THERE
    # (de-slop LED as lens 1; aggregate missing tests as lens 2; aggregate logic bugs as
    # lens 3), so dropping/renumbering a lens reds.
    lenses = _norm(_section(text, r"^##\s+The three lenses\b"))
    assert re.search(r"1\.\s*\*?\*?de-slop\b.*\bLED\b", lenses, re.IGNORECASE), (
        "lens 1 must be de-slop, LED (the lens harden defers here)"
    )
    assert re.search(r"2\.\s*\*?\*?aggregate missing tests", lenses, re.IGNORECASE), (
        "lens 2 must be the aggregate missing-tests lens"
    )
    assert re.search(r"3\.\s*\*?\*?aggregate logic bugs", lenses, re.IGNORECASE), (
        "lens 3 must be the aggregate logic-bugs lens"
    )
    # Architectural findings route: durable finalize-todo.md, promoted to repo-root TODO.md.
    # SECTION-BOUNDED to `## Architectural findings → durable $RUN_DIR/finalize-todo.md`
    # (drive-finalize.md:107). The bare tokens `finalize-todo.md` / `TODO.md` recur in Step 3,
    # the Loop-counter §, and the Phase-2 obligations note, so a file-wide check stays GREEN
    # even if the real routing section is deleted. Slice it and pin its load-bearing clauses
    # THERE: finalize APPENDS findings to $RUN_DIR/finalize-todo.md, and NEVER writes/commits
    # any project TODO.md.
    arch = _norm(_section(text, r"^##\s+Architectural findings\b"))
    assert "finalize-todo.md" in arch, (
        "the Architectural-findings section must route findings to $RUN_DIR/finalize-todo.md"
    )
    assert re.search(r"\bAPPENDS?\b.*finalize-todo\.md", arch, re.IGNORECASE), (
        "the section must state finalize APPENDS the finding to $RUN_DIR/finalize-todo.md"
    )
    # NOT a finalize working-tree TODO.md (the broken design D10 ruled out) — the load-bearing
    # negative clause, pinned WITHIN this section so deleting it reds.
    assert re.search(r"NEVER writes or commits any project `?TODO\.md`?", arch), (
        "the Architectural-findings section must state finalize NEVER writes or commits any "
        "project TODO.md (architectural findings go to $RUN_DIR/finalize-todo.md, not a "
        "wt/finalize/TODO.md)"
    )


# =========================================================================== #
# AC43 — drive-ship precondition/promotion + CLAUDE.md pipeline/invariant
# =========================================================================== #
def test_ship_spec_finalize_precondition_and_promotion():
    """drive-ship.md: a Finalize-CONVERGED precondition that is TOLERANT (NOT strict
    `== tip`), remediation that names `/drive-finalize`, promotion of `finalize-todo.md`
    -> `TODO.md`, and the 3-entry `SHIP_LEDGER_ALLOWLIST` surfaced at Gate B. Pins AC43
    (ship half)."""
    text = _text(DRIVE_SHIP)
    norm = _norm(text)

    assert re.search(r"Finalize CONVERGED", norm, re.IGNORECASE), (
        "ship must gate a Finalize-CONVERGED precondition"
    )
    assert "/drive-finalize" in norm, "ship remediation must name /drive-finalize"

    # ---- (a) the TOLERANT finalize-CONVERGED precondition #3, SECTION-BOUNDED. -------- #
    # Bound to `## Preconditions` and pin the SPECIFIC tolerant test: the finalize
    # artifact's `reviewed-sha R` is an ANCESTOR of the featureBranch tip with `R..tip` ≤1
    # commit ⊆ the ledger allowlist — NOT strict `== tip`. A bare `ancestor` mention is
    # vacuous (it also appears in the `## Ship conformance` prose); pin the precondition's
    # load-bearing co-occurrence: the finalize artifact + ancestor-of-tip + the ≤1-commit
    # allowlist tolerance, so weakening precondition #3 to strict `== tip` (or dropping the
    # ancestor/≤1-commit tolerance) reds.
    pre = _norm(_section(text, r"^##\s+Preconditions\b"))
    assert "review-finalize-N.md" in pre, (
        "precondition #3 must name the run's terminal review-finalize-N.md artifact"
    )
    assert re.search(
        r"reviewed-sha\s+R\b.*\bANCESTOR\b.*featureBranch.*tip", pre, re.IGNORECASE
    ), (
        "precondition #3 must require finalize's `reviewed-sha R` be an ANCESTOR of the "
        "featureBranch tip (the tolerant test, not strict == tip)"
    )
    assert re.search(r"R\.\.tip\b.*≤1\s*commit|R\.\.tip\b.*<=?\s*1\s*commit", pre), (
        "precondition #3's tolerance must bound `R..tip` to ≤1 commit ⊆ the ledger allowlist"
    )
    assert re.search(r"strict\b.*==\s*tip\b.*FALSE-STOP", pre, re.IGNORECASE) or re.search(
        r"TOLERATE\b.*ledger commit", pre, re.IGNORECASE
    ), (
        "precondition #3 must EXPLICITLY tolerate the one post-ledger commit (strict == "
        "tip would FALSE-STOP a resumed ship); weakening it to strict == tip must red"
    )

    # ---- ledger promotion + 3-entry allowlist. ---------------------------------------- #
    # SECTION-BOUNDED to `## Ship worktree + ledger promotion` (drive-ship.md:41). The bare
    # tokens (`finalize-todo.md`, `TODO.md`, `SHIP_LEDGER_ALLOWLIST`, `.harness/...`) recur in
    # `## Build the PR` + `## Ship conformance`, so a file-wide check stays GREEN even if the
    # real promotion paragraph (drive-ship.md:44-62) is deleted. Slice the promotion section
    # and pin the promotion clause THERE.
    promo = _norm(_section(text, r"^##\s+Ship worktree \+ ledger promotion\b"))
    assert re.search(
        r"finalize-todo\.md\b.*(promote|into).*\brepo-root `?TODO\.md", promo, re.IGNORECASE
    ) or re.search(
        r"promote\b.*finalize-todo\.md\b.*\bTODO\.md", promo, re.IGNORECASE
    ), (
        "the ledger-promotion section must promote $RUN_DIR/finalize-todo.md -> the repo-root "
        "TODO.md; the Build-the-PR / conformance mentions of these tokens do NOT satisfy this"
    )
    assert "SHIP_LEDGER_ALLOWLIST" in promo, (
        "the ledger-promotion section must name the SHIP_LEDGER_ALLOWLIST constant it keeps "
        "in sync (the single ledger commit's allowlist)"
    )
    # The 3-entry allowlist contents, pinned WITHIN the promotion section.
    assert (
        "TODO.md" in promo and ".harness/decisions.md" in promo and ".harness/followups.md" in promo
    ), "the 3-entry ledger allowlist {.harness/decisions.md, .harness/followups.md, TODO.md}"
    # And the SINGLE-commit discipline (the promotion lands in the one ledger commit).
    assert re.search(r"SINGLE commit\b|single commit\b", promo), (
        "the promotion must land in the SINGLE ledger commit (R..tip ≤1 commit ⊆ allowlist)"
    )

    # ---- (b) the finalize-todo Gate-B SURFACING bullet, SECTION-BOUNDED. -------------- #
    # `"Gate B" in text` is vacuous — `## Gate B` is its own section + the constant appears
    # in conformance prose. Pin the SPECIFIC bullet (in `## Build the PR`) that surfaces
    # $RUN_DIR/finalize-todo.md's architectural follow-ups from the DURABLE $RUN_DIR copy
    # before approving the push at Gate B, so deleting that bullet reds.
    build = _norm(_section(text, r"^##\s+Build the PR\b"))
    assert re.search(
        r"finalize-todo\.md\b.*surface.*architectural follow-ups", build, re.IGNORECASE
    ) or re.search(
        r"surface.*finalize-todo\.md.*architectural follow-ups", build, re.IGNORECASE
    ), (
        "Build-the-PR must surface $RUN_DIR/finalize-todo.md's architectural follow-ups "
        "before Gate B (the specific finalize-todo surfacing bullet)"
    )
    assert re.search(r"Gate B", build), (
        "the finalize-todo surfacing must be tied to Gate B (before approving the push)"
    )
    # And the durable-$RUN_DIR-copy source (NOT the worktree) is load-bearing: the ship
    # worktree is rebuilt from the tip and never carries finalize-todo.md.
    assert re.search(r"\$RUN_DIR\b.*copy|durable\b.*\$RUN_DIR", build, re.IGNORECASE), (
        "the surfacing must read finalize-todo.md from the durable $RUN_DIR copy "
        "(not the ship worktree, which does not carry it)"
    )


def test_claudemd_pipeline_and_invariant():
    """LOAD-BEARING pin of the real CLAUDE.md finalize contract — not bare token presence.
    Three regression-tight assertions, each grounded against the live CLAUDE.md and each
    RED on a real drift:

    (i)  the numbered Pipeline lists `/drive-finalize` ORDERED between harden and verify
         (a step number > harden's and < verify's — order-bounded, so reordering or
         dropping the finalize step reds, where a bare token would not);
    (ii) the FINALIZE invariant is omission-proof (ship's terminal SHA-bound artifact IS
         the finalize review; a run that omits finalize CANNOT ship) WITH cap 3 + counter;
    (iii)the harden artifact/lens descriptions are CONSISTENT with the 2-lens model — the
         old `3-lens`/`three hardening lenses`/active `Reduce AI slop` constructs are
         ABSENT (so the 3-lens drift this test was blind to can never recur).

    Pins AC43 (CLAUDE.md half)."""
    text = _text(CLAUDE_MD)
    norm = _norm(text)
    lines = text.splitlines()

    # ---- (i) ORDERED pipeline: harden < finalize < verify by NUMBERED step. ---------- #
    # The Pipeline block is a numbered list (`5. /drive-harden`, `6. /drive-finalize`,
    # `7. verify`). Parse the step NUMBER that introduces each stage and assert the order,
    # so a finalize step that is dropped or moved out from between harden and verify reds —
    # a bare `Stage 4c` / `/drive-finalize` token cannot satisfy this.
    def _step_no(stage_re):
        for ln in lines:
            m = re.match(r"\s*(\d+)\.\s", ln)
            if m and re.search(stage_re, ln):
                return int(m.group(1))
        return None

    n_harden = _step_no(r"/drive-harden\b")
    n_finalize = _step_no(r"/drive-finalize\b")
    n_verify = _step_no(r"^\s*\d+\.\s*verify\b")
    assert n_harden is not None, "Pipeline must have a numbered /drive-harden step"
    assert n_finalize is not None, "Pipeline must have a numbered /drive-finalize step"
    assert n_verify is not None, "Pipeline must have a numbered verify step"
    assert n_harden < n_finalize < n_verify, (
        f"Pipeline order must be harden({n_harden}) < finalize({n_finalize}) < "
        f"verify({n_verify}); /drive-finalize must sit BETWEEN harden and verify"
    )
    assert re.search(r"Stage 4c", norm), "CLAUDE.md must place finalize as Stage 4c"

    # Harden's stage description defers de-slop to finalize (not applied in harden).
    # SECTION-BOUNDED to the `Each phase ends with a HARDEN pass` invariant bullet (up to the
    # next top-level `- **` bullet). A file-wide `defer.*de-slop.*finalize` is VACUOUS: `norm`
    # is the whole file collapsed to one line, so the alternation spans CLAUDE.md:38's
    # unrelated "DEFERRED ... /drive-finalize" across to a distant "de-slop"/"finalize" and
    # stays GREEN even if the harden bullet's own deferral clause is deleted. Slice the HARDEN
    # bullet and pin the deferral THERE.
    harden_bullet = _norm(_slice_between(text, r"Each phase ends with a HARDEN pass", r"^- \*\*"))
    assert re.search(r"de-slop is [Dd]eferred to `?/drive-finalize`?", harden_bullet), (
        "CLAUDE.md's HARDEN-pass invariant bullet must state de-slop is deferred to "
        "/drive-finalize (a file-wide defer/finalize co-occurrence elsewhere does NOT "
        "satisfy this)"
    )

    # ---- (ii) FINALIZE invariant is OMISSION-PROOF (the load-bearing property). ------- #
    # Not just the token `omission-`: the invariant must state that ship's terminal/
    # tip-binding artifact IS the finalize review, so a run that omits finalize CANNOT
    # ship. Pin the causal clause, not a loose word.
    assert re.search(
        r"omits .*finalize\b.*\bCANNOT ship", norm, re.IGNORECASE
    ), "the omission-proof property (a run that omits/fails finalize CANNOT ship)"
    assert re.search(
        r"\bTERMINAL\b.*review-finalize-N\.md|review-finalize-N\.md.*tip-binding",
        norm,
        re.IGNORECASE,
    ), "ship's terminal SHA-bound review must BE the finalize artifact (tip-binding)"
    # The cap + counter must be pinned to the FINALIZE invariant BULLET, not file-wide:
    # `finalizeRound` recurs in the `## Run state` inventory (CLAUDE.md:171) and `FINALIZE_CAP`
    # could be defined elsewhere, so a norm-wide check stays GREEN even if the invariant's own
    # `Own cap FINALIZE_CAP=3 ... counter state.finalizeRound` line is deleted. Slice the
    # FINALIZE bullet (`- **The run ends with a single FINALIZE pass**` up to the next
    # top-level `- **` bullet) and assert the cap/counter THERE.
    finalize_inv = _norm(_slice_between(text, r"single FINALIZE pass", r"^- \*\*"))
    assert re.search(r"FINALIZE_CAP\s*=\s*3", finalize_inv), (
        "the FINALIZE invariant bullet must state its own cap FINALIZE_CAP = 3 (a file-wide "
        "occurrence elsewhere does NOT satisfy this)"
    )
    assert "finalizeRound" in finalize_inv, (
        "the FINALIZE invariant bullet must name the state.finalizeRound counter (the "
        "run-state inventory mention does NOT satisfy this)"
    )

    # ---- (iii) harden 2-lens CONSISTENCY — the 3-lens drift cannot recur. ------------ #
    # The harden artifact ledger entry must describe a 2-lens audit (the narrowed model),
    # and the OLD 3-lens / three-lenses / active de-slop-lens constructs must be ABSENT.
    assert re.search(r"harden-<P>-N\.md\b[^\n]*\b2-lens\b", text), (
        "the harden artifact entry must describe a 2-lens audit (the narrowed model), "
        "not the OLD 3-lens audit"
    )
    assert not re.search(r"\b3-lens\b", norm), (
        "CLAUDE.md must NOT describe a 3-lens harden audit (harden was narrowed to two "
        "correctness lenses; de-slop deferred to /drive-finalize)"
    )
    assert not re.search(r"\bthree hardening lenses\b", norm, re.IGNORECASE), (
        "CLAUDE.md must NOT advertise THREE hardening lenses"
    )

    # Run-state lists the finalize artifacts — SECTION-BOUNDED to `## Run state & shared
    # memory`. The bare tokens recur in the FINALIZE invariant above (`review-finalize-N.md`
    # at CLAUDE.md:135, `finalize-todo` / `finalizeRound` in the same invariant), so a
    # file-wide check stays GREEN even if the real run-state inventory drops the finalize
    # entries. Slice the run-state section and pin the inventory THERE. NOTE: run-state
    # represents the finalize REVIEW via the collapsed `review-<scope>-N.md` family whose
    # scope list includes `finalize` (NOT a literal `review-finalize-N.md`), so assert that
    # collapsed-family form, not the invariant's literal.
    runstate = _norm(_section(text, r"^##\s+Run state\b"))
    assert re.search(
        r"review-<scope>-N\.md\b[^\n]*\bfinalize\b", _section(text, r"^##\s+Run state\b")
    ), (
        "the Run-state section must list the finalize review via the `review-<scope>-N.md` "
        "family whose scope list includes `finalize` (the run-state inventory entry, NOT "
        "the invariant's literal review-finalize-N.md)"
    )
    assert "finalize-todo.md" in runstate, "Run-state must list finalize-todo.md"
    assert "inflight-finalize" in runstate, (
        "Run-state must mention the inflight-finalize marker"
    )


# =========================================================================== #
# AC44 — finalize-token consistency: PER-TOKEN REQUIRED-PRESENCE (not set-equality)
# =========================================================================== #
# Required carrier sets, grounded by `grep -rln '<token>' .claude/commands/ bin/ CLAUDE.md`
# on the real worktree. EXTRA occurrences elsewhere are tolerated (a superset is fine).
_REQUIRED_CARRIERS = {
    # The dispatch marker: owned by the coordinator (drive.md) + documented in CLAUDE.md's
    # run-state. drive-finalize.md / conformance.sh do NOT reference it.
    "inflight-finalize": (DRIVE_MD, CLAUDE_MD),
    # The state field: read/written by every consumer.
    "finalizeRound": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE, CLAUDE_MD),
    # The review-scope token: all six genuinely carry it (the merge-gate emits the
    # review-finalize-N.md remediation).
    "review-finalize": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE, DRIVE_SHIP, MERGE_GATE, CLAUDE_MD),
    # The exact `## AppliedEdits: yes` literal (heading prefix + `: yes` value). NOT
    # drive-harden.md (carries `## AppliedEdits: pending` + an inline non-`##`
    # `AppliedEdits: yes` only); NOT CLAUDE.md (never the literal heading). Requiring
    # either would red on correct code.
    "## AppliedEdits: yes": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE),
}


def test_finalize_token_consistency_across_files():
    """Each load-bearing finalize token appears, spelled IDENTICALLY (the byte-literal
    token), in every REQUIRED carrier file. Asserted as PER-TOKEN REQUIRED-PRESENCE: each
    required carrier MUST contain the literal; extra occurrences elsewhere are tolerated.
    NOT exact-set-equality (which reds on correct code the moment a token legitimately
    appears in one more file). Passes on the current worktree; reds when a required
    carrier drops the token or drifts its spelling. Pins AC44."""
    for token, required in _REQUIRED_CARRIERS.items():
        missing = [p.name for p in required if token not in _text(p)]
        assert not missing, (
            f"token {token!r} is REQUIRED in {[p.name for p in required]} but is "
            f"missing from {missing} (a drop or spelling-drift in a required carrier)"
        )
