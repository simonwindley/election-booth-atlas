#!/bin/zsh
# Double-click to run the Election Booth Atlas on this Mac: serves site/ on http://localhost:8000 and opens it.
# Close this window (or press Ctrl+C) to stop.
cd "$(dirname "$0")/site" || exit 1
PORT=8000
while lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT+1)); done   # next free port if 8000 is taken
( sleep 1; open "http://localhost:$PORT/" ) &
echo "Election Booth Atlas: http://localhost:$PORT/  (Ctrl+C to stop)"
python3 -m http.server $PORT
