#!/usr/bin/env bash
# One-time setup: creates a GitHub repo, pushes the project, and enables Pages.
# Requires: gh (GitHub CLI) authenticated — run `gh auth login` first if needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="seattle-rentals"

echo "=== Seattle Rentals — GitHub Pages Setup ==="

# 1. Init git if not already a repo
cd "$SCRIPT_DIR"
if ! git rev-parse --git-dir &>/dev/null; then
  echo ""
  echo "1. Initialising git repo…"
  git init
  git add .
  git commit -m "initial commit"
else
  echo ""
  echo "1. Git repo already initialised."
fi

# 2. Create GitHub repo (public so Pages is free)
echo ""
echo "2. Creating GitHub repo '$REPO_NAME'…"
if gh repo view "$REPO_NAME" &>/dev/null 2>&1; then
  echo "   Repo already exists — skipping create."
else
  gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
  echo "   ✓ Repo created and pushed."
fi

# Make sure remote is set and up to date
if ! git remote get-url origin &>/dev/null; then
  GH_USER=$(gh api user --jq '.login')
  git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
fi

git push -u origin main 2>/dev/null || git push -u origin master 2>/dev/null || true

# 3. Enable GitHub Pages from /docs
echo ""
echo "3. Enabling GitHub Pages (docs/ folder)…"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/$(gh api user --jq '.login')/$REPO_NAME/pages" \
  -f "source[branch]=$BRANCH" \
  -f "source[path]=/docs" \
  2>/dev/null || \
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/$(gh api user --jq '.login')/$REPO_NAME/pages" \
  -f "source[branch]=$BRANCH" \
  -f "source[path]=/docs" \
  2>/dev/null || \
echo "   Pages may already be enabled — check repo Settings → Pages."

# 4. Install launchd plist
PLIST_NAME="com.meenakshi.seattle-rentals"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo ""
echo "4. Installing launchd agent (runs scraper every 3 hours)…"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "   ✓ Agent loaded."

# 5. Done — print the URL
GH_USER=$(gh api user --jq '.login')
echo ""
echo "=== Done! ==="
echo ""
echo "  Your live page (available in ~60s after first push):"
echo "  https://$GH_USER.github.io/$REPO_NAME/"
echo ""
echo "  Scraper runs every 3 hours and pushes updated listings."
echo "  The page auto-refreshes every 5 minutes."
echo ""
echo "  Useful commands:"
echo "    Run manually : $SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/scraper.py"
echo "    View log     : tail -f $SCRIPT_DIR/scraper.log"
echo "    Stop agent   : launchctl unload $PLIST_DEST"
echo "    Start agent  : launchctl load $PLIST_DEST"
echo ""
