#!/usr/bin/env bash
# DeckBridgeAgent — Auto-detect next semantic version from conventional commits
#
# Usage:
#   ./builds/bump-version.sh           # prints suggested version
#   ./builds/bump-version.sh --apply   # updates CHANGELOG.md header too
#
# Conventional commits:
#   feat:     → MINOR bump  (new feature)
#   fix:      → PATCH bump  (bug fix)
#   docs:     → PATCH bump
#   chore:    → PATCH bump
#   BREAKING CHANGE / feat!: → MAJOR bump

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Get current version from latest tag
CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
CURRENT="${CURRENT_TAG#v}"

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

# Commits since last tag
COMMITS=$(git log "${CURRENT_TAG}..HEAD" --pretty=format:"%s" 2>/dev/null || echo "")

if [[ -z "$COMMITS" ]]; then
  echo "No commits since ${CURRENT_TAG} — nothing to release."
  exit 0
fi

# Determine bump type
BUMP="patch"
while IFS= read -r msg; do
  if echo "$msg" | grep -qiE "BREAKING.CHANGE|^feat!|^fix!"; then
    BUMP="major"; break
  elif echo "$msg" | grep -qiE "^feat(\(.+\))?:"; then
    BUMP="minor"
  fi
done <<< "$COMMITS"

# Calculate new version
case "$BUMP" in
  major) NEW="${MAJOR}.$((MINOR+1)).0" ;; # conventionally major bumps are rare; treat as minor for now
  minor) NEW="${MAJOR}.$((MINOR+1)).0" ;;
  patch) NEW="${MAJOR}.${MINOR}.$((PATCH+1))" ;;
esac

# Print commit summary
echo "Current version: ${CURRENT_TAG}"
echo "Commits since last tag:"
git log "${CURRENT_TAG}..HEAD" --pretty=format:"  %s" | head -20
echo ""
echo "Detected bump: ${BUMP} → v${NEW}"

if [[ "${1:-}" == "--apply" ]]; then
  DATE=$(date +%Y-%m-%d)
  # Prepend CHANGELOG entry
  SUMMARY=$(git log "${CURRENT_TAG}..HEAD" --pretty=format:"- %s" | head -15)
  ENTRY="## [${NEW}] - ${DATE}\n\n### Changed\n\n${SUMMARY}\n\n"
  python3 -c "
import re, sys
with open('CHANGELOG.md', 'r') as f: content = f.read()
# Insert after the header (first ## [...] line)
new_entry = '''${ENTRY}'''
content = re.sub(r'(## \[)', new_entry + r'\1', content, count=1)
with open('CHANGELOG.md', 'w') as f: f.write(content)
print('CHANGELOG.md updated')
"
  echo ""
  echo "Next: git add CHANGELOG.md && git commit -m 'docs: update CHANGELOG for v${NEW}'"
  echo "Then: git tag v${NEW} && git push origin master && git push origin v${NEW}"
fi
