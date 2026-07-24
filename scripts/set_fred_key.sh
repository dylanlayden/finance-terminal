#!/usr/bin/env bash
# Set the FRED_API GitHub secret — but only if the key is actually valid.
#
# Run this LOCALLY so the key never leaves your machine except straight into
# GitHub's encrypted secret store. It refuses to set a malformed value, which
# is the whole point: the last two pastes were 105-char non-keys.
#
# Usage:
#   1. Get the key: https://fredaccount.stlouisfed.org/apikeys
#   2. Run:  ./scripts/set_fred_key.sh
#   3. Paste ONLY the 32-character key when prompted (input is hidden).
#
set -euo pipefail

REPO="dylanlayden/finance-terminal"

printf "Paste your FRED API key (32 lowercase letters/digits), then Enter: "
read -rs KEY
echo

# Trim whitespace/newlines a stray copy may have added.
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"

if [[ ! "$KEY" =~ ^[a-z0-9]{32}$ ]]; then
  echo "✗ That is not a valid FRED key." >&2
  echo "  Length: ${#KEY} (need exactly 32)." >&2
  case "$KEY" in
    http*)      echo "  It looks like a URL — paste only the key, not the API URL." >&2 ;;
    *api_key=*) echo "  It contains 'api_key=' — paste only the value after the '='." >&2 ;;
    *[A-Z]*)    echo "  It contains uppercase — FRED keys are all lowercase." >&2 ;;
  esac
  echo "  Nothing was changed." >&2
  exit 1
fi

echo "✓ Key looks valid (32 lowercase alphanumeric). Setting secret on $REPO..."
gh secret set FRED_API --repo "$REPO" --body "$KEY"
echo "✓ Done. Now trigger a refresh:"
echo "    gh workflow run 'Refresh data' --repo $REPO"
