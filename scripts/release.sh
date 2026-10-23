#!/usr/bin/env bash

# Release script for ChronoSync
# Usage: ./scripts/release.sh <new_version>
# Example: ./scripts/release.sh 0.1.1

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <new_version>"
  exit 1
fi

NEW_VERSION="$1"
PACKAGE_DIR="chronosync"
INIT_FILE="$PACKAGE_DIR/__init__.py"
CHANGELOG="CHANGELOG.md"

# Ensure version format looks like X.Y.Z
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must be in the form X.Y.Z"
  exit 1
fi

# Update __version__ in __init__.py
if grep -q "__version__ = \"[^"]*\"" "$INIT_FILE"; then
  sed -i.bak "s/__version__ = \"[^"]*\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
  rm "$INIT_FILE.bak"
else
  echo "__version__ = \"$NEW_VERSION\"" >> "$INIT_FILE"
fi

# Add entry to CHANGELOG.md
TODAY=$(date +%Y-%m-%d)
printf "\n## [%s] - %s\n\n- TODO: describe changes\n" "$NEW_VERSION" "$TODAY" >> "$CHANGELOG"

# Commit changes
git add "$INIT_FILE" "$CHANGELOG"
git commit -m "Release $NEW_VERSION"

# Tag the release
git tag -a "v$NEW_VERSION" -m "Version $NEW_VERSION"

# Push commit and tags
git push origin main
git push origin "v$NEW_VERSION"

echo "Release $NEW_VERSION prepared and pushed."
