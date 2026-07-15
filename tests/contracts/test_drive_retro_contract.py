"""Contract pins for `.claude/commands/drive-retro.md` (the /drive-retro RETRO pass).

Slice 2.1 of the TR-3 spike: the command file IS the production artifact (no shipped
code), so these are SPEC-PROSE pins over its load-bearing clauses — the proposals-only
invariant, the single-output-path clause, the tolerant-parse/no-line-split contract,
the completeness gate, STOP-on-ambiguity, the READ-ONLY dedup-references class, and the
unified extraction rule (Rule U). Every pin is SECTION-BOUND (located within its named
`## N —` section or anchor paragraph, never a whole-file grep) so a clause moving out
of its governing section — or being deleted while its tokens survive elsewhere — reds.

drive-retro.md rides the existing frontmatter glob in test_drive_command_refs.py
(`drive*.md`); this file pins only what that suite does not.
"""
import re

from _helpers import REPO_ROOT

RETRO_MD = REPO_ROOT / ".claude" / "commands" / "drive-retro.md"


def _text():
    assert RETRO_MD.is_file(), f"expected command file at {RETRO_MD}"
    return RETRO_MD.read_text(encoding="utf-8")


def _norm(text):
    """Collapse whitespace runs to one space — robust to wrap/reflow, load-bearing on words."""
    return re.sub(r"\s+", " ", text)


def _section(text, header_re, *, stop_re=r"^#{1,2}\s"):
    """Lines from the FIRST match of `header_re` up to the next `#`/`##` header or EOF.
    Asserts the header exists so a renamed/removed section reds."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section header /{header_re}/ not found in drive-retro.md"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        len(lines),
    )
    return "\n".join(lines[start:end])


# --------------------------------------------------------------------------- #
# AC1 — frontmatter + not-a-pipeline-stage
# --------------------------------------------------------------------------- #
def test_frontmatter_argument_hint_is_runid():
    """The shared drive*.md glob test pins description:; the <runId> hint is ours."""
    lines = _text().splitlines()
    assert lines[0].strip() == "---"
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    hint = next((ln for ln in lines[1:end] if ln.startswith("argument-hint:")), None)
    assert hint is not None and hint.split(":", 1)[1].strip() == "<runId>"


def test_drive_retro_frontmatter_invocation_status():
    """AC6: the frontmatter description must drop the now-false v1-manual claims and carry the
    accurate auto-invoked status (regression guard for the D4 status refresh)."""
    text = (REPO_ROOT / ".claude" / "commands" / "drive-retro.md").read_text(encoding="utf-8")
    # the frontmatter description line
    m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    assert m, "drive-retro.md must have a frontmatter description"
    desc = m.group(1)
    # removed now-false claims
    assert "manual, operator-invoked" not in desc, "stale 'manual, operator-invoked' claim must be gone"
    assert "Not invoked by /drive" not in desc, "stale 'Not invoked by /drive (v1)' claim must be gone"
    # accurate new status
    assert "Auto-invoked by /drive" in desc, "description must state retro is auto-invoked by /drive at the true run-wrap"
    assert "still operator-invocable" in desc, "description must state retro is still operator-invocable"
    assert "completed-run-only" in desc, "description must state retro is completed-run-only"
    assert "single-run" in desc, "description must state retro is single-run"


def _drive_md():
    return (REPO_ROOT / ".claude" / "commands" / "drive.md").read_text(encoding="utf-8")


def _drive_section(text, header_re, stop_re):
    """Normalized text of the section matched by `header_re` up to the next `stop_re`."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"drive.md section /{header_re}/ not found"
    end = next((j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
               len(lines))
    return re.sub(r"\s+", " ", "\n".join(lines[start:end]))


def test_drive_md_wires_retro_into_completion_before_decant():
    """Wiring pin (inverts + strengthens the former negative pin). Anchored to the ACTUAL
    invocation/route text so it cannot pass vacuously and reds under mutation:
    (1) `## Completion` defines the wrap — the `/drive-retro <runId>` INVOCATION (not the
        possessive `retro`) ORDERED before the wrap-`/decant`, gated on the terminal-done signal;
    (2) the resume Done-via-resume teardown runs the wrap BEFORE it writes `stage="done"` LAST
        (the pre-done, stop-hook-forced window);
    (3) Stage 5's ship routes into `## Completion`.
    Mutation checks (design-verified): deleting the teardown wrap step, reordering it after the
    `stage="done"` write, or deleting the Stage 5 route each RED this test."""
    text = _drive_md()
    # (1) Completion defines the ordered, done-gated wrap sequence
    comp = _drive_section(text, r"^## Completion\b", r"^#{1,2}\s")
    r_idx = comp.find("/drive-retro <runId>")   # the INVOCATION, not "retro's ..." possessive
    d_idx = comp.find("/decant")
    assert r_idx >= 0, "`## Completion` must invoke `/drive-retro <runId>`"
    assert d_idx >= 0, "`## Completion` must name the wrap-/decant"
    assert r_idx < d_idx, "the /drive-retro <runId> invocation must precede the wrap-/decant"
    assert comp.count("/drive-retro <runId>") == 1, (
        "the /drive-retro <runId> invocation must appear exactly once in `## Completion` "
        "(only wrap step 1) — a second earlier mention would let the numbered steps reverse"
    )
    assert comp.count("/decant") == 1, (
        "the wrap-/decant slash token must appear exactly once in `## Completion` (only wrap step 2)"
    )
    assert "completedAt" in comp and 'stage == "done"' in comp, (
        "Completion's wrap sequence must be gated on the terminal-done signal"
    )
    # the gate must name the REAL is_done() contract — a PARSEABLE completedAt, not mere existence.
    # Positive anchor ("a parseable ... completedAt") — restructured (not a negation blocklist) so it
    # REDs on the "exists" revert AND on negated phrasings ("un-/non-/not parseable"), while the
    # "unparseable does NOT authorize" clarifier (no "a parseable") never satisfies it.
    assert re.search(r"\ba\s+\*{0,2}parseable\*{0,2}[^\n]{0,40}completedAt", comp), (
        "Completion's gate must state 'a parseable completedAt' (is_done()'s real contract) — "
        "not mere existence, and not a negated 'un-/non-/not parseable' phrasing"
    )
    # AC5 — the wrap steps are best-effort / non-fatal
    assert "best-effort" in comp, "Completion must state the wrap sequence is best-effort/non-fatal"
    assert comp.count("note it and CONTINUE") >= 2, (
        "both wrap steps must be non-fatal: retro-failure→note it and CONTINUE, decant-failure→note it and CONTINUE"
    )
    # AC5 — Path A (ship, post-stage=done) is a tolerated best-effort window, manual-recovery-only
    assert "manual re-run" in comp and "not automatically" in comp, (
        "Completion must document Path A's post-done wrap as tolerated best-effort — "
        "recovered only by a manual re-run, not automatically"
    )
    # (1b) TRUE-run-wrap-ONLY exclusivity (design-phase1.md: retro is at the true run-wrap only;
    # the per-seam I1 step-5.5 rebirth decant is retro-free). The `/drive-retro <runId>` INVOCATION
    # must exist at EXACTLY the two terminal-done wrap sites — `## Completion` step 1 and the
    # Done-via-resume teardown route step — and NOWHERE else in drive.md. A third occurrence
    # (e.g. a mid-run seam picking up retro) reds this pin, forcing re-review of the invariant.
    assert text.count("/drive-retro <runId>") == 2, (
        f"drive.md has {text.count('/drive-retro <runId>')} `/drive-retro <runId>` invocations; "
        "the true-run-wrap-only criterion requires EXACTLY 2 (## Completion step 1 + the "
        "Done-via-resume teardown route step) — a mid-run invocation would breach it"
    )
    # (2) resume teardown runs the wrap in the pre-done window: completedAt (step 4) is written
    # BEFORE the wrap route (step 5), which runs BEFORE stage="done" LAST (step 6).
    teardown = _drive_section(text, r"Done-via-resume teardown", r"^(  - \*\*|#{1,2}\s)")
    completedat_idx = teardown.find('"$RUN_DIR/completedAt"')  # step-4 marker WRITE target
    route_idx = teardown.find("Run the `## Completion` wrap sequence NOW")
    write_idx = teardown.find('Write `stage="done"` LAST')
    assert route_idx >= 0, "the teardown must run the `## Completion` wrap sequence pre-stage=done"
    assert completedat_idx >= 0 and completedat_idx < route_idx, (
        "the teardown must WRITE a parseable `$RUN_DIR/completedAt` (step 4) BEFORE running the "
        "wrap (step 5) — the wrap's completeness gate / is_done() needs it in the pre-done window"
    )
    assert write_idx >= 0 and route_idx < write_idx, (
        'the wrap must run BEFORE `stage="done"` is written LAST (pre-done, stop-hook-forced)'
    )
    retro_in_teardown = teardown.find("/drive-retro <runId>")
    assert route_idx < retro_in_teardown < write_idx, (
        "the teardown's /drive-retro <runId> invocation must sit in the wrap route step, "
        "after 'Run the `## Completion` wrap sequence NOW' and before the stage=done write"
    )
    # (3) Stage 5 (ship, Path A) routes into Completion AFTER `stage = done` (the post-done wrap site)
    stage5 = _drive_section(text, r"^### Stage 5 — Ship", r"^#{1,2}\s")
    ship_done_idx = stage5.find("`stage = done`")
    ship_route_idx = stage5.find("then run the `## Completion`")
    assert ship_route_idx >= 0, "Stage 5 (ship) must route into `## Completion`"
    assert ship_done_idx >= 0 and ship_done_idx < ship_route_idx, (
        "Stage 5's `## Completion` route must come AFTER `stage = done` — Path A is the "
        "post-stage=done ship wrap site (drive.md Stage 5 → Completion ordering)"
    )


# --------------------------------------------------------------------------- #
# AC13 — SLOC cap: ≤150 lines, or exactly the reviewed overage size (exact pin)
# --------------------------------------------------------------------------- #
REVIEWED_OVERAGE_LINES = 189  # reviewed size after the decant/drive-retro dedup re-point (was 184); logged in decisions.md


def test_sloc_cap_or_exact_reviewed_overage():
    """Contract: drive-retro.md is ≤150 lines, OR exactly REVIEWED_OVERAGE_LINES — any
    drift from the reviewed size (up or down) reds, forcing a re-review that moves this
    pin and its `drive-retro SLOC overage` decisions.md entry together."""
    n = len(_text().splitlines())
    assert n <= 150 or n == REVIEWED_OVERAGE_LINES, (
        f"drive-retro.md is {n} lines — neither ≤150 (AC13 cap) nor the reviewed overage "
        f"size ({REVIEWED_OVERAGE_LINES}). Re-review the file, update the `drive-retro "
        "SLOC overage` entry in decisions.md, and move REVIEWED_OVERAGE_LINES with it."
    )


# --------------------------------------------------------------------------- #
# AC2 — runId binding, three-way resolution, rebind-on-resolve, STOP-on-ambiguity
# --------------------------------------------------------------------------- #
def test_bind_section_runs_root_and_resolution():
    sec = _norm(_section(_text(), r"^## 1 — Bind the run"))
    assert "${HARNESS_RUNS_ROOT:-$HOME/.claude/harness-runs}" in sec
    assert "EXACTLY ONE run dir has the argument as a name prefix" in sec
    assert "REBIND `<runId>` to that dir's FULL basename before ANY downstream use" in sec
    assert "prefix and full-id invocations of the same run write the IDENTICAL single file" in sec
    assert "state the resolution in the terminal report" in sec


def test_bind_section_stop_on_ambiguity_writes_nothing():
    sec = _norm(_section(_text(), r"^## 1 — Bind the run"))
    assert "zero or ≥2 matches, or no argument given → STOP" in sec
    assert ('print usage plus the available run ids (`ls -1t "$RUNS_ROOT"`, '
            "newest first, capped ~20)") in sec
    assert "write NOTHING" in sec
    assert "Never guess among multiple matches; never default to the latest run" in sec


# --------------------------------------------------------------------------- #
# AC3 — completeness gate bound to the real authority, fail closed, degraded paths
# --------------------------------------------------------------------------- #
def test_completeness_gate_authority_and_fail_closed():
    sec = _norm(_section(_text(), r"^## 2 — Completeness gate"))
    assert "standalone marker FILE `$RUN_DIR/completedAt`" in sec
    assert "never a `state.json` key" in sec
    assert 'OR `state.json.stage == "done"`' in sec
    assert "`is_done()` in `bin/drive-retention.sh`" in sec
    assert "Neither signal → STOP without writing" in sec
    assert "NO override or partial mode exists" in sec


def test_completeness_gate_marker_absent_done_path():
    """`is_done()` accepts stage=="done" with the marker entirely ABSENT — the command must
    state it as an accepted (non-degraded) done path with its exact header rendering."""
    sec = _norm(_section(_text(), r"^## 2 — Completeness gate"))
    assert "EITHER signal alone passes" in sec
    assert "`completed: stage=done (marker absent)`" in sec
    assert 'marker is entirely ABSENT and `stage == "done"`' in sec
    assert "stats and Overlap compute normally" in sec


def test_completeness_gate_normal_path_renders_marker_content():
    """Interface B's `completed:` contract has THREE renderings; the normal accepted path
    renders the parseable marker content itself (design-phase2.md Interface B header)."""
    sec = _norm(_section(_text(), r"^## 2 — Completeness gate"))
    assert "the header's `completed:` field renders the accepted path" in sec
    assert "the marker content when parseable" in sec


def test_completeness_gate_degraded_done_paths():
    sec = _norm(_section(_text(), r"^## 2 — Completeness gate"))
    assert "`n/a (state.json unreadable)`" in sec
    assert "The output header never degrades" in sec
    assert "`completed: stage=done (marker unparseable)`" in sec


# --------------------------------------------------------------------------- #
# AC14 — dedup references: fixed, read-only, exact paths, tolerated absence
# --------------------------------------------------------------------------- #
def test_dedup_references_read_only_and_paths():
    sec = _norm(_section(_text(), r"^## 3 — Inputs"))
    assert "FIXED, READ-ONLY set consulted SOLELY to fill each proposal's Overlap field" in sec
    assert "never mined for stats or findings, never written" in sec
    for ref in (
        "`$REPO_ROOT/OPERATING.md`",
        "`$REPO_ROOT/TODO.md`",
        "`$REPO_ROOT/.harness/decisions.md`",
        "`$REPO_ROOT/.harness/followups.md`",
        "`~/.claude/projects/<proj>/memory/MEMORY.md`",
    ):
        assert ref in sec, f"dedup reference {ref} not bound in §3"
    assert "every `/` and `.` replaced by `-`" in sec
    assert "`not checked (<file> unavailable)`" in sec
    assert "`not checked (repoRoot unknown)`" in sec
    assert "no cwd fallback" in sec
    # Re-point (guard-repoint): §3 adds the per-slug memory FILE as the CONTENT-comparison
    # reference; the MEMORY.md index (asserted above) is retained only as the candidate enumerator.
    assert "`~/.claude/projects/<proj>/memory/<slug>.md`" in sec, (
        "§3 must add the linked per-slug memory FILE as the CONTENT-comparison reference "
        "(the index only enumerates candidates)"
    )
    assert "compare its CONTENT" in sec, (
        "§3 must instruct comparing the memory FILE's CONTENT, not the lossy index line"
    )


def test_mining_inputs_durable_only():
    sec = _norm(_section(_text(), r"^## 3 — Inputs"))
    assert "durable `$RUN_DIR` artifacts ONLY" in sec
    assert "never `wt/` or the `codex-raw-*.log`/`codex-harden-*.log` raw logs" in sec
    assert "`event-log.jsonl`" in sec


# --------------------------------------------------------------------------- #
# AC6 — tolerant stream decode; line-split forbidden; whitespace advance
# --------------------------------------------------------------------------- #
def test_event_log_parse_contract():
    sec = _section(_text(), r"^## 4 — Parse the event log")
    n = _norm(sec)
    assert "Line-split parsing is FORBIDDEN" in n
    assert "raw_decode" in sec
    assert r"[ \t\r\n]*" in sec, "inter-record whitespace advance missing from the snippet"
    assert "NEVER counted" in n
    assert "decode error at non-whitespace: skip to next newline, count ONE segment" in n
    assert "a well-formed mixed log reports 0 skipped" in n
    assert "skipped count is surfaced in the output header" in n
    assert "degrade, don't abort" in n
    assert 'the header notes "event-log absent — timeline stats omitted"' in n


# --------------------------------------------------------------------------- #
# AC7 — stats: sourced per metric, best-effort event stats, no STOP-cause stat
# --------------------------------------------------------------------------- #
def test_stats_sourced_and_best_effort():
    sec = _norm(_section(_text(), r"^## 5 — Derive stats"))
    assert "never eyeballed" in sec
    assert "pure-integer-N `review-<scope>-<N>.md` files" in sec
    assert "`## AppliedEdits: yes`" in sec
    assert "the file counts are the fallback when `state.json` is unreadable" in sec
    assert "mismatch is itself reported as signal" in sec
    assert "BEST-EFFORT by contract" in sec
    assert "NO stat requires a specific event kind" in sec
    assert "underivable ⇒ `n/a`, never a STOP" in sec
    assert "gates + timestamps · dispatches by kind · wall-clock" in sec
    assert "earliest → latest parseable `at`/`ts`" in sec
    assert "NO STOP-cause stat is emitted" in sec
    # AC9 (R2/R4): the degraded-scope stat names BOTH first-line degradation tokens the
    # supervisor writes. Mutation-verify: drop CODEX_KILLED_TIMEOUT → reds.
    assert (
        "whose FIRST LINE begins with `CODEX_UNAVAILABLE` or `CODEX_KILLED_TIMEOUT` (prefix match)"
        in sec
    )


# --------------------------------------------------------------------------- #
# AC16 — Rule U: unified, four carriers, uniform guards, dedup, budget
# --------------------------------------------------------------------------- #
def _rule_u():
    return _norm(_section(_text(), r"^## 6 — Mine findings: Rule U"))


def test_rule_u_unified_and_carriers():
    sec = _rule_u()
    assert "NO per-file or per-family rule selection" in sec
    for carrier in ("heading-bracket", "heading-bare", "line-bracket", "line-bare"):
        assert f"**{carrier}**" in sec, f"carrier {carrier} missing"
    assert "`BLOCKING|MAJOR|MINOR|NIT|P[123]`" in sec
    assert "case-SENSITIVE" in sec
    assert "section groupers, never candidates" in sec  # ##-level heading exclusion
    assert "optional list marker" in sec and "optional `**`" in sec


def test_rule_u_tag_window_and_mapping():
    sec = _rule_u()
    assert "Grade from tag-window tokens ONLY" in sec
    assert "never re-grade" in sec
    assert "P1 = {BLOCKING, MAJOR, P1}; P2 = {MINOR, P2}; P3 = {NIT, P3}" in sec
    assert "counts ONCE at its highest P-level" in sec
    assert "FINDING-MENTIONS per artifact" in sec
    assert "`FIXED` is deliberately NOT a resolution token" in sec


def test_rule_u_uniform_guards():
    sec = _rule_u()
    assert "`non-`/`non `" in sec  # guard 1: negation
    assert "RESOLVED|VETOED|OVERRULED|REFUTED|CLOSED" in sec  # guard 2
    assert "case-insensitive inside a bracket window, UPPERCASE-only elsewhere" in sec
    # guard 3: named, carrier-scoped continuation forms + the pinned ':' adjacency,
    # the parenthesized-token-list skip, and the word-bounded lowercase-as-written match rule
    assert "skipping one optional parenthesized token list" in sec
    assert "ONLY when it immediately follows the window with no intervening space" in sec
    assert "matched word-bounded, lowercase-as-written" in sec
    for form in ("`remains`", "`remaining`", "`none`", "`is addressed`", "`closed`",
                 "`split correct`"):
        assert form in sec, f"continuation form {form} missing from the named list"
    assert "non-heading carriers — a digit, `count`, `counts`" in sec
    assert "PLAIN line-bare carriers only (no bracket, no `**`) — `fix`, `fixes`, `fixed`" in sec
    assert "extendable only via a decisions.md calibration note" in sec
    # guard 4: hyphen back-reference with heading exemption
    assert "Hyphen back-reference** (non-heading carriers only)" in sec
    assert "heading carriers are EXEMPT" in sec


def test_rule_u_dedup_and_imprecision_budget():
    sec = _rule_u()
    assert "nearest preceding `###`–`######` heading is itself a Rule-U finding is not separately counted" in sec
    assert "bare `P1:` label line counts once" in sec
    assert "stated best-effort undercount" in sec
    assert "stubs are mined by nothing" in sec
    assert "≤2% residual misgrades" in sec
    assert "never grounds to re-architect the rule" in sec


# --------------------------------------------------------------------------- #
# AC4 — exactly one write, fixed section order, deterministic overwrite
# --------------------------------------------------------------------------- #
def test_single_output_path_and_overwrite():
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    assert "Exactly ONE write: `$RUN_DIR/retro-<runId>.md`" in sec
    assert "resolved FULL basename" in sec
    assert "OVERWRITES it (no `-N` versioning)" in sec
    assert 'say "overwrote existing retro" when it did' in sec


def test_output_fixed_section_order():
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    order = ["# Retro <runId>", "## Run statistics", "## Recurrence themes",
             "## Lesson proposals", "## No-action notes", "## Operator next step"]
    idx = [sec.find(tok) for tok in order]
    assert all(i >= 0 for i in idx), f"missing output section token(s): {list(zip(order, idx))}"
    assert idx == sorted(idx), f"output sections out of order: {list(zip(order, idx))}"


# --------------------------------------------------------------------------- #
# AC15 — recurrence themes: instructed synthesis over the mined list
# --------------------------------------------------------------------------- #
def test_recurrence_themes_instructed_synthesis():
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    assert "INSTRUCTED SYNTHESIS, not a computed metric" in sec
    assert "MUST appear in the mined candidate list" in sec
    assert "≥2 cited findings from ≥2 distinct artifacts" in sec


# --------------------------------------------------------------------------- #
# AC8 — proposal shape: 5 fields, signal-conditional ≥1 bar
# --------------------------------------------------------------------------- #
def test_proposal_five_fields():
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    for field in ("**Evidence**", "**Class**", "**Destination (proposal only)**",
                  "**Draft**", "**Overlap**"):
        assert field in sec, f"proposal field {field} missing"
    assert "`single-instance` flag" in sec
    assert "extend > new" in sec


def test_class_to_destination_routing():
    """Class-side drift must red too: pins BOTH vocabularies (the Class taxonomy and the
    Destination set) plus the class→destination semantics — the memory classes route via
    OPERATING.md §Self-Improvement's matrix, and the retro-specific class routes
    `process-signal → TODO.md` (design-phase2.md Class→Destination mapping)."""
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    assert ("**Class** behavioral-rule | tool/env-gotcha | skill-gap | process-signal "
            "| one-off") in sec
    assert ("**Destination (proposal only)** OPERATING.md | project CLAUDE.md/docs | "
            "skill/command file <name> | auto-memory | TODO.md") in sec
    assert "OPERATING.md §Self-Improvement's matrix + process-signal → TODO.md" in sec


def test_proposal_bar_conditional_on_signal():
    sec = _norm(_section(_text(), r"^## 7 — Write the ONE output"))
    assert "Emit ≥1 proposal when the run shows signal" in sec
    for trigger in ("≥1 P1-mapped finding under Rule U", "round/reviewCount > 1",
                    "`hardenRound ≥ 1` or `finalizeRound ≥ 1`", "redesign marker",
                    "stranded inflight marker", "non-null final `waiting`"):
        assert trigger in sec, f"signal trigger '{trigger}' missing"
    assert "or `## AppliedEdits: yes` artifacts when state is unreadable" in sec
    assert "ZERO proposals iff No-action notes states why" in sec
    assert "never invent a lesson to fill quota" in sec


# --------------------------------------------------------------------------- #
# AC5 — proposals-only invariant names every protected surface
# --------------------------------------------------------------------------- #
def test_proposals_only_invariant():
    sec = _norm(_section(_text(), r"\*\*Proposals-only invariant \(absolute\):\*\*",
                         stop_re=r"^Terminal report"))
    assert "never edit" in sec
    for surface in ("OPERATING.md", "CLAUDE.md", "TODO.md", "MEMORY.md/auto-memory",
                    "skill or command files", "`state.json`", "`event-log.jsonl`"):
        assert surface in sec, f"protected surface {surface} missing from the invariant"
    assert "no repo write of any kind" in sec


# --------------------------------------------------------------------------- #
# AC9 / AC12 — decant complement boundary (≤3 lines) + v1 scope guards
# --------------------------------------------------------------------------- #
def test_role_paragraph_scope_guards_and_decant_boundary():
    text = _text()
    role = text.split("## 1 — Bind the run")[0]
    n = _norm(role)
    assert "SINGLE-RUN and completed-run-only" in n            # was "MANUAL and SINGLE-RUN"
    assert "auto-invoked at the true run-wrap and still operator-invocable" in n  # corrected invocation status
    assert "not a gated numbered pipeline stage" in n          # was "not a `/drive` pipeline stage"
    assert "cross-run aggregation is out of scope" in n        # unchanged — still true
    assert "wired into drive.md Completion at the true run-wrap" in n  # was "named follow-on, not built"
    # the decant complement boundary is stated in ≤3 physical lines
    lines = [ln for ln in role.splitlines() if "Complement boundary" in ln]
    assert lines, "decant complement boundary missing"
    start = role.splitlines().index(lines[0])
    boundary = " ".join(role.splitlines()[start:start + 3])
    for clause in ("NOTICED", "TRACES SHOW", "promote"):
        assert clause in boundary, f"boundary clause '{clause}' not within 3 lines"
