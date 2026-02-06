#!/bin/bash
# Update RCC from git repository

cd /opt/rcc

echo "Pulling latest changes..."
git pull

echo ""
echo "Reinstalling package..."
.venv/bin/pip install . --quiet

echo ""
echo "Update complete!"
read -p "Press Enter to close..."