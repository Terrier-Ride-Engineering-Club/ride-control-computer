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

## Building Requirements <br>
Python 3.14.0
Raspberry Pi 5 (or compatible system). <br>
Dependencies listed in requirements.txt

## Building Instructions <br>
This project uses a standard python build structure. <br>
The instructions for building on MacOS/Linux are listed below. <br>
`python3.14 -m venv .venv` to create virtual environment. <br>
`pip install -r ./requirements.txt` to install dependencies. <br>
