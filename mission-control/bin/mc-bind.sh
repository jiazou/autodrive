#!/usr/bin/env bash
# Mission Control — bind a Claude session to a task/project. Appends one event line
# to ~/mission-control/bindings.jsonl (append-only; harvest reads the latest per session).
#
# Usage:
#   mc bind [SESSION_ID] --project "<Project>" [--task <slug>] [--tab <name>]
#   mc bind --unbind [SESSION_ID]
#
# SESSION_ID is a full UUID or the 8-char short form shown by harvest. If omitted,
# defaults to THIS session ($CLAUDE_CODE_SESSION_ID). Color and name are auto-resolved
# from the session transcript, so they are not set here.
set -euo pipefail

BINDINGS="$HOME/mission-control/bindings.jsonl"
SESSIONS_DIR="$HOME/.claude/sessions"

event="bind"
session_arg=""
project="" task="" tab=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unbind) event="unbind"; shift ;;
    --project) project="$2"; shift 2 ;;
    --task)    task="$2"; shift 2 ;;
    --tab)     tab="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) session_arg="$1"; shift ;;
  esac
done

# Resolve session id: explicit arg, else this session.
if [[ -z "$session_arg" ]]; then
  sid="${CLAUDE_CODE_SESSION_ID:-}"
  [[ -z "$sid" ]] && { echo "No SESSION_ID given and \$CLAUDE_CODE_SESSION_ID is unset." >&2; exit 1; }
elif [[ ${#session_arg} -le 12 ]]; then
  # short form -> resolve to full UUID via the live session files. Refuse to
  # guess if the prefix matches more than one live session (mirrors done.py).
  sid=$(python3 - "$session_arg" "$SESSIONS_DIR" <<'PY'
import json,sys,glob,os
short,dirp=sys.argv[1],sys.argv[2]
matches=[]
for f in glob.glob(os.path.join(dirp,"*.json")):
    try: d=json.load(open(f))
    except Exception: continue
    s=d.get("sessionId","")
    if s.startswith(short): matches.append(s)
matches=sorted(set(matches))
if len(matches)==1:
    print(matches[0])
elif not matches:
    sys.stderr.write(f"No live session matches '{short}'.\n")
else:
    sys.stderr.write(f"'{short}' is ambiguous — {len(matches)} sessions match:\n")
    for s in matches: sys.stderr.write(f"  {s}\n")
    sys.stderr.write("refusing to bind; use more characters of the id.\n")
PY
)
  # Python printed the specific reason (none vs ambiguous) to stderr already.
  [[ -z "$sid" ]] && exit 1
else
  sid="$session_arg"
fi

ts=$(date +%s)
# Build the JSON line with python (handles quoting/escaping).
python3 - "$BINDINGS" "$ts" "$event" "$sid" "$project" "$task" "$tab" <<'PY'
import json,sys
path,ts,event,sid,project,task,tab=sys.argv[1:8]
rec={"ts":int(ts),"event":event,"session_id":sid}
if project: rec["project"]=project
if task:    rec["task"]=task
if tab:     rec["tab_name"]=tab
with open(path,"a") as fh:
    fh.write(json.dumps(rec)+"\n")
print(("unbound" if event=="unbind" else "bound")+f" {sid[:8]}"+(f" -> {project}" if project else ""))
PY
