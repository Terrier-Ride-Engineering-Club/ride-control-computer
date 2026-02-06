# Ride Control Computer (RCC) 2025-2026
This repo hosts all of the code and files related to Terrier Ride Engineering Club's (TREC) Ride Control Computer (RCC) project for the Ride Engineering Competition (REC) 25-26 season.

## About the Project
The RCC is a Raspberry Pi-based control system for an amusement ride, built for the Ride Engineering Competition. It coordinates motor control, safety monitoring, operator controls, and theming elements to safely operate a ride from dispatch through cycle completion.

## Structure
```
ride_control_computer/
├── RCC.py                 # Main controller, safety logic, state machine
├── main.py                # Entry point, logging setup
├── loop_timer.py          # Timing utility
├── motor_controller/      # Motor control (RoboClaw, Mock)
├── control_panel/         # Operator inputs (Mock)
├── theming_controller/    # Show control (Mock)
└── webserver/             # Status dashboard (Flask, Mock)
```
Each subsystem has an abstract interface (ABC) and a Mock implementation for testing w/o hardware.

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
