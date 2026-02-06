# RoboClaw TREC's REC Ride Control Computer
    # Created by BasicMicro
    # Modified by Jackson Justus (jackjust@bu.edu)

import time
import serial
import struct
import logging
from threading import Lock
from PyCRC.CRCCCITT import CRCCCITT # Package is named 'pythoncrc' NOT 'pycrc' on pip
from ride_control_computer.motor_controller.RoboClaw_cmd import Cmd

# --- SETUP LOGGING ---
logger = logging.getLogger(__name__)

# --- SETUP EXCEPTIONS ---
class CRCException(Exception):
    """Raised when CRC validation fails during serial communication."""
    pass

# --- MISC DOCUMENTATION ---
# The format '>IiIiB' corresponds to:
#   'I' : unsigned 4-byte acceleration
#   'i' : signed 4-byte QSpeed (cruising speed)
#   'I' : unsigned 4-byte deceleration
#   'i' : signed 4-byte target position
#   'B' : 1-byte buffer indicator


class RoboClaw:
    """
    Stateless Interface for low-level communication between the software motor controller
    and the hardware RoboClaw. Abstracts the specifics of the RoboClaw's serial protocol.
    """
    def __init__(self, port='/dev/ttyAMA1', address=0x80, auto_recover=False, **kwargs):
        self.port = serial.Serial(baudrate=115200, timeout=0.1, interCharTimeout=0.01)
        self.port.port = port
        self.address = address
        self.serial_lock = Lock()
        self.auto_recover = auto_recover
        try:
            self.port.close()
            self.port.open()
        except serial.serialutil.SerialException:
            if auto_recover:
                self.recover_serial()
            else:
                raise

    # =========================================================================
    #                           WRITE COMMANDS
    # =========================================================================

    def set_speed_with_acceleration(self, motor: int, speed: int, acceleration: int):
        """
        Drive a motor with signed speed and unsigned acceleration.

        The motor accelerates incrementally until the target speed is reached.
        Acceleration is measured in speed increase per second (QPPS/s).

        Example: acceleration=12000, speed=12000 accelerates from 0 to 12000 QPPS in 1 second.

        Args:
            motor: Motor number (1 or 2)
            speed: Signed speed in QPPS (quad pulses per second). Sign indicates direction.
            acceleration: Unsigned acceleration in QPPS/s

        Raises:
            ValueError: If motor is not 1 or 2
        """
        if motor == 1:
            cmd = Cmd.M1SPEEDACCEL
        elif motor == 2:
            cmd = Cmd.M2SPEEDACCEL
        else:
            raise ValueError(f"Motor #{motor} is not valid!")

        # Format: 'I' = unsigned 4-byte accel, 'i' = signed 4-byte speed
        self._write(cmd, '>Ii', acceleration, speed)

    def drive_to_position_with_speed_acceleration_deceleration(self, motor: int, position: int, speed: int,
                                                               acceleration: int, deceleration: int, buffer: int = 0):
        """
        Move motor to an absolute position with speed, acceleration, and deceleration control.

        The motor accelerates to cruising speed, travels to the target position,
        then decelerates and holds the position.

        Args:
            motor: Motor number (1 or 2)
            position: Signed target position in encoder counts
            speed: Signed cruising speed in QPPS
            acceleration: Unsigned acceleration in QPPS/s
            deceleration: Unsigned deceleration in QPPS/s
            buffer: Command queue buffer index (0 for immediate execution)

        Raises:
            ValueError: If motor is not 1 or 2, or if values exceed limits
        """
        if motor == 1:
            cmd = Cmd.M1SPEEDACCELDECCELPOS
        elif motor == 2:
            cmd = Cmd.M2SPEEDACCELDECCELPOS
        else:
            raise ValueError(f"Motor #{motor} is not valid!")

        if speed > 2000 or acceleration > 500 or deceleration > 500:
            raise ValueError(f"Value too great! spd: {speed}, acc: {acceleration}, dec: {deceleration}")

        # Format: '>IiIiB' = accel(U4), speed(S4), decel(U4), position(S4), buffer(U1)
        self._write(cmd, '>IiIiB', acceleration, speed, deceleration, position, buffer)

    def reset_quad_encoders(self, motors: list[int] | None = None):
        """
        Reset motor encoders to zero.

        Args:
            motors: List of motor numbers to reset (default: [1, 2] for both)
        """
        if motors is None:
            motors = [1, 2]

        for motor in motors:
            cmd = Cmd.SETM1ENCCOUNT if motor == 1 else Cmd.SETM2ENCCOUNT
            self._write(cmd, '>I', 0)

    def set_max_current_limit(self, motor: int, max_current: int):
        """
        Set maximum current limit for a motor.

        Args:
            motor: Motor number (1 or 2)
            max_current: Maximum current in 10mA units (e.g., 1000 = 10A)
        """
        cmd = Cmd.SETM1MAXCURRENT if motor == 1 else Cmd.SETM2MAXCURRENT
        self._write(cmd, '>IBBBB', max_current, 0, 0, 0, 0)

    def set_s_pin_modes(self, s3_mode: int, s4_mode: int, s5_mode: int):
        """
        Set the modes for S3, S4, and S5 pins.

        Args:
            s3_mode: Mode value for S3 pin
            s4_mode: Mode value for S4 pin
            s5_mode: Mode value for S5 pin

        See read_s_pin_modes() for mode value meanings.
        """
        self._write(Cmd.SETPINFUNCTIONS, '>BBB', s3_mode, s4_mode, s5_mode)

    # =========================================================================
    #                           READ COMMANDS
    # =========================================================================

    def read_encoder_pos(self, motor: int) -> dict:
        """
        Read encoder count/position with status flags.

        Quadrature encoders have a range of 0 to 4,294,967,295. Absolute encoder
        values are converted from an analog voltage into a value from 0 to 2047.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Dictionary with keys:
                - encoder: Signed encoder count
                - underflow: True if counter underflow occurred (cleared after reading)
                - direction: "Forward" or "Backward"
                - overflow: True if counter overflow occurred (cleared after reading)
        """
        cmd = Cmd.GETM1ENC if motor == 1 else Cmd.GETM2ENC
        encoder, status = self._read(cmd, '>iB')
        return {
            "encoder": encoder,
            "underflow": bool(status & 0x01),
            "direction": "Backward" if (status & 0x02) else "Forward",
            "overflow": bool(status & 0x04)
        }

    def read_encoder_speed(self, motor: int) -> dict:
        """
        Read encoder speed in pulses per second.

        RoboClaw tracks how many pulses are received per second for both encoder channels.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Dictionary with keys:
                - speed: Speed in pulses per second (unsigned)
                - direction: "Forward" or "Backward"
        """
        cmd = Cmd.GETM1SPEED if motor == 1 else Cmd.GETM2SPEED
        speed, status = self._read(cmd, '>IB')
        return {
            "speed": speed,
            "direction": "Backward" if status else "Forward"
        }

    def read_range(self, motor: int) -> tuple:
        """
        Read the configured position range for a motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Tuple of (min_position, max_position)
        """
        cmd = Cmd.READM1POSPID if motor == 1 else Cmd.READM2POSPID
        pid_vals = self._read(cmd, '>IIIIIii')
        return pid_vals[5], pid_vals[6]

    def read_position(self, motor: int) -> float:
        """
        Read position as a percentage across the motor's configured range.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Position as percentage (0-100) of the configured range
        """
        encoder = self.read_encoder_pos(motor)["encoder"]
        range_vals = self.read_range(motor)
        return ((encoder - range_vals[0]) / float(range_vals[1] - range_vals[0])) * 100.0

    def read_max_speed(self, motor: int) -> int:
        """
        Read the maximum speed (QPPS) for a motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Maximum speed in QPPS
        """
        cmd = Cmd.READM1PID if motor == 1 else Cmd.READM2PID
        return self._read(cmd, '>IIII')[3]

    def read_status(self) -> str:
        """
        Read the current error/status state of the controller.

        Returns:
            Human-readable status string
        """
        raw = self._read(Cmd.GETERROR, '>BBBB')
        status = (raw[0] << 24) | (raw[1] << 16) | (raw[2] << 8) | raw[3]

        status_codes = {
            0x00000000: 'Normal',
            0x00000001: 'E-Stop',
            0x00000002: 'Temperature Error',
            0x00000004: 'Temperature 2 Error',
            0x00000008: 'Main Voltage High Error',
            0x00000010: 'Logic Voltage High Error',
            0x00000020: 'Logic Voltage Low Error',
            0x00000040: 'M1 Driver Fault Error',
            0x00000080: 'M2 Driver Fault Error',
            0x00000100: 'M1 Speed Error',
            0x00000200: 'M2 Speed Error',
            0x00000400: 'M1 Position Error',
            0x00000800: 'M2 Position Error',
            0x00001000: 'M1 Current Error',
            0x00002000: 'M2 Current Error',
            0x00010000: 'M1 Over Current Warning',
            0x00020000: 'M2 Over Current Warning',
            0x00040000: 'Main Voltage High Warning',
            0x00080000: 'Main Voltage Low Warning',
            0x00100000: 'Temperature Warning',
            0x00200000: 'Temperature 2 Warning',
            0x00400000: 'S4 Signal Triggered',
            0x00800000: 'S5 Signal Triggered',
            0x01000000: 'Speed Error Limit Warning',
            0x02000000: 'Position Error Limit Warning'
        }
        return status_codes.get(status, f'Unknown Error: {status}')

    def read_temp_sensor(self, sensor: int) -> float:
        """
        Read temperature from a sensor.

        Args:
            sensor: Sensor number (1 or 2)

        Returns:
            Temperature in degrees Celsius
        """
        cmd = Cmd.GETTEMP if sensor == 1 else Cmd.GETTEMP2
        return self._read(cmd, '>H')[0] / 10.0

    def read_batt_voltage(self, battery: str = "Main") -> float:
        """
        Read battery voltage.

        Args:
            battery: "Main" or "Logic" (case insensitive, or "L" for logic)

        Returns:
            Voltage in volts
        """
        cmd = Cmd.GETLBATT if battery.lower() in ['logic', 'l'] else Cmd.GETMBATT
        return self._read(cmd, '>H')[0] / 10.0

    def read_currents(self) -> tuple:
        """
        Read motor currents.

        Returns:
            Tuple of (motor1_current, motor2_current) in amps
        """
        currents = self._read(Cmd.GETCURRENTS, '>hh')
        return tuple(c / 100.0 for c in currents)

    def read_motor_current(self, motor: int) -> float:
        """
        Read current for a specific motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Current in amps
        """
        return self.read_currents()[0] if motor == 1 else self.read_currents()[1]

    def read_max_current_limit(self, motor: int) -> int:
        """
        Read maximum current limit for a motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Maximum current in 10mA units (e.g., 1000 = 10A)
        """
        cmd = Cmd.GETM1MAXCURRENT if motor == 1 else Cmd.GETM2MAXCURRENT
        max_current, _ = self._read(cmd, '>II')
        return max_current

    def read_version(self) -> str | None:
        """
        Read RoboClaw firmware version string.

        Returns:
            Firmware version string (e.g., "RoboClaw 10.2A v4.1.11")
        """
        cmd = 21
        cmd_bytes = struct.pack('>BB', self.address, cmd)

        try:
            with self.serial_lock:
                self.port.write(cmd_bytes)
                response = bytearray()
                start_time = time.time()

                while True:
                    byte = self.port.read(1)
                    if not byte:
                        if time.time() - start_time > self.port.timeout:
                            break
                        continue
                    response.extend(byte)
                    # Termination: LF (0x0A) followed by NULL (0x00)
                    if len(response) >= 2 and response[-2:] == b'\x0a\x00':
                        break

                crc_bytes = self.port.read(2)

            crc_actual = CRCCCITT().calculate(cmd_bytes + response)
            crc_expected = struct.unpack('>H', crc_bytes)[0]

            if crc_actual != crc_expected:
                logger.error('read version CRC failed')
                raise CRCException('CRC failed')

            return response.decode('utf-8', errors='ignore').rstrip('\n\x00')

        except serial.serialutil.SerialException:
            if self.auto_recover:
                self.recover_serial()
            else:
                logger.exception('roboclaw serial')
                raise

    def read_s_pin_modes(self) -> dict:
        """
        Read the modes for S3, S4, and S5 pins.

        Returns:
            Dictionary with keys 'S3', 'S4', 'S5' containing mode descriptions
        """
        raw_modes = self._read(Cmd.GETPINFUNCTIONS, '>BBBBB')
        s3_mode, s4_mode, s5_mode = raw_modes[0], raw_modes[1], raw_modes[2]

        s3_mapping = {
            0x00: "Default", 0x01: "E-Stop", 0x81: "E-Stop(Latching)",
            0x14: "Voltage Clamp", 0x24: "RS485 Direction", 0x84: "Encoder toggle",
            0x04: "Brake", 0xE2: "Home(Auto)", 0x62: "Home(User)",
            0xF2: "Home(Auto)/Limit(Fwd)", 0x72: "Home(User)/Limit(Fwd)",
            0x12: "Limit(Fwd)", 0x22: "Limit(Rev)", 0x32: "Limit(Both)"
        }
        s4_mapping = {
            0x00: "Disabled", 0x01: "E-Stop", 0x81: "E-Stop(Latching)",
            0x14: "Voltage Clamp", 0x04: "Brake", 0x62: "Home(User)",
            0xF2: "Home(Auto)/Limit(Fwd)", 0x72: "Home(User)/Limit(Fwd)",
            0x12: "Limit(Fwd)", 0x22: "Limit(Rev)", 0x32: "Limit(Both)"
        }
        s5_mapping = {
            0x00: "Disabled", 0x01: "E-Stop", 0x81: "E-Stop(Latching)",
            0x14: "Voltage Clamp", 0x62: "Home(User)",
            0xF2: "Home(Auto)/Limit(Fwd)", 0x72: "Home(User)/Limit(Fwd)"
        }

        return {
            "S3": s3_mapping.get(s3_mode, f"Unknown (0x{s3_mode:02X})"),
            "S4": s4_mapping.get(s4_mode, f"Unknown (0x{s4_mode:02X})"),
            "S5": s5_mapping.get(s5_mode, f"Unknown (0x{s5_mode:02X})")
        }

    def read_standard_config(self) -> dict:
        """
        Read and decode the standard configuration bitmask.

        Returns:
            Dictionary with boolean flags for each configuration option
        """
        config, = self._read(Cmd.GETCONFIG, '>H')
        return self.decode_standard_config(config)

    # =========================================================================
    #                           MISC
    # =========================================================================

    def _read(self, cmd, fmt):
        """
        Send a read command and receive a formatted response.

        Args:
            cmd: Command byte to send
            fmt: struct format string for unpacking the response

        Returns:
            Tuple of unpacked values according to fmt

        Raises:
            CRCException: If CRC validation fails
            Exception: If read is incomplete or serial error occurs
        """
        cmd_bytes = struct.pack('>BB', self.address, cmd)
        expected_length = struct.calcsize(fmt)

        try:
            with self.serial_lock:
                self.port.reset_input_buffer()
                self.port.write(cmd_bytes)
                response = bytearray()
                start_time = time.time()

                while len(response) < expected_length + 2:
                    byte = self.port.read(1)
                    if not byte:
                        if time.time() - start_time > self.port.timeout:
                            break
                        continue
                    response.extend(byte)

                if len(response) < expected_length + 2:
                    raise Exception("Incomplete read")

            crc_actual = CRCCCITT().calculate(cmd_bytes + response[:-2])
            crc_expect = struct.unpack('>H', response[-2:])[0]

            if crc_actual != crc_expect:
                logger.error(f'CRC failed: computed {crc_actual:04x}, expected {crc_expect:04x}')
                raise CRCException('CRC failed')

            return struct.unpack(fmt, response[:-2])

        except serial.serialutil.SerialException:
            if self.auto_recover:
                self.recover_serial()
            else:
                logger.exception('roboclaw serial')
                raise

    def _write(self, cmd, fmt, *data):
        """
        Send a write command with data and wait for acknowledgment.

        Args:
            cmd: Command byte to send
            fmt: struct format string for packing the data
            *data: Data values to pack and send

        Raises:
            CRCException: If acknowledgment fails
            Exception: If no verification byte received or serial error occurs
        """
        cmd_bytes = struct.pack('>BB', self.address, cmd)
        data_bytes = struct.pack(fmt, *data) if fmt else b''
        message = cmd_bytes + data_bytes
        write_crc = CRCCCITT().calculate(message)
        crc_bytes = struct.pack('>H', write_crc)

        try:
            with self.serial_lock:
                self.port.write(message + crc_bytes)
                self.port.flush()
                start_time = time.time()
                verification = None

                while True:
                    verification = self.port.read(1)
                    if verification:
                        break
                    if time.time() - start_time > self.port.timeout:
                        break

                if not verification:
                    logger.error("No verification byte received")
                    raise Exception("No verification byte received")

            if 0xff != struct.unpack('>B', verification)[0]:
                logger.error(f"ACK failed: expected 0xFF, received {struct.unpack('>B', verification)[0]}")
                raise CRCException('CRC failed')

        except serial.serialutil.SerialException:
            if self.auto_recover:
                self.recover_serial()
            else:
                logger.exception('roboclaw serial')
                raise

    def decode_standard_config(self, config: int) -> dict:
        """
        Decode a 16-bit standard config value into a dictionary of settings.

        Args:
            config: The 16-bit configuration bitmask

        Returns:
            Dictionary with configuration option names as keys and boolean values
        """
        result = {}

        # Serial Mode (bits 0-1)
        serial_mode = config & 0x0003
        result["RC Mode"] = (serial_mode == 0x0000)
        result["Analog Mode"] = (serial_mode == 0x0001)
        result["Simple Serial Mode"] = (serial_mode == 0x0002)
        result["Packet Serial Mode"] = (serial_mode == 0x0003)

        # Battery Mode (bits 2-4)
        battery_mode = config & 0x001C
        battery_modes = {
            0x0000: "Off", 0x0004: "Auto", 0x0008: "2 Cell", 0x000C: "3 Cell",
            0x0010: "4 Cell", 0x0014: "5 Cell", 0x0018: "6 Cell", 0x001C: "7 Cell"
        }
        for val, name in battery_modes.items():
            result[f"Battery Mode {name}"] = (battery_mode == val)

        # Baud Rate (bits 5-7)
        baud_rate = config & 0x00E0
        baud_rates = {
            0x0000: 2400, 0x0020: 9600, 0x0040: 19200, 0x0060: 38400,
            0x0080: 57600, 0x00A0: 115200, 0x00C0: 230400, 0x00E0: 460800
        }
        for val, rate in baud_rates.items():
            result[f"BaudRate {rate}"] = (baud_rate == val)

        # FlipSwitch (bit 8)
        result["FlipSwitch"] = bool(config & 0x0100)

        # Packet Address (bits 8-10)
        packet_address_field = (config & 0x0700) >> 8
        for i in range(8):
            result[f"Packet Address 0x{0x80 + i:02X}"] = (packet_address_field == i)

        # Individual flags
        result["Slave Mode"] = bool(config & 0x0800)
        result["Relay Mode"] = bool(config & 0x1000)
        result["Swap Encoders"] = bool(config & 0x2000)
        result["Swap Buttons"] = bool(config & 0x4000)
        result["Multi-Unit Mode"] = bool(config & 0x8000)

        return result

    def print_telemetry(self, motors: list[int] | None = None):
        """
        Print a summary of current motor telemetry to stdout.

        Args:
            motors: List of motor numbers to print telemetry for (default: [1, 2])
        """
        if motors is None:
            motors = [1, 2]

        voltage = self.read_batt_voltage()
        currents = self.read_currents()

        print(f"Vb: {voltage}V")

        for motor in motors:
            encoder_data = self.read_encoder_pos(motor)
            encoder = encoder_data["encoder"]
            direction = encoder_data["direction"]
            max_speed = self.read_max_speed(motor)
            min_pos, max_pos = self.read_range(motor)
            current = currents[motor - 1]

            print(f"  M{motor}: I={current}A, Enc={encoder} ({direction}), "
                  f"MaxSpd={max_speed}, Range=({min_pos}, {max_pos})")

    def recover_serial(self):
        """Attempt to recover the serial connection after a failure."""
        self.port.close()
        while not self.port.is_open:
            try:
                self.port.close()
                self.port.open()
            except serial.serialutil.SerialException:
                time.sleep(0.2)
                logger.warning('Failed to recover serial. Retrying.')