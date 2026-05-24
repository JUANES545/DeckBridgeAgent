# Check DeckBridgeAgent status on all platforms

Quick health check of both Mac and Windows agents.

## Steps (run in parallel)

1. Mac: `curl -s http://localhost:8765/api/status`
2. Windows: `curl -s http://192.168.1.29:8765/api/status`

## Report as table
| Platform | Version | State | Device | Last Action | Accessibility | UDP |
|---|---|---|---|---|---|---|
| macOS | ... | ... | ... | ... | ✓/✗ | ✓/✗ |
| Windows | ... | ... | ... | ... | — | ✓/✗ |

Also show last 3 actions from each agent if available.
If an agent is not responding, say so clearly.
