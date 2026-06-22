#!/usr/bin/env bash
# drive-retention.sh — REPORT-ONLY retention classifier for /drive run residue.
#
# Phase 1 of drive-retention-hygiene. Enumerates sibling run dirs under the
# harness-runs root and, per run, classifies what WOULD be swept and why — emitting a
# structured per-run / per-tier report. It performs NO deletion of any kind: there is
# no --apply flag, no `trash`, no `git worktree remove`, no removal of any run content
# in this file. Phase 2 adds the destructive path; Phase 1 is structurally incapable of
# deleting (the report is the safety preview of what Phase 2 --apply will sweep).
#
# Usage:
#   drive-retention.sh [--root <dir>] [--age-days <N=14>] [--now <epoch>] [--json]
#
# Best-effort isolation (D3): this is NOT `set -euo pipefail`. A per-run classification
# failure becomes a SKIP with a reason; the scan ALWAYS exits 0. The ONLY non-zero exit
# is 2 on an unknown CLI flag (a caller programming error at the CLI boundary, surfaced
# before enumeration begins).
#
# Two tiers, classified INDEPENDENTLY per run:
#   Tier-L  heavy-log eligibility (codex-raw-*.log / codex-harden-*.log). No git gate.
#   Tier-W  per-CHILD drive-owned worktree eligibility under wt/. Full git-truth gate.
# Every unverifiable/error input routes to a SKIP (fail-safe) — no fail-open path exists.

# Deliberately NO `set -e` / `set -u` / `set -o pipefail` (best-effort contract, D3 /
# DP3). No `set -u` also sidesteps the same-line `local a=$1 b=$a` expansion gotcha.

# ----------------------------------------------------------------------------- #
# CLI parse
# ----------------------------------------------------------------------------- #
ROOT="${HARNESS_RUNS_ROOT:-$HOME/.claude/harness-runs}"
AGE_DAYS=14
NOW=""
JSON=0

# Each valued flag bounds-checks for a value BEFORE `shift 2`: a valued flag as the
# trailing token (no value) is a CLI usage error ⇒ exit 2 (same lane as an unknown flag).
# Without this, `shift 2` with only one positional left does NOT shift, so $1 stays the
# flag and the loop spins forever (a hang — neither exit 0 nor exit 2; would block
# GC-at-setup). A missing flag value is the same class of caller error as an unknown flag.
# A flag-shaped value (the next token starts with `-`, e.g. `--root --json`) is ALSO a
# missing value: silently swallowing the next flag as the value would scan the wrong root.
# `need_value <flag> <remaining-argc> <next>`: exit 2 if no next token OR it is flag-shaped.
need_value() {
  local flag="$1" argc="$2" next="$3"
  [ "$argc" -ge 2 ] || { echo "drive-retention.sh: $flag needs a value" >&2; exit 2; }
  case "$next" in
    -*) echo "drive-retention.sh: $flag needs a value (got flag-shaped: $next)" >&2; exit 2 ;;
  esac
}
while [ $# -gt 0 ]; do
  case "$1" in
    --root)     need_value --root "$#" "$2"; ROOT="$2"; shift 2 ;;
    --age-days) need_value --age-days "$#" "$2"; AGE_DAYS="$2"; shift 2 ;;
    --now)      need_value --now "$#" "$2"; NOW="$2"; shift 2 ;;
    --json)     JSON=1; shift ;;
    *)
      echo "drive-retention.sh: unknown flag: $1" >&2
      echo "usage: drive-retention.sh [--root <dir>] [--age-days <N>] [--now <epoch>] [--json]" >&2
      exit 2
      ;;
  esac
done

# --now default = wall clock. A non-integer override falls back with a notice.
if [ -z "$NOW" ]; then
  NOW="$(date +%s)"
elif ! printf '%s' "$NOW" | grep -qE '^[0-9]+$'; then
  echo "drive-retention.sh: --now must be a unix epoch integer; using current time" >&2
  NOW="$(date +%s)"
fi

# --age-days must be a non-negative integer; malformed ⇒ fall back to 14 with a notice.
if ! printf '%s' "$AGE_DAYS" | grep -qE '^[0-9]+$'; then
  echo "drive-retention.sh: --age-days must be a non-negative integer; using 14" >&2
  AGE_DAYS=14
fi
AGE_SECS=$((AGE_DAYS * 86400))

# jq is required to classify. Absent ⇒ best-effort notice + exit 0 (D3: a missing tool
# must never abort a new run's setup).
if ! command -v jq >/dev/null 2>&1; then
  echo "drive-retention.sh: jq not found on PATH; cannot classify (best-effort, nothing done)" >&2
  exit 0
fi

# Root must exist and be a directory; absent ⇒ one-line notice + exit 0 (nothing to do).
if [ ! -d "$ROOT" ]; then
  echo "drive-retention.sh: root not a directory: $ROOT (nothing to do)" >&2
  exit 0
fi

# ----------------------------------------------------------------------------- #
# Small helpers
# ----------------------------------------------------------------------------- #

# Read a top-level scalar field from a run's state.json. Echoes the value or empty
# (torn/missing JSON, absent field, or jq error ⇒ empty — conservative). $1=run_dir $2=field
state_field() {
  local sj="$1/state.json" field="$2" v
  [ -f "$sj" ] || { printf ''; return; }
  v="$(jq -r --arg f "$field" '.[$f] // empty' "$sj" 2>/dev/null)"
  [ "$v" = "null" ] && v=""
  printf '%s' "$v"
}

# rc0 iff the run is LIVE-QUIET on the waiting axis: state.json's `.waiting` is ABSENT or
# explicitly JSON null. ANY PARSEABLE present-and-non-null `.waiting` (including `false`,
# `0`, or a string) means the run is NOT live-quiet ⇒ rc1 (the caller emits skip:waiting).
# `state_field` collapses false/0/null to empty, so it CANNOT distinguish `waiting:false`
# (NOT live-quiet) from an absent field — gate on `.waiting == null` directly instead.
# Mirrors the sibling drive-conformance.sh, which treats a non-null `waiting` as malformed.
# A MISSING / torn / unreadable state.json (jq error) is NOT a present non-null waiting — it
# is treated as quiet here and caught downstream by the DONE gate (a torn state can never
# produce a done signal ⇒ skip:not-done — the documented edge-2 fail-safe, kept CONSISTENT
# across tiers). $1=run_dir
is_waiting_quiet() {
  local sj="$1/state.json" v
  [ -f "$sj" ] || return 0          # no state.json ⇒ no waiting field ⇒ quiet (caught by DONE gate)
  # `.waiting == null` is true for BOTH an absent key and an explicit null — exactly the two
  # live-quiet cases. A jq error on torn JSON ⇒ rc≠0 ⇒ treat as quiet (DONE gate catches it).
  v="$(jq -r 'if (.waiting == null) then "quiet" else "set" end' "$sj" 2>/dev/null)" || return 0
  [ "$v" = "quiet" ]
}

# Parse a timestamp string to a unix epoch. Echoes the epoch on success, rc1 on failure.
# Accepts either a bare integer (already epoch) or an ISO-8601 string (e.g.
# 2026-06-22T10:11:00Z). $1=string
parse_ts() {
  local s="$1" e
  [ -n "$s" ] || return 1
  if printf '%s' "$s" | grep -qE '^[0-9]+$'; then
    printf '%s\n' "$s"; return 0
  fi
  # GNU date (-d) and BSD/macOS date (-j -f) differ — try both forms; suppress errors.
  e="$(date -d "$s" +%s 2>/dev/null)" && [ -n "$e" ] && { printf '%s\n' "$e"; return 0; }
  # macOS: strip trailing Z and parse as UTC.
  local sz="${s%Z}"
  e="$(TZ=UTC date -j -f '%Y-%m-%dT%H:%M:%S' "$sz" +%s 2>/dev/null)" \
    && [ -n "$e" ] && { printf '%s\n' "$e"; return 0; }
  return 1
}

# Echo the parseable completedAt epoch for a run, rc1 if missing/unparseable. $1=run_dir
completedat_epoch() {
  local f="$1/completedAt" content
  [ -f "$f" ] || return 1
  content="$(head -n1 "$f" 2>/dev/null)"
  content="$(printf '%s' "$content" | tr -d '[:space:]')"
  parse_ts "$content"
}

# rc0 iff a parseable completedAt marker exists (the run-level W4 authorization signal).
# $1=run_dir
completedat_authorizes() {
  completedat_epoch "$1" >/dev/null 2>&1
}

# Newest event-log timestamp epoch = MAX over ALL parseable .at values across EVERY line
# (NOT the last line — a torn/backdated tail line could otherwise hide a newer earlier
# timestamp, and appending does not bump run-dir mtime ⇒ a fail-open on age). Echoes the
# epoch or empty if no parseable line. rc1 on a READ FAILURE of a PRESENT log (file exists
# but is unreadable / cannot be read by jq) — distinct from a genuinely-absent/empty log
# (which is rc0 + empty). A read failure must NOT be conflated with empty: an unreadable
# log may hold a RECENT timestamp, so the caller fails the age gate safe (treats the run as
# recent, never aged ⇒ never swept) rather than falling back to a stale mtime (a fail-open
# that would sweep a recently-active run whose age evidence we cannot read). $1=run_dir
eventlog_newest_epoch() {
  local log="$1/event-log.jsonl" best="" at e
  [ -e "$log" ] || { printf ''; return 0; }   # genuinely absent ⇒ empty, NOT a read failure
  # Present but unreadable ⇒ READ FAILURE (rc1): a dirent exists (caught by -e above) but it
  # is not a regular readable file, OR a `cat` of it errors (perm-denied / unreadable). Both
  # the file-test AND an actual read are checked — a present log we cannot read its bytes is
  # a read failure, never conflated with a genuinely-empty log.
  { [ -f "$log" ] && [ -r "$log" ] && cat "$log" >/dev/null 2>&1; } || return 1
  # PER-LINE tolerant parse: `-R` reads each raw line, `fromjson?` yields nothing for an
  # unparseable (torn / non-JSON) line instead of erroring the whole pipeline. A whole-file
  # `jq '.at'` errors on the FIRST invalid line and STOPS — dropping every timestamp AFTER
  # it (a newer .at past a torn line would be lost ⇒ a recently-touched run looks aged ⇒
  # age fail-open). With `-R 'fromjson? | .at // empty'` a torn line is skipped and the
  # other lines' .at values still count. Each emitted .at is parsed (ISO-8601 or epoch).
  while IFS= read -r at; do
    [ -n "$at" ] || continue
    e="$(parse_ts "$at")" || continue
    if [ -z "$best" ] || [ "$e" -gt "$best" ]; then best="$e"; fi
  done < <(jq -R -r 'fromjson? | .at // empty' "$log" 2>/dev/null)
  printf '%s' "$best"
  return 0
}

# Run-dir mtime epoch. $1=run_dir
mtime_epoch() {
  local d="$1" e
  e="$(stat -f %m "$d" 2>/dev/null)" || e="$(stat -c %Y "$d" 2>/dev/null)"
  printf '%s' "$e"
}

# Age union: max(run-dir mtime, newest event-log .at, completedAt-if-parseable). Sets
# globs AGE_EPOCH (the max), AGE_ANCHOR (which input supplied it: mtime|event-log|completedAt).
# $1=run_dir
compute_age() {
  local d="$1" m el ca best="" anchor="mtime" el_rc
  m="$(mtime_epoch "$d")"
  el="$(eventlog_newest_epoch "$d")"; el_rc=$?
  ca="$(completedat_epoch "$d" 2>/dev/null)" || ca=""

  # FAIL-SAFE: a PRESENT-but-UNREADABLE event-log (rc1) may hold a RECENT timestamp we cannot
  # read. Do NOT fall back to a stale mtime (which would wrongly age the run ⇒ sweep a
  # recently-active run). Treat the unreadable log as supplying a NOW anchor — most-recent-
  # wins ⇒ age 0 ⇒ never aged ⇒ never swept. The anchor is reported as `event-log`.
  if [ "$el_rc" -ne 0 ]; then el="$NOW"; fi

  if [ -n "$m" ]; then best="$m"; anchor="mtime"; fi
  if [ -n "$el" ] && { [ -z "$best" ] || [ "$el" -gt "$best" ]; }; then best="$el"; anchor="event-log"; fi
  if [ -n "$ca" ] && { [ -z "$best" ] || [ "$ca" -gt "$best" ]; }; then best="$ca"; anchor="completedAt"; fi

  AGE_EPOCH="${best:-0}"
  AGE_ANCHOR="$anchor"
}

# rc0 iff the run is past the age threshold. Age = max(now - AGE_EPOCH, 0) clamped at 0
# (a future anchor ⇒ age 0 ⇒ never aged ⇒ recently-touched never swept). Uses AGE_EPOCH.
is_aged() {
  local age=$((NOW - AGE_EPOCH))
  [ "$age" -lt 0 ] && age=0
  [ "$age" -ge "$AGE_SECS" ]
}

# rc0 iff the run shows a positive DONE signal: parseable completedAt OR state.stage=="done".
# $1=run_dir
is_done() {
  completedat_authorizes "$1" && return 0
  [ "$(state_field "$1" stage)" = "done" ] && return 0
  return 1
}

# rc0 iff a name matches the drive-owned wt/ grammar:
#   slice-id ^[0-9]+[a-z]?\.[0-9]+$ | phase<P> | design<P> | ship | verify* | finalize
# $1=name
is_drive_owned_name() {
  local n="$1"
  case "$n" in
    ship|finalize) return 0 ;;
  esac
  printf '%s' "$n" | grep -qE '^[0-9]+[a-z]?\.[0-9]+$' && return 0   # slice-id
  printf '%s' "$n" | grep -qE '^phase[0-9]+[a-z]?$' && return 0      # phase<P>
  printf '%s' "$n" | grep -qE '^design[0-9]+[a-z]?$' && return 0     # design<P>
  printf '%s' "$n" | grep -qE '^verify[0-9]*$' && return 0           # verify*
  return 1
}

# Three-way registration of a run's wt/<name>/.git by PATH EQUALITY (DP9). Echoes
# `registered` | `not-registered` | `unprovable`. $1=run_dir $2=child-name
#   not-registered : NO wt/<name>/.git pointer file at all (the ONLY fall-through to W7).
#   registered     : pointer resolves to <repo>/.git/worktrees/<id> AND that admin entry's
#                    `gitdir` back-reference file content equals THIS run's wt/<name>/.git
#                    (absolute path equality).
#   unprovable     : pointer EXISTS but path equality can be neither confirmed nor refuted
#                    (admin dir missing / back-ref unreadable / dangling / different / error).
wt_registered_anywhere() {
  local d="$1" name="$2"
  local ptr="$d/wt/$name/.git"
  # The worktree-registration POINTER is a FILE containing `gitdir: <path>`.
  #   - `.git` is a DIRECTORY, or there is NO `.git` at all ⇒ "no pointer file" ⇒
  #     not-registered (the ONLY fall-through to W7 — a restored/recreated full checkout,
  #     edge 11).
  #   - a `.git` dirent EXISTS but is not a readable regular file (a DANGLING symlink, an
  #     unreadable pointer) ⇒ a pointer is present yet unprovable ⇒ unprovable (edge 5).
  #   - a readable `.git` regular file ⇒ proceed to the path-equality test below.
  if [ -d "$ptr" ]; then printf 'not-registered'; return; fi
  if [ ! -e "$ptr" ] && [ ! -L "$ptr" ]; then printf 'not-registered'; return; fi
  if [ ! -f "$ptr" ]; then printf 'unprovable'; return; fi

  local line admin backref selfpath
  line="$(head -n1 "$ptr" 2>/dev/null)" || { printf 'unprovable'; return; }
  case "$line" in
    gitdir:\ *) admin="${line#gitdir: }" ;;
    gitdir:*)   admin="${line#gitdir:}" ;;
    *)          printf 'unprovable'; return ;;
  esac
  [ -n "$admin" ] || { printf 'unprovable'; return; }
  # The admin entry's gitdir back-reference must exist and its content must path-equal THIS
  # run's wt/<name>/.git.
  backref="$admin/gitdir"
  [ -f "$backref" ] || { printf 'unprovable'; return; }
  backref="$(head -n1 "$backref" 2>/dev/null)" || { printf 'unprovable'; return; }
  backref="$(printf '%s' "$backref" | sed 's/[[:space:]]*$//')"
  selfpath="$ptr"
  if [ "$backref" = "$selfpath" ]; then
    printf 'registered'
  else
    printf 'unprovable'
  fi
}

# Owning-repo resolution (DP6): state.repoRoot (non-null AND existing dir) ELSE the first
# path-verified registered wt/<name>/.git gitdir → <repo> ELSE empty (UNRESOLVABLE).
# Echoes <repo-root> or empty. $1=run_dir
resolve_owning_repo() {
  local d="$1" rr child name reg admin repo
  rr="$(state_field "$d" repoRoot)"
  if [ -n "$rr" ] && [ -d "$rr" ]; then
    printf '%s' "$rr"; return
  fi
  # Fall back to the first registered wt/<name>/.git: admin = <repo>/.git/worktrees/<id>,
  # strip /worktrees/<id> → <repo>/.git, strip /.git → <repo>.
  if [ -d "$d/wt" ]; then
    for child in "$d"/wt/*; do
      [ -d "$child" ] || continue
      name="${child##*/}"
      # Only a DRIVE-OWNED-named registered child may resolve the owning repo (DP6 intends
      # the repo /drive cut the run's branches from). A real run carries ad-hoc children
      # (converter/scripts/test_projects — edge 10); trusting one's gitdir would resolve the
      # owning repo to a FOREIGN repo, so the ancestry probe would run in the WRONG repo and
      # could falsely authorize a sibling drive-owned child. Filter ad-hoc names out here.
      is_drive_owned_name "$name" || continue
      reg="$(wt_registered_anywhere "$d" "$name")"
      [ "$reg" = "registered" ] || continue
      admin="$(head -n1 "$child/.git" 2>/dev/null)"
      case "$admin" in
        gitdir:\ *) admin="${admin#gitdir: }" ;;
        gitdir:*)   admin="${admin#gitdir:}" ;;
        *) continue ;;
      esac
      # admin = <repo>/.git/worktrees/<id> → strip trailing /worktrees/<id>
      repo="${admin%/worktrees/*}"   # <repo>/.git
      repo="${repo%/.git}"           # <repo>
      [ -n "$repo" ] && [ -d "$repo" ] && { printf '%s' "$repo"; return; }
    done
  fi
  printf ''
}

# Live READ-ONLY ancestry probe (DP5). Echoes `yes` | `no` | `unprovable`. ALWAYS attempts
# the probe when the repo is resolvable (no baseRef pre-check — let git's rc decide):
#   rc0 → yes (ancestor) · rc1 → no (not ancestor) · rc>1 (incl. baseRef absent / git error) → unprovable
# $1=run_dir $2=repo_root
is_ancestor_in_owning_repo() {
  local d="$1" repo="$2" runId baseRef rc
  runId="${d##*/}"
  baseRef="$(state_field "$d" baseRef)"
  command -v git >/dev/null 2>&1 || { printf 'unprovable'; return; }
  git -C "$repo" merge-base --is-ancestor "drive/$runId" "$baseRef" >/dev/null 2>&1
  rc=$?
  case "$rc" in
    0) printf 'yes' ;;
    1) printf 'no' ;;
    *) printf 'unprovable' ;;
  esac
}

# W7b cleanliness probe of an EXISTING unregistered (no-pointer) dir. Echoes
# `clean` | `dirty` | `unpushed` | `unreadable`. ALWAYS required for an existing dir,
# REGARDLESS of completedAt (DP8). $1=dir
wt_cleanliness() {
  local dir="$1" porcelain rc
  command -v git >/dev/null 2>&1 || { printf 'unreadable'; return; }
  porcelain="$(git -C "$dir" status --porcelain 2>/dev/null)"
  rc=$?
  [ "$rc" -eq 0 ] || { printf 'unreadable'; return; }
  [ -z "$porcelain" ] || { printf 'dirty'; return; }
  # Unpushed: any local commit not reachable from any remote-tracking ref. `--all` (not
  # `--branches`) so a commit reachable ONLY from a DETACHED HEAD or refs/stash is also
  # caught — a /drive worktree is often on a detached HEAD, and `--branches` would miss its
  # unpushed commit (report==apply fail-open: Phase 2 --apply would lose it). `--all` covers
  # HEAD + branches + stash; a genuinely-pushed-clean checkout still yields empty. If there
  # are no remotes/upstreams the conservative answer is unpushed (cannot prove pushed).
  local unpushed
  unpushed="$(git -C "$dir" log --all --not --remotes --oneline 2>/dev/null)"
  rc=$?
  [ "$rc" -eq 0 ] || { printf 'unreadable'; return; }
  [ -z "$unpushed" ] || { printf 'unpushed'; return; }
  printf 'clean'
}

# ----------------------------------------------------------------------------- #
# Tier-L classification — echoes `eligible` | `skip:<reason>`. $1=run_dir
# L1 waiting==null · L2 no open inflight · L3 done signal · L4 aged.
# ----------------------------------------------------------------------------- #
classify_tier_L() {
  local d="$1"
  is_waiting_quiet "$d" || { printf 'skip:waiting'; return; }
  has_open_inflight "$d" && { printf 'skip:inflight-open'; return; }
  is_done "$d" || { printf 'skip:not-done'; return; }
  is_aged || { printf 'skip:not-aged'; return; }
  printf 'eligible'
}

# rc0 iff ANY open inflight-*.marker exists (`-e || -L` so a dangling symlink still counts
# as open, mirroring drive-conformance.sh). $1=run_dir
has_open_inflight() {
  local d="$1" f
  for f in "$d"/inflight-*.marker; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    return 0
  done
  return 1
}

# ----------------------------------------------------------------------------- #
# Tier-W per-child classification — echoes `eligible` | `skip:<reason>`.
# First-failing-gate-wins precedence: W6 → W5 → W1/W2/Wd/W3 → W4 → W7b.
# $1=run_dir $2=child-name $3=owning-repo (may be empty = UNRESOLVABLE)
# ----------------------------------------------------------------------------- #
classify_tier_W_child() {
  local d="$1" name="$2" repo="$3"

  # W6 — drive-owned name (per-child; no repo, no git). Cheapest first.
  is_drive_owned_name "$name" || { printf 'skip:not-drive-owned'; return; }

  # W5 — registration (three-way path equality; per-child; pure file reads, no git).
  local reg
  reg="$(wt_registered_anywhere "$d" "$name")"
  case "$reg" in
    registered) printf 'skip:wt-registered'; return ;;
    unprovable) printf 'skip:registration-unprovable'; return ;;
    not-registered) ;;   # the ONLY fall-through to W7
  esac

  # W1/W2/Wd/W3 — run-level liveness + DONE + age.
  is_waiting_quiet "$d" || { printf 'skip:waiting'; return; }
  has_open_inflight "$d" && { printf 'skip:inflight-open'; return; }
  is_done "$d" || { printf 'skip:not-done'; return; }
  is_aged || { printf 'skip:not-aged'; return; }

  # W4 — authorization (run-level). completedAt replaces ancestry; else probe the repo.
  if ! completedat_authorizes "$d"; then
    [ -n "$repo" ] || { printf 'skip:unresolvable-repo'; return; }
    local anc
    anc="$(is_ancestor_in_owning_repo "$d" "$repo")"
    case "$anc" in
      yes) ;;   # authorized
      no) printf 'skip:not-ancestor'; return ;;
      unprovable) printf 'skip:ancestry-unprovable'; return ;;
    esac
  fi

  # W7b — cleanliness of the existing no-pointer dir (ALWAYS, regardless of completedAt).
  local clean
  clean="$(wt_cleanliness "$d/wt/$name")"
  case "$clean" in
    clean) printf 'eligible' ;;
    dirty) printf 'skip:dirty' ;;
    unpushed) printf 'skip:unpushed' ;;
    unreadable) printf 'skip:unreadable' ;;
  esac
}

# ----------------------------------------------------------------------------- #
# Tier-L log inventory — echoes one `name<TAB>bytes` line per heavy log file.
# Families: codex-raw-*.log and codex-harden-*.log. KEEP all .md/.json/.jsonl. $1=run_dir
# ----------------------------------------------------------------------------- #
heavy_logs() {
  local d="$1" f b name
  for f in "$d"/codex-raw-*.log "$d"/codex-harden-*.log; do
    [ -f "$f" ] || continue
    b="$(stat -f %z "$f" 2>/dev/null)" || b="$(stat -c %s "$f" 2>/dev/null)"
    name="${f##*/}"
    printf '%s\t%s\n' "$name" "${b:-0}"
  done
}

# ----------------------------------------------------------------------------- #
# Output rendering
# ----------------------------------------------------------------------------- #

# JSON-emit one run object (JSONL). Uses globals set by classify_run. $1=run_dir
emit_json_run() {
  local d="$1" runId="${1##*/}"

  # Tier-L logs JSON array + total bytes.
  local logs_json="[]" total_bytes=0 line name bytes
  local logs_acc=""
  while IFS=$'\t' read -r name bytes; do
    [ -n "$name" ] || continue
    logs_acc="$logs_acc$(jq -cn --arg n "$name" --argjson b "${bytes:-0}" '{name:$n,bytes:$b}'),"
    total_bytes=$((total_bytes + ${bytes:-0}))
  done < <(heavy_logs "$d")
  [ -n "$logs_acc" ] && logs_json="[${logs_acc%,}]"

  local tierL_eligible="false" tierL_reason=""
  if [ "$TIERL_VERDICT" = "eligible" ]; then tierL_eligible="true"; else tierL_reason="${TIERL_VERDICT#skip:}"; fi

  # Tier-W children array.
  local children_json="[]" children_acc="" child verdict elig reason owned regfield
  local i=0
  while [ "$i" -lt "${#TW_NAMES[@]:-0}" ]; do
    child="${TW_NAMES[$i]}"
    verdict="${TW_VERDICTS[$i]}"
    owned="${TW_OWNED[$i]}"
    regfield="${TW_REG[$i]}"   # true | false | unprovable
    if [ "$verdict" = "eligible" ]; then elig="true"; reason=""; else elig="false"; reason="${verdict#skip:}"; fi
    if [ "$regfield" = "unprovable" ]; then
      children_acc="$children_acc$(jq -cn --arg n "$child" --argjson e "$elig" --arg r "$reason" \
        --argjson o "$owned" --arg reg "unprovable" \
        '{name:$n,eligible:$e,reason:$r,driveOwned:$o,registered:$reg}'),"
    else
      children_acc="$children_acc$(jq -cn --arg n "$child" --argjson e "$elig" --arg r "$reason" \
        --argjson o "$owned" --argjson reg "$regfield" \
        '{name:$n,eligible:$e,reason:$r,driveOwned:$o,registered:$reg}'),"
    fi
    i=$((i + 1))
  done
  [ -n "$children_acc" ] && children_json="[${children_acc%,}]"

  local owningRepo_json="null"
  [ -n "$OWNING_REPO" ] && owningRepo_json="$(jq -cn --arg r "$OWNING_REPO" '$r')"
  local past="false"; [ "$PAST_THRESHOLD" = "1" ] && past="true"

  jq -cn \
    --arg runId "$runId" \
    --argjson owningRepo "$owningRepo_json" \
    --argjson ageDays "$AGE_REPORT_DAYS" \
    --arg ageAnchor "$AGE_ANCHOR" \
    --argjson pastThreshold "$past" \
    --argjson tierL_eligible "$tierL_eligible" \
    --arg tierL_reason "$tierL_reason" \
    --argjson tierL_logs "$logs_json" \
    --argjson tierL_bytes "$total_bytes" \
    --argjson children "$children_json" \
    '{runId:$runId, owningRepo:$owningRepo, ageDays:$ageDays, ageAnchor:$ageAnchor,
      pastThreshold:$pastThreshold,
      tierL:{eligible:$tierL_eligible, reason:$tierL_reason, logs:$tierL_logs, bytes:$tierL_bytes},
      tierW:{children:$children}}'
}

# Human report for one run. $1=run_dir
report_run() {
  local d="$1" runId="${1##*/}" repo_disp past_disp
  repo_disp="${OWNING_REPO:-UNRESOLVABLE}"
  past_disp="no"; [ "$PAST_THRESHOLD" = "1" ] && past_disp="yes"

  printf 'run: %s\n' "$runId"
  printf '  owning-repo: %s\n' "$repo_disp"
  printf '  age: %sd (anchor: %s)  threshold: %sd  past: %s\n' \
    "$AGE_REPORT_DAYS" "$AGE_ANCHOR" "$AGE_DAYS" "$past_disp"

  if [ "$TIERL_VERDICT" = "eligible" ]; then
    local nfiles=0 total=0 name bytes
    while IFS=$'\t' read -r name bytes; do
      [ -n "$name" ] || continue
      nfiles=$((nfiles + 1)); total=$((total + ${bytes:-0}))
    done < <(heavy_logs "$d")
    printf '  Tier-L (heavy logs): WOULD-SWEEP <%s files, ~%s MB>\n' "$nfiles" "$((total / 1048576))"
  else
    printf '  Tier-L (heavy logs): SKIP (%s)\n' "${TIERL_VERDICT#skip:}"
  fi

  printf '  Tier-W (drive-owned worktrees):\n'
  if [ "${#TW_NAMES[@]:-0}" -eq 0 ]; then
    printf '    (no wt/ children)\n'
  else
    local i=0 child verdict
    while [ "$i" -lt "${#TW_NAMES[@]}" ]; do
      child="${TW_NAMES[$i]}"; verdict="${TW_VERDICTS[$i]}"
      if [ "$verdict" = "eligible" ]; then
        printf '    wt/%s: WOULD-REMOVE\n' "$child"
      else
        printf '    wt/%s: SKIP (%s)\n' "$child" "${verdict#skip:}"
      fi
      i=$((i + 1))
    done
  fi
}

# ----------------------------------------------------------------------------- #
# Per-run classification — populates the globals report_run / emit_json_run read.
# $1=run_dir
# ----------------------------------------------------------------------------- #
classify_run() {
  local d="$1" child name reg verdict age

  OWNING_REPO="$(resolve_owning_repo "$d")"

  compute_age "$d"   # sets AGE_EPOCH, AGE_ANCHOR
  age=$((NOW - AGE_EPOCH)); [ "$age" -lt 0 ] && age=0
  AGE_REPORT_DAYS=$((age / 86400))
  if is_aged; then PAST_THRESHOLD=1; else PAST_THRESHOLD=0; fi

  TIERL_VERDICT="$(classify_tier_L "$d")"

  TW_NAMES=(); TW_VERDICTS=(); TW_OWNED=(); TW_REG=()
  if [ -d "$d/wt" ]; then
    for child in "$d"/wt/*; do
      [ -e "$child" ] || [ -L "$child" ] || continue
      name="${child##*/}"
      reg="$(wt_registered_anywhere "$d" "$name")"
      verdict="$(classify_tier_W_child "$d" "$name" "$OWNING_REPO")"
      TW_NAMES+=("$name")
      TW_VERDICTS+=("$verdict")
      if is_drive_owned_name "$name"; then TW_OWNED+=("true"); else TW_OWNED+=("false"); fi
      case "$reg" in
        registered)     TW_REG+=("true") ;;
        not-registered) TW_REG+=("false") ;;
        *)              TW_REG+=("unprovable") ;;
      esac
    done
  fi
}

# ----------------------------------------------------------------------------- #
# Main scan
# ----------------------------------------------------------------------------- #
runs_scanned=0
tierL_runs=0
tierL_bytes_total=0
tierW_worktrees=0
tierW_runs=0
skipped=0

for run_dir in "$ROOT"/*; do
  [ -d "$run_dir" ] || continue
  runs_scanned=$((runs_scanned + 1))

  # Per-run isolation: any unexpected failure inside classification is swallowed (the loop
  # continues), never aborting the scan (D3). classify_run + the renderers are best-effort.
  classify_run "$run_dir" 2>/dev/null

  if [ "$JSON" -eq 1 ]; then
    emit_json_run "$run_dir" 2>/dev/null
  else
    report_run "$run_dir" 2>/dev/null
  fi

  # Summary tallies. Tier-L and Tier-W are counted INDEPENDENTLY (each tier's skip is its
  # own "item skipped"); a Tier-W skip under a Tier-L-eligible run is NOT lost. Bytes are
  # SUMMED across runs and converted to MB ONCE at the end (per-run flooring would report
  # several sub-MB reclaimable logs as ~0 MB total).
  if [ "$TIERL_VERDICT" = "eligible" ]; then
    tierL_runs=$((tierL_runs + 1))
    while IFS=$'\t' read -r lname lbytes; do
      [ -n "$lname" ] || continue
      tierL_bytes_total=$((tierL_bytes_total + ${lbytes:-0}))
    done < <(heavy_logs "$run_dir")
  else
    skipped=$((skipped + 1))   # Tier-L skip for this run
  fi

  run_has_wt_elig=0
  i=0
  while [ "$i" -lt "${#TW_VERDICTS[@]:-0}" ]; do
    if [ "${TW_VERDICTS[$i]}" = "eligible" ]; then
      tierW_worktrees=$((tierW_worktrees + 1))
      run_has_wt_elig=1
    else
      skipped=$((skipped + 1))   # Tier-W child skip — counted independently of Tier-L
    fi
    i=$((i + 1))
  done
  [ "$run_has_wt_elig" -eq 1 ] && tierW_runs=$((tierW_runs + 1))
done

if [ "$JSON" -ne 1 ]; then
  tierL_mb=$((tierL_bytes_total / 1048576))
  printf 'summary: %s runs scanned · Tier-L would reclaim ~%s MB across %s runs · Tier-W would remove %s worktrees across %s runs · %s runs/items skipped\n' \
    "$runs_scanned" "$tierL_mb" "$tierL_runs" "$tierW_worktrees" "$tierW_runs" "$skipped"
fi

exit 0
