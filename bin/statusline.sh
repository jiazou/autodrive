#!/bin/bash
input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name')
MODEL_ID=$(echo "$input" | jq -r '.model.id // empty')
DIR=$(echo "$input" | jq -r '.workspace.current_dir')
TRANSCRIPT=$(echo "$input" | jq -r '.transcript_path // empty')

# Colors matching Starship config
CYAN='\033[36m'
ORANGE='\033[38;5;202m'
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
RESET='\033[0m'

# Context % — sum input + cache_creation + cache_read from the latest
# assistant message in the transcript, divide by the model's actual window.
# The window-by-model table lives in ONE place — bin/rebirth-thresholds.json (the
# shared source of truth the rebirth Stop-hook also reads). Resolve $WINDOW by the
# first windows[].match substring of $MODEL or $MODEL_ID, else defaultWindow. A
# missing/malformed data file falls back to the inline default so it never breaks.
THRESHOLDS_FILE="$(dirname "${BASH_SOURCE[0]}")/rebirth-thresholds.json"
WINDOW=$(jq -r --arg model "$MODEL" --arg modelid "$MODEL_ID" '
    (.windows[] | select(.match | any(. as $m | ($model | contains($m)) or ($modelid | contains($m)))) | .window) // .defaultWindow
    | first(., empty)
' "$THRESHOLDS_FILE" 2>/dev/null | head -1)
if [ -z "$WINDOW" ] || ! [ "$WINDOW" -gt 0 ] 2>/dev/null; then
# Inline fallback (kept at column 0 so it mirrors rebirth-thresholds.json's window
# groups): the SAME 200k match set as the json — display-name AND id-forms — matched
# against "$MODEL $MODEL_ID" like the primary jq path, so a generic display_name with a
# specific model.id still resolves. Used only when the data file is unreadable. AC6 pins
# this `case` and the json to identical numbers.
case "$MODEL $MODEL_ID" in
    *"Fable 5"*|*"claude-fable-5"*|*"fable-5"*)                          WINDOW=1000000 ;;
    *"Haiku"*|*"haiku"*|*"Sonnet 4.5"*|*"sonnet-4-5"*|*"sonnet-4.5"*|*"Sonnet 4.0"*|*"sonnet-4-0"*|*"sonnet-4.0"*|*"Opus 4.5"*|*"opus-4-5"*|*"opus-4.5"*|*"Opus 4.1"*|*"opus-4-1"*|*"opus-4.1"*)   WINDOW=200000 ;;
    *)                                                                   WINDOW=1000000 ;;
esac
fi
# The 1M-context beta is authoritative when active: Claude Code marks it as `[1m]` in
# the model name/id. Honor that over the table — a per-session beta the table can't know.
# (Statusline-only: the rebirth Stop-hook reads the transcript, which carries no [1m].)
case "$MODEL_ID:$MODEL" in (*"[1m]"*) WINDOW=1000000 ;; esac
CTX_STATUS=""
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    TOKENS=$(jq -r 'select(.type=="assistant" and .message.usage) | ((.message.usage.input_tokens // 0) + (.message.usage.cache_creation_input_tokens // 0) + (.message.usage.cache_read_input_tokens // 0))' "$TRANSCRIPT" 2>/dev/null | tail -1)
    if [ -n "$TOKENS" ] && [ "$TOKENS" -gt 0 ] 2>/dev/null; then
        PCT=$((TOKENS * 100 / WINDOW))
        if [ "$PCT" -ge 80 ]; then
            CTX_COLOR="$RED"
        elif [ "$PCT" -ge 50 ]; then
            CTX_COLOR="$YELLOW"
        else
            CTX_COLOR="$GREEN"
        fi
        CTX_STATUS=$(printf " ${CTX_COLOR}%s%%${RESET}" "$PCT")
    fi
fi

# Usage segment: 💰 $/day + $/hr (ccusage; the payload's cost is session-only),
# and ⏳ block% / week% toward the real plan limits (CC payload rate_limits — the /usage numbers).
pct_color() {                       # color a 0-100 percentage (handles floats)
    local n="${1%%.*}"; [ -z "$n" ] && n=0
    if   [ "$n" -ge 80 ]; then printf "$RED"
    elif [ "$n" -ge 50 ]; then printf "$YELLOW"
    else                       printf "$GREEN"; fi
}

USAGE_STATUS=""

# $/day (today total) + $/hr (burn rate) from ccusage's statusline output.
CCUSAGE_BIN="$HOME/.bun/bin/ccusage"
[ -x "$CCUSAGE_BIN" ] || CCUSAGE_BIN=$(command -v ccusage 2>/dev/null)
COST_SEG=""
if [ -n "$CCUSAGE_BIN" ] && [ -x "$CCUSAGE_BIN" ]; then
    RAW=$(printf '%s' "$input" | "$CCUSAGE_BIN" statusline 2>/dev/null)
    if [ -n "$RAW" ]; then
        DAY=$(printf '%s' "$RAW" | grep -oE '\$[0-9.]+ today' | grep -oE '\$[0-9.]+')
        HR=$(printf '%s' "$RAW"  | grep -oE '\$[0-9.]+/hr')
        [ -n "$DAY" ] && COST_SEG="${DAY}/day"
        [ -n "$HR" ]  && COST_SEG="${COST_SEG:+$COST_SEG · }${HR}"
    fi
fi

# block% / week% straight from the CC payload (Pro/Max only, present after the first API call).
BLOCK=$(printf '%s' "$input" | jq -r '(.rate_limits.five_hour.used_percentage | select(. != null) | round) // empty' 2>/dev/null)
WEEK=$(printf '%s' "$input" | jq -r '(.rate_limits.seven_day.used_percentage | select(. != null) | round) // empty' 2>/dev/null)
LIMIT_SEG=""
[ -n "$BLOCK" ] && LIMIT_SEG="block $(printf "$(pct_color "$BLOCK")%s%%${RESET}" "$BLOCK")"
[ -n "$WEEK" ]  && LIMIT_SEG="${LIMIT_SEG:+$LIMIT_SEG · }week $(printf "$(pct_color "$WEEK")%s%%${RESET}" "$WEEK")"

# ⏳ block/week first so it survives terminal-width truncation; 💰 cost (longer) trails.
[ -n "$LIMIT_SEG" ] && USAGE_STATUS=" │ ⏳ $LIMIT_SEG"
[ -n "$COST_SEG" ]  && USAGE_STATUS="$USAGE_STATUS │ 💰 $COST_SEG"

# Truncate directory to last 3 segments (mirrors starship truncation_length = 3)
TRUNCATED=$(echo "$DIR" | awk -F'/' '{
    n=NF; start=(n>3)?n-2:1;
    path="";
    for(i=start;i<=n;i++) { path=(path=="")?$i:path"/"$i }
    print path
}')

# Git info
GIT_STATUS=""
if git -C "$DIR" rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
    PORCELAIN=$(git -C "$DIR" status --porcelain 2>/dev/null)

    FLAGS=""
    echo "$PORCELAIN" | grep -q "^M\|^ M" && FLAGS="$FLAGS ✗"
    echo "$PORCELAIN" | grep -q "^??" && FLAGS="$FLAGS ?"
    echo "$PORCELAIN" | grep -q "^A\|^M[[:space:]]" && FLAGS="$FLAGS ✓"

    AHEAD=$(git -C "$DIR" rev-list --count @{u}..HEAD 2>/dev/null)
    BEHIND=$(git -C "$DIR" rev-list --count HEAD..@{u} 2>/dev/null)
    [ "$AHEAD" -gt 0 ] 2>/dev/null && FLAGS="$FLAGS ⇡"
    [ "$BEHIND" -gt 0 ] 2>/dev/null && FLAGS="$FLAGS ⇣"

    GIT_STATUS=" $(printf "${ORANGE}%s${RESET}" "$BRANCH")$(printf "${RED}%s${RESET}" "$FLAGS")"
fi

printf "${CYAN}%s${RESET}%s [%s]%s%s\n" "$TRUNCATED" "$GIT_STATUS" "$MODEL" "$CTX_STATUS" "$USAGE_STATUS"
