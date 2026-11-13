"""Adapters; importing this module never opens a device or imports its drivers."""

import math
import re

from .core import AcquisitionError


def parse_reading(text, unit):
    """Reject error codes, unexpected units and incomplete numeric replies."""
    match = re.fullmatch(r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(" +
                         re.escape(unit) + r")?\s*", text)
    if not match:
        raise AcquisitionError(f"Invalid {unit} response: {text!r}")
    value = float(match.group(1))
    if not math.isfinite(value):
        raise AcquisitionError(f"Non-finite {unit} response.")
    return value


class SimulatedStand:
    """Illustrative 10 N/mm spring, not a calibrated or fitted specimen model."""

    simulated = True

    def __init__(self, clock):
        self.clock = clock
        self.position = 0.0
        self.last_time = clock.now()
        self.direction = 0
        self.motion = "STOP"
        self.speed = 0.0
        self.closed = False
        self.opened = False

    def open(self):
        self.opened = True
        self.last_time = self.clock.now()

    def _advance(self):
        now = self.clock.now()
        self.position += self.direction * self.speed / 60.0 * (now - self.last_time)
        self.last_time = now

    def read(self):
        self._advance()
        return max(0.0, 10.0 * self.position), self.position

    def set_speed(self, speed):
        self._advance()
        self.speed = speed

    def move(self, direction):
        self._advance()
        self.direction = direction
        self.motion = "DOWN" if direction > 0 else "UP"

    def stop(self):
        self._advance()
        self.direction = 0
        self.motion = "STOP"

    def close(self):
        self.closed = True


class SimulatedLCR:
    simulated = True

    def __init__(self, stand, clock):
        self.stand, self.clock = stand, clock
        self.closed = False

    def open(self):
        pass

    def read(self):
        if self.stand.direction:
            raise AssertionError("LCR acquisition was attempted while motion was commanded.")
        self.clock.sleep(0.02)
        force, _ = self.stand.read()
        return (5.8 + 0.1 * force) * 1e-12, 0.003

    def close(self):
        self.closed = True


class F305Serial:
    """Series F PC Control profile, pending verification on the installed system.

    The command framing follows the Series F EasyMESUR manual, section 10.
    The installed control option/firmware must be identified before hardware use.
    """

    simulated = False

    def __init__(self, settings, clock, serial_factory=None):
        self.cfg, self.clock = settings, clock
        self.factory = serial_factory
        self.connection = None
        self.speed = 0.0
        self.motion = "UNKNOWN"

    def command(self, text, reply=False):
        if self.connection is None:
            raise AcquisitionError("The F305 serial port is not open.")
        if reply:
            self.connection.reset_input_buffer()
        payload = text.encode("ascii")  # Fixed-width PC Control commands, no terminator.
        if self.connection.write(payload) != len(payload):
            raise AcquisitionError("Incomplete F305 command write.")
        self.clock.sleep(self.cfg.command_gap_s)
        if reply:
            raw = self.connection.read_until(b"\n", size=128)
            if not raw.endswith(b"\r\n"):
                raise AcquisitionError("Incomplete F305 response or serial timeout.")
            return raw.decode("ascii").strip()
        return None

    def open(self):
        if self.factory is None:
            import serial
            self.factory = serial.Serial
        self.connection = self.factory(self.cfg.mark10_port, self.cfg.baud_rate,
                                       timeout=self.cfg.serial_timeout_s,
                                       write_timeout=self.cfg.serial_timeout_s)
        self.connection.reset_input_buffer()
        self.stop()
        self.command("i")
        # Limit mode retains the existing frame limits; no travel limits are overwritten.
        self.command("l")
        status = self.command("p", reply=True).replace(" ", "").replace(",", "")
        if status != "SL":
            raise AcquisitionError(f"Expected stopped limit mode (SL), received {status!r}.")
        if self.command("A", reply=True) != "N":
            raise AcquisitionError("Configure the force display in N before acquisition.")
        if self.command("S", reply=True).upper() not in {"N", "NORMAL"}:
            raise AcquisitionError("Configure normal/live load mode before acquisition.")

    def read(self):
        force = parse_reading(self.command("X", reply=True), "N")
        displacement = parse_reading(self.command("x", reply=True), "mm")
        return force, displacement

    def set_speed(self, speed):
        if not math.isfinite(speed) or not 0.1 <= speed <= self.cfg.max_speed_mm_min:
            raise ValueError("Requested speed is outside configured limits.")
        if speed != round(speed, 1):
            raise ValueError("Speed must have one decimal place.")
        self.command(f"e{speed:06.1f}")
        self.command("o")
        self.speed = speed

    def move(self, direction):
        if direction not in {-1, 1}:
            raise ValueError("Motion direction must be -1 or 1.")
        self.command("d" if direction > 0 else "u")
        self.motion = "DOWN" if direction > 0 else "UP"

    def stop(self):
        if self.connection is None:
            return
        self.command("s")
        self.motion = "STOP_REQUESTED"
        status = self.command("p", reply=True).replace(" ", "").replace(",", "")
        if not re.fullmatch(r"S[CLM](?:UL|DL)?", status):
            raise AcquisitionError(f"The frame did not report a stopped state: {status!r}.")
        self.motion = "STOP_REPORTED"

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class E4980QCodes:
    """QCoDeS transport with explicit triggering and instrument-status checking."""

    simulated = False

    def __init__(self, settings, factory=None, cpd=None):
        self.cfg = settings
        self.factory, self.cpd = factory, cpd
        self.meter = None

    def open(self):
        if self.factory is None:
            from qcodes.instrument_drivers.Keysight import KeysightE4980A, KeysightE4980AMeasurements
            self.factory, self.cpd = KeysightE4980A, KeysightE4980AMeasurements.CPD
        self.meter = self.factory("portfolio_lcr", self.cfg.lcr_resource,
                                  timeout=self.cfg.visa_timeout_s)
        self.meter.measurement_function(self.cpd)
        self.meter.frequency(self.cfg.frequency_hz)
        self.meter.voltage_level(self.cfg.ac_voltage_v)
        self.meter.meas_time_mode("long")
        self.meter.averaging_rate(1)
        self.meter.write(":FORMat ASCii")
        self.meter.write(":INITiate:CONTinuous OFF")
        self.meter.write(":TRIGger:SOURce BUS")

    def read(self):
        self.meter.write(":INITiate:IMMediate")
        self.meter.write("*TRG")
        if self.meter.ask("*OPC?").strip() != "1":
            raise AcquisitionError("LCR completion was not acknowledged.")
        # The pinned driver's measurement property discards the third status field.
        # Read the same formatted result through its transport and keep that field.
        values = self.meter.ask(":FETCh:IMPedance:FORMatted?").split(",")
        if len(values) != 3:
            raise AcquisitionError("Unexpected E4980 result shape.")
        capacitance, dissipation, status = (float(v) for v in values)
        if not all(math.isfinite(v) for v in (capacitance, dissipation, status)) or status != 0:
            raise AcquisitionError(f"E4980 returned a non-normal measurement status: {status}.")
        return capacitance, dissipation

    def close(self):
        if self.meter is not None:
            self.meter.close()
            self.meter = None
