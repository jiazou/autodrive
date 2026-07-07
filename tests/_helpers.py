"""Non-fixture helpers importable by fixtures and tests.

These deliberately live OUTSIDE conftest so the installer / hook phases (which run
shell scripts via subprocess) can use them without pulling in the MC module-reload
machinery.
"""
import os
import subprocess
from pathlib import Path

# Repo root = two levels up from this file (tests/_helpers.py -> tests/ -> repo).
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_script(args, *, home, cwd=None, env=None, timeout=30):
    """Run `args` (a list) as a subprocess with HOME redirected to `home`.

    The child env is os.environ overlaid with any `env` mapping and then HOME forced
    to `home`. Working dir defaults to the repo root. Output is captured as text.
    Returns the CompletedProcess (no check=True — callers assert on returncode).
    """
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    child_env["HOME"] = str(home)
    return subprocess.run(
        list(args),
        env=child_env,
        cwd=str(cwd) if cwd is not None else str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )


def _rev(repo, ref):
    """Resolve a ref to its full 40-char sha (for asserting expected/found_sha exactly)."""
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(repo, path, content, msg):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _review(rd, scope, n, sha="0" * 40, verdict="CONVERGED"):
    # Matches the REAL writer schema (drive-review.md § "Write review-<scope>-N.md"): a header
    # preamble (`## Verdict:` + `reviewed-sha:`) followed by the ALWAYS-present `## Findings`
    # header. The `## Findings` delimiter is load-bearing — the checkpoint counter's review-phase
    # parseability boundary REQUIRES it (a review-phase file lacking it is `unparseable-review`),
    # and it bounds the header region the delimiter-required `reviewed_sha_of`/`is_marked` read.
    # This writes an UNMARKED review (no `harden-regress:` marker); the marked/no-Findings shapes
    # have their own dedicated fixtures.
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n\n## Verdict: {verdict}\n\n"
        f"reviewed-sha: {sha}\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )


def _codex(rd, scope):
    (rd / f"codex-review-{scope}.md").write_text(
        f"codex review for {scope}\nlooks fine\n", encoding="utf-8"
    )


def seed_mc_home(home):
    """Create the data dirs that mc-bind.sh / mc-hook.py assume already exist.

    On a real machine `mission-control/install.sh` creates ~/mission-control. As of
    the F2 fix, mc-hook.py self-creates it via os.makedirs(..., exist_ok=True) before
    appending to status.jsonl, but mc-bind.sh still only APPENDS to
    ~/mission-control/bindings.jsonl and never mkdirs it. Seeding here mirrors
    install.sh so mc-bind.sh and the short-id session path (which also reads
    ~/.claude/sessions/*.json) work in tests — real usage, not a test workaround.
    Returns `home`.
    """
    home = Path(home)
    (home / "mission-control").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "sessions").mkdir(parents=True, exist_ok=True)
    return home
