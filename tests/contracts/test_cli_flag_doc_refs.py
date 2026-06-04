"""AC3 — every documented Mission Control CLI flag/command resolves to a real entrypoint.

Scope (design criterion 3, codex-P2 note): this contract covers **Mission Control**
CLI forms ONLY — `mc <subcommand>` (+ the standalone `today` alias) and the
`mission-control/bin` flags. The `/drive-*`, `/autoplan`, `/qa-only` slash-commands
and generic shell examples are EXCLUDED; `/drive-*` command NAMES stay covered by the
sibling `tests/contracts/test_drive_command_refs.py`, which this file does not touch.

The check is data-driven from the REAL sources, not a hardcoded allow-list:

  * Subcommand -> entrypoint is parsed from the `mc` router's `case` dispatch
    (`mission-control/bin/mc`). A documented `mc <sub>` that the router can't dispatch
    fails.
  * A flag is "handled" by an entrypoint when it appears as an argv token in that
    entrypoint's source — Python (`"--x" in sys.argv`, `args.index("--x")`,
    `"--x" in args`) or shell (a `--x)` case branch / the `mc` router heredoc). The
    `bind` subcommand's flags resolve in `mc-bind.sh`.

Docs scanned: top-level `README.md`, `CLAUDE.md`, `docs/flow.md`, and
`mission-control/README.md`. Each documented `mc <sub>` usage (and the standalone
`today`) is associated with the `--flags` mentioned in the SAME context (line / table
row); every such flag must resolve in that subcommand's entrypoint. This scoping is
what makes the check MC-only even in docs that also carry `/drive --flag` prose — a
flag is only pinned when it sits next to an `mc` command — and it is what catches a
reintroduced `--prep`-style drift: `mc standup ... --prep` would resolve to
`standup.py`, which handles no `--prep`, and fail with the doc location named.
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

# An `mc <subcommand>` usage. The subcommand is the first bare lowercase word after
# `mc`. Matches `mc standup`, `` `mc harvest --log` ``, and the slash-joined compact
# form `mc harvest/today/tasks` (each subcommand picked up via _MC_SLASH below).
_MC_CMD = re.compile(r"\bmc\s+([a-z]+)")
# Compact slash-joined list e.g. `mc harvest/today/tasks` -> harvest, today, tasks.
_MC_SLASH = re.compile(r"\bmc\s+([a-z]+(?:/[a-z]+)+)")


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
# Documented surface (scanned from docs, scoped to mc context)
# --------------------------------------------------------------------------- #
def _documented_subcommands():
    """{subcommand: [(doc_name, lineno), ...]} for every `mc <sub>` usage in the docs."""
    found = {}
    for doc in DOC_FILES:
        for lineno, line in enumerate(_read(doc).splitlines(), start=1):
            subs = set(_MC_CMD.findall(line))
            for slash in _MC_SLASH.findall(line):
                subs.update(slash.split("/"))
            for sub in subs:
                # `mc help` is the router's own builtin, not a dispatched entrypoint.
                if sub in ("help",):
                    continue
                found.setdefault(sub, []).append((doc.name, lineno))
    return found


def _documented_flags_by_subcommand():
    """{subcommand: {flag: [(doc_name, lineno), ...]}} — flags scoped to the mc command
    they sit next to (same line / table row). A flag with no neighbouring `mc <sub>` is
    NOT attributed to MC, which is how `/drive --flag` prose stays out of scope."""
    found = {}
    for doc in DOC_FILES:
        for lineno, line in enumerate(_read(doc).splitlines(), start=1):
            subs = set(_MC_CMD.findall(line))
            for slash in _MC_SLASH.findall(line):
                subs.update(slash.split("/"))
            subs.discard("help")
            if not subs:
                continue
            flags = set(_FLAG.findall(line))
            if not flags:
                continue
            for sub in subs:
                bucket = found.setdefault(sub, {})
                for flag in flags:
                    bucket.setdefault(flag, []).append((doc.name, lineno))
    return found


# --------------------------------------------------------------------------- #
# Tests
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
