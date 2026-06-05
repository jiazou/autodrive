#!/usr/bin/env bash
# drive-merge-gate.sh — PreToolUse(Bash) hook: the primary /drive enforcement gate.
#
# Reads the hook JSON on stdin (.tool_input.command, .cwd via jq). Matches the
# command against the gate matcher table, resolves the runId of the /drive run, runs
# drive-conformance.sh for the matched mode, and — ONLY on a conformance violation —
# emits a PreToolUse `deny` whose reason names the scope + the exact /drive-review
# command to run before retrying.
#
# Composition contract (D5): the gate emits `deny` ONLY. Clean OR non-matching
# command → NO output, exit 0. This lets it compose with the existing Bash PreToolUse
# hooks (which emit `allow`/`ask`) and never override their decisions; correctness
# relies on Claude Code's documented deny-beats-allow precedence for same-event hooks.
#
# Fail mode (D4, asymmetric): plan-gate + ship are RUN-BOUNDARY gates → on a
# conformance exit 2 (git/IO error) they fail CLOSED (DENY). slice-merge + phase-merge
# are mid-build per-unit gates → on exit 2 they fail OPEN (silent, exit 0) so a
# transient git error cannot wedge a mid-build run; the ship gate backstops them.
#
# Locate sibling scripts robustly (works installed or in a worktree).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/drive-hook-lib.sh"
CONFORMANCE="$SCRIPT_DIR/drive-conformance.sh"

# Emit a PreToolUse deny with the given reason (JSON-escaped) and exit 0.
# (We exit 0 because the *hook* ran fine — the deny verdict is carried in the JSON,
# not in the hook's exit code.)
emit_deny() {
  local reason="$1"
  # JSON-escape: backslash, double-quote, then control chars (newline/tab/CR).
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  reason="${reason//$'\n'/\\n}"
  reason="${reason//$'\t'/\\t}"
  reason="${reason//$'\r'/\\r}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 0
}

# --- read hook JSON from stdin ---
INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0
[ -n "$CWD" ] || CWD="$PWD"

# detect_subcommand <binary> <words...> : echo the real subcommand for a binary
# invocation, i.e. the first NON-flag word AFTER the binary, skipping:
#   - env `VAR=val` prefixes that precede the binary (handled by the caller, which
#     scans for the binary first; this fn is called with the binary as $1),
#   - global options that take a separate argument: `-C <path>`, `-c <kv>`,
#     `-R <x>`, `--repo <x>` (consume the following word),
#   - inline global options: `--git-dir=…`, `--work-tree=…`, `--repo=…`,
#   - generic short `-x` and long `--x` / `--x=y` flags.
# Returns the subcommand on stdout (empty if none). bash 3.2-safe (positional args).
detect_subcommand() {
  shift                                   # drop the binary itself ($1)
  while [ "$#" -gt 0 ]; do
    case "$1" in
      # global options that consume the NEXT word as their value:
      -C|-c|-R|--repo|--git-dir|--work-tree)
        shift; [ "$#" -gt 0 ] && shift; continue ;;
      # inline `--opt=value` (and `--opt` with no value): a single flag word.
      --*=*|--*) shift; continue ;;
      # short flags `-x` (incl. clustered like `-xyz`): a single flag word.
      -?*) shift; continue ;;
      # bare `-` or empty → not a subcommand; stop.
      -|"") break ;;
      # first non-flag word → this is the real subcommand.
      *) printf '%s' "$1"; return 0 ;;
    esac
  done
  return 0
}

# subcommand_of <binary> : tokenize $CMD (word-split is intentional here — we only
# read the leading binary+flags region), identify the binary at the START of the
# command (after skipping ONLY leading env `VAR=val` prefixes), then return the real
# subcommand via detect_subcommand. Echoes empty if the START binary isn't <binary>.
#
# CRITICAL: we do NOT rescan for a later bare <binary> token. The binary is whatever
# word starts the command after env assignments — so `echo git push` has binary
# `echo` (not `git`) → subcommand_of git returns empty → inert. Only a `NAME=value`
# word (POSIX env-assignment shape: NAME is [A-Za-z_][A-Za-z0-9_]* and contains `=`)
# is skipped as a prefix; the first non-assignment word IS the binary.
# NOTE: this inspects the *literal* command; runtime-variable refs in later args are
# handled elsewhere. bash 3.2-safe.
subcommand_of() {
  local bin="$1" w
  set -f                                   # noglob: a literal `*` in $CMD must not expand.
  # shellcheck disable=SC2086  # intentional word-split of the command string.
  set -- $CMD
  set +f
  # Skip leading env VAR=val prefixes ONLY (POSIX assignment shape).
  while [ "$#" -gt 0 ]; do
    w="$1"
    case "$w" in
      [A-Za-z_]*=*) shift; continue ;;     # env assignment prefix → skip
      *) break ;;                          # first non-assignment word = the binary
    esac
  done
  # The START binary must be exactly <binary>; no rescan for a later token.
  [ "$#" -gt 0 ] || { printf ''; return 0; }
  [ "$1" = "$bin" ] || { printf ''; return 0; }
  detect_subcommand "$@"
}

# action_after <binary> <subcommand> : echo the next NON-flag word AFTER the resolved
# subcommand for a binary invocation (the "action"), e.g. for `gh pr create` →
# subcommand `pr`, action `create`; for `gh pr view --json createdAt` → action `view`.
# Used so gh/glab ship detection matches the subcommand+action pair EXACTLY
# (`pr create` / `mr create`), not a `*create*` substring anywhere in the command.
# Returns empty if the binary's START match fails or there is no action word.
# bash 3.2-safe (positional args; same env-prefix / global-option skipping rules as
# subcommand_of + detect_subcommand).
action_after() {
  local bin="$1" w
  set -f
  # shellcheck disable=SC2086
  set -- $CMD
  set +f
  # Skip leading env VAR=val prefixes; require START binary == <bin> (no rescan).
  while [ "$#" -gt 0 ]; do
    case "$1" in [A-Za-z_]*=*) shift; continue ;; *) break ;; esac
  done
  [ "$#" -gt 0 ] && [ "$1" = "$bin" ] || { printf ''; return 0; }
  shift                                     # drop the binary
  # Skip global options exactly as detect_subcommand does, to reach the subcommand.
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -C|-c|-R|--repo|--git-dir|--work-tree) shift; [ "$#" -gt 0 ] && shift; continue ;;
      --*=*|--*) shift; continue ;;
      -?*) shift; continue ;;
      -|"") printf ''; return 0 ;;
      *) break ;;                           # this is the subcommand
    esac
  done
  [ "$#" -gt 0 ] || { printf ''; return 0; }
  shift                                     # drop the subcommand; find the action word
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --*=*|--*) shift; continue ;;
      -?*) shift; continue ;;
      -|"") printf ''; return 0 ;;
      *) printf '%s' "$1"; return 0 ;;      # first non-flag word after subcommand = action
    esac
  done
  return 0
}

# git_target_repo : if the git invocation carries a repo-locating global option
# (`-C <path>`, `--git-dir=<path>`/`--git-dir <path>`, `--work-tree=<path>`/
# `--work-tree <path>`), echo that path; else echo empty. The LAST such option wins
# (git's own semantics: a later -C/-git-dir overrides an earlier one). When present,
# the caller uses this path as the repo for runId-from-HEAD AND as the conformance cd
# target, instead of $CWD — so `git -C <repo> push` from outside resolves correctly.
# Only meaningful when the START binary is `git`. bash 3.2-safe.
git_target_repo() {
  local w path=""
  set -f
  # shellcheck disable=SC2086
  set -- $CMD
  set +f
  while [ "$#" -gt 0 ]; do
    case "$1" in [A-Za-z_]*=*) shift; continue ;; *) break ;; esac
  done
  [ "$#" -gt 0 ] && [ "$1" = git ] || { printf ''; return 0; }
  shift
  # Scan the global-option region (stop at the first non-flag word = the subcommand).
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -C|--git-dir|--work-tree)
        # separate-argument form: value is the next word.
        if [ "$#" -gt 1 ]; then path="$2"; shift 2; else shift; fi
        continue ;;
      --git-dir=*) path="${1#--git-dir=}"; shift; continue ;;
      --work-tree=*) path="${1#--work-tree=}"; shift; continue ;;
      # other global options that consume the next word:
      -c|-R|--repo) shift; [ "$#" -gt 0 ] && shift; continue ;;
      --*=*|--*) shift; continue ;;
      -?*) shift; continue ;;
      *) break ;;                           # subcommand reached → stop scanning options
    esac
  done
  printf '%s' "$path"
}

# push_ship_runid : for a `git push ...` invocation, decide whether it SHIPS the drive
# feature branch and, if so, echo the runId (rc 0); else rc 1. ERRS TOWARD GATING over
# arbitrary push syntax (findings #3 + #4) — a false-positive gate is safe (annoying),
# a false-negative is a review-skip bypass. Ship iff:
#   - ANY positional refspec's SOURCE side is drive/<runId> (scans ALL refspecs, so
#     `git push origin main drive/<id>` is gated — not only the 2nd word), OR
#   - an aggregate flag (`--all`/`--mirror`) is present (these push the drive branch), OR
#   - a source==HEAD / bare / remote-only push while REPO's HEAD is drive/<runId>.
# `git push origin main` (explicit non-drive target, non-drive HEAD) → rc 1 (not ship).
# Reads ONLY structural ref args + HEAD — never flag/body VALUE tokens — so a ref-shaped
# token in --body/--push-option cannot fake or re-key a ship. bash 3.2-safe.
push_ship_runid() {
  set -f
  # shellcheck disable=SC2086
  set -- $CMD
  set +f
  # Skip env VAR=val prefixes; require START binary == git.
  while [ "$#" -gt 0 ]; do
    case "$1" in [A-Za-z_]*=*) shift; continue ;; *) break ;; esac
  done
  [ "$#" -gt 0 ] && [ "$1" = git ] || return 1
  shift
  # Skip the git global-option region to reach the subcommand.
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -C|-c|-R|--repo|--git-dir|--work-tree) shift; [ "$#" -gt 0 ] && shift; continue ;;
      --*=*|--*) shift; continue ;;
      -?*) shift; continue ;;
      *) break ;;
    esac
  done
  [ "$#" -gt 0 ] && [ "$1" = push ] || return 1
  shift
  # Walk push args. Err TOWARD gating: collect ALL positional refspecs (not just the
  # 2nd), note aggregate flags (--all/--mirror push the drive branch implicitly), and
  # note a source==HEAD refspec. NEVER read flag VALUES as refs (so a ref-shaped token
  # in --body/--push-option text can't influence classification).
  local positional=0 aggregate=0 head_based=0 refs=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --all|--mirror) aggregate=1; shift ;;
      -o|--push-option|--repo|--receive-pack|--exec) shift; [ "$#" -gt 0 ] && shift ;;
      --*=*|--*) shift ;;
      -?*) shift ;;     # short flags (incl. -u clustered) take no separate value here
      -|"") shift ;;
      *)
        positional=$((positional+1))
        # positional #1 is the remote; #2.. are refspecs
        if [ "$positional" -ge 2 ]; then refs="$refs
$1"; fi
        shift ;;
    esac
  done
  # Scan every refspec's SOURCE side (left of `src:dst`, leading `+` stripped) for the
  # drive feature branch; a literal HEAD/empty source means "current branch".
  local oifs="$IFS" r src found=""
  IFS='
'
  for r in $refs; do
    [ -n "$r" ] || continue
    src="${r#+}"; src="${src%%:*}"
    case "$src" in
      HEAD|"") head_based=1 ;;
      *) if is_drive_branch_ref "$src"; then
           src="${src#refs/heads/}"; found="${src#drive/}"; break
         fi ;;
    esac
  done
  IFS="$oifs"
  # Explicit drive refspec source → authoritative runId (a real positional arg).
  if [ -n "$found" ]; then printf '%s' "$found"; return 0; fi
  # Aggregate push, an explicit HEAD source, or a bare/remote-only push (source == the
  # current branch) → ship iff REPO's HEAD is the drive feature branch.
  if [ "$aggregate" -eq 1 ] || [ "$head_based" -eq 1 ] || [ "$positional" -le 1 ]; then
    local hid; hid="$(drive_runid_from_head "$REPO")" || return 1
    printf '%s' "$hid"; return 0
  fi
  # Push that explicitly targets only non-drive refs (e.g. `git push origin main`) → not ship.
  return 1
}

# is_drive_branch_ref <ref> : rc0 iff <ref> names the drive feature branch
# drive/<runId> (optionally as refs/heads/drive/<runId>) with EXACTLY 2 ref segments
# after `drive/`. Used to decide whether an explicit push source ref is the drive
# branch. bash 3.2-safe.
is_drive_branch_ref() {
  local ref="${1-}"
  ref="${ref#refs/heads/}"
  case "$ref" in
    drive/*)
      local rest="${ref#drive/}"
      case "$rest" in
        */*) return 1 ;;     # extra segment(s) → not the bare feature branch
        "") return 1 ;;
        *) return 0 ;;
      esac ;;
    *) return 1 ;;
  esac
}

# --- match the command to a gate mode ---------------------------------------------
# We classify by structural git/ship intent. A command that matches no class →
# exit 0 silent (inert; not a managed-run transition).

is_plan_gate=false
is_slice_merge=false
is_phase_merge=false
is_ship=false
phase_P=""
# For an explicit `git push <remote> drive/<runId>` the source ref IS a real positional
# argument (NOT body text), so the runId is authoritative from it. Captured here and
# preferred over HEAD in the resolve step. Empty for gh/glab + bare/HEAD-source pushes,
# which key from HEAD (finding #1: never from command/body tokens).
ship_runid=""

# Collect slice ids (multi-slice merge support) into a plain string (bash 3.2-safe).
slice_ids=""

# Distinct phase ids (P = a slice id's prefix before the first '.') whose per-phase design
# review must be gated when their slices are first built (a worktree-add). bash 3.2-safe.
phasedesign_Ps=""

# Identify the REAL subcommand for each candidate binary (first non-flag word after
# the binary, skipping env VAR=val prefixes + global options). This is what defeats
# the contiguous-binary+subcommand bypass: `git -C repo push`, `git -c k=v push`,
# `gh --repo o/r pr create`, `glab -R x mr create` all resolve their subcommand here.
git_sub="$(subcommand_of git)"
gh_sub="$(subcommand_of gh)"
glab_sub="$(subcommand_of glab)"

# Extract every slice/<runId>/<id> token (3-segment) appearing in the command.
# Used both for matching AND for gating EACH slice in a multi-slice merge.
slice_tokens="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])slice/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+' 2>/dev/null || true)"

# Extract the FIRST phaseInt/... token as it appears in the command. We accept ANY
# phaseInt/<...> arg form (not only the 3-segment phaseInt/<runId>/<P>) so the gate
# stays correct regardless of phaseInt naming (Slice 3.1 ordering). The last path
# segment is taken as P and passed to conformance, which keys phase-merge by P.
phaseint_token="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])phaseInt/[A-Za-z0-9._/-]+' 2>/dev/null | head -n1 || true)"

# --- resolve the TARGET REPO (needed by ship/push classification below) -----------
# A `git -C <path>` / `--git-dir=<path>` / `--work-tree=<path>` option names a repo
# OTHER than $CWD; git operates on THAT repo, so the gate must too. When such an
# option is present, REPO = that path; otherwise REPO = $CWD. REPO is the directory
# used for runId-from-HEAD AND as the conformance cd target. Effect:
#   git -C <drive_repo> push      (from outside)  → resolves the drive repo → deny if unreviewed
#   git -C ../other     push      (from a drive cwd) → evaluates the OTHER repo → inert
#                                                       if it's not a managed drive run (correct)
REPO="$CWD"
git_repo_opt="$(git_target_repo)"
if [ -n "$git_repo_opt" ]; then
  case "$git_repo_opt" in
    /*) REPO="$git_repo_opt" ;;            # absolute path: use as-is
    *)  REPO="$CWD/$git_repo_opt" ;;       # relative path: resolve against $CWD (git's own base)
  esac
fi

# --- ship detection ---
# `gh pr create` / `glab mr create` / a `git push` that ships the DRIVE branch.
# Subcommand-based so global flags before the subcommand don't bypass. The gh/glab
# match is the subcommand+action PAIR exactly: subcommand `pr`/`mr` AND the next
# non-flag word (action) == `create`. This kills `*create*` substring false positives
# like `gh pr view --json createdAt` (action `view` → NOT ship → inert).
if [ "$gh_sub" = pr ] && [ "$(action_after gh pr)" = create ]; then is_ship=true; fi
if [ "$glab_sub" = mr ] && [ "$(action_after glab mr)" = create ]; then is_ship=true; fi
# A `git push` is ship when it ships the drive feature branch — decided by
# push_ship_runid, which ERRS TOWARD GATING over arbitrary push syntax (finding #3 + #4):
#   - ANY positional refspec whose SOURCE side is drive/<runId> (scans ALL refspecs, so
#     `git push origin main drive/<id>` is still gated — not just the 2nd word), OR
#   - an aggregate push (`--all`/`--mirror`, which include the drive branch), OR
#   - a source==HEAD / bare / remote-only push while REPO's HEAD is drive/<runId>.
# `git push origin main` (explicit non-drive target, non-drive HEAD) → inert. The
# decision reads ONLY structural ref args + HEAD — never body/option VALUE tokens — so a
# ref-shaped token in --body/--push-option can't re-key or fake a ship.
# RESIDUAL (documented, see docs/drive-enforcement.md): truly exotic push forms
# (e.g. --mirror from a non-drive HEAD, server-side refspec expansion) may slip the
# matcher; the AUTHORITATIVE ship guarantee is the in-prose `--mode ship` conformance
# in drive-ship.md + the single canonical push /drive actually emits.
if [ "$git_sub" = push ]; then
  if psr="$(push_ship_runid)"; then
    is_ship=true
    ship_runid="$psr"   # may be empty only if HEAD resolution succeeded but returned empty; resolve step re-derives
  fi
fi

# --- plan-gate detection: `git worktree add ... -b slice/<runId>/<id>` ---
# A slice worktree-add starts a phase's implementation. It is gated by BOTH the run-level
# plan-gate (whole-run design converged) AND the per-phase design gate (this phase's design
# review converged). Derive each slice's phase P = the id prefix before the first '.'.
if [ "$git_sub" = worktree ] && [ -n "$slice_tokens" ]; then
  is_plan_gate=true
  while IFS= read -r st; do
    [ -n "$st" ] || continue
    case "$st" in slice/*) ;; *) st="${st#?}" ;; esac
    r="${st#slice/}"             # <runId>/<id>
    sid="${r#*/}"                # <id> = <P>.<k>
    pdp="${sid%%.*}"             # phase P = prefix before the first '.'
    # An empty pdp (id like `.1`, `2.`, `..x`) skips this phase's gate — but every such id
    # is one `git check-ref-format` rejects, so `-b slice/<runId>/<id>` fails at git before
    # any branch exists (no phase work can be built through the skip). Fail-closed downstream:
    # a hand-built empty <P> reaching conformance exits 2 → deny.
    [ -n "$pdp" ] && case " $phasedesign_Ps " in
      *" $pdp "*) ;;                                  # already collected
      *) phasedesign_Ps="$phasedesign_Ps$pdp " ;;
    esac
  done <<EOF
$slice_tokens
EOF
fi

# --- phase-merge detection ---
# `git branch -f drive/<runId> <phaseIntRef>` OR `git merge ... <phaseIntRef>`.
# runId is derived (in the resolve step) from the drive/<runId> token; here we only
# extract P = last segment of the phaseInt ref AS IT APPEARS in the command.
if [ -n "$phaseint_token" ] && { [ "$git_sub" = branch ] || [ "$git_sub" = merge ]; }; then
  is_phase_merge=true
  pt="$phaseint_token"
  case "$pt" in phaseInt/*) ;; *) pt="${pt#?}" ;; esac   # strip leading boundary char
  phase_P="${pt##*/}"            # P = final path segment of the phaseInt ref
fi

# --- slice-merge detection: `git merge ... slice/<runId>/<id>` (and NOT a worktree add).
if [ "$is_plan_gate" = false ] && [ "$git_sub" = merge ] && [ -n "$slice_tokens" ]; then
  is_slice_merge=true
  # collect each slice id (strip boundary char, take 3rd segment)
  while IFS= read -r st; do
    [ -n "$st" ] || continue
    case "$st" in slice/*) ;; *) st="${st#?}" ;; esac
    r="${st#slice/}"             # <runId>/<id>
    sid="${r#*/}"                # <id>
    [ -n "$sid" ] && slice_ids="$slice_ids$sid "
  done <<EOF
$slice_tokens
EOF
fi

# If nothing matched, inert.
if [ "$is_plan_gate" = false ] && [ "$is_slice_merge" = false ] \
   && [ "$is_phase_merge" = false ] && [ "$is_ship" = false ]; then
  exit 0
fi

# --- resolve runId + RUN_DIR ------------------------------------------------------
# SHIP commands (gh pr create / glab mr create / git push of the drive branch) key the
# runId from the TARGET REPO's HEAD ONLY (finding #1) — NEVER from command/body tokens.
# A SHIP command's only structural ref is whatever HEAD points at; a ref-shaped token in
# the PR title/body (e.g. `--body "...slice/otherrun/4a..."`) is NOT a real positional
# ref and must not re-key conformance to a DIFFERENT run. drive-ship runs from the ship
# worktree checked out on drive/<runId>, so HEAD is authoritative. For merge/branch/
# worktree commands the ref IS a real positional argument → parse it from the command.
runId=""
if [ "$is_ship" = true ]; then
  # Prefer an authoritative explicit push-source drive ref; else HEAD. NEVER the body.
  if [ -n "$ship_runid" ]; then
    runId="$ship_runid"
  else
    runId="$(drive_runid_from_head "$REPO")" || runId=""
  fi
elif runId="$(drive_runid_from_command "$CMD")"; then
  :
else
  runId=""
fi
[ -n "$runId" ] || exit 0          # not a managed run → inert

RUN_DIR=""
if ! RUN_DIR="$(drive_run_dir "$runId")"; then
  exit 0                           # RUN_DIR absent → treat as not-a-managed-run
fi

# --- run conformance for the matched mode -----------------------------------------
# run_conformance <mode-arg> : runs the checker from $REPO and returns a NORMALIZED rc
# (D4). We must distinguish three things the raw exit code conflates:
#   - a real conformance verdict (0 clean / 1 violation / 2 git-IO error),
#   - a broken checker (missing/non-exec → 126/127),
#   - a `cd "$REPO"` failure (e.g. repo dir was deleted), which must NOT masquerade as
#     a conformance verdict (a bare `cd` failure yields rc 1 ≡ "violation", which would
#     wrongly DENY the mid-build gates).
# Normalized rc contract:
#   0 = clean | 1 = violation | 9 = abnormal (checker broken, cd-fail, or any other rc)
# Callers map 9 per-mode: run-boundary gates (plan/ship) treat 9 as fail-CLOSED (deny);
# mid-build gates (slice/phase) treat 9 as fail-OPEN (silent). 2 is folded into 9
# (D4 treats exit-2 and the other abnormal rcs identically per gate class).
# Run from $REPO (the git -C / --git-dir / --work-tree target, else $CWD) so
# conformance's bare-`git` ref lookups resolve against the repo git actually operates on.
run_conformance() {
  # Verify the checker is present + executable up front; otherwise it's "abnormal".
  [ -x "$CONFORMANCE" ] || return 9
  # Probe the cd separately so a cd failure can't be read as a conformance verdict.
  ( cd "$REPO" ) 2>/dev/null || return 9
  local rc
  ( cd "$REPO" && "$CONFORMANCE" "$RUN_DIR" --mode "$1" ) >/dev/null 2>&1
  rc=$?
  case "$rc" in
    0) return 0 ;;
    1) return 1 ;;
    *) return 9 ;;     # 2, 126, 127, or anything else → abnormal
  esac
}

if [ "$is_plan_gate" = true ]; then
  run_conformance "plan-gate"; rc=$?
  # Run-boundary gate, fail-CLOSED: rc 1 (violation) OR 9 (abnormal: error / broken
  # checker / cd-fail) → DENY. Only rc 0 (clean) allows (silent).
  if [ "$rc" -ne 0 ]; then
    emit_deny "Plan/design review not converged for run $runId. Run \`/drive-review design\` until it converges, then retry: implementation cannot begin until the design review is CONVERGED (with codex)."
  fi
  # ALSO enforce the per-phase DESIGN review (Tier 2) for each phase whose slice is being
  # built here — same fail-CLOSED run-boundary semantics. A phase's slices cannot be built
  # until its detailed design review has CONVERGED.
  for pdp in $phasedesign_Ps; do
    [ -n "$pdp" ] || continue
    run_conformance "phasedesign-gate:$pdp"; rc=$?
    if [ "$rc" -ne 0 ]; then
      emit_deny "Phase $pdp design review not converged for run $runId. Run \`/drive-review phase $pdp design\` until it converges (with codex), then retry: a phase's slices cannot be built until its detailed design review is CONVERGED."
    fi
  done
  exit 0
fi

if [ "$is_slice_merge" = true ]; then
  # Mid-build per-unit gate, fail-OPEN: gate EACH slice id; DENY only on rc 1 (true
  # violation). rc 9 (abnormal: error / broken checker / cd-fail) → silent allow
  # (the ship gate backstops). NOTE: runtime-variable slice refs in $CMD (e.g.
  # `git merge "slice/$v/$id"`) cannot be expanded by the hook from the literal
  # command, so such merges silently pass here — they are backstopped by the ship
  # gate (HEAD-based, whole-tip diff) plus the drive.md literal-ref instruction
  # (Slice 3.1 owns that doc note).
  for sid in $slice_ids; do
    [ -n "$sid" ] || continue
    run_conformance "slice-merge:$sid"; rc=$?
    if [ "$rc" -eq 1 ]; then
      emit_deny "Slice $sid is not reviewed for its current tip. Run \`/drive-review slice $sid\` until it converges, then retry the merge."
    fi
  done
  exit 0
fi

if [ "$is_phase_merge" = true ]; then
  # Mid-build per-unit gate, fail-OPEN: DENY only on rc 1; rc 9 → silent allow.
  # (Same runtime-variable-ref limitation as slice-merge above; ship gate backstops.)
  run_conformance "phase-merge:$phase_P"; rc=$?
  if [ "$rc" -eq 1 ]; then
    emit_deny "Phase $phase_P is not reviewed for its current integration tip. Run \`/drive-review phase $phase_P\` until it converges, then retry the advance."
  fi
  exit 0
fi

if [ "$is_ship" = true ]; then
  run_conformance "ship"; rc=$?
  # Run-boundary gate, fail-CLOSED: rc 1 OR 9 → DENY; only rc 0 allows (silent).
  if [ "$rc" -ne 0 ]; then
    emit_deny "The code being shipped for run $runId is not fully covered by a converged review. Run \`/drive-review phase <P>\` for the final phase so its reviewed-sha covers the shipped tip (ship-mode passes when a converged phase review's reviewed-sha is an ancestor of the tip and only the ledger commit sits past it), then retry the push/PR."
  fi
  exit 0
fi

exit 0
