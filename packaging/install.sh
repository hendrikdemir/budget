#!/bin/bash
# Builds Budget and replaces the copy in Applications. Data is stored separately and stays
# untouched. If Budget is open it's closed first and reopened afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."

packaging/build.sh

APP=/Applications/Budget.app
ID=nl.hendrikdemir.budget
if [ -d "$APP" ] && [ "$(defaults read "$APP/Contents/Info" CFBundleIdentifier)" != "$ID" ]; then
  echo "$APP is a different app; not replacing it." >&2
  exit 1
fi

was_running=false
if pgrep -f "$APP/Contents/MacOS/Budget" >/dev/null; then
  was_running=true
  osascript -e 'tell application id "'"$ID"'" to quit'
  for _ in {1..20}; do pgrep -f "$APP/Contents/MacOS/Budget" >/dev/null || break; sleep 0.5; done
  if pgrep -f "$APP/Contents/MacOS/Budget" >/dev/null; then
    echo "Budget didn't quit; close it and run this again." >&2
    exit 1
  fi
fi

rm -rf "$APP"
ditto dist/Budget.app "$APP"
$was_running && open "$APP"
echo "Installed $APP"
