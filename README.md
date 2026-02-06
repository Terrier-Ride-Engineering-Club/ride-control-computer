# Ride Control Computer (RCC) 2024-2025
This repo hosts all of the code and files related to Terrier Ride Engineering Club's (TREC) Ride Control Computer (RCC) project for the Ride Engineering Competition (REC) 25-26 season.

## About the Project
- TODO

## Key Features
- TODO

## Credits
__Project Credits:__ <br>
Jackson Justus - Electrical Lead -- jackjust@bu.edu <br>
Liam Mertens - Electrical Member -- lmertens@bu.edu <br>

__Club Leadership:__ <br>
Electrical Lead: Jackson Justus (jackjust@bu.edu) <br>
Mechanical Lead: Daniel Ulrich (dculrich@bu.edu) <br>
Design Lead: Jon Chuang (chuangj@bu.edu) <br>

## Requirements
- Python 3.14
- Raspberry Pi 5 (production) or macOS/Windows/Linux (development)

## Installation

### macOS / Linux
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package and dependencies
pip install -e .

# Or with dev tools (pytest, ruff, black)
pip install -e ".[dev]"
```

### Windows
```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install the package and dependencies
pip install -e .

# Or with dev tools (pytest, ruff, black)
pip install -e ".[dev]"
```

### Running
```bash
rcc             # Uses mock implementations (default, safe for development)
rcc --hardware  # Uses hardware implementations (Pi deployment)
```

### Running Tests
```bash
pytest
```

## Deployment (Raspberry Pi)

### Install
```bash
# Clone to /opt/rcc
sudo mkdir -p /opt/rcc
sudo chown $USER:$USER /opt/rcc
git clone https://github.com/Terrier-Ride-Engineering-Club/ride-control-computer.git /opt/rcc

# Create venv and install
cd /opt/rcc
python3 -m venv .venv
.venv/bin/pip install .
```

### Kiosk Mode Setup
On boot, shows a 5-second prompt. Press any key for desktop, otherwise launches Chrome kiosk with the RCC webserver.

```bash
# Make startup script executable
chmod +x /opt/rcc/scripts/rcc-startup.sh

# Configure console auto-login
sudo raspi-config
# Navigate: System Options → Boot / Auto Login → Console Autologin

# Add startup script to bashrc
echo '/opt/rcc/scripts/rcc-startup.sh' >> ~/.bashrc
```

Reboot to test.
