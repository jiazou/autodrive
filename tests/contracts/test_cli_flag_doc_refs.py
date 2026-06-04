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
  command token has intervened.

  What ENDS a binding (the codex P2 ownership-cutoff contract — generic, not just
  slash/`mc`): tokens (quote-aware: a `"..."`/`'...'` span is ONE token) are walked after
  the anchor. A flag-bearing token continues the binding; a VALUE token — a `<...>`/`[...]`
  placeholder OR a quoted span (including a multi-word `"My Project"`, codex round-5
  finding 2) — does NOT end it; ANY OTHER bare WORD ENDS it. So
  `mc standup --draft /drive-review --bogus`, `mc standup --draft foo --bogus`, and
  `mc standup --draft && foo --bogus` ALL bind ONLY `--draft`→standup and never attribute
  `--bogus` — the slash command, the bare word `foo`, and the segment break each end the
  binding. Positional arguments and bracketed/quoted value placeholders (`<id>`, `<slug>`,
  `[--task <slug>]`, `"<P>"`, `"My Project"`) are NOT command tokens, so real forms like
  `mc bind <id> --project "<P>" [--task <slug>]` and `mc done <slug> [--status <s>]`
  still bind their flags to the right subcommand. (We deliberately treat only quoted/
  placeholder tokens as flag VALUES; an UNQUOTED bare word like `foo` always terminates —
  doc flag-values are always written as placeholders or quoted, never bare, so this loses
  no real form while keeping the `--draft foo --bogus` cutoff sound.)

  Documentation `|`s that are NOT shell pipes are masked before splitting: a backslash-
  escaped `\\|` (the Markdown-table cell escape in `mc standup [--draft\\|--json]`) and a
  `|` inside a `[--a|--b]` flag-alternatives group. This keeps both alternative flags in
  the same segment so the live `mc standup --json` form is actually validated, while a
  genuine shell pipe (`mc standup --draft | grep ...`) still ends ownership.

  Reported doc locations are the flag's OWN line (computed from its offset within the
  snippet), not merely the snippet's first line.

Resolution (data-driven from REAL sources, not a hardcoded allow-list):
  * Subcommand -> entrypoint is parsed from the `mc` router's `case` dispatch
    (`mission-control/bin/mc`). The doc scan extracts EVERY syntactic `mc <sub>` token
    (independent of the router set), then `test_documented_subcommands_resolve_in_router`
    asserts that extracted set ⊆ the router dispatch. A documented `mc bogus` therefore
    FAILS — the check is NOT gated by the router set (that earlier gating was fail-open:
    it dropped unknown subs before the assertion could see them).
  * A flag is "handled" by an entrypoint ONLY when it appears at a REAL argv PARSE SITE
    in that entrypoint's source — never at an incidental string literal (printed example,
    help/usage text, docstring, comment). The real idioms in mission-control/bin are:
      - Python: argv-membership tests `"--x" in sys.argv` / `"--x" in args`, and index
        lookups `<argv>.index("--x")` (done.py uses `args = list(sys.argv[1:])` then
        `"--status" in args` / `args.index("--status")`). NOT a bare `"--x"` literal
        inside `print(...)`/docstrings/comments (harvest.py:309 prints
        `mc bind --project/--task`, harvest.py:13 docstrings `--log`, etc).
      - Shell: `case` arms `--x)` (mc-bind.sh's `--project)`/`--task)`/`--tab)`/`--unbind)`
        and the router's `--help)` arm). NOT a bare literal in a heredoc/help block.
    This presence-only-at-parse-site rule is what stops a doc-only `mc harvest --project`
    from falsely passing on harvest.py's printed `--project` example. The `bind`
    subcommand's flags resolve at `mc-bind.sh`'s `case` arms.

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
import ast
import io
import re
import tokenize

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


# Token classification for the per-segment walk (codex-P2 generic ownership cutoff). A
# segment is tokenized quote-aware (a `"..."`/`'...'` span is ONE token even with internal
# spaces, so a real `--project "My Project"` value is a single value token, not two bare
# words — codex round-5 finding 2) and each token is classified so a bare WORD (a new
# command token) ends an open binding, while flag-bearing tokens, placeholders, and
# flag-values do not.
#   * a token may CONTAIN one or more `--flag`s (possibly wrapped in `[...]` doc notation,
#     e.g. `[--draft\x00--json]` after pipe-masking, or `[--task`); `_FLAG.findall` pulls
#     them out and they bind to the anchor.
#   * a PLACEHOLDER/value token (`<id>`, `<slug>]`, quoted `"<P>"`, quoted `"My Project"`)
#     is the value of a positional or a flag; it never ends a binding.
#   * ANY OTHER bare WORD is a new command token and ENDS the binding.
# A placeholder/value: starts with `<`/`[`/quote, or ends with `>`/`]`/quote, or is a fully
# quoted span (possibly multi-word).
_TOK_PLACEHOLDER = re.compile(r"""^["']?[<\[]|[>\]]["']?$|^["'].*["']$""")
# Quote-aware token: a `"..."` or `'...'` span (kept whole, internal spaces and all), or a
# run of non-space chars. This is what keeps `--project "My Project"` a single value token.
_TOKEN = re.compile(r"""\"[^\"]*\"|'[^']*'|\S+""")

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


# --- Real argv parse-site idioms (NOT incidental string literals) ----------- #
# A flag-shaped string LITERAL value (the content of a `"--x"` token, quotes stripped).
_FLAG_LITERAL = re.compile(r"^--[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _py_handled_flags(text):
    """Flags a PYTHON entrypoint genuinely parses, detected on the TOKEN STREAM (structural,
    not a text regex) so parse-shaped text inside COMMENTS / DOCSTRINGS / printed strings is
    never counted (codex round-5 finding 1). A flag is handled when a STRING token whose
    value is `--x` is used as either:
      * the LEFT operand of an `in` against an argv receiver: `"--x" in sys.argv|argv|<alias>`; or
      * an argument to `<argv>.index(...)`: `args.index("--x")` / `sys.argv.index("--x")`.

    Receiver tightening (codex-P2): the receiver must PROVABLY be `sys.argv`, NOT just any
    attribute named `.argv`. We accept only:
      * the `sys.argv` chain — NAME("sys") OP(".") NAME("argv");
      * a bare `argv` (from `from sys import argv`); and
      * a local ALIAS provably derived from `sys.argv` — a name first bound by an assignment
        whose right-hand side TOKENS contain the `sys.argv` chain (done.py:
        `args = list(sys.argv[1:])`). Aliases are collected in a first pass over the token
        stream, then required at the parse site. An unrelated `foo.argv` receiver (no `sys.`
        base) and an unrelated `args` that was never bound from sys.argv are both REJECTED.
    A `# "--x" in sys.argv` comment yields a COMMENT token (not a STRING), and a docstring
    `'... "--x" in sys.argv ...'` is ONE STRING token whose VALUE is the whole sentence (not
    `--x`), so neither is mistaken for a parse site. harvest.py:309's printed `--project`
    f-string is a STRING token not followed by `in argv`, so it is correctly ignored.
    """
    # Significant tokens only (drop COMMENT, NL/NEWLINE, INDENT/DEDENT, ENCODING, ENDMARKER).
    toks = []
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type in (
            tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
            tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER,
        ):
            continue
        toks.append(t)

    def str_value(tok):
        """The literal value of a STRING token if it's a simple (non-f, non-byte) quoted
        string, else None. f-strings tokenize differently (FSTRING_* or a STRING with an
        `f` prefix) so a printed f-string never yields a clean `--x` value here."""
        if tok.type != tokenize.STRING:
            return None
        s = tok.string
        if re.match(r"^[A-Za-z]", s):  # has a prefix (f/r/b/...) -> not a plain literal
            return None
        try:
            val = ast.literal_eval(s)
        except Exception:
            return None
        return val if isinstance(val, str) else None

    n = len(toks)

    def is_sys_argv_chain(j):
        """True if tokens at j..j+2 are the `sys` `.` `argv` chain."""
        return (
            j + 2 < n
            and toks[j].type == tokenize.NAME and toks[j].string == "sys"
            and toks[j + 1].type == tokenize.OP and toks[j + 1].string == "."
            and toks[j + 2].type == tokenize.NAME and toks[j + 2].string == "argv"
        )

    # First pass: collect local aliases provably derived from sys.argv. An alias is a NAME
    # at statement start assigned (`=`) a right-hand side whose tokens contain the sys.argv
    # chain — `args = sys.argv`, `args = sys.argv[1:]`, `args = list(sys.argv[1:])`. The RHS
    # span runs from the `=` to the logical end (NEWLINE/NL was dropped, so until the next
    # plausible statement boundary; we just scan forward a bounded window for the chain).
    argv_aliases = set()
    for i, t in enumerate(toks):
        if (
            t.type == tokenize.NAME
            and i + 1 < n
            and toks[i + 1].type == tokenize.OP and toks[i + 1].string == "="
        ):
            # Scan the RHS until a statement-terminating token; a NEWLINE was filtered out,
            # so stop at the next `=`-led assignment isn't needed — instead bound the scan to
            # the same source line via token start rows.
            rhs_row = toks[i + 1].start[0]
            j = i + 2
            while j < n and toks[j].start[0] == rhs_row:
                if is_sys_argv_chain(j):
                    argv_aliases.add(t.string)
                    break
                j += 1

    def receiver_at(j):
        """If tokens starting at j are a recognized argv receiver, return (kind, advance):
        kind in {"chain","name"} and advance = number of tokens consumed. Else (None, 0)."""
        if is_sys_argv_chain(j):
            return "chain", 3
        if j < n and toks[j].type == tokenize.NAME:
            name = toks[j].string
            if name == "argv" or name in argv_aliases:
                # Reject `sys.argv` mis-detected as bare here: a bare `argv` must NOT be the
                # `.argv` tail of a `something.argv` chain (the chain branch above handles
                # the real `sys.argv`). If preceded by a `.`, it's an attribute access.
                if j >= 1 and toks[j - 1].type == tokenize.OP and toks[j - 1].string == ".":
                    return None, 0
                return "name", 1
        return None, 0

    handled = set()
    for i, t in enumerate(toks):
        # Membership: STRING("--x") `in` <argv receiver>.
        val = str_value(t)
        if (
            val and _FLAG_LITERAL.match(val)
            and i + 1 < n
            and toks[i + 1].type == tokenize.NAME and toks[i + 1].string == "in"
        ):
            kind, _adv = receiver_at(i + 2)
            if kind is not None:
                handled.add(val)
        # Index: <argv receiver> "." "index" "(" STRING("--x"). The receiver may be the
        # `sys.argv` chain or a bare alias name; require `.index(` immediately after it.
        kind, adv = receiver_at(i)
        if kind is not None and (i == 0 or not (
            toks[i - 1].type == tokenize.OP and toks[i - 1].string == "."
        )):
            j = i + adv
            if (
                j + 3 < n
                and toks[j].type == tokenize.OP and toks[j].string == "."
                and toks[j + 1].type == tokenize.NAME and toks[j + 1].string == "index"
                and toks[j + 2].type == tokenize.OP and toks[j + 2].string == "("
            ):
                aval = str_value(toks[j + 3])
                if aval and _FLAG_LITERAL.match(aval):
                    handled.add(aval)
    return handled


# Shell: a flag is genuinely parsed ONLY as a `case` arm pattern `--x)` (optionally one of
# several alternatives `--a|--b)`), OUTSIDE comments and heredoc bodies (codex round-5
# finding 1). `_sh_strip` blanks `#` line-comments and `<<EOF ... EOF` heredoc bodies first.
_SH_CASE_ARM = re.compile(r"^[ \t]*((?:--[a-z][a-z0-9-]*\|)*--[a-z][a-z0-9-]*)\)", re.M)
_SH_HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _sh_strip(text):
    """Blank shell `#` line-comments and heredoc bodies so a parse-shaped line inside them
    (`# --ghost)` or a `--ghost)` example in a here-doc) is NOT mistaken for a real `case`
    arm. Line count is preserved so any future line-based reporting stays accurate."""
    out = []
    pending_heredoc = None  # the terminator we're scanning for, or None
    for line in text.splitlines():
        if pending_heredoc is not None:
            if line.strip() == pending_heredoc:
                pending_heredoc = None
            out.append("")  # blank the heredoc body line (and its terminator)
            continue
        # A `#` comment: blank from the first unquoted `#`. The mc/* scripts have no `#`
        # inside quoted strings on case-arm lines, so a simple first-`#` cut is sufficient.
        code = line.split("#", 1)[0]
        m = _SH_HEREDOC_START.search(code)
        if m:
            pending_heredoc = m.group(2)
        out.append(code)
    return "\n".join(out)


def _handled_flags(path):
    """The set of `--flags` an entrypoint genuinely PARSES — detected ONLY at real argv
    parse sites, never at incidental string literals (printed examples, help/usage text,
    docstrings, comments, heredocs). This is the codex P1b + round-5 finding-1 soundness
    fix: counting a `--flag` substring anywhere in the file can MASK drift (a doc-only
    `mc harvest --project` would falsely pass because harvest.py PRINTS `--project` in an
    example, though it parses only --log/--summarize).

    Dispatch by file kind:
      * `.py`  -> token-stream detection of argv membership (`"--x" in sys.argv|argv|args`)
                  and index lookups (`<argv>.index("--x")`). These are the only idioms used
                  in mission-control/bin's Python entrypoints (no argparse/getopt).
      * shell  -> `case` arm patterns `--x)` / `--a|--b)` OUTSIDE comments/heredocs
                  (mc-bind.sh option handling).
    """
    text = _read(path)
    if path.suffix == ".py":
        return _py_handled_flags(text)
    # Shell entrypoints (mc-bind.sh, and the `mc` router itself): case-arm options only,
    # scanned after blanking comments + heredoc bodies.
    handled = set()
    for arm in _SH_CASE_ARM.findall(_sh_strip(text)):
        for flag in arm.split("|"):
            handled.add(flag)
    return handled


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


_PROMPT = re.compile(r"^[ \t]*(?:[$>][ \t]+)?")

# Subcommands that take a LEADING POSITIONAL argument before their flags (codex-P1
# concrete-positional fix). Derived from the real entrypoints, NOT invented:
#   * `bind` — mc-bind.sh's option loop has a `*) session_arg="$1"` arm, i.e. a bare
#     non-flag word is consumed as the (optional) SESSION_ID positional.
#   * `done` — done.py does `args = list(sys.argv[1:]); ...; slug = args[0]`, i.e. the
#     first non-flag word is the task SLUG positional.
# For these, ONE leading CONCRETE positional token (a bare word like `af85ee12` /
# `2026-06-02-pa-rental`, which is otherwise binding-terminating) is allowed BETWEEN the
# subcommand and its flags WITHOUT ending the binding — so a doc example written with a
# real id/slug (not a `<id>`/`<slug>` placeholder) still pins its flags. A SECOND bare
# word, or any new-command token, still terminates (the /drive-*, second-command cutoff
# is preserved). Subcommands NOT in this set take no positional, so any bare word
# terminates immediately as before.
_POSITIONAL_SUBS = frozenset({"bind", "done"})


def _segment_invocations(segment):
    """Attribute `--flags` to the `mc <sub>` anchor at the START of ONE command segment.

    Returns (subs_with_off, flag_pairs):
      * subs_with_off — list of (subcommand, segment_local_offset) for EVERY syntactic
                     `mc <sub>` (or slash-joined `mc a/b/c`) subcommand token at this
                     segment's command START. Recorded INDEPENDENT of the router's real
                     subcommand set (the codex-P1a fail-open fix): a documented `mc bogus`
                     MUST surface here so the subcommand-resolution test can fail on it,
                     rather than being dropped before the assertion. The offset is the
                     sub token's OWN position so the resolution test reports the sub's
                     true line, not the snippet's first line (codex-P3).
      * flag_pairs — list of (subcommand, flag, segment_local_offset): a flag is owned by
                     the segment's `mc <sub>` anchor only while the binding is still open.

    Anchoring rule (round-4 structural decision, preserved): the anchor is recognized
    ONLY at the segment's COMMAND START — the first command word must be a bare `mc`
    (optionally behind a `$`/`>` prompt). So `echo mc today`, `tool mc standup`, and the
    slash-skill `/mc harvest` do NOT anchor (`mc` is not the command word). Bare
    standalone subcommand words never anchor either.

    Ownership cutoff (codex-P2 generic termination): after the `mc <sub>` anchor, tokens
    are walked left-to-right. A flag-bearing token binds its `--flag`(s) to the open
    anchor. A `<...>`/`[...]` placeholder or quoted value (the ONLY shapes a documented
    flag/positional VALUE ever takes — `--status <s>`, `--project "<P>"`) does NOT end the
    binding. ANY OTHER bare word — a fresh `mc`, a slash command (`/drive-review`), or a
    plain literal like `foo` — is a NEW command token and ENDS the binding. So
    `mc standup --draft foo --bogus`, `mc standup --draft /drive-review --bogus`, and a
    later `mc <sub>` all stop `--bogus` from being attributed. (We deliberately do NOT
    treat a bare word as a preceding flag's value: doc value tokens are always placeholders
    or quoted, so a bare `foo` after `--draft` is a new command, not `--draft`'s argument —
    which is exactly what makes the generic cutoff fire. Cross-segment flags are already
    isolated by the segment split.)
    """
    # Strip a leading `$ `/`> ` prompt; the rest is the command line.
    pm = _PROMPT.match(segment)
    body_off = pm.end()
    body = segment[body_off:]

    # Tokenize quote-aware (a `"..."`/`'...'` span is one token), keeping each token's
    # offset within the ORIGINAL segment.
    tokens = [(body_off + m.start(), m.group(0)) for m in _TOKEN.finditer(body)]

    subs = []  # (subcommand, segment_local_offset)
    pairs = []  # (subcommand, flag, segment_local_offset)
    if not tokens:
        return subs, pairs

    # The anchor is only at the command START: first token must be exactly `mc`.
    if tokens[0][1] != "mc" or len(tokens) < 2:
        return subs, pairs

    # The subcommand token: a bare lowercase word, or a slash-joined list `a/b/c`. Strip
    # nothing else — a `<...>`/`--flag`/quoted token in the sub slot means no real sub.
    sub_off, sub_tok = tokens[1]
    sub_parts = sub_tok.split("/")
    if not all(re.fullmatch(r"[a-z]+", p) for p in sub_parts):
        return subs, pairs  # not an `mc <sub>` form (e.g. `mc --help` handled elsewhere)
    for p in sub_parts:
        subs.append((p, sub_off))
    # The binding owner is the (single) subcommand; for a slash-joined list, flags after
    # it are documentation of the shared surface, so attribute to each listed sub.
    owners = list(sub_parts)
    # A leading CONCRETE positional is allowed for positional-taking subcommands (codex-P1).
    # Allow exactly ONE such token between the sub and its flags. A slash-joined sub list
    # is the shared-surface doc form and never carries a concrete positional, so the
    # allowance applies only to a single positional-taking subcommand.
    positional_budget = (
        1 if len(owners) == 1 and owners[0] in _POSITIONAL_SUBS else 0
    )

    for off, tok in tokens[2:]:
        flags_in = list(_FLAG.finditer(tok))
        if flags_in:
            # Flag-bearing token (`--draft`, `[--task`, masked `[--draft\x00--json]`).
            # Bind every flag it contains to the open anchor(s) at its own offset.
            for fm in flags_in:
                for owner in owners:
                    pairs.append((owner, fm.group(0), off + fm.start()))
            continue
        if _TOK_PLACEHOLDER.search(tok):
            # `<id>`, `<slug>]`, quoted `"<P>"` — a positional/flag VALUE placeholder, not
            # a command word. Does not end the binding. (Real doc flag-values are ALWAYS
            # placeholders/quoted — `--status <s>`, `--project "<P>"` — never a bare literal
            # word, so we never need an `expect_value` heuristic that a bare word like the
            # `foo` in `--draft foo` would falsely swallow.)
            continue
        # A bare WORD here. For a positional-taking subcommand, the FIRST such word is the
        # subcommand's CONCRETE leading positional (a real id/slug like `af85ee12` /
        # `2026-06-02-pa-rental`) — consume it WITHOUT ending the binding so flags after a
        # concrete id/slug still pin (codex-P1). The budget is 1, so a SECOND bare word —
        # or a bare word for a non-positional subcommand — is a NEW command token and ENDS
        # the binding (the /drive-*, second-command cutoff is preserved).
        if positional_budget > 0:
            positional_budget -= 1
            continue
        # Any other BARE word is a NEW command token (a fresh `mc`, a slash command like
        # `/drive-review`, or just `foo`): it ENDS the binding (codex-P2 generic cutoff).
        break
    return subs, pairs


def _invocations_in_snippet(snippet):
    """Split a snippet into command segments and union each segment's invocations.

    Splitting on shell separators (`;`, `&&`, `||`, `|`, newline) is what gives
    PER-SEGMENT ownership: a flag can only be attributed to an `mc <sub>` anchor in its
    OWN segment, so an `mc` command in one segment can never claim a flag that lives in
    a neighbouring segment. Documentation `|`s that are NOT shell pipes (escaped `\\|`
    table cells, `[--a|--b]` flag groups) are masked first so they never split a segment.

    Returns (subs_off, pairs, pairs_off):
      * subs_off  — set of (subcommand, snippet_local_offset): the offset is the sub
                    token's OWN position so `_scan_docs` reports the sub's true line, not
                    the snippet's first line (codex-P3).
      * pairs     — set of (subcommand, flag).
      * pairs_off — set of (subcommand, flag, snippet_local_offset).
    Segments are walked with their base offset into the snippet so each token's
    SNIPPET-LOCAL offset can be computed. Walking via `finditer` over the separators
    (rather than `re.split`, which discards positions) is what preserves those offsets."""
    masked = _mask_non_separator_pipes(snippet)
    subs_off = set()
    pairs = set()
    # Segment spans: text between consecutive separators, with the segment's base offset.
    base = 0
    spans = []
    for sep in _SEGMENT_SPLIT.finditer(masked):
        spans.append((base, masked[base : sep.start()]))
        base = sep.end()
    spans.append((base, masked[base:]))
    for seg_base, segment in spans:
        sub_list, triples = _segment_invocations(segment)
        for sub, off in sub_list:
            subs_off.add((sub, seg_base + off))
        for sub, flag, off in triples:
            pairs.add((sub, flag, seg_base + off))
    return subs_off, {(sub, flag) for sub, flag, _ in pairs}, pairs


def _scan_docs():
    """Scan all docs once. Returns (documented_subs, documented_flags):

      * documented_subs  — {sub: [(doc, lineno), ...]} EVERY syntactic `mc <sub>` invoked,
                           independent of the router set (so a doc-only `mc bogus` surfaces
                           and the resolution test can fail on it — codex-P1a).
      * documented_flags — {sub: {flag: [(doc, lineno), ...]}} each flag owned by the
                           `mc <sub>` anchor it follows in its command segment."""
    documented_subs = {}
    documented_flags = {}
    for doc in DOC_FILES:
        # repo-relative path so the two README.md files are distinguishable in messages.
        doc_label = str(doc.relative_to(REPO_ROOT))
        for base_lineno, snippet in _command_snippets(_read(doc)):
            subs_off, _pairs, pairs_off = _invocations_in_snippet(snippet)
            for sub, off in subs_off:
                if sub == "help":  # router builtin, not a dispatched entrypoint
                    continue
                # Exact doc line of THIS sub = snippet's base line + newlines before it
                # (codex-P3): report the subcommand's OWN line, not the snippet start.
                sub_lineno = base_lineno + snippet.count("\n", 0, off)
                documented_subs.setdefault(sub, []).append((doc_label, sub_lineno))
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
    """{subcommand: [(doc_name, lineno), ...]} for EVERY syntactic `mc <sub>` usage in
    docs — extracted independent of the router set so the resolution test sees (and can
    fail on) a doc-only `mc bogus`."""
    return _scan_docs()[0]


def _documented_flags_by_subcommand():
    """{subcommand: {flag: [(doc_name, lineno), ...]}} — flags scoped to the `mc <sub>`
    anchor they follow in a command segment. A flag with no `mc <sub>` owner in its own
    segment is NOT attributed, which is how `/drive --flag` prose, slash-skill `/mc`
    examples, and cross-segment flags stay out of scope."""
    return _scan_docs()[1]


# --------------------------------------------------------------------------- #
# Direct scanner unit tests (codex P2 — exercise the segment function, not just live
# docs). The scanner anchors on EVERY syntactic `mc <sub>` (no valid-subs gating), so
# these probe the raw extraction + ownership-cutoff behaviour directly.
# --------------------------------------------------------------------------- #
def _pins(snippet):
    """(subs, pairs) the scanner pins for a raw snippet. `subs` is flattened to plain
    subcommand NAMES (dropping the per-sub offset) and `pairs` to plain (sub, flag), so
    unit tests assert on names/pairs without the offset tags."""
    subs_off, pairs, _pairs_off = _invocations_in_snippet(snippet)
    return {sub for sub, _ in subs_off}, pairs


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


def test_unit_concrete_leading_positional_does_not_mask_flags():
    """codex-P1: a CONCRETE leading positional (a real id/slug, not a `<id>`/`<slug>`
    placeholder) for a positional-taking subcommand must NOT terminate the binding, so the
    flags after it still pin and drift is still caught. `bind` takes a session-id positional
    (mc-bind.sh `*) session_arg=`), `done` takes a slug positional (done.py `slug=args[0]`)."""
    # bind with a concrete short-id: both flags must still pin.
    _, pairs = _pins('mc bind af85ee12 --project "X" --task t1')
    assert ("bind", "--project") in pairs, f"expected (bind, --project); got {pairs}"
    assert ("bind", "--task") in pairs, f"expected (bind, --task); got {pairs}"
    # done with a concrete slug: --status must still pin.
    _, pairs = _pins("mc done 2026-06-02-pa-rental --status all")
    assert ("done", "--status") in pairs, f"expected (done, --status); got {pairs}"
    _, pairs = _pins("mc done somereal-slug --status all")
    assert ("done", "--status") in pairs, f"expected (done, --status); got {pairs}"


def test_unit_concrete_positional_still_catches_drift():
    """codex-P1: allowing ONE concrete leading positional must NOT mask a bogus flag — a
    drift flag after a concrete id still pins so the resolution test fails on it."""
    _, pairs = _pins("mc bind af85ee12 --bogus")
    assert ("bind", "--bogus") in pairs, (
        f"a drift flag after a concrete id must still pin; got {pairs}"
    )


def test_unit_only_one_leading_positional_allowed():
    """codex-P1: the positional allowance is exactly ONE token — a SECOND bare word is a new
    command token and ENDS the binding, so a flag after it is NOT attributed to the sub."""
    _, pairs = _pins("mc done slug-one secondword --bogus")
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"a second bare word must end the binding; --bogus must NOT pin; got {pairs}"
    )


def test_unit_non_positional_sub_bare_word_still_terminates():
    """codex-P1: only positional-taking subs (bind/done) get the leading-positional
    allowance. A non-positional sub (standup) still terminates on the FIRST bare word, so a
    concrete leading word does NOT let a later flag pin."""
    _, pairs = _pins("mc standup somearg --bogus")
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"standup takes no positional; the bare word must end the binding; got {pairs}"
    )


def test_unit_new_command_token_ends_binding():
    """A `/drive-review` (new command token) ENDS the standup binding, so `--bogus`
    after it is NOT attributed — only (standup, --draft) is pinned."""
    _, pairs = _pins("mc standup --draft /drive-review --bogus")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"--bogus must NOT be attributed after /drive-review; got {pairs}"
    )


def test_unit_bare_word_ends_binding():
    """codex-P2 generic cutoff: a bare WORD (not a flag, not a placeholder) after the
    `mc <sub>` flags ENDS the binding — so `mc standup --draft foo --bogus` pins ONLY
    (standup, --draft), never (standup, --bogus). This is the case the old slash/`mc`-only
    `_NEW_CMD` cutoff missed (it kept pinning --bogus to standup)."""
    _, pairs = _pins("mc standup --draft foo --bogus")
    assert ("standup", "--draft") in pairs, f"expected (standup, --draft); got {pairs}"
    assert not any(flag == "--bogus" for _, flag in pairs), (
        f"a bare word `foo` must end the binding; --bogus must NOT pin; got {pairs}"
    )


def test_unit_subcommand_extraction_is_router_independent():
    """codex-P1a: the scanner extracts EVERY syntactic `mc <sub>` token regardless of the
    router's real subcommand set — so a doc-only `mc bogus` SURFACES as a subcommand and
    the resolution test can fail on it. (The old fail-open path dropped unknown subs before
    the assertion, making `test_documented_subcommands_resolve_in_router` un-failable.)"""
    subs, _pairs = _pins("mc bogus --x")
    assert "bogus" in subs, f"`mc bogus` must surface as an extracted subcommand; got {subs}"


def test_unit_handled_flags_ignore_incidental_literals():
    """codex-P1b: `_handled_flags` detects a flag ONLY at a real argv parse site, never at
    an incidental string literal (printed example, help/usage text, docstring, comment).

    harvest.py PRINTS `mc bind --project/--task` (an example) and docstrings `--log`, but
    only PARSES `--summarize`/`--log` via `"--x" in sys.argv`. So `--project`/`--task`
    (printed-only) must NOT be reported as handled, while `--log`/`--summarize` (real parse
    sites) must be. Without this, a doc-only `mc harvest --project` would falsely pass."""
    handled = _handled_flags(MC_BIN / "harvest.py")
    assert handled == {"--log", "--summarize"}, (
        f"harvest.py must report ONLY its real parse-site flags; got {sorted(handled)}"
    )
    # The drift this guards: harvest does NOT parse --project, so the doc-attributed pair
    # is unhandled and `test_documented_flags_resolve_in_their_entrypoint` would fail.
    _, pairs = _pins("mc harvest --project")
    assert ("harvest", "--project") in pairs, (
        f"`mc harvest --project` must attribute the pair so the flag test can catch it; got {pairs}"
    )
    assert "--project" not in handled


def test_unit_handled_flags_reject_parse_shaped_text():
    """codex round-5 finding 1: a parse-SHAPED literal inside a comment, docstring, printed
    f-string, or a non-argv `.index()` must NOT be counted as handled — only the genuine
    token-level parse site is. Guards the masking hole where an entrypoint's example text
    could falsely satisfy a doc-only flag."""
    src = (
        '"""usage: mc x [--ghostdoc]; e.g. "--ghostdoc" in sys.argv"""\n'
        '# "--ghostcmt" in sys.argv  -- a comment, not a parse site\n'
        'print(f"mc bind --ghostprint")\n'
        'usage = ["--ghostidx"]\n'
        'x = usage.index("--ghostidx")  # not argv\n'
        'if "--real" in sys.argv:\n'
        '    pass\n'
        'args = list(sys.argv[1:])\n'
        'if "--realarg" in args:\n'
        '    args.index("--realarg")\n'
    )
    handled = _py_handled_flags(src)
    assert handled == {"--real", "--realarg"}, (
        f"only genuine token-level parse sites must count; got {sorted(handled)}"
    )


def test_unit_handled_flags_require_sys_argv_derived_receiver():
    """codex-P2: the argv receiver must PROVABLY be sys.argv — `"--x" in sys.argv`, a bare
    `argv`, or an alias bound from sys.argv (`args = list(sys.argv[1:]); "--x" in args`).
    An unrelated `foo.argv` (no sys. base) and an `args` never bound from sys.argv are NOT
    parse sites and must NOT be counted."""
    src = (
        'if "--unrelated" in foo.argv:\n'          # foo.argv — NOT sys.argv-derived
        '    pass\n'
        'bogus = get_args()\n'                       # bogus NOT bound from sys.argv
        'if "--alsobogus" in bogus:\n'
        '    pass\n'
        'if "--direct" in sys.argv:\n'               # real: sys.argv chain
        '    pass\n'
        'args = list(sys.argv[1:])\n'                # real: alias derived from sys.argv
        'if "--viaalias" in args:\n'
        '    pass\n'
        'x = args.index("--viaindex")\n'             # real: index on derived alias
        'y = sys.argv.index("--viachain")\n'         # real: index on sys.argv chain
    )
    handled = _py_handled_flags(src)
    assert handled == {"--direct", "--viaalias", "--viaindex", "--viachain"}, (
        f"only sys.argv-derived receivers must count; got {sorted(handled)}"
    )


def test_unit_handled_flags_reject_unrelated_argv_attr():
    """codex-P2, sharpened: `if "--x" in foo.argv:` must NOT be counted — the `.argv` tail
    alone is not enough; the receiver must be the `sys.argv` chain or a derived alias."""
    handled = _py_handled_flags('if "--x" in foo.argv:\n    pass\n')
    assert handled == set(), f"foo.argv must not be a parse site; got {sorted(handled)}"
    handled = _py_handled_flags('if "--x" in sys.argv:\n    pass\n')
    assert handled == {"--x"}, f"sys.argv must be a parse site; got {sorted(handled)}"


def test_unit_shell_case_arm_rejects_heredoc_and_comment():
    """codex round-5 finding 1 (shell): a `--x)`-shaped line inside a heredoc body or after
    a `#` comment must NOT be read as a real `case` arm."""
    src = (
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    --realflag) ok ;;\n"
        "    # --commentflag) not real ;;\n"
        "  esac\n"
        "done\n"
        "cat <<EOF\n"
        "    --heredocflag) also not real\n"
        "EOF\n"
    )
    handled = {f for arm in _SH_CASE_ARM.findall(_sh_strip(src)) for f in arm.split("|")}
    assert handled == {"--realflag"}, (
        f"only real case arms (outside comments/heredocs) must count; got {sorted(handled)}"
    )


def test_unit_multiword_quoted_value_does_not_end_binding():
    """codex round-5 finding 2: a multi-word quoted flag VALUE (`--project "My Project"`) is
    a single value token and must NOT end the binding — a following `--task` still pins. A
    naive whitespace tokenizer split `"My`/`Project"` into bare words and false-failed the
    real `mc bind ... --project "<...>" --task <slug>` form."""
    _, pairs = _pins('mc bind <id> --project "My Project" --task <slug>')
    assert ("bind", "--project") in pairs, f"expected (bind, --project); got {pairs}"
    assert ("bind", "--task") in pairs, (
        f"--task after a multi-word quoted value must still pin; got {pairs}"
    )


def test_unit_handled_flags_parse_idioms():
    """The real argv-parse idioms used across mission-control/bin are all recognized:
      * Python membership on sys.argv (harvest/standup/today/weekly)
      * Python membership + index on a local argv alias `args` (done.py)
      * shell `case` arms (mc-bind.sh)
    A regression in any detector would drop a real flag and false-fail a live doc form."""
    assert _handled_flags(MC_BIN / "standup.py") == {"--draft", "--json"}  # `in sys.argv`
    assert _handled_flags(MC_BIN / "today.py") == {"--swiftbar"}
    assert _handled_flags(MC_BIN / "weekly.py") == {"--json"}
    assert _handled_flags(MC_BIN / "done.py") == {"--status"}  # `in args` + args.index()
    # shell case arms (no router heredoc literals leak in):
    assert _handled_flags(MC_BIN / "mc-bind.sh") == {"--project", "--task", "--tab", "--unbind"}


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


def test_unit_subcommand_offset_is_its_own_line():
    """codex-P3: the unresolved-subcommand diagnostic must report the subcommand's OWN line,
    not the snippet's first line. A fenced block whose body starts a few lines before the
    `mc bogus` line must yield the `mc bogus` line, computed from the sub token's offset the
    same way flag offsets already are."""
    # A snippet with several leading lines before the `mc bogus` invocation.
    snippet = (
        "mc today        # line 0 of the body\n"
        "mc standup      # line 1\n"
        "mc bogus --x    # line 2 — the unresolved sub lives here\n"
    )
    subs_off, _pairs, _pairs_off = _invocations_in_snippet(snippet)
    bogus_offs = [off for sub, off in subs_off if sub == "bogus"]
    assert bogus_offs, f"expected `bogus` to surface; got {subs_off}"
    # mirror _scan_docs' line math: base_lineno + newlines before the sub's offset.
    base_lineno = 10  # arbitrary block-body start line
    bogus_line = base_lineno + snippet.count("\n", 0, bogus_offs[0])
    assert bogus_line == base_lineno + 2, (
        f"`mc bogus` must report its own line (base+2), not the block start; got {bogus_line}"
    )
    # And the block start (`mc today`) is a DIFFERENT, earlier line — proving the diagnostic
    # is not collapsing every sub onto the snippet's first line.
    today_offs = [off for sub, off in subs_off if sub == "today"]
    today_line = base_lineno + snippet.count("\n", 0, today_offs[0])
    assert today_line == base_lineno, f"`mc today` is on the block-start line; got {today_line}"
    assert bogus_line != today_line, "bogus and today must report distinct lines"


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
