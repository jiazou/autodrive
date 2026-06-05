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
# conformance exit 2 (git/IO error) they fail CLOSED (DENY). The mid-build REVIEW gates
# (slice-merge review + phase-merge) fail OPEN on exit 2 (silent, exit 0) so a transient
# git error cannot wedge a mid-build run; the ship gate backstops them. EXCEPTION: the
# mid-build impl-presence (TEST-presence) check fails CLOSED on exit 2 (Item C / Decision
# C3) — it has NO ship backstop, so its irreversible boundary must block on abnormal.
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

# tokenize_cmd <string> : shell-accurate argv tokenizer for the literal command string.
# Populates the global array `_TOKENS` with the argv git/bash WOULD see, then the four
# parsers below `set -- "${_TOKENS[@]}"` so they all read the SAME token stream. This
# replaces the old `set -f; set -- $CMD` whitespace word-split, which (a) split a quoted
# path WITH A SPACE into two words (`git -C "/a b" push` → `-C` `"/a` `b"` `push`, so the
# subcommand was misread and ship detection never ran — a silent bypass on LEGITIMATE
# input), and (b) kept quote characters literal so `""` produced the literal token `""`
# (resolving REPO to `$CWD/""`) instead of an empty arg (a git -C no-op).
#
# Rules (no `eval`, no command execution, no $var expansion — the gate sees the
# PRE-expansion string by design; runtime variable refs are a documented limitation):
#   - split on UNQUOTED whitespace (space/tab/newline);
#   - single-quoted '…' : literal, no escapes inside (POSIX); quotes removed;
#   - double-quoted "…" : literal, but backslash escapes the next char; quotes removed;
#   - backslash OUTSIDE quotes escapes the next char (`\ ` → a literal space in the arg);
#   - LINE CONTINUATION: a backslash IMMEDIATELY followed by a newline is ELIDED (both
#     chars removed, producing NO character) exactly as bash does — both in the default
#     (unquoted) state AND inside double quotes. NOT elided inside single quotes (where a
#     backslash is literal, per POSIX). Verified empirically against bash.
#   - a quote/escape STARTS a token even with no other chars, so `""`/`''` yield an
#     EMPTY-STRING arg (preserved — the -C compose treats it as a no-op, per git).
# Fail-safe: an UNTERMINATED quote is UNPARSEABLE — the real shell would reject the
# command and git would NEVER run — so we return rc 1 and leave _TOKENS empty. Callers
# treat that as "no recognizable command" → inert, which is safe precisely because such a
# command cannot execute (it can't be a real bypass). (A command ending in a bare trailing
# backslash is NOT rejected by the shell — `git push \` runs as `git push` — so it does NOT
# fail closed here; the escape just drops the final backslash, matching bash, and any
# residual evasion is a forgery-class residual, not an omission gap.) This is a deliberate
# fail-CLOSED-against-misparse for the unterminated-quote case: we never emit a mis-split
# argv that could desync the gate from git. bash 3.2-safe (char state machine; no bash-4
# features). NOTE: this lexer resolves the LITERAL string only — it does NOT perform shell
# EXPANSIONS ($var/$(…)/backtick/$'…'/~user/brace `{…,…}`/`{…..…}`); those are caught fail-closed downstream
# (see has_unresolved_expansion + expand_tilde).
tokenize_cmd() {
  local s="$1" n=${#1} i=0 ch
  local state=default          # default | single | double | escape | dquote_escape
  local cur="" started=0       # `started` = the current token has begun (so "" emits empty)
  # Per-token EXPANSION-ACTIVE flag: 1 iff THIS token carries a shell-expansion construct
  # that bash WOULD expand from the literal string but the gate cannot reproduce — set ONLY
  # in expansion-active contexts (unquoted or double-quoted `$`/backtick; an unquoted leading
  # `~user`; an unquoted brace-expansion — BOTH the comma form `{…,…}` (a `,` inside an open
  # brace) AND the range form `{…..…}` (a `..` inside an open brace; an embedded range like
  # `pus{g..h}` / `slic{e..f}/R/4a` CAN synthesize a managed verb or ref, so it is flagged too)).
  # NOT set inside SINGLE quotes,
  # where `$`/backtick/`~`/`{` are all literal (so `'slice/$run/4a'` is a literal ref, not an
  # expansion — quote context is preserved, fixing the strip-then-rescan false positive). The
  # parallel _TOK_EXP array mirrors _TOKENS 1:1 so downstream can ask "did THIS lexed token
  # have an unresolved expansion?" without re-scanning the quote-stripped value.
  local cur_exp=0 cur_first=1 brace_depth=0 lead_tilde=0
  _TOKENS=(); _TOK_EXP=()
  while [ "$i" -lt "$n" ]; do
    ch="${s:$i:1}"
    i=$((i+1))
    case "$state" in
      default)
        case "$ch" in
          ' '|$'\t'|$'\n')
            if [ "$started" -eq 1 ]; then
              # ~user finalize (see end-of-string note): an UNQUOTED leading ~<non-slash> is
              # the passwd form → expansion-active. Must run at EVERY flush, not just EOF.
              if [ "$lead_tilde" -eq 1 ]; then
                case "$cur" in '~'/*|'~') ;; '~'?*) cur_exp=1 ;; esac
              fi
              _TOKENS[${#_TOKENS[@]}]="$cur"; _TOK_EXP[${#_TOK_EXP[@]}]="$cur_exp"
              cur=""; started=0; cur_exp=0; cur_first=1; brace_depth=0; lead_tilde=0
            fi ;;
          \') state=single; started=1; cur_first=0 ;;
          \") state=double; started=1; cur_first=0 ;;
          \\) state=escape ;;              # do NOT mark started yet: a bare `\<newline>`
                                           # is a line continuation (elided) and must NOT
                                           # begin a word; the escape handler sets started
                                           # only for a non-newline escaped char.
          \$|\`) cur="$cur$ch"; started=1; cur_exp=1; cur_first=0 ;;  # $… or backtick → expands
          \~) cur="$cur$ch"; started=1
              # An UNQUOTED LEADING ~ may be ~user (expansion-active) — decided at finalize.
              # Record it as leading ONLY when it is genuinely the first char of the token
              # (cur_first), so a quoted leading `'~root'` (literal) is NOT flagged.
              [ "$cur_first" -eq 1 ] && lead_tilde=1; cur_first=0 ;;
          \{) cur="$cur$ch"; started=1; cur_first=0; brace_depth=$((brace_depth+1)) ;;  # open brace
          \}) cur="$cur$ch"; started=1; cur_first=0; [ "$brace_depth" -gt 0 ] && brace_depth=$((brace_depth-1)) ;;
          ,)  cur="$cur$ch"; started=1; cur_first=0
              [ "$brace_depth" -gt 0 ] && cur_exp=1 ;;   # `,` inside an open unquoted brace → brace expansion (comma form)
          .)  cur="$cur$ch"; started=1; cur_first=0
              # `..` (two consecutive dots) inside an open unquoted brace → brace RANGE expansion
              # (`pus{g..h}`→`pusg push`, `slic{e..f}/R/4a`→`slice/R/4a`). Flagged the same as the
              # comma form. A SINGLE dot (e.g. a `{1.1}` ref id) is NOT a range → not flagged.
              case "$cur" in *..) [ "$brace_depth" -gt 0 ] && cur_exp=1 ;; esac ;;
          *)  cur="$cur$ch"; started=1; cur_first=0 ;;
        esac ;;
      single)
        case "$ch" in
          \') state=default ;;             # close single-quote
          *)  cur="$cur$ch" ;;             # everything literal (incl. $ ` ~ { ) inside '…'
        esac ;;
      double)
        case "$ch" in
          \") state=default ;;             # close double-quote
          \\) state=dquote_escape ;;       # backslash escapes the next char in "…"
          \$|\`) cur="$cur$ch"; cur_exp=1 ;;  # $… or backtick STILL expands inside "…"
          *)  cur="$cur$ch" ;;
        esac ;;
      dquote_escape)
        # In bash "…", backslash is literal EXCEPT before $ ` " \ (and newline). We keep
        # the chars the gate cares about (quotes/backslash) correct; for any other char a
        # literal backslash is preserved, matching shell semantics closely enough for the
        # path/flag tokens this gate parses. A backslash-escaped $ or ` is LITERAL (not an
        # expansion), so it does NOT set cur_exp.
        case "$ch" in
          $'\n') : ;;                       # \<newline> inside "…" → line continuation: ELIDE both
          \"|\\|\$|\`) cur="$cur$ch" ;;
          *) cur="$cur\\$ch" ;;
        esac
        state=double ;;
      escape)
        case "$ch" in
          $'\n') : ;;                       # \<newline> outside quotes → line continuation:
                                            # ELIDE both; does NOT begin a word (started left as-is).
          *) cur="$cur$ch"; started=1; cur_first=0 ;;  # \<char> → literal char (begins a word)
        esac
        state=default ;;
    esac
  done
  # Finalize. A trailing BARE backslash (state=escape, the `\` had no following char) is
  # NOT a shell error — bash runs `git push \` as `git push`, just dropping the dangling
  # backslash — so we finalize the token like the default state (started stays as set, so a
  # token whose only content was an elided line-continuation does NOT emit an empty arg).
  # An UNTERMINATED QUOTE (single/double/dquote_escape) IS a shell error → fail rc 1, no
  # tokens (fail-closed-against-misparse; the command cannot run).
  case "$state" in
    default|escape)
      if [ "$started" -eq 1 ]; then
        # An UNQUOTED leading ~ followed by a non-slash char is the ~user passwd form (an
        # unresolved expansion); `~/…` and bare `~` are resolvable, so they are NOT flagged.
        # lead_tilde guarantees the ~ was unquoted+leading (a quoted `'~user'` is literal).
        if [ "$lead_tilde" -eq 1 ]; then
          case "$cur" in '~'/*|'~') ;; '~'?*) cur_exp=1 ;; esac
        fi
        _TOKENS[${#_TOKENS[@]}]="$cur"; _TOK_EXP[${#_TOK_EXP[@]}]="$cur_exp"
      fi
      return 0 ;;
    *)
      _TOKENS=(); _TOK_EXP=()
      return 1 ;;
  esac
}

# set_argv_from_cmd : tokenize $CMD into _TOKENS once. rc 1 if the command is either
# unparseable (unterminated quote) OR yields zero tokens (whitespace-only) — both cases
# the callers treat as "no recognizable command" (inert / no subcommand). On rc 1 the
# caller MUST NOT expand `"${_TOKENS[@]}"` (bash 3.2 errors on an empty array under
# `set -u`); rc 1 guarantees the caller bails before that expansion.
set_argv_from_cmd() {
  tokenize_cmd "$CMD" || return 1
  [ "${#_TOKENS[@]}" -gt 0 ] || return 1
  return 0
}

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
  set_argv_from_cmd || { printf ''; return 0; }   # unparseable command → no subcommand
  set -- "${_TOKENS[@]}"
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
  set_argv_from_cmd || { printf ''; return 0; }
  set -- "${_TOKENS[@]}"
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

# _compose <base> <p> : compose a git `-C` path component onto an accumulated base,
# matching git's "composed left to right, absolute resets" rule (git(1) -C). Echoes
# the composed path. bash 3.2-safe (pure string ops, no fs access).
#   - p absolute (/*)        → p           (an absolute -C REPLACES the accumulator)
#   - base empty             → p           (first component; resolved vs $CWD by caller)
#   - p empty                → base        (empty -C is a no-op chdir in git)
#   - else                   → base/p      (string-join; caller anchors $CWD if base rel)
_compose() {
  local base="$1" p="$2"
  case "$p" in
    /*) printf '%s' "$p" ;;
    "") printf '%s' "$base" ;;
    *)  if [ -z "$base" ]; then printf '%s' "$p"; else printf '%s/%s' "$base" "$p"; fi ;;
  esac
}

# expand_tilde <path> : resolve the CHEAP, deterministic tilde forms a repo-locating path
# value may carry — a LEADING `~/` or a BARE `~` token — to $HOME, exactly as bash does for
# an unquoted value (verified: `~/x`→$HOME/x, bare `~`→$HOME). The `~user` form is NOT
# expanded here (it needs a passwd lookup the gate can't safely do) — it is caught
# fail-closed downstream by has_unresolved_expansion, which treats a leading `~` followed by
# a non-`/` char as unresolvable. Any non-leading `~` (e.g. `/a/~/b`) is literal in bash, so
# it is left untouched. Echoes the resolved path. bash 3.2-safe (pure string ops).
expand_tilde() {
  local p="$1"
  case "$p" in
    "~")    printf '%s' "$HOME" ;;          # bare ~ → $HOME
    "~/"*)  printf '%s%s' "$HOME" "${p#\~}" ;;  # ~/rest → $HOME/rest
    *)      printf '%s' "$p" ;;             # ~user (caught downstream) or no leading ~ → as-is
  esac
}

# git_target_repo : resolve the directory whose gitdir git itself would read HEAD/refs
# from, modelling the REPO-IDENTITY axes of git's repo-locating global options:
#   - `-C <path>` : composed LEFT-TO-RIGHT (git: `-C a -C b` == `-C a/b`; an absolute
#     `-C` resets the accumulated base). SEPARATE-ARG value ONLY — `-C=<p>` is NOT real
#     git syntax (git rejects `-C=/path` as an unknown option), so it is not special-cased.
#   - `--git-dir <p>` / `--git-dir=<p>` : the gitdir override (the IDENTITY axis), resolved
#     relative to the `-C`-established cwd. LAST `--git-dir` wins (same-axis override).
#   - `--work-tree <p>` / `--work-tree=<p>` : PARSE-AND-DISCARD — its value is consumed so
#     it is not mistaken for the subcommand, but it is NOT a repo-identity axis. git reads
#     HEAD/refs from the gitdir, which `--work-tree` does NOT change (verified empirically);
#     treating it as the target was a silent-allow bypass (codex BLOCKING R1).
# Identity = `--git-dir` (if set, composed onto the -C cwd) else the composed `-C` cwd
# else empty (→ caller falls back to $CWD). Echoes an ABSOLUTE or $CWD-relative path (it
# does NOT itself prepend $CWD — the caller's existing `case` anchors the relative branch).
# Only meaningful when the START binary is `git`. bash 3.2-safe.
git_target_repo() {
  local c_base="" gitdir="" have_gitdir=0
  set_argv_from_cmd || { printf ''; return 0; }
  set -- "${_TOKENS[@]}"
  while [ "$#" -gt 0 ]; do
    case "$1" in [A-Za-z_]*=*) shift; continue ;; *) break ;; esac
  done
  [ "$#" -gt 0 ] && [ "$1" = git ] || { printf ''; return 0; }
  shift
  # Scan the global-option region (stop at the first non-flag word = the subcommand).
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -C)
        # SEPARATE-ARG value only; compose left-to-right. Resolve a leading ~/ or bare ~.
        if [ "$#" -gt 1 ]; then c_base="$(_compose "$c_base" "$(expand_tilde "$2")")"; shift 2; else shift; fi
        continue ;;
      --git-dir)
        if [ "$#" -gt 1 ]; then gitdir="$(expand_tilde "$2")"; have_gitdir=1; shift 2; else shift; fi
        continue ;;
      --git-dir=*) gitdir="$(expand_tilde "${1#--git-dir=}")"; have_gitdir=1; shift; continue ;;
      --work-tree)
        # PARSE-AND-DISCARD: consume the value (so it is not read as the subcommand);
        # NEVER used as the target (not a repo-identity axis).
        if [ "$#" -gt 1 ]; then shift 2; else shift; fi
        continue ;;
      --work-tree=*) shift; continue ;;
      # other global options that consume the next word:
      -c|-R|--repo) shift; [ "$#" -gt 0 ] && shift; continue ;;
      --*=*|--*) shift; continue ;;
      -?*) shift; continue ;;
      *) break ;;                           # subcommand reached → stop scanning options
    esac
  done
  # RESOLUTION: identity = --git-dir (composed onto the -C cwd) else the composed -C cwd.
  if [ "$have_gitdir" -eq 1 ]; then
    printf '%s' "$(_compose "$c_base" "$gitdir")"
  else
    printf '%s' "$c_base"
  fi
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
  set_argv_from_cmd || return 1            # unparseable command → not a ship
  set -- "${_TOKENS[@]}"
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

# managed_git_expansion_deny : rc 0 (and sets _MGED_REASON) iff $CMD is a WOULD-BE-MANAGED
# operation whose DECISION-CRITICAL argv carries an UNRESOLVED shell-expansion construct
# — the structural fail-closed catch-all that ends the `$'push'` / `git -C ~user/repo` /
# `git {push,}` / `gh {pr,} create` bypass class.
#
# QUOTE-AWARE: it reads the per-token expansion-active flags `_TOK_EXP[]` the lexer produces
# (1 iff that token had a construct bash WOULD expand from the literal string — an unquoted or
# double-quoted `$`/backtick, an unquoted brace-expansion `{…,…}` (comma) or `{…..…}` (range), or an unquoted leading
# `~user`). A SINGLE-QUOTED `'slice/$run/4a'` or `'~root/repo'` is LITERAL → its flag is 0 →
# NOT treated as an expansion (fixes the strip-then-rescan false positive). Resolvable forms
# (`~/…`, bare `~`, line-continuation) are NOT flagged either.
#
# WOULD-BE-MANAGED:
#   - START binary == git AND the subcommand is a managed verb (push|merge|branch|worktree) OR
#     the subcommand token is ITSELF expansion-active (so a managed verb can't be ruled out —
#     e.g. `git $'push'`, `git {push,}`); OR
#   - START binary == gh/glab AND the subcommand (pr/mr) OR the action (create) token is
#     expansion-active (so a managed ship verb can't be ruled out — e.g. `gh {pr,} create`,
#     `gh pr {create,}`, `glab {mr,} create`).
# This EXCLUDES non-managed commands (`echo $X`, `ls $HOME`) and non-managed git verbs
# (`git commit -m "$msg"`, `git log --format=$x`, `git show slice/R/4a`) — they never qualify
# → stay inert (a managed ref under a read-only verb is NOT a gated op, so it does not deny).
#
# DECISION-CRITICAL tokens (those the gate actually interprets for its verdict) are checked for
# an active construct — and ONLY those, so an incidental `$`-path/value the gate IGNORES never
# trips the net (this is what keeps /drive's OWN `git worktree add $RUN_DIR/wt/<id> -b
# slice/<runId>/<id> <sha>` and `git merge -s $strategy slice/<runId>/4a` from being denied):
#   - the subcommand/verb token (and, for gh/glab, the action token);
#   - every -C/--git-dir/--work-tree repo-path VALUE (git only);
#   - the per-verb REF/REFSPEC operand(s) ONLY — extracted exactly as the gate's own matchers
#     read them: `push` → refspecs AFTER the remote (positional #2..); `merge` → the ref
#     positionals (skipping `-s/-X/--strategy*/-m` VALUES); `branch` → the branch-name + start-
#     point positionals (skipping `-u/--set-upstream-to` VALUE); `worktree add` → the `-b/-B`
#     branch VALUE ONLY (NOT the worktree-PATH positional, NOT the start-point sha).
# A `$` in any consumed/skipped non-critical value/path (`worktree add <path>`, `merge -s <val>`,
# `-m <msg>`, `--push-option`) does NOT trip this. bash 3.2-safe (index-walk; no assoc arrays).
_MGED_REASON=""
_mged_reason_set() {
  _MGED_REASON="drive-merge-gate: cannot safely parse a managed command containing shell expansion (\`\$\`/backtick/\`~user\`/brace \`{…,…}\`/\`{…..…}\`); use a literal, fully-expanded form (the gate sees the pre-expansion command string by design — see docs/drive-enforcement.md)."
}
managed_git_expansion_deny() {
  set_argv_from_cmd || return 1            # unparseable (unterminated quote) → handled elsewhere
  local ntok=${#_TOKENS[@]} idx=0
  # Skip leading env VAR=val prefixes; identify the START binary.
  while [ "$idx" -lt "$ntok" ]; do
    case "${_TOKENS[$idx]}" in [A-Za-z_]*=*) idx=$((idx+1)); continue ;; *) break ;; esac
  done
  [ "$idx" -lt "$ntok" ] || return 1
  local bin="${_TOKENS[$idx]}"
  case "$bin" in
    git)       managed_git_expansion_deny_git "$idx" "$ntok" ;;
    gh|glab)   managed_cli_expansion_deny "$bin" "$idx" "$ntok" ;;
    *) return 1 ;;                          # non-managed binary → not our concern
  esac
}

# git branch of the net. $1=idx of the `git` token, $2=ntok. rc 0 (sets _MGED_REASON) iff a
# would-be-managed git op carries an expansion in a DECISION-CRITICAL token.
managed_git_expansion_deny_git() {
  local idx="$1" ntok="$2"
  idx=$((idx+1))                            # drop the `git` token
  # Walk the global-option region to the subcommand, checking repo-path VALUES en route.
  local tainted=0 sub="" sub_exp=0 cur
  while [ "$idx" -lt "$ntok" ]; do
    cur="${_TOKENS[$idx]}"
    case "$cur" in
      -C|--git-dir|--work-tree)
        if [ "$((idx+1))" -lt "$ntok" ]; then
          [ "${_TOK_EXP[$((idx+1))]}" = 1 ] && tainted=1
          idx=$((idx+2))
        else idx=$((idx+1)); fi
        continue ;;
      --git-dir=*|--work-tree=*)
        # The VALUE side of an inline --opt=val: the lexer's flag covers the WHOLE token, which
        # is what we want (a `$` anywhere in `--git-dir=$x` is expansion-active).
        [ "${_TOK_EXP[$idx]}" = 1 ] && tainted=1; idx=$((idx+1)); continue ;;
      -c|-R|--repo) idx=$((idx+2)); continue ;;
      --*=*|--*) idx=$((idx+1)); continue ;;
      -?*) idx=$((idx+1)); continue ;;
      *) sub="$cur"; sub_exp="${_TOK_EXP[$idx]}"; break ;;   # first non-flag word = subcommand
    esac
  done
  # The subcommand token is decision-critical (it picks the gate mode).
  [ "$sub_exp" = 1 ] && tainted=1
  # Managed iff a literal managed verb OR an expansion-active subcommand we can't rule out.
  local managed_verb=0
  case "$sub" in push|merge|branch|worktree) managed_verb=1 ;; esac
  [ "$sub_exp" = 1 ] && managed_verb=1
  [ "$managed_verb" -eq 1 ] || return 1     # not a would-be-managed op → inert (no over-deny)
  # PRECISE per-verb operand scan. Taint-check ONLY the ref/refspec operand(s) the gate's own
  # matchers read for this verb — never a blanket positional scan (which would deny /drive's own
  # `$`-path worktree-add / `-s $strategy` merge). An expansion-active subcommand (`$sub`/brace)
  # has no known verb shape → scan conservatively (every positional) so a smuggled managed verb
  # with a tainted ref is still caught.
  idx=$((idx+1))                            # drop the subcommand token
  case "$sub" in
    push)
      # Refspecs are positional #2.. (positional #1 is the remote). A `$`-remote is NOT a
      # decision ref; only the refspecs are. Skip value-consuming push flags.
      local pos=0
      while [ "$idx" -lt "$ntok" ]; do
        cur="${_TOKENS[$idx]}"
        case "$cur" in
          -o|--push-option|--repo|--receive-pack|--exec) idx=$((idx+2)); continue ;;
          --*=*|--*) idx=$((idx+1)); continue ;;
          -?*) idx=$((idx+1)); continue ;;
          *) pos=$((pos+1))
             [ "$pos" -ge 2 ] && [ "${_TOK_EXP[$idx]}" = 1 ] && tainted=1
             idx=$((idx+1)) ;;
        esac
      done ;;
    merge)
      # Ref positionals; skip strategy/message VALUES (the args /drive's `merge -s $strategy`
      # parks the `$` in — NOT a decision ref). Inline `--strategy=…` forms are single flag words.
      while [ "$idx" -lt "$ntok" ]; do
        cur="${_TOKENS[$idx]}"
        case "$cur" in
          -s|-X|--strategy|--strategy-option|-m|--message|-F|--file) idx=$((idx+2)); continue ;;
          --*=*|--*) idx=$((idx+1)); continue ;;
          -?*) idx=$((idx+1)); continue ;;
          *) [ "${_TOK_EXP[$idx]}" = 1 ] && tainted=1; idx=$((idx+1)) ;;   # ref operand
        esac
      done ;;
    branch)
      # `git branch -f <name> [<start-point>]`: the name + start-point positionals are refs the
      # gate reads (phase-advance: `git branch -f drive/<runId> phaseInt/<runId>/<P>`). Skip the
      # upstream VALUE; -f/-d/-D etc are bare flags.
      while [ "$idx" -lt "$ntok" ]; do
        cur="${_TOKENS[$idx]}"
        case "$cur" in
          -u|--set-upstream-to|-t|--track) idx=$((idx+2)); continue ;;
          --*=*|--*) idx=$((idx+1)); continue ;;
          -?*) idx=$((idx+1)); continue ;;
          *) [ "${_TOK_EXP[$idx]}" = 1 ] && tainted=1; idx=$((idx+1)) ;;   # name / start-point
        esac
      done ;;
    worktree)
      # `git worktree add <path> -b <branch> [<commit-ish>]`: the ONLY decision ref is the
      # `-b`/`-B` branch VALUE. The worktree PATH positional and the start-point commit-ish are
      # NOT refs (this is exactly /drive's `git worktree add $RUN_DIR/wt/<id> -b slice/.. <sha>`,
      # whose `$RUN_DIR` path must NOT taint). Taint-check ONLY the -b/-B value.
      while [ "$idx" -lt "$ntok" ]; do
        cur="${_TOKENS[$idx]}"
        case "$cur" in
          -b|-B)
            if [ "$((idx+1))" -lt "$ntok" ]; then
              [ "${_TOK_EXP[$((idx+1))]}" = 1 ] && tainted=1; idx=$((idx+2))
            else idx=$((idx+1)); fi
            continue ;;
          -b=*|-B=*|--*=*|--*) idx=$((idx+1)); continue ;;
          -?*) idx=$((idx+1)); continue ;;
          *) idx=$((idx+1)) ;;              # path / commit-ish positionals → NOT decision refs
        esac
      done ;;
    *)
      # Expansion-active (unknown-shape) subcommand: conservatively scan every positional, since
      # we can't know which is the ref. (`$sub`/brace already forced tainted=1 above, but a
      # smuggled verb could carry a tainted ref too — keep catching it.)
      while [ "$idx" -lt "$ntok" ]; do
        cur="${_TOKENS[$idx]}"
        case "$cur" in
          --*=*|--*) idx=$((idx+1)); continue ;;
          -?*) idx=$((idx+1)); continue ;;
          *) [ "${_TOK_EXP[$idx]}" = 1 ] && tainted=1; idx=$((idx+1)) ;;
        esac
      done ;;
  esac
  [ "$tainted" -eq 1 ] || return 1
  _mged_reason_set
  return 0
}

# gh/glab branch of the net (finding #1). $1=bin (gh|glab), $2=idx of the bin token, $3=ntok.
# Ship detection manages `gh pr create` and `glab mr create`. If the SUBCOMMAND token (pr/mr)
# OR the ACTION token (create) is expansion-active, the gate can't confirm the subcommand/action
# pair from the literal string → a would-be-managed ship op it can't safely parse → DENY. Mirrors
# the git path. Walks the gh/glab global-option region the SAME way subcommand_of/action_after do
# (env prefixes already skipped by the caller; the START binary is $bin).
managed_cli_expansion_deny() {
  local bin="$1" idx="$2" ntok="$3"
  idx=$((idx+1))                            # drop the gh/glab token
  local sub="" sub_exp=0 action="" action_exp=0 cur seen_sub=0
  # Reach the subcommand (skip global options exactly as subcommand_of/action_after do).
  while [ "$idx" -lt "$ntok" ]; do
    cur="${_TOKENS[$idx]}"
    case "$cur" in
      -C|-c|-R|--repo|--git-dir|--work-tree) idx=$((idx+2)); continue ;;
      --*=*|--*) idx=$((idx+1)); continue ;;
      -?*) idx=$((idx+1)); continue ;;
      *) sub="$cur"; sub_exp="${_TOK_EXP[$idx]}"; seen_sub=1; idx=$((idx+1)); break ;;
    esac
  done
  [ "$seen_sub" -eq 1 ] || return 1         # no subcommand → not a managed op
  # Reach the action (first non-flag word after the subcommand).
  while [ "$idx" -lt "$ntok" ]; do
    cur="${_TOKENS[$idx]}"
    case "$cur" in
      --*=*|--*) idx=$((idx+1)); continue ;;
      -?*) idx=$((idx+1)); continue ;;
      *) action="$cur"; action_exp="${_TOK_EXP[$idx]}"; break ;;
    esac
  done
  # The managed gh/glab op is the `pr create` / `mr create` PAIR. If EITHER the subcommand or the
  # action token is expansion-active, the pair can't be confirmed → fail closed. We further gate
  # on the op being plausibly that pair: the subcommand is pr/mr (or tainted, so unknown), AND
  # the action is create (or tainted/absent, so unknown). A clearly-different literal pair
  # (`gh pr view --json $x`, `gh issue list`) is NOT force-denied (no over-deny on unrelated gh).
  local sub_ok=0 action_ok=0
  case "$bin" in
    gh)   case "$sub" in pr) sub_ok=1 ;; esac ;;
    glab) case "$sub" in mr) sub_ok=1 ;; esac ;;
  esac
  [ "$sub_exp" = 1 ] && sub_ok=1            # tainted subcommand → can't rule out pr/mr
  case "$action" in create|"") action_ok=1 ;; esac
  [ "$action_exp" = 1 ] && action_ok=1     # tainted action → can't rule out create
  [ "$sub_ok" -eq 1 ] && [ "$action_ok" -eq 1 ] || return 1
  # Only DENY when a decision-critical token is actually tainted.
  if [ "$sub_exp" = 1 ] || [ "$action_exp" = 1 ]; then
    _mged_reason_set
    return 0
  fi
  return 1
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
# Collect the DISTINCT runIds named across all slice tokens. A normal /drive slice-merge
# references exactly ONE runId (`git merge slice/<runId>/<id>` per slice). A multi-runId
# octopus merge (`git merge slice/runA/4a slice/runB/4a`) is never a normal /drive op and
# would let the single-runId resolution below silently check ONLY the first runId's slice,
# leaving the others un-test/-review-checked — so we DENY it fail-closed (see below).
slice_runids=""

# Identify the REAL subcommand for each candidate binary (first non-flag word after
# the binary, skipping env VAR=val prefixes + global options). This is what defeats
# the contiguous-binary+subcommand bypass: `git -C repo push`, `git -c k=v push`,
# `gh --repo o/r pr create`, `glab -R x mr create` all resolve their subcommand here.
git_sub="$(subcommand_of git)"
gh_sub="$(subcommand_of gh)"
glab_sub="$(subcommand_of glab)"

# --- structural fail-closed catch-all (ends the shell-expansion bypass class) -------
# BEFORE any repo/ref resolution: if $CMD is a would-be-managed git op whose decision-
# critical argv carries an UNRESOLVED shell-expansion construct (a `$` form, a backtick, a
# `~user`, or a brace expansion `{…,…}`/`{…..…}`), the gate cannot faithfully interpret it
# from the literal string — so it FAILS
# CLOSED = DENY rather than silently mis-resolve and bypass (e.g. `git $'push'` lexes to a
# non-`push` subcommand → would-be-inert; `git -C ~user/repo push` mis-targets). This is
# omission-safe: an unresolvable managed command DENIES. Non-git and non-managed commands
# (`echo $X`, `ls $HOME`, `git commit -m "$msg"`) never qualify → unaffected (stay inert).
if managed_git_expansion_deny; then
  emit_deny "$_MGED_REASON"
fi

# CMD_LEX : the command re-serialized from the LEXED tokens (one per line). The ref-extraction
# greps + drive_runid_from_command read THIS, not the raw $CMD, so they see the SAME string the
# argv parsers do — line-continuations elided, quotes removed, each token isolated. Reading the
# raw $CMD here would DESYNC the gate from git: a ref split by a `\`<newline> continuation
# (`git merge sli\`↵`ce/R/4a`) is one token `slice/R/4a` to git AND to the lexer, but the raw
# string still holds the backslash+newline → a raw grep would miss the ref and the gate would
# go inert on a real managed merge. One-token-per-line keeps each ref atomic (refs carry no
# newline) and preserves the per-token boundary the grep's `(^|[^…])` anchor needs.
CMD_LEX="$CMD"
if set_argv_from_cmd; then
  CMD_LEX="$(printf '%s\n' "${_TOKENS[@]}")"
fi

# Extract every slice/<runId>/<id> token (3-segment) appearing in the command.
# Used both for matching AND for gating EACH slice in a multi-slice merge.
slice_tokens="$(printf '%s' "$CMD_LEX" | grep -oE '(^|[^A-Za-z0-9._-])slice/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+' 2>/dev/null || true)"

# Extract the FIRST phaseInt/... token as it appears in the command. We accept ANY
# phaseInt/<...> arg form (not only the 3-segment phaseInt/<runId>/<P>) so the gate
# stays correct regardless of phaseInt naming (Slice 3.1 ordering). The last path
# segment is taken as P and passed to conformance, which keys phase-merge by P.
phaseint_token="$(printf '%s' "$CMD_LEX" | grep -oE '(^|[^A-Za-z0-9._-])phaseInt/[A-Za-z0-9._/-]+' 2>/dev/null | head -n1 || true)"

# --- resolve the TARGET REPO (needed by ship/push classification below) -----------
# A `git -C <path>` / `--git-dir=<path>` option names a repo-IDENTITY OTHER than $CWD;
# git reads HEAD/refs from THAT repo, so the gate must too. git_target_repo composes the
# `-C` chain + `--git-dir` (last-wins) and echoes an absolute or $CWD-relative path;
# `--work-tree` is EXCLUDED from identity (parsed only to consume its value — it does not
# change which gitdir/HEAD git uses). When present, REPO = that path; else REPO = $CWD.
# REPO is the directory used for runId-from-HEAD AND as the conformance cd target. Effect:
#   git -C <drive_repo> push      (from outside)  → resolves the drive repo → deny if unreviewed
#   git -C ../other     push      (from a drive cwd) → evaluates the OTHER repo → inert
#                                                       if it's not a managed drive run (correct)
#   git --work-tree=<reviewed> push (from an unreviewed drive cwd) → identity = $CWD (the
#                                   unreviewed drive repo) → DENY (the old bypass is closed)
REPO="$CWD"
git_repo_opt="$(git_target_repo)"
if [ -n "$git_repo_opt" ]; then
  case "$git_repo_opt" in
    /*) REPO="$git_repo_opt" ;;            # absolute path: use as-is
    *)  REPO="$CWD/$git_repo_opt" ;;       # relative path: resolve against $CWD (git's own base)
  esac
fi
# Gitfile reduction: a linked-worktree `.git` is a regular FILE (a gitfile), but the
# callers use REPO as a DIRECTORY (`git -C "$REPO" rev-parse`, `cd "$REPO" && conformance`).
# So if a `--git-dir=<wt>/.git` resolved REPO to a gitfile, reduce it to its parent — the
# worktree root — which is the directory git reads HEAD/refs from for that gitfile. This
# handles the CANONICAL `<worktree>/.git` case (the representation /drive's slice worktrees
# use); a real `.git` DIRECTORY is unaffected (`-f` is false). A symlinked/non-canonical
# gitfile wrapper is a ratified out-of-scope forgery residual (DR11; docs/drive-enforcement.md).
[ -f "$REPO" ] && REPO="$(dirname "$REPO")"

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
if [ "$git_sub" = worktree ] && [ -n "$slice_tokens" ]; then
  is_plan_gate=true
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
  # collect each slice id (strip boundary char, take 3rd segment) AND its OWN runId.
  while IFS= read -r st; do
    [ -n "$st" ] || continue
    case "$st" in slice/*) ;; *) st="${st#?}" ;; esac
    r="${st#slice/}"             # <runId>/<id>
    srid="${r%%/*}"              # <runId> (this token's OWN runId)
    sid="${r#*/}"                # <id>
    [ -n "$sid" ] && slice_ids="$slice_ids$sid "
    # Track the DISTINCT runId set (space-delimited; bash 3.2-safe membership test).
    if [ -n "$srid" ]; then
      case " $slice_runids " in (*" $srid "*) ;; (*) slice_runids="$slice_runids$srid " ;; esac
    fi
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
elif runId="$(drive_runid_from_command "$CMD_LEX")"; then
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
# Callers map 9 per-mode (NOT a single blanket rule): the run-boundary gates (plan/ship)
# treat 9 as fail-CLOSED (deny), and so does the mid-build impl-presence (TEST-presence)
# check — it has no ship backstop, so its irreversible boundary must fail closed (Item C /
# Decision C3). The mid-build REVIEW gates (slice-merge review + phase-merge) treat 9 as
# fail-OPEN (silent), because the ship gate is their fail-closed backstop. 2 is folded into
# 9 (D4 treats exit-2 and the other abnormal rcs identically within each gate's posture).
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
  exit 0
fi

if [ "$is_slice_merge" = true ]; then
  # FAIL-CLOSED on a MULTI-runId octopus merge. The single-runId resolution above keys
  # RUN_DIR + conformance to ONE runId (the first slice token's). If the command merges
  # slice branches from DIFFERENT runIds in one `git merge` (e.g.
  # `git merge slice/runA/4a slice/runB/4a`), the per-slice loop below would reconstitute
  # EVERY id as `slice/$runId/<id>` against that single runId — so slice/runB/4a's review
  # and test-presence are NEVER checked (it binds to runA's RUN_DIR + refs). A multi-runId
  # octopus merge is never a normal /drive operation (/drive emits one
  # `git merge slice/<runId>/<id>` per slice), so we DENY it rather than silently pass the
  # unchecked runs. Counts DISTINCT runIds from the slice tokens (space-delimited set).
  _nrunids=0
  for _rid in $slice_runids; do
    [ -n "$_rid" ] && _nrunids=$((_nrunids+1))
  done
  if [ "$_nrunids" -gt 1 ]; then
    emit_deny "This merge references slice branches from MORE THAN ONE /drive run ($slice_runids). A multi-run octopus merge is not a /drive operation and cannot be conformance-checked as one unit — merge each run's slices with a separate \`git merge slice/<runId>/<id>\`, one run at a time, so each slice's review + test-presence is enforced."
  fi
  # The slice-merge boundary runs TWO conformance checks per slice id, with a DELIBERATE,
  # DOCUMENTED POSTURE ASYMMETRY (design Item C / Decision C3) justified by their different
  # backstops:
  #   1. slice-merge:<id>  (REVIEW presence)       — fail-OPEN. The ship gate is its
  #      fail-closed backstop (ship re-checks review ancestry against the shipped tip), so an
  #      abnormal rc 9 here can silently allow now and still be caught at ship. DENY only on
  #      rc 1 (true violation); rc 9 (error / broken checker / cd-fail) → silent allow.
  #   2. impl-presence:<id> (TEST presence)         — fail-CLOSED. There is NO ship backstop
  #      for test-presence (ship mode never re-derives per-slice test presence — the merged
  #      featureBranch has lost per-slice identity). The slice-merge is therefore the
  #      IRREVERSIBLE boundary for this invariant and must fail closed here (OPERATING: "place
  #      the hard gate at the irreversible boundary, failing closed"): BOTH rc 1 (violation:
  #      no test + no waiver) AND rc 9 (abnormal: missing/corrupt drive/<runId> or slice ref)
  #      → DENY. A fail-OPEN impl-presence would let an rc-2/abnormal silently allow a no-test
  #      merge with nothing catching it later, defeating the very invariant.
  # NOTE: runtime-variable slice refs in $CMD (e.g. `git merge "slice/$v/$id"`) cannot be
  # expanded by the hook from the literal command, so such merges don't reach this gate at all
  # (no parseable slice token) — backstopped by the ship gate + the drive.md literal-ref note.
  for sid in $slice_ids; do
    [ -n "$sid" ] || continue
    # (1) REVIEW presence — fail-OPEN (rc 1 → DENY; rc 9 → silent).
    run_conformance "slice-merge:$sid"; rc=$?
    if [ "$rc" -eq 1 ]; then
      emit_deny "Slice $sid is not reviewed for its current tip. Run \`/drive-review slice $sid\` until it converges, then retry the merge."
    fi
    # (2) TEST presence — fail-CLOSED (rc 1 OR rc 9 → DENY). The remediation names BOTH the
    # violation fix (add a test / waiver trailer) and the abnormal fix (resolve the missing
    # drive/<runId> / slice ref); a real run always has drive/<runId> (the live featureBranch)
    # at slice-merge, so rc 9 here is genuine corruption, not normal flow.
    run_conformance "impl-presence:$sid"; rc=$?
    if [ "$rc" -ne 0 ]; then
      emit_deny "Slice $sid adds no test file. Add a test for this slice, or mark it test-less with a \`Drive-Test-Waiver: <reason>\` commit trailer on the slice branch, before merging. (If this is an abnormal git result — e.g. a missing/corrupt drive/$runId or slice/$runId/$sid ref — resolve the missing ref or retry; this test-presence check fails CLOSED because it has no ship backstop, unlike the review check above.)"
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
