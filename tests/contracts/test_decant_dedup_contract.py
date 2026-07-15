"""AC-12 — decant/SKILL.md destructive-dedup bullet is the byte-exact memory-file-content re-point.

`/decant` Step 3's FIRST bullet is the destructive dedup gate. A sibling DIET run greps its
sentinel (`decant-dedup-input: memory-file-content (v1)`) byte-for-byte from the DEPLOYED skill,
so any reword parks that run forever. This pins the whole first bullet BYTE-IDENTICAL to the
reviewed replacement block (design-phase1.md §1) — one gate that subsumes sentinel-present,
old-lossy-clause-gone, and memory-file-CONTENT-as-input. The surviving FILENAME-dedup clause
`already saved it; delete one.` deliberately SURVIVES (D-57).
"""
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
