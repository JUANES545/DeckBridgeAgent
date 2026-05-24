#!/usr/bin/env bash
# DeckBridgeAgent — Smoke test
# Sends a set of test actions to all running agents and verifies responses.
#
# Usage:
#   ./builds/test-agent.sh              # test Mac (localhost) + Windows (192.168.1.29)
#   ./builds/test-agent.sh --mac-only
#   ./builds/test-agent.sh --win-only
#   ./builds/test-agent.sh --host 192.168.1.5  # custom host

set -euo pipefail

MAC_HOST="localhost"
WIN_HOST="192.168.1.29"
PORT=8765
TEST_MAC=1
TEST_WIN=1
PAIR_TOKEN=""

for arg in "$@"; do
  case "$arg" in
    --mac-only) TEST_WIN=0 ;;
    --win-only) TEST_MAC=0 ;;
    --host)     shift; WIN_HOST="$1" ;;
  esac
done

PASS=0; FAIL=0

# Colours
GREEN='\033[0;32m'; RED='\033[0;31m'; RESET='\033[0m'; BOLD='\033[1m'

check() {
  local label="$1" host="$2"
  local base="http://${host}:${PORT}"
  echo ""
  echo -e "${BOLD}── $label ($host) ──────────────────────────────${RESET}"

  # 1. Health check
  local health
  health=$(curl -sf --max-time 5 "${base}/health" 2>/dev/null) || { echo -e "  ${RED}✗ /health — unreachable${RESET}"; FAIL=$((FAIL+1)); return; }
  local agent_os; agent_os=$(echo "$health" | python3 -c "import sys,json;print(json.load(sys.stdin)['agent_os'])" 2>/dev/null)
  echo -e "  ${GREEN}✓${RESET} /health — agent_os=${agent_os}"
  PASS=$((PASS+1))

  # Grab pair token from paired_device.json if available
  local token=""
  if [[ "$host" == "localhost" ]]; then
    token=$(python3 -c "
import json,os; p=os.path.expanduser('~/.deckbridge/paired_device.json')
print(json.load(open(p))['pair_token'] if os.path.exists(p) else '')" 2>/dev/null)
  fi

  auth_header=""
  [[ -n "$token" ]] && auth_header="-H \"X-DeckBridge-Pair-Token: ${token}\""

  # 2. /api/status
  local status
  status=$(curl -sf --max-time 5 "${base}/api/status" 2>/dev/null) || { echo -e "  ${RED}✗ /api/status — failed${RESET}"; FAIL=$((FAIL+1)); return; }
  local state version; state=$(echo "$status" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['state'])" 2>/dev/null)
  version=$(echo "$status" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'])" 2>/dev/null)
  echo -e "  ${GREEN}✓${RESET} /api/status — state=${state} version=${version}"
  PASS=$((PASS+1))

  # 3. POST /action (key: enter) — requires pair token
  if [[ "$state" == "paired" || "$state" == "connected" ]]; then
    if [[ -z "$token" ]]; then
      echo -e "  ⚠  POST /action — skipped (no local pair token for ${host})"
    else
      local action_result
      action_result=$(curl -sf --max-time 5 -X POST "${base}/action" \
        -H "Content-Type: application/json" \
        -H "X-DeckBridge-Pair-Token: ${token}" \
        -d '{"type":"key","key":"enter"}' 2>/dev/null) || action_result='{"ok":false}'
      local ok; ok=$(echo "$action_result" | python3 -c "import sys,json;print(json.load(sys.stdin).get('ok',False))" 2>/dev/null)
      if [[ "$ok" == "True" ]]; then
        echo -e "  ${GREEN}✓${RESET} POST /action key=enter — ok"
        PASS=$((PASS+1))
      else
        echo -e "  ${RED}✗${RESET} POST /action — ${action_result}"
        FAIL=$((FAIL+1))
      fi
    fi
  else
    echo -e "  ${YELLOW:-}⚠${RESET} POST /action — skipped (not paired or no token)"
  fi

  # 4. UDP discovery check
  local udp; udp=$(echo "$status" | python3 -c "import sys,json;print(json.load(sys.stdin)['udp_ok'])" 2>/dev/null)
  [[ "$udp" == "True" ]] && \
    { echo -e "  ${GREEN}✓${RESET} UDP discovery — listening"; PASS=$((PASS+1)); } || \
    { echo -e "  ${RED}✗${RESET} UDP discovery — not listening"; FAIL=$((FAIL+1)); }
}

[[ $TEST_MAC -eq 1 ]] && check "macOS" "$MAC_HOST"
[[ $TEST_WIN -eq 1 ]] && check "Windows" "$WIN_HOST"

echo ""
echo -e "${BOLD}── Results ─────────────────────────────────────${RESET}"
echo -e "  ${GREEN}Passed: ${PASS}${RESET}  ${RED}Failed: ${FAIL}${RESET}"
echo ""
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
