# Release DeckBridgeAgent

Create a new release. Auto-detects the version from conventional commits.

## Usage
`/release-agent`          — auto-detect version
`/release-agent 1.11.0`   — specify version explicitly

## Steps

### 1. Detect version (if not specified)
```bash
cd /Users/juamejia/Andes/DeckBridgeAgent
./builds/bump-version.sh
```
Show the output and ask the user to confirm the suggested version before proceeding.

### 2. Run smoke tests
```bash
./builds/test-agent.sh
```
If tests fail, warn and ask for confirmation.

### 3. Update CHANGELOG
```bash
./builds/bump-version.sh --apply   # if using auto-detected version
# OR manually add entry to CHANGELOG.md
```

### 4. Commit + tag + push
```bash
git config commit.gpgsign false
PRE_COMMIT_ALLOW_NO_CONFIG=1 git add CHANGELOG.md
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "docs: update CHANGELOG for vVERSION"
git push origin master
git tag vVERSION && git push origin vVERSION
```

### 5. Monitor GitHub Actions
```bash
gh run list --repo JUANES545/DeckBridgeAgent --limit 1
```
Wait for both jobs (macOS DMG + Windows Setup) to complete, then show release URL.

## Notes
- Verify active gh account: `gh auth switch --user JUANES545`
- Release assets: `DeckBridgeAgent-vX.Y.Z-macOS.dmg` + `DeckBridgeAgent-vX.Y.Z-Windows-Setup.exe`
- Never add Claude/AI references in commit messages
