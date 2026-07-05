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
    # verified-1M models (C2): Fable 5 pre-fix GREEN (was default fallthrough — now an
    # explicit entry); Sonnet 5 / Sonnet 4.6 pre-fix RED (bare "Sonnet" 200k -> 454);
    # Opus 4.6 pre-fix RED (reclassified 200k -> 1M per the model reference).
    "Fable 5")            printf '%s[36m%s%s[0m [Fable 5] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Sonnet 5")           printf '%s[36m%s%s[0m [Sonnet 5] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Sonnet 4.6")         printf '%s[36m%s%s[0m [Sonnet 4.6] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
    "Opus 4.6")           printf '%s[36m%s%s[0m [Opus 4.6] %s[31m90%%%s[0m' "$GE" "zzz-not-a-git-repo/golden/statusline-dir" "$GE" "$GE" "$GE" ;;
  esac
}
golden_payload() {  # <display_name> <transcript> — uses the FIXED non-git dir
  jq -n --arg m "$1" --arg t "$2" --arg d "$GOLDEN_DIR" \
    '{model:{display_name:$m}, workspace:{current_dir:$d}, transcript_path:$t}'
}
GOLDEN_HOME="$(mktemp -d)"  # empty HOME -> no $HOME/.bun/bin/ccusage -> empty cost seg
for M in "Opus 4.8" "Opus 4.7" "Sonnet 4.5" "Haiku 4" "Some Unknown Model" \
         "Fable 5" "Sonnet 5" "Sonnet 4.6" "Opus 4.6"; do
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
# Includes the order-sensitive boundary pair (Sonnet 4.6 vs Sonnet 4 — "Sonnet 4.6"
# contains "Sonnet 4"; rule order keeps 4.6 at 1M) and the reclassified Opus 4.6.
for M in "Opus 4.8" "Sonnet 4.5" "Sonnet 4.6" "Sonnet 4" "Fable 5" "Opus 4.6"; do
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
# honors it (a per-session beta the table can't know). Use a 200k-rule model so the
# override is load-bearing: Sonnet 4.5 normally -> 200000 -> PCT 454; with [1m] -> 1M -> PCT 90.
onem_name_pct="$(printf '%s' "$(payload "Sonnet 4.5 [1m]" "$TRANS")" | bash "$STATUSLINE" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "[1m] marker in display_name overrides a 200k model to 1M (PCT 90)" \
  "90" "$onem_name_pct"
# The marker can arrive in the model.id field instead — honor it there too.
onem_id_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Sonnet 4.5", id:"claude-sonnet-4-5[1m]"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "[1m] marker in model.id overrides a 200k model to 1M (PCT 90)" "90" "$onem_id_pct"
# MODEL_ID matching: a model whose DISPLAY name does not match the table but whose ID
# does still resolves from the table (id forms live in windows[].match). Brand X
# alone -> default 1M -> 90; with the opus-4-1 id -> 200k -> 454, so the id does the work.
id_match_pct="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Brand X", id:"claude-opus-4-1"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "MODEL_ID matches a 200k family when display_name does not (opus-4-1 -> 200k, PCT 454)" \
  "454" "$id_match_pct"
# MODEL_ID path, BOTH sides of the sonnet-4 boundary pair + the reclassified model —
# the jq id resolution (statusline L24-27) is a distinct code path from the display
# case, so the order-sensitive models run through it in id form too. One helper,
# 3 ids (mirrors the rendered_pct pattern; display_name "Brand X" never matches, so
# the model.id does the resolving):
id_rendered_pct() {  # <model.id> — PCT the statusline prints for a Brand-X payload with this id
  jq -n --arg t "$TRANS" --arg id "$1" \
    '{model:{display_name:"Brand X", id:$id}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
    | bash "$STATUSLINE" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%'
}
#   claude-sonnet-4-6 -> 1M (order-protected: the id contains the 200k entry sonnet-4)
assert_eq "MODEL_ID boundary pair 1M side (claude-sonnet-4-6 -> 1M, PCT 90)" \
  "90" "$(id_rendered_pct "claude-sonnet-4-6")"
#   claude-sonnet-4-20250514 -> 200k (the pair's 200k partner via the sonnet-4 id entry)
assert_eq "MODEL_ID boundary pair 200k side (claude-sonnet-4-20250514 -> 200k, PCT 454)" \
  "454" "$(id_rendered_pct "claude-sonnet-4-20250514")"
#   claude-opus-4-6 -> 1M (reclassified 200k -> 1M; pre-fix RED: the old table listed it 200k)
assert_eq "MODEL_ID reclassified model (claude-opus-4-6 -> 1M, PCT 90)" \
  "90" "$(id_rendered_pct "claude-opus-4-6")"

# --- Fallback (I3): a malformed data file falls back to the inline default window ---
# so the statusline never breaks on a bad file (still renders a correct PCT).
BAD_DIR="$(mktemp -d)"
cp -R "$REPO/bin" "$BAD_DIR/bin"
printf 'this is not json {{{' > "$BAD_DIR/bin/rebirth-thresholds.json"
# Opus 4.8 -> inline fallback case -> 1_000_000 -> PCT 90.
bad_opus="$(printf '%s' "$(payload "Opus 4.8" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline Opus window (PCT 90)" "90" "$bad_opus"
# Sonnet 4.5 -> inline 200k ARM (*"Sonnet 4"* match, not the default arm) -> PCT 454.
bad_default="$(printf '%s' "$(payload "Sonnet 4.5" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline 200k arm (PCT 454)" "454" "$bad_default"
# CASE arm ORDER: Sonnet 4.6 must hit the 1M arm even though it contains "Sonnet 4"
# (the 200k arm) — proves the inline arms mirror the json rule order, forced onto the
# case path by the malformed json.
bad_s46="$(printf '%s' "$(payload "Sonnet 4.6" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline 1M arm wins the Sonnet 4.6 boundary (PCT 90)" \
  "90" "$bad_s46"
# Reclassified arm move: Opus 4.6 sits in the inline 1M arm now (pre-fix RED: 200k arm -> 454).
bad_o46="$(printf '%s' "$(payload "Opus 4.6" "$TRANS")" | bash "$BAD_DIR/bin/statusline.sh" \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: malformed json -> inline 1M arm for reclassified Opus 4.6 (PCT 90)" \
  "90" "$bad_o46"
# Fallback id-parity: on the fallback path (data file unreadable) a payload whose
# display_name is generic/unidentifiable ("Claude") but whose model.id names a 200k
# family must still resolve 200k via the id — the inline `case` mirrors the json's
# id-form match strings and keys on "$MODEL $MODEL_ID". Pre-fix RED: the old
# `case "$MODEL"` keyed only on display_name, so "Claude" fell to the default 1M arm -> 90.
bad_fallback_id="$(jq -n --arg t "$TRANS" \
  '{model:{display_name:"Claude", id:"claude-haiku-4-5-20251001"}, workspace:{current_dir:"/tmp/x"}, transcript_path:$t}' \
  | bash "$BAD_DIR/bin/statusline.sh" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%')"
assert_eq "fallback: generic display_name but 200k model.id -> inline 200k via id (PCT 454)" \
  "454" "$bad_fallback_id"
rm -rf "$BAD_DIR"

rm -f "$TRANS"

if [ "$fail" -ne 0 ]; then
  printf '\nSOME TESTS FAILED\n'; exit 1
fi
printf '\nALL PASS\n'
