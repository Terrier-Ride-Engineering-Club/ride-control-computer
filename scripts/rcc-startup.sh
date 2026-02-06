#!/bin/bash
# RCC Startup Script
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
    echo "Starting RCC in kiosk mode..."

    # Start the RCC service with hardware implementations
    /opt/rcc/.venv/bin/rcc --hardware &
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

    # If Chrome exits, stop RCC
    kill $RCC_PID 2>/dev/null

    echo ""
    echo "Kiosk exited. Press Enter to close..."
    read
fi
