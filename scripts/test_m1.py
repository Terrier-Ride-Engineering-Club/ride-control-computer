"""
M1 Motor Test Script
Standalone script to test Motor 1 independently of the RCC.
Connects directly to the RoboClaw and drives M1 to a target position,
printing encoder position and speed in real time.

Usage:
    python scripts/test_m1.py [--port /dev/ttyACM0] [--position 10000] [--speed 500]

Press Ctrl+C to stop and hold the motor at position 0.
"""

import argparse
import sys
import time

# Allow running from repo root without installing the package
sys.path.insert(0, "src")

from ride_control_computer.motor_controller.RoboClaw import RoboClaw

PORTS = ["/dev/ttyAMA1", "/dev/ttyACM0", "/dev/ttyACM1"]
ADDRESS = 0x80

ACCEL = 200
DECEL = 200


def connect(port_override: str | None) -> RoboClaw:
    ports = [port_override] if port_override else PORTS
    for port in ports:
        try:
            rc = RoboClaw(port=port, address=ADDRESS)
            version = rc.read_version()
            print(f"Connected on {port}: {version}")
            return rc
        except Exception as e:
            print(f"  {port}: {e}")
    print("ERROR: RoboClaw not found on any port.")
    sys.exit(1)


def print_status(rc: RoboClaw, target: int):
    enc  = rc.read_encoder_pos(1)["encoder"]
    spd  = rc.read_encoder_speed(1)
    status, _ = rc.read_status()
    err  = abs(enc - target)
    print(f"  pos={enc:7d}  speed={spd['speed']:5d} {spd['direction']:<8s}  err={err:6d}  mc_status={status}")


def main():
    parser = argparse.ArgumentParser(description="M1 motor test")
    parser.add_argument("--port",     default=None,  help="Serial port (auto-detect if omitted)")
    parser.add_argument("--position", type=int, default=10000, help="Target encoder position (default 10000)")
    parser.add_argument("--speed",    type=int, default=500,   help="Cruise speed in QPPS (default 500)")
    args = parser.parse_args()

    rc = connect(args.port)

    print(f"\nResetting M1 encoder to 0...")
    rc.reset_quad_encoders([1])
    time.sleep(0.1)

    enc = rc.read_encoder_pos(1)["encoder"]
    print(f"M1 encoder after reset: {enc}")

    print(f"\nDriving M1 to position {args.position} at speed {args.speed} QPPS...")
    print(f"(accel={ACCEL}, decel={DECEL})\n")

    rc.drive_to_position_with_speed_acceleration_deceleration(
        motor=1,
        position=args.position,
        speed=args.speed,
        acceleration=ACCEL,
        deceleration=DECEL,
    )

    try:
        while True:
            print_status(rc, args.position)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping M1...")
        rc.set_speed_with_acceleration(1, 0, 500)
        time.sleep(0.5)
        enc = rc.read_encoder_pos(1)["encoder"]
        print(f"Stopped at position: {enc}")


if __name__ == "__main__":
    main()
