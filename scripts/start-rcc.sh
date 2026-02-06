#!/bin/bash
# Start RCC manually

cd /opt/rcc
.venv/bin/rcc --hardware

echo ""
echo "RCC exited. Press Enter to close..."
read