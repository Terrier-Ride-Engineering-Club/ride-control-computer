#!/bin/bash
# RCC Boot Script
# Shows a prompt, then either boots to desktop or kiosk mode

TIMEOUT=5
WEBSERVER_URL="http://127.0.0.1:8080"

echo "=========================================="
echo "   Ride Control Computer - Startup"
echo "=========================================="
echo ""
echo "Press any key within $TIMEOUT seconds for desktop..."
echo "Otherwise, starting kiosk mode."
echo ""

# Wait for keypress with timeout
if read -n 1 -t $TIMEOUT; then
    echo ""
    echo "Starting desktop environment..."
    startx
else
    echo ""
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
    echo "Starting RCC in kiosk mode..."

    # Start the RCC service with hardware implementations
    .venv/bin/rcc --hardware &
    RCC_PID=$!

    # Wait for webserver to be ready
    echo "Waiting for webserver..."
    sleep 3

    # Start Chromium in kiosk mode
    chromium \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-restore-session-state \
        --disable-features=TranslateUI \
        --disable-sync \
        --check-for-update-interval=31536000 \
        "$WEBSERVER_URL"

    # If Chromium exits, stop RCC
    kill $RCC_PID 2>/dev/null

    echo ""
    echo "Kiosk exited. Press Enter to close..."
    read
fi
