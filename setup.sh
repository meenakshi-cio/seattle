#!/usr/bin/env bash
# One-time setup script for the Seattle rental monitor.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.meenakshi.seattle-rentals"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Seattle Rental Monitor Setup ==="

# 1. Create virtualenv and install deps
echo ""
echo "1. Creating Python virtualenv..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "   ✓ Dependencies installed."

# 2. Prompt for Slack webhook
echo ""
echo "2. Slack webhook URL"
echo "   Paste your Slack incoming webhook URL and press Enter:"
read -r WEBHOOK_URL

if [[ -z "$WEBHOOK_URL" ]]; then
    echo "   ⚠ No URL provided — you can add it later by editing $PLIST_DEST"
else
    # Inject the URL into the plist copy
    sed "s|REPLACE_WITH_YOUR_SLACK_WEBHOOK_URL|$WEBHOOK_URL|g" \
        "$PLIST_SRC" > /tmp/$PLIST_NAME.plist
    PLIST_SRC="/tmp/$PLIST_NAME.plist"
    echo "   ✓ Webhook URL saved."
fi

# 3. Install launchd agent
echo ""
echo "3. Installing launchd agent..."
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DEST"

# Unload first in case it's already loaded
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "   ✓ Agent loaded — runs every 3 hours, and right now on first load."

echo ""
echo "=== Setup complete ==="
echo ""
echo "Useful commands:"
echo "  View live log  : tail -f $SCRIPT_DIR/scraper.log"
echo "  Run manually   : $SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/scraper.py"
echo "  Stop the agent : launchctl unload $PLIST_DEST"
echo "  Start again    : launchctl load $PLIST_DEST"
echo "  Seen listings  : cat $SCRIPT_DIR/seen_listings.json"
echo ""
