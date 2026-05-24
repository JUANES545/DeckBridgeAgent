# Test DeckBridgeAgent on all platforms

Run smoke tests against running agents.

## Steps

```bash
cd /Users/juamejia/Andes/DeckBridgeAgent
./builds/test-agent.sh
```

For Mac only: `./builds/test-agent.sh --mac-only`
For Windows only: `./builds/test-agent.sh --win-only`

## What is tested
1. `/health` — agent responds and returns `ok: true`
2. `/api/status` — returns state, version, udp_ok
3. `POST /action` — sends `key: enter`, verifies `ok: true` (only if paired + token available)
4. UDP discovery — verifies `udp_ok: true`

## Report as table
Show pass/fail for each check per platform.
