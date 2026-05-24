# Release DeckBridgeAgent

Create a new release of DeckBridgeAgent with the given version.

## Usage
`/release-agent 1.11.0`

## Steps

1. Update `CHANGELOG.md` — add entry `## [VERSION] - DATE` with summary of changes since last tag
   - Run `git log <last-tag>..HEAD --oneline` to see commits
2. Commit: `git config commit.gpgsign false && PRE_COMMIT_ALLOW_NO_CONFIG=1 git add CHANGELOG.md && git commit -m "docs: update CHANGELOG for vVERSION"`
3. Push: `git push origin master`
4. Tag + push: `git tag vVERSION && git push origin vVERSION`
5. GitHub Actions will automatically build and upload:
   - `DeckBridgeAgent-vVERSION-macOS.dmg`
   - `DeckBridgeAgent-vVERSION-Windows-Setup.exe`
6. Monitor: `gh run list --repo JUANES545/DeckBridgeAgent --limit 1`
7. Wait for completion and show release URL

## Notes
- Verify active gh account is JUANES545: `gh auth switch --user JUANES545`
- Never add Claude/AI references in commit messages
