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
After installation, run the application with:
```bash
rcc
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

### Option A: Kiosk Mode (recommended for production)
On boot, shows a 5-second prompt. Press any key for desktop, otherwise launches Chrome kiosk with the RCC webserver.

```bash
# Make startup script executable
chmod +x /opt/rcc/scripts/rcc-startup.sh

# Configure auto-login to console via raspi-config
sudo raspi-config
# Navigate: System Options → Boot / Auto Login → Console Autologin

# Add to end of ~/.bashrc
echo '/opt/rcc/scripts/rcc-startup.sh' >> ~/.bashrc
```

### Option B: Background Service (headless)
Runs RCC as a background service without display.

```bash
# Copy service file and enable
sudo cp rcc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rcc
sudo systemctl start rcc
```

### Manage the service (Option B)
```bash
sudo systemctl status rcc   # Check status
sudo systemctl stop rcc     # Stop
sudo systemctl restart rcc  # Restart
journalctl -u rcc -f        # View logs
```
