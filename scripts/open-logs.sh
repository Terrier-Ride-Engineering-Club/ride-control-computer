#!/bin/bash
# Open RCC logs folder

pcmanfm /home/trec/logs/ || {
    echo "Failed to open logs folder"
    read -p "Press Enter to close..."
}
