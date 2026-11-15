#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
TMP_DIR=$(mktemp -d)
PORT=0 node server.js > "$TMP_DIR/server.log" 2> "$TMP_DIR/server.err" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; rm -rf "$TMP_DIR"' EXIT
tries=0
while ! grep -q '^LISTEN ' "$TMP_DIR/server.log"; do
  tries=$((tries+1)); [ "$tries" -lt 100 ]; sleep 0.02
done
port=$(awk '/^LISTEN / { print $2; exit }' "$TMP_DIR/server.log")
base="http://127.0.0.1:$port"
curl --max-time 3 -si -H "Cookie: session={{secret:cookie_0}}" -H "X-Client-ID: cookie-0" -H "X-CSRF-Case: 0" "$base/v1/search"
curl --max-time 3 -si -H "Cookie: session={{secret:cookie_1}}" -H "X-Client-ID: cookie-1" -H "X-CSRF-Case: 1" "$base/v1/search"
curl --max-time 3 -si -H "Cookie: session={{secret:cookie_2}}" -H "X-Client-ID: cookie-2" -H "X-CSRF-Case: 2" "$base/v1/search"
curl --max-time 3 -v -H "Authorization: Bearer {{secret:token_0}}" -H "X-Client-ID: burst" "$base/v1/search"
curl --max-time 3 -v -H "Authorization: Bearer {{secret:token_1}}" -H "X-Client-ID: burst" "$base/v1/search"
curl --max-time 3 -v -H "Authorization: Bearer {{secret:token_2}}" -H "X-Client-ID: burst" "$base/v1/search"
curl --max-time 3 -si -H "X-Client-ID: csrf" -H "X-CSRF-Case: 3" "$base/v1/search"
status=$(curl --max-time 3 -s -o /dev/null -w "%{http_code}" -H "X-Client-ID: burst" "$base/v1/search")
[ "$status" = 429 ]
echo "smoke: 429 verified"
