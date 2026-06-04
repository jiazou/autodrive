"""AC3 — every documented Mission Control CLI flag/command resolves to a real entrypoint.

Scope (design criterion 3, codex-P1/P2 notes): this contract covers **Mission
Control** CLI forms invoked through the `mc` router ONLY — i.e. explicit
`mc <subcommand> [--flags]`. The `/drive-*`, `/autoplan`, `/qa-only` slash-commands
and generic shell examples are EXCLUDED; `/drive-*` command NAMES stay covered by the
sibling `tests/contracts/test_drive_command_refs.py`, which this file does not touch.

Why `mc`-prefixed ONLY (the round-4 structural decision):
  Earlier rounds anchored BARE subcommand words (`harvest`, `review`, `done`, ...) when
  they appeared in a command/code context. That was fundamentally brittle: a bare word
  like `review`/`done` collides with unrelated commands (`tool review --bogus`,
  `foo done --status`), and a subcommand word embedded in a compound (`/drive-review`,
  `plan-eng-review`) leaked into MC scope. The `mc ` router prefix is the one
  unambiguous marker that a token is the Mission Control CLI, so we pin a flag ONLY when
  it is owned by an explicit `mc <sub>` anchor. Standalone `harvest`/`standup`/`today`/
  `review`/`plan`/`done` words are NO LONGER treated as commands. This eliminates the
  entire bare-word leak class.

Per-segment ownership (the codex P1 flag-bleed fix):
  Each code/inline snippet is split into COMMAND SEGMENTS on shell separators
  (`;`, `&&`, `||`, `|`, newline). The `mc <sub>` anchor is recognized ONLY at a
  segment's COMMAND START (so a foreign command that merely contains the words `mc <sub>`
  mid-line — `echo mc today --swiftbar`, `tool mc standup --draft` — does NOT anchor). A
  `--flag` is bound to the `mc <sub>` anchor of the SAME segment, and only while no NEW
  command token has intervened. A new command token (another `mc`/`/mc`, or any
  `/`-prefixed command such as `/drive-review`) ENDS the binding. So
  `mc standup --draft /drive-review --bogus` binds ONLY `--draft`→standup and never
  attributes `--bogus`. Positional arguments and bracketed value placeholders
  (`<id>`, `<slug>`, `[--task <slug>]`) are NOT command tokens, so real forms like
  `mc bind <id> --project "<P>" [--task <slug>]` and `mc done <slug> [--status <s>]`
  still bind their flags to the right subcommand.

  Documentation `|`s that are NOT shell pipes are masked before splitting: a backslash-
  escaped `\\|` (the Markdown-table cell escape in `mc standup [--draft\\|--json]`) and a
  `|` inside a `[--a|--b]` flag-alternatives group. This keeps both alternative flags in
  the same segment so the live `mc standup --json` form is actually validated, while a
  genuine shell pipe (`mc standup --draft | grep ...`) still ends ownership.

  Reported doc locations are the flag's OWN line (computed from its offset within the
  snippet), not merely the snippet's first line.

Resolution (data-driven from REAL sources, not a hardcoded allow-list):
  * Subcommand -> entrypoint is parsed from the `mc` router's `case` dispatch
    (`mission-control/bin/mc`). A documented `mc <sub>` that the router can't dispatch
    fails.
  * A flag is "handled" by an entrypoint when it appears as an argv token in that
    entrypoint's source — Python (`"--x" in sys.argv`, `args.index("--x")`,
    `"--x" in args`) or shell (a `--x)` case branch / the `mc` router heredoc). The
    `bind` subcommand's flags resolve in `mc-bind.sh`.

Docs scanned: top-level `README.md`, `CLAUDE.md`, `docs/flow.md`, and
`mission-control/README.md`. Only `mc <sub>` forms inside a COMMAND/CODE context
(fenced ```` ``` ```` blocks and inline `` `backtick` `` spans) are scanned; prose that
merely contains a word like "today"/"done" is out of scope.

NOTE on BARE forms still in the docs: `mission-control/README.md` also writes a few BARE
invocations (`standup --draft`, `harvest --log` at lines ~95,141). Those are being
normalized to `mc `-prefixed in a SEPARATE Phase-2 harden step, so it is CORRECT that
this `mc`-prefixed-only check does not pin them yet.

This scoping catches a reintroduced `--prep`-style drift: `mc standup ... --prep`
resolves to `standup.py`, which handles no `--prep`, and fails with the doc location
named.
"""
import re

import pytest

# tests/_helpers locates the repo root the same way the rest of the suite does.
from _helpers import REPO_ROOT  # noqa: E402  (conftest puts tests/ on sys.path)


MC_BIN = REPO_ROOT / "mission-control" / "bin"

# Docs in scope. (CLAUDE.md / docs/flow.md carry no mc CLI refs today; they are
# scanned anyway so a future mc reference added there is covered, not silently missed.)
DOC_FILES = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "flow.md",
    REPO_ROOT / "mission-control" / "README.md",
)

# A CLI flag token: `--word` with optional internal hyphens. Excludes a bare `--`
# and markdown emphasis artifacts (the trailing char class forbids `-` runs).
_FLAG = re.compile(r"--[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

# An `mc <subcommand>` usage through the router, anchored at the COMMAND START of a
# segment: `^` + optional leading whitespace/prompt then `mc`. Anchoring at the start is
# what stops a foreign command that merely CONTAINS the token sequence `mc <sub>` mid-line
# (`echo mc today --swiftbar`, `tool mc standup --draft`) from being mistaken for the MC
# CLI — `mc` must be the command word, not an argument. The slash-skill form `/mc <sub>`
# (README:104) never starts with bare `mc` (it starts with `/`), so it is excluded too.
# `$` (prompt) and `> ` (continuation) are tolerated as leading prompt chars. The
# subcommand is the first bare lowercase word after `mc`.
_MC_CMD = re.compile(r"^[ \t]*(?:[$>][ \t]+)?mc[ \t]+([a-z]+)")
# Compact slash-joined list e.g. `mc harvest/today/tasks` -> harvest, today, tasks.
_MC_SLASH = re.compile(r"^[ \t]*(?:[$>][ \t]+)?mc[ \t]+([a-z]+(?:/[a-z]+)+)")

# A NEW command token that ENDS an `mc <sub>` flag binding within a segment: another
# `mc`/`/mc` router call, or any slash-prefixed command (`/drive-review`, `/qa-only`,
# `/autoplan`, ...). Positional args and `<...>`/`[...]` placeholders are deliberately
# NOT here — they must not end a binding (so `mc bind <id> --project` still binds).
_NEW_CMD = re.compile(r"(?<![\w/])(?:/[a-z][\w-]*|mc(?=[ \t]|$))")

# A fenced ``` code block: capture its body (group 1) so its commands are in-scope.
_FENCE = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.M | re.S)
# An inline `backtick` span. `[^`\n]` segments joined by single newlines lets a span
# wrap ONE line break (the README's `harvest`/`--log --summarize` span) without letting
# a stray backtick swallow whole paragraphs.
_INLINE = re.compile(r"`([^`\n]*(?:\n[^`\n]*)*?)`")

# Shell command separators that split a snippet into independent command SEGMENTS.
# A `|` is a separator ONLY when it is a genuine pipe — NOT when backslash-escaped
# (`\|`, the Markdown-table cell escape used in `mc standup [--draft\|--json]`) and NOT
# inside a `[...]` flag-alternatives group (`[--draft|--json]`). Both are neutralized by
# `_mask_non_separator_pipes` before the split, so those `|`s never break a segment.
_SEGMENT_SPLIT = re.compile(r";|&&|\|\|?|\n")
_ESCAPED_PIPE = re.compile(r"\\\|")
_BRACKET_GROUP = re.compile(r"\[[^\]\n]*\]")


def _mask_non_separator_pipes(snippet):
    """Replace `|` characters that are NOT shell pipes with a placeholder, preserving
    length so segment-local offsets stay valid. Escaped `\\|` (Markdown-table cell escape)
    and `|` inside a `[...]` group (flag-alternative notation like `[--draft|--json]`) are
    documentation syntax, not command separators — masking them keeps both flags in the
    same segment so they stay owned by the preceding `mc <sub>`."""
    chars = list(snippet)
    for m in _ESCAPED_PIPE.finditer(snippet):
        chars[m.start()] = " "  # the backslash
        chars[m.start() + 1] = "\x00"  # the pipe -> non-separator sentinel
    text = "".join(chars)
    chars = list(text)
    for m in _BRACKET_GROUP.finditer(text):
        for i in range(m.start(), m.end()):
            if chars[i] == "|":
                chars[i] = "\x00"
    return "".join(chars)


def _read(path):
    assert path.is_file(), f"expected doc/source at {path}"
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# REAL entrypoint surface (parsed from sources, not hardcoded)
# --------------------------------------------------------------------------- #
def _router_dispatch():
    """Parse `mission-control/bin/mc`'s case dispatch into {subcommand: entrypoint_path}.

    Each `name1|name2)  exec ... "$MC/<file>"` branch maps every alias to its file.
    `$MC` is `$HOME/mission-control/bin`, which mirrors this repo's mission-control/bin,
    so we resolve the basename against MC_BIN.
    """
    text = _read(MC_BIN / "mc")
    branch = re.compile(
        r'^\s*([a-z|]+)\)\s+exec\s+(?:"\$PY"\s+)?(?:bash\s+)?"\$MC/([^"]+)"', re.M
    )
    dispatch = {}
    for names, fname in branch.findall(text):
        for name in names.split("|"):
            dispatch[name] = MC_BIN / fname
    return dispatch


def _handled_flags(path):
    """The set of `--flags` an entrypoint genuinely parses, read from its source.

    Python: any `--flag` literal appearing in the module body (the readers test via
    `"--x" in sys.argv` / `args.index("--x")`). Shell: any `--flag` literal (case
    branches `--x)` and the `mc` router heredoc). This is intentionally permissive on
    HOW the flag is matched but strict on PRESENCE — a doc-only flag never appears.
    """
    return set(_FLAG.findall(_read(path)))


# --------------------------------------------------------------------------- #
# Documented surface (scanned from docs, scoped to `mc <sub>` command contexts)
# --------------------------------------------------------------------------- #
def _command_snippets(text):
    """Yield (lineno, snippet) for each COMMAND/CODE context in `text`.

    Two contexts count as a place where a token may be a CLI invocation: fenced ```
    code blocks and inline `backtick` spans. Restricting to these is what keeps prose
    that merely contains the word "today"/"done" out of scope. Fenced blocks are
    extracted first and blanked out (newlines preserved so line numbers stay accurate)
    so their inner backticks can't make an inline span swallow an entire block. `lineno`
    is the 1-based line where the snippet's body starts."""

    def lineno_at(pos):
        return text.count("\n", 0, pos) + 1

    chars = list(text)
    for m in _FENCE.finditer(text):
        yield lineno_at(m.start(1)), m.group(1)
        for i in range(m.start(), m.end()):  # blank the fence, keep newlines
            if chars[i] != "\n":
                chars[i] = " "
    masked = "".join(chars)
    for m in _INLINE.finditer(masked):
        yield lineno_at(m.start(1)), m.group(1)


def _segment_invocations(segment, valid_subs):
    """Attribute `--flags` to the `mc <sub>` anchors inside ONE command segment.

    Returns (subs, flag_pairs):
      * subs       — set of MC subcommands invoked via `mc <sub>` (or slash-joined
                     `mc a/b/c`) in this segment.
      * flag_pairs — set of (subcommand, flag): a flag is owned by the most-recent
                     `mc <sub>` anchor to its LEFT, UNLESS a NEW command token
                     (another `mc`/`/mc`, or any `/`-prefixed command) intervenes
                     between that anchor and the flag — in which case the binding has
                     ended and the flag is dropped.

    `valid_subs` is the router's real subcommand set; a subcommand that is not a genuine
    MC entrypoint name is ignored. The `/mc <sub>` slash-skill form is excluded by
    `_MC_CMD`'s negative lookbehind, and `/mc` is itself a binding-ending token.

    Bare standalone subcommand words are NOT anchors — only an explicit `mc <sub>`
    prefix anchors a command. This is the round-4 structural fix that drops all
    brittle bare-word matching.
    """
    # Collect typed boundary events along the segment, sorted by offset:
    #   ("anchor", sub)  — an `mc <sub>` / slash-joined subcommand
    #   ("end",   None)  — a NEW command token that ends any open binding
    #   ("flag",  flag)  — a `--flag` token
    events = []  # (offset, kind, value)

    for m in _MC_CMD.finditer(segment):
        sub = m.group(1)
        if sub in valid_subs:
            events.append((m.start(1), "anchor", sub))
        # An `mc <sub>` is itself a command start; the anchor offset doubles as the
        # boundary, so a *second* `mc <sub>` later naturally re-anchors (handled below).
    for m in _MC_SLASH.finditer(segment):
        base = m.start(1)
        off = base
        for part in m.group(1).split("/"):
            if part in valid_subs:
                events.append((off, "anchor", part))
            off += len(part) + 1  # +1 for the '/'

    # NEW command tokens that END a binding (another `mc`/`/mc`, or any `/`-prefixed
    # command). The `mc` of an `mc <sub>` anchor matches here too, but its offset is the
    # `mc` literal while the anchor's offset is the SUBcommand (a few chars later), so an
    # `mc <sub>` is always processed as: end-prior-binding, THEN re-anchor on <sub>.
    # That is exactly the desired behaviour, so no special-casing is needed — and an
    # `mc <unknown-sub>` (no anchor recorded) correctly just ends the prior binding.
    for m in _NEW_CMD.finditer(segment):
        events.append((m.start(), "end", None))

    for m in _FLAG.finditer(segment):
        events.append((m.start(), "flag", m.group(0)))

    # Sort by offset; at equal offsets, "anchor" < "end" < "flag" alphabetically, so an
    # anchor wins over an end at the same position (never actually collides today, but
    # makes the ordering total and deterministic).
    _ORDER = {"anchor": 0, "end": 1, "flag": 2}
    events.sort(key=lambda e: (e[0], _ORDER[e[1]]))

    subs = set()
    pairs = []  # (subcommand, flag, segment_local_offset)
    owner = None  # current open `mc <sub>` binding, or None if ended/none-yet
    for off, kind, value in events:
        if kind == "anchor":
            owner = value
            subs.add(value)
        elif kind == "end":
            owner = None
        elif kind == "flag":
            if owner is not None:
                pairs.append((owner, value, off))
    return subs, pairs


def _invocations_in_snippet(snippet, valid_subs):
    """Split a snippet into command segments and union each segment's invocations.

    Splitting on shell separators (`;`, `&&`, `||`, `|`, newline) is what gives
    PER-SEGMENT ownership: a flag can only be attributed to an `mc <sub>` anchor in its
    OWN segment, so an `mc` command in one segment can never claim a flag that lives in
    a neighbouring segment. Documentation `|`s that are NOT shell pipes (escaped `\\|`
    table cells, `[--a|--b]` flag groups) are masked first so they never split a segment.

    Returns (subs, pairs) where `pairs` is a set of (subcommand, flag). Segments are
    walked with their base offset into the snippet so each pair's SNIPPET-LOCAL offset
    can be computed (used by `_scan_docs` to report the exact doc line, not just the
    snippet's first line). Walking via `finditer` over the separators (rather than
    `re.split`, which discards positions) is what preserves those offsets."""
    masked = _mask_non_separator_pipes(snippet)
    subs = set()
    pairs = set()
    # Segment spans: text between consecutive separators, with the segment's base offset.
    base = 0
    spans = []
    for sep in _SEGMENT_SPLIT.finditer(masked):
        spans.append((base, masked[base : sep.start()]))
        base = sep.end()
    spans.append((base, masked[base:]))
    for seg_base, segment in spans:
        s, triples = _segment_invocations(segment, valid_subs)
        subs |= s
        for sub, flag, off in triples:
            pairs.add((sub, flag, seg_base + off))
    return subs, {(sub, flag) for sub, flag, _ in pairs}, pairs


def _scan_docs(valid_subs):
    """Scan all docs once. Returns (documented_subs, documented_flags):

      * documented_subs  — {sub: [(doc, lineno), ...]} every `mc <sub>` invoked.
      * documented_flags — {sub: {flag: [(doc, lineno), ...]}} each flag owned by the
                           `mc <sub>` anchor it follows in its command segment."""
    documented_subs = {}
    documented_flags = {}
    for doc in DOC_FILES:
        # repo-relative path so the two README.md files are distinguishable in messages.
        doc_label = str(doc.relative_to(REPO_ROOT))
        for base_lineno, snippet in _command_snippets(_read(doc)):
            subs, _pairs, pairs_off = _invocations_in_snippet(snippet, valid_subs)
            for sub in subs:
                if sub == "help":  # router builtin, not a dispatched entrypoint
                    continue
                documented_subs.setdefault(sub, []).append((doc_label, base_lineno))
            for sub, flag, off in pairs_off:
                if sub == "help":
                    continue
                # Exact doc line of THIS flag = snippet's base line + newlines before it.
                lineno = base_lineno + snippet.count("\n", 0, off)
                documented_flags.setdefault(sub, {}).setdefault(flag, []).append(
                    (doc_label, lineno)
                )
    return documented_subs, documented_flags


def _documented_subcommands():
    """{subcommand: [(doc_name, lineno), ...]} for every `mc <sub>` usage in docs."""
    return _scan_docs(set(_router_dispatch()))[0]


def _documented_flags_by_subcommand():
    """{subcommand: {flag: [(doc_name, lineno), ...]}} — flags scoped to the `mc <sub>`
    anchor they follow in a command segment. A flag with no `mc <sub>` owner in its own
    segment is NOT attributed, which is how `/drive --flag` prose, slash-skill `/mc`
    examples, and cross-segment flags stay out of scope."""
    return _scan_docs(set(_router_dispatch()))[1]


# --------------------------------------------------------------------------- #
# Direct scanner unit tests (codex P2 — exercise the segment function, not just live
# docs). `valid_subs` mirrors the real router subcommand set.
# --------------------------------------------------------------------------- #
_PROBE_SUBS = {"harvest", "standup", "today", "weekly", "review", "plan", "tasks", "done", "bind"}


def _pins(snippet):
    """(subs, pairs) the scanner pins for a raw snippet, using the real subcommand set.
    Drops the offset-tagged third element so unit tests assert on plain (sub, flag)."""
    subs, pairs, _pairs_off = _invocations_in_snippet(snippet, _PROBE_SUBS)
    return subs, pairs


def test_unit_mc_sub_flag_pins():
    """`mc <sub> --flag` pins (sub, flag)."""
    _, pairs = _pins("mc harvest --bogus")
    assert ("harvest", "--bogus") in pairs, f"expected (harvest, --bogus); got {pairs}"
    _, pairs = _pins("mc standup --draft")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"


def test_unit_real_bind_done_flags_pin_past_positionals():
    """Positional args / `<...>` placeholders do NOT end a binding, so the real
    `mc bind <id> --project ...` and `mc done <slug> [--status]` forms still pin."""
    _, pairs = _pins('mc bind <id> --project "<P>" [--task <slug>] [--tab <name>]')
    assert ("bind", "--project") in pairs, f"expected (bind, --project); got {pairs}"
    assert ("bind", "--task") in pairs, f"expected (bind, --task); got {pairs}"
    assert ("bind", "--tab") in pairs, f"expected (bind, --tab); got {pairs}"
    _, pairs = _pins("mc done <slug> [--status <s>]")
    assert ("done", "--status") in pairs, f"expected (done, --status); got {pairs}"


def test_unit_new_command_token_ends_binding():
    """A `/drive-review` (new command token) ENDS the standup binding, so `--bogus`
    after it is NOT attributed — only (standup, --draft) is pinned."""
    _, pairs = _pins("mc standup --draft /drive-review --bogus")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"--bogus must NOT be attributed after /drive-review; got {pairs}"
    )


def test_unit_bare_forms_pin_nothing():
    """Bare (un-`mc`-prefixed) invocations pin NOTHING — the round-4 structural change
    that drops all bare-word anchoring."""
    for snippet in (
        "harvest --log qa-only --bogus",
        "standup --draft",
        "harvest --log --summarize",
        "done --status x",
    ):
        subs, pairs = _pins(snippet)
        assert not pairs, f"bare {snippet!r} must pin no flags; got {pairs}"


def test_unit_slash_and_foreign_commands_pin_nothing():
    """Slash commands and foreign commands that merely CONTAIN a subcommand word pin
    nothing: `/drive-review`, `/drive review`, `tool review`, `foo done`, `/mc`."""
    for snippet in (
        "/drive-review --bogus",
        "/drive review --bogus",
        "tool review --bogus",
        "foo done --status",
        "/mc harvest --x",
    ):
        subs, pairs = _pins(snippet)
        assert not pairs, f"{snippet!r} must pin no flags; got {pairs}"
    # /mc harvest is the slash-skill, not the CLI binary: it must not even anchor.
    subs, _ = _pins("/mc harvest --x")
    assert "harvest" not in subs, f"/mc harvest must not anchor harvest; got subs {subs}"


def test_unit_segments_isolate_ownership():
    """Per-segment ownership: an `mc` command in one segment cannot claim a flag in a
    neighbouring segment split by a shell separator."""
    _, pairs = _pins("mc standup --draft && foo --bogus")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"--bogus lives in a foreign segment; got {pairs}"
    )


def test_unit_embedded_mc_does_not_anchor():
    """codex-P2: a foreign command that merely CONTAINS `mc <sub>` mid-line is NOT an MC
    invocation — `mc` must be the COMMAND word (segment start), not an argument. These
    must pin NOTHING."""
    for snippet in (
        "echo mc today --swiftbar",
        "tool mc standup --draft",
        "sudo mc harvest --log",
    ):
        subs, pairs = _pins(snippet)
        assert not pairs, f"embedded {snippet!r} must pin no flags; got {pairs}"
        assert not subs, f"embedded {snippet!r} must anchor no subcommand; got {subs}"


def test_unit_doc_pipe_alternatives_pin_both_flags():
    """codex-P1: a documentation `|` that is NOT a shell pipe must not split a segment, so
    BOTH flags in a `[--a|--b]` group (and the Markdown-table-escaped `[--a\\|--b]` form,
    the live `mc standup [--draft\\|--json]` at mission-control/README.md:135) are owned by
    the preceding `mc <sub>`. A naive split on `|` would drop the second flag and silently
    stop validating it."""
    for snippet in ("mc standup [--draft|--json]", r"mc standup [--draft\|--json]"):
        _, pairs = _pins(snippet)
        assert ("standup", "--draft") in pairs, f"{snippet!r}: missing --draft; got {pairs}"
        assert ("standup", "--json") in pairs, f"{snippet!r}: missing --json; got {pairs}"


def test_unit_real_pipe_still_splits():
    """A genuine shell pipe still ends ownership: `mc standup --draft | grep --color` must
    NOT attribute `--color` to standup (it belongs to the piped `grep`)."""
    _, pairs = _pins("mc standup --draft | grep --color")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"
    assert not any(flag == "--color" for _, flag in pairs), (
        f"--color is past a real pipe; got {pairs}"
    )


def test_scan_reports_exact_flag_line():
    """codex-P3: the reported doc location is the flag's OWN line, not just the snippet's
    first line. The live `mc bind ... --project` sits on its own line inside the fenced
    block whose body starts a few lines earlier; the reported lineno must match the
    `--project` line, not the block start."""
    flags = _documented_flags_by_subcommand()
    locs = flags.get("bind", {}).get("--project", [])
    assert locs, "expected `mc bind --project` to be documented"
    mc_readme = (REPO_ROOT / "mission-control" / "README.md").read_text().splitlines()
    for doc, lineno in locs:
        if doc != "mission-control/README.md":
            continue
        line = mc_readme[lineno - 1]
        assert "--project" in line, (
            f"reported line {lineno} for `mc bind --project` does not contain it: {line!r}"
        )


# --------------------------------------------------------------------------- #
# Router-parse + live-doc contract tests
# --------------------------------------------------------------------------- #
def test_router_dispatch_parses_known_subcommands():
    """Sanity: the router parse yields the real subcommand surface, so the data-driven
    checks below have correct inputs. Pins the known-real set; a router rename that drops
    one of these (or a regex break) fails here rather than silently weakening the check."""
    dispatch = _router_dispatch()
    for sub in ("harvest", "standup", "today", "weekly", "tasks", "done", "bind"):
        assert sub in dispatch, f"mc router no longer dispatches '{sub}': {sorted(dispatch)}"
        assert dispatch[sub].is_file(), f"mc routes '{sub}' to a missing file {dispatch[sub]}"
    # aliases are dispatched too
    assert dispatch.get("plan") == dispatch["standup"]
    assert dispatch.get("review") == dispatch["weekly"]


def test_documented_subcommands_resolve_in_router():
    """Every `mc <sub>` documented in the docs is a subcommand the router can dispatch."""
    dispatch = _router_dispatch()
    documented = _documented_subcommands()
    assert documented, "no `mc <sub>` usages found in the docs — regex or docs changed"
    unresolved = {
        sub: locs for sub, locs in documented.items() if sub not in dispatch
    }
    assert not unresolved, (
        "documented `mc <sub>` commands with no router dispatch (doc-only): "
        + "; ".join(
            f"mc {sub} @ {', '.join(f'{d}:{ln}' for d, ln in locs)}"
            for sub, locs in sorted(unresolved.items())
        )
    )


def test_documented_flags_resolve_in_their_entrypoint():
    """Every `--flag` documented next to an `mc <sub>` is parsed by that subcommand's
    real entrypoint (Python argv or shell case). This is the assertion that catches a
    reintroduced `--prep`-style doc-only flag."""
    dispatch = _router_dispatch()
    documented = _documented_flags_by_subcommand()
    assert documented, "no flags found next to any `mc <sub>` — regex or docs changed"

    failures = []
    for sub, flags in sorted(documented.items()):
        entry = dispatch.get(sub)
        if entry is None:
            # Covered by the subcommand-resolution test; skip here to keep messages crisp.
            continue
        handled = _handled_flags(entry)
        for flag, locs in sorted(flags.items()):
            if flag not in handled:
                where = ", ".join(f"{d}:{ln}" for d, ln in locs)
                failures.append(
                    f"`mc {sub} {flag}` documented at {where} but {entry.name} "
                    f"parses no {flag} (handled: {sorted(handled) or 'none'})"
                )
    assert not failures, "doc-only MC CLI flag(s) found:\n  " + "\n  ".join(failures)


def test_known_real_flags_are_handled_by_their_entrypoint():
    """Positive guard: the known real flag surface resolves to its entrypoint. Locks the
    intended mapping so the data-driven checks above can't pass vacuously (e.g. if the
    doc scan regex silently matched nothing)."""
    dispatch = _router_dispatch()
    expected = {
        "harvest": {"--summarize", "--log"},
        "standup": {"--draft", "--json"},
        "today": {"--swiftbar"},
        "weekly": {"--json"},
        "done": {"--status"},
        "bind": {"--project", "--task", "--tab", "--unbind"},
    }
    for sub, flags in expected.items():
        entry = dispatch[sub]
        handled = _handled_flags(entry)
        missing = flags - handled
        assert not missing, (
            f"{entry.name} (mc {sub}) no longer parses {sorted(missing)} "
            f"(handled: {sorted(handled)})"
        )


def test_standalone_today_alias_resolves():
    r"""The docs advertise `today` standalone (`also: just \`today\``); it is the same
    entrypoint the `mc today` router branch dispatches, installed on PATH by install.sh.
    A documented standalone alias with no backing entrypoint would be doc-only."""
    dispatch = _router_dispatch()
    assert dispatch["today"].name == "today.py"
    # the standalone alias appears in the docs (mc README line ~113 "(also: just `today`)")
    mc_readme = _read(REPO_ROOT / "mission-control" / "README.md")
    assert "`today`" in mc_readme, "expected the standalone `today` alias to be documented"
