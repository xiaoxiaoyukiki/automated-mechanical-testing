"""Experiment settings expressed in explicit engineering units."""

import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class Settings:
    targets_n: Tuple[float, ...] = (0.0, 0.5, 1.0, 2.0)
    cycles: int = 2
    force_tolerance_n: float = 0.05
    sensor_capacity_n: float = 100.0
    max_force_n: float = 5.0
    min_displacement_mm: float = -0.5
    max_displacement_mm: float = 8.0
    speed_mm_min: float = 3.0
    max_speed_mm_min: float = 3.0
    pulse_min_s: float = 0.04
    pulse_max_s: float = 0.25
    full_pulse_error_n: float = 0.5
    poll_s: float = 0.02
    settle_s: float = 0.05
    dwell_s: float = 0.2
    sample_interval_s: float = 0.05
    step_timeout_s: float = 120.0
    serial_timeout_s: float = 0.5
    visa_timeout_s: float = 3.0
    command_gap_s: float = 0.03
    frequency_hz: float = 1000.0
    ac_voltage_v: float = 1.0
    stand_model: str = "Mark-10 F305"
    sensor_model: Optional[str] = None
    mark10_port: Optional[str] = None
    lcr_resource: Optional[str] = None
    baud_rate: int = 115200
    hardware_profile_verified: bool = False

    def validate(self, hardware=False):
        numeric = [f.name for f in fields(self) if f.name not in {
            "targets_n", "cycles", "stand_model", "sensor_model", "mark10_port",
            "lcr_resource", "baud_rate", "hardware_profile_verified",
        }]
        for name in numeric:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        for name in ("cycles", "baud_rate"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if not isinstance(self.hardware_profile_verified, bool):
            raise ValueError("hardware_profile_verified must be a JSON boolean.")
        if len(self.targets_n) < 2:
            raise ValueError("Provide at least two strictly increasing loading targets.")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in self.targets_n):
            raise ValueError("Force targets must be finite numbers.")
        if self.targets_n[0] < 0 or any(a >= b for a, b in zip(self.targets_n, self.targets_n[1:])):
            raise ValueError("Targets must be nonnegative and strictly increasing.")
        positive = [name for name in numeric if name not in {"min_displacement_mm", "max_displacement_mm"}]
        if any(getattr(self, name) <= 0 for name in positive):
            raise ValueError("Timing, load, speed and signal settings must be positive.")
        if not self.targets_n[-1] + self.force_tolerance_n < self.max_force_n < self.sensor_capacity_n:
            raise ValueError("Targets plus tolerance must be below max_force_n, below sensor capacity.")
        if self.min_displacement_mm >= self.max_displacement_mm:
            raise ValueError("Displacement limits are not ordered.")
        if self.speed_mm_min > self.max_speed_mm_min or self.speed_mm_min < 0.1:
            raise ValueError("Speed must be at least 0.1 mm/min and within its configured limit.")
        if self.pulse_min_s > self.pulse_max_s or self.poll_s > self.pulse_max_s:
            raise ValueError("Pulse timing settings are inconsistent.")
        if self.full_pulse_error_n <= self.force_tolerance_n:
            raise ValueError("full_pulse_error_n must exceed force_tolerance_n.")
        if self.speed_mm_min != round(self.speed_mm_min, 1):
            raise ValueError("The Series F speed command uses one decimal place.")
        if hardware:
            if not self.hardware_profile_verified:
                raise ValueError("The installed F305 control option and hardware profile are not verified.")
            if not self.mark10_port or not self.lcr_resource:
                raise ValueError("Hardware mode needs a serial port and VISA resource in a local configuration.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def load(cls, path):
        values = json.loads(Path(path).read_text())
        if "targets_n" in values:
            values["targets_n"] = tuple(values["targets_n"])
        settings = cls(**values)
        settings.validate()
        return settings
