"""AC-12 — decant/SKILL.md destructive-dedup bullet is the byte-exact memory-file-content re-point.

Slice 1.1 of the guard-repoint run. `/decant` Step 3's FIRST bullet is the destructive dedup
gate. A sibling DIET run greps its sentinel (`decant-dedup-input: memory-file-content (v1)`)
byte-for-byte from the DEPLOYED skill, so any reword parks that run forever. This pins the whole
bullet BYTE-IDENTICAL to the reviewed replacement block (design-phase1.md §1), which subsumes:
it names the linked memory FILES' CONTENT as the comparison input; the sentinel is present
verbatim on ONE physical line; and the OLD lossy `near-duplicate descriptions` clause is gone.
The surviving FILENAME-dedup clause `already saved it; delete one.` is deliberately NOT asserted
absent (it SURVIVES — D-57).

Every assertion is SECTION-BOUND to `## Step 3` so a recurrence elsewhere in the skill can't make
it vacuous, and the byte comparison is RAW (no whitespace/indentation normalization) — byte-identity
is the cross-run contract. `_section` / `_norm` are defined locally: each existing contract file
keeps its own copy (`_section` is never a shared import).
"""
import re

from _helpers import REPO_ROOT

SKILL_MD = REPO_ROOT / "skills" / "decant" / "SKILL.md"

# The reviewed replacement block (design-phase1.md §1), byte-for-byte. The `- ` opener, the
# two-space continuation indent, the em-dash, and the sentinel on ONE physical line are all
# load-bearing — do NOT reflow. No trailing newline: the block ends at the sentinel line.
EXPECTED_BULLET = (
    "- `ls` the project memory directory for files with overlapping concepts.\n"
    "  A duplicate FILENAME = the user (or another subagent) already saved it; delete one.\n"
    "  For CONTENT overlap, never compare `MEMORY.md` index lines — under the hook format they\n"
    "  are deliberately lossy TRIGGERS, not descriptions. Open BOTH linked memory FILES and\n"
    "  compare their CONTENT before deleting anything.\n"
    "  Dedup input contract (do not reword): `decant-dedup-input: memory-file-content (v1)`"
)

SENTINEL = "`decant-dedup-input: memory-file-content (v1)`"


def _text():
    assert SKILL_MD.is_file(), f"expected decant skill at {SKILL_MD}"
    return SKILL_MD.read_text(encoding="utf-8")


def _norm(text):
    """Collapse whitespace runs to one space. Used ONLY for the absence check, never the
    byte-identity check — that one must stay raw."""
    return re.sub(r"\s+", " ", text)


def _section(text, header_re, *, stop_re=r"^#{1,2}\s"):
    """Lines from the FIRST match of `header_re` up to the next `#`/`##` header or EOF.
    Asserts the header exists so a renamed/removed section reds. Local to this file — the
    other contract files each define their own; `_section` is never a shared import."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section header /{header_re}/ not found in decant/SKILL.md"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _first_bullet_bytes(raw):
    """The RAW BYTES of the FIRST top-level (`- `) bullet under `## Step 3` — byte-delimited from the
    section header, NOT via read_text()/splitlines() (which universal-newline-normalize) and NOT a
    whole-file search. From the `- ` opener up to (exclusive) the next `- ` opener, so the bytes are
    exactly the deployed first bullet: a CRLF bullet keeps its `\\r`s, a decoy copy elsewhere is out of
    scope, and the `\\n- ` bound requires the marker-grep 2nd bullet to exist (extraction unambiguous)."""
    hdr = raw.find(b"\n## Step 3")
    assert hdr != -1, "## Step 3 header not found in decant/SKILL.md (raw bytes)"
    b_start = raw.find(b"\n- ", hdr)
    assert b_start != -1, "no top-level `- ` bullet found under Step 3 (raw bytes)"
    b_start += 1  # start at the `- ` opener, past the leading newline
    b_end = raw.find(b"\n- ", b_start)
    assert b_end != -1, "expected a SECOND Step-3 bullet (the marker-grep bullet) to bound the first"
    return raw[b_start:b_end]


def test_destructive_dedup_bullet_is_byte_identical():
    """AC-12 GATE: the FIRST Step-3 bullet is byte-identical to the reviewed replacement block.
    BYTE-DELIMITED, SECTION-BOUND extraction from RAW bytes — no read_text()/splitlines()
    newline-normalization and no whole-file substring — so a CRLF bullet, a decoy copy of the block
    elsewhere, or any whitespace/encoding drift in the DEPLOYED first Step-3 bullet REDs (the sibling
    DIET run greps the deployed bytes byte-for-byte). Mutation-verify ($RUN_DIR/repoint-mutation.md):
    old bullet ⇒ RED; CRLF bullet ⇒ RED; CRLF-bullet + LF-decoy ⇒ RED."""
    bullet_bytes = _first_bullet_bytes(SKILL_MD.read_bytes())
    assert bullet_bytes == EXPECTED_BULLET.encode("utf-8"), (
        "decant Step-3 FIRST bullet is NOT byte-identical (raw bytes) to the reviewed replacement "
        "block — a line-ending / whitespace / encoding drift the sibling DIET run greps byte-for-byte.\n"
        f"--- expected ---\n{EXPECTED_BULLET.encode('utf-8')!r}\n--- actual ---\n{bullet_bytes!r}"
    )


def test_sentinel_present_on_one_physical_line():
    """The cross-run contract byte: the dedup-input sentinel must appear verbatim on exactly ONE
    physical line of Step 3 (subsumed by byte-identity above; pinned explicitly for a clear signal
    if a future reflow wraps it across lines)."""
    step3 = _section(_text(), r"^## Step 3")
    sentinel_lines = [ln for ln in step3.splitlines() if SENTINEL in ln]
    assert len(sentinel_lines) == 1, (
        f"expected the sentinel {SENTINEL!r} on exactly ONE physical line of Step 3, "
        f"found {len(sentinel_lines)} — a wrap/reword breaks the sibling run's byte-grep"
    )


def test_old_lossy_index_clause_is_gone():
    """The OLD destructive clause `near-duplicate descriptions` (comparing lossy index lines) must
    be ABSENT from Step 3. Section-bound so an unrelated recurrence elsewhere can't mask it. The
    surviving FILENAME-dedup clause `already saved it; delete one.` is NOT asserted absent (D-57)."""
    step3 = _norm(_section(_text(), r"^## Step 3"))
    assert "near-duplicate descriptions" not in step3, (
        "the OLD lossy-index dedup clause `near-duplicate descriptions` must be gone from Step 3"
    )
