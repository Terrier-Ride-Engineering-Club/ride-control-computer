#!/bin/bash
# RCC Terminal Script
# Runs RCC in terminal without Chromium (for debugging)

cd /opt/rcc

# Try to update from git
echo "Checking for updates..."
PULL_OUTPUT=$(git pull 2>&1)
PULL_STATUS=$?

if [ $PULL_STATUS -eq 0 ]; then
    if echo "$PULL_OUTPUT" | grep -q "Already up to date"; then
        echo "Already up to date."
    else
        echo "Updates found, reinstalling..."
        echo "$PULL_OUTPUT"
        .venv/bin/pip install . --quiet
        echo "Reinstall complete."
    fi
else
    echo "Git pull failed (no network?), continuing with current version."
fi

echo ""
echo "Starting RCC..."
.venv/bin/rcc --hardware

echo ""
echo "RCC exited. Press Enter to close..."
read