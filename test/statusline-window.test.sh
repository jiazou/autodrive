#!/usr/bin/env bash
# Tests for bin/statusline.sh's window de-dup (design phase 2, slice 2.2): AC5 (no
# output change after the refactor) + the BASH half of AC6 (the statusline's window
# now comes from bin/rebirth-thresholds.json, in ONE place). Plain bash, no bats.
# Prints PASS/FAIL per case; exits nonzero on any failure.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
STATUSLINE="$REPO/bin/statusline.sh"
THRESHOLDS="$REPO/bin/rebirth-thresholds.json"

fail=0
pass() { printf 'PASS: %s\n' "$1"; }
bad()  { printf 'FAIL: %s\n' "$1"; fail=1; }

assert_eq() {  # <name> <expected> <actual>
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then pass "$name"; else
    bad "$name (expected '$expected'; got '$actual')"; fi
}

# A transcript whose latest assistant usage sums to a known number, for a stable PCT.
TRANS="$(mktemp)"
cat > "$TRANS" <<'EOF'
{"type": "user", "message": {"role": "user", "content": "x"}}
{"type": "assistant", "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 4200, "cache_creation_input_tokens": 15000, "cache_read_input_tokens": 890000}}}
EOF
# token sum = 909200; window(Opus 4.8 / default)=1_000_000 -> PCT 90; window(Sonnet/Haiku 200k)=200_000 -> PCT 454

# Payload for a given display_name + transcript.
payload() {  # <display_name> <transcript>
  jq -n --arg m "$1" --arg t "$2" \
    '{model:{display_name:$m}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}'
}

# --- AC5: displayed output is byte-identical to the pre-refactor statusline ---
# Self-contained GOLDEN guard: hardcode the EXACT displayed output the statusline
# must produce for a fixed set of (model, stdin payload) cases, then assert the
# current bin/statusline.sh reproduces each golden byte-for-byte. The goldens were
# captured from the current statusline.sh — confirmed byte-identical to the
# pre-refactor (inline-`case`) version — so they ARE the pre-refactor outputs.
# No git ancestor ref and no run state.json: the guard works in a bare repo checkout
# (CI, main) and reds if any case's displayed output changes.
#
# Determinism: the env-dependent segments are pinned away so only the model+context
# part (what this refactor touches) is golden — a FIXED non-git current_dir (empty
# git segment), an empty $HOME + ccusage-free $PATH (empty cost segment), and a
# payload with no rate_limits (empty limit segment). \033[36m=cyan dir, \033[31m=red
# ctx (PCT>=80), \033[0m=reset. token sum 909200: window(Opus / default)=1_000_000 -> 90%,
# window(Sonnet/Haiku 200k)=200_000 -> 454%.
GOLDEN_DIR="/zzz-not-a-git-repo/golden/statusline-dir"
GE="$(printf '\033')"  # ESC
golden_for() {  # <model> — the exact line statusline.sh must print (no trailing \n)
  case "$1" in
    "Opus 4.8")           printf '%s[36m%s%s[0m [Opus 4.8] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Opus 4.7")           printf '%s[36m%s%s[0m [Opus 4.7] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Sonnet 4.5")         printf '%s[36m%s%s[0m [Sonnet 4.5] %s[31m454%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Haiku 4")            printf '%s[36m%s%s[0m [Haiku 4] %s[31m454%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Some Unknown Model") printf '%s[36m%s%s[0m [Some Unknown Model] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
  esac
}
golden_payload() {  # <display_name> <transcript> — uses the FIXED non-git dir
  jq -n --arg m "$1" --arg t "$2" --arg d "$GOLDEN_DIR" \
    '{model:{display_name:$m}, workspace:{current_dir:$d}, transcript_path:$t}'
}
GOLDEN_HOME="$(mktemp -d)"  # empty HOME -> no $HOME/.bun/bin/ccusage -> empty cost seg
for M in "Opus 4.8" "Opus 4.7" "Sonnet 4.5" "Haiku 4" "Some Unknown Model"; do
  P="$(golden_payload "$M" "$TRANS")"
  # Strip ccusage from PATH so the cost segment is empty in any environment.
  got="$(printf '%s' "$P" | HOME="$GOLDEN_HOME" PATH=/usr/bin:/bin bash "$STATUSLINE")"
  assert_eq "AC5 displayed output matches golden for [$M]" "$(golden_for "$M")" "$got"
done
rm -rf "$GOLDEN_HOME"

# --- AC6 (bash half): the statusline window comes from rebirth-thresholds.json ---
# Resolve the window the SAME way the statusline does, directly from the data file,
# and assert the statusline's rendered PCT is consistent with it (window in ONE place).
# pct = tokens * 100 / window (integer floor), token sum = 909200.
TOKENS=909200
resolve_window() {  # <display_name> — mirrors statusline's jq resolution
  jq -r --arg model "$1" '
    (.windows[] | select(.match | any(. as $m | $model | contains($m))) | .window) // .defaultWindow
    | first(., empty)
  ' "$THRESHOLDS" | head -1
}
rendered_pct() {  # <display_name> — the PCT the statusline prints (strip ANSI + %)
  printf '%s' "$(payload "$1" "$TRANS")" | bash "$STATUSLINE" \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%'
}
# Sonnet 4 (200k -> PCT 454, the reported bug) and Sonnet 4.6 (1M -> PCT 90, the collision
# that must resolve 1M because the 1M rule precedes the 200k `Sonnet 4`) are in the loop.
for M in "Opus 4.8" "Sonnet 4.5" "Sonnet 4" "Sonnet 4.6"; do
  W="$(resolve_window "$M")"
  expect_pct=$(( TOKENS * 100 / W ))
  assert_eq "AC6 [$M] window from data file = $W -> PCT $expect_pct" \
    "$expect_pct" "$(rendered_pct "$M")"
done

# Drift guard: mutating the data file's window changes the statusline's rendered PCT
# (proves the number is NOT hardcoded — it reads the file). Use an unmatched-model so
# the resolution falls to defaultWindow, then mutate defaultWindow.
MUT_DIR="$(mktemp -d)"
cp -R "$REPO/bin" "$MUT_DIR/bin"
# Point the copy's statusline at the copy's data file by editing defaultWindow there.
jq '.defaultWindow = 100000' "$THRESHOLDS" > "$MUT_DIR/bin/rebirth-thresholds.json"
mut_pct="$(printf '%s' "$(payload "Some Unknown Model" "$TRANS")" | bash "$MUT_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
# tokens 909200 / window 100000 -> PCT 909
assert_eq "AC6 mutating defaultWindow changes the rendered PCT (no hardcode)" \
  "909" "$mut_pct"
rm -rf "$MUT_DIR"

# --- [1m] beta marker is AUTHORITATIVE: forces the 1M window over the table ---
# CC marks the active 1M-context beta as `[1m]` in the model name/id; the statusline
# honors it (a per-session beta the table can't know). Use a DENYLIST (200k) model so the
# override is load-bearing: Sonnet normally -> 200000 -> PCT 454; with [1m] -> 1M -> PCT 90.
onem_name_pct="$(printf '%s' "$(payload "Sonnet 4.5 [1m]" "$TRANS")" | bash "$STATUSLINE" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "[1m] marker in display_name overrides a 200k model to 1M (PCT 90)" \
  "90" "$onem_name_pct"
# The marker can arrive in the model.id field instead — honor it there too.
onem_id_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Sonnet 4.5", id:"claude-sonnet-4-5[1m]"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "[1m] marker in model.id overrides a 200k model to 1M (PCT 90)" "90" "$onem_id_pct"
# MODEL_ID matching: a model whose DISPLAY name matches no rule token but whose ID matches a
# 200k-rule token still resolves to 200k from the table (id forms live in windows[].match).
# Brand X alone -> default 1M -> 90; with the opus-4-1 id -> 200k -> 454, so the id does the work.
id_match_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Brand X", id:"claude-opus-4-1"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "MODEL_ID matches the 200k rule when display_name does not (opus-4-1 -> 200k, PCT 454)" \
  "454" "$id_match_pct"
# Sonnet-4 the reported bug, via the id alone: a generic display + the real Sonnet-4 id
# (claude-sonnet-4-20250514, contains the 200k-rule `sonnet-4`) -> 200k -> PCT 454.
sonnet4_id_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Brand X", id:"claude-sonnet-4-20250514"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "MODEL_ID claude-sonnet-4-20250514 -> 200k rule (PCT 454), the reported bug" \
  "454" "$sonnet4_id_pct"
# Load-bearing id-beats-collision: display "Sonnet 4" (a 200k-rule token) paired with the 1M
# id claude-sonnet-4-6 (contains the 200k substring `sonnet-4` AND the 1M substring
# `sonnet-4-6`). The 1M rule precedes the 200k rule -> 1M -> PCT 90. This reds if `sonnet-4-6`
# is dropped from the 1M rule (the display "Sonnet 4" would then win the 200k rule -> 454).
# NOT covered by the display-only Sonnet 4.6 case, whose display alone catches it.
id_beats_collision_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Sonnet 4", id:"claude-sonnet-4-6"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "id claude-sonnet-4-6 (1M) beats colliding display Sonnet 4 (200k) -> 1M (PCT 90)" \
  "90" "$id_beats_collision_pct"

# --- Fallback (I3): a malformed data file falls back to the inline default window ---
# so the statusline never breaks on a bad file (still renders a correct PCT).
BAD_DIR="$(mktemp -d)"
cp -R "$REPO/bin" "$BAD_DIR/bin"
printf 'this is not json {{{' > "$BAD_DIR/bin/rebirth-thresholds.json"
# Opus 4.8 -> inline fallback case -> 1_000_000 -> PCT 90.
bad_opus="$(printf '%s' "$(payload "Opus 4.8" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline Opus window (PCT 90)" "90" "$bad_opus"
# Sonnet -> inline fallback default 200_000 -> PCT 454.
bad_default="$(printf '%s' "$(payload "Sonnet 4.5" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline default window (PCT 454)" "454" "$bad_default"
# Fallback keys on the model.id too (mirrors the primary jq path): a GENERIC display_name
# with a specific 200k model.id still resolves 200k from the inline fallback. Brand X alone
# -> 1M -> 90; with the opus-4-1 id -> 200k -> 454, so the id does the work in the fallback.
bad_id="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Brand X", id:"claude-opus-4-1"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$BAD_DIR/bin/statusline.sh" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json + generic display_name but 200k model.id -> 200k via id (PCT 454)" \
  "454" "$bad_id"
rm -rf "$BAD_DIR"

rm -f "$TRANS"

if [ "$fail" -ne 0 ]; then
  printf '\nSOME TESTS FAILED\n'; exit 1
fi
printf '\nALL PASS\n'
