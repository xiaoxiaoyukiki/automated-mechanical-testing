"""Single-owner acquisition loop. No instrument packages are imported here."""

import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path


class RunAborted(RuntimeError):
    pass


class LimitViolation(RuntimeError):
    pass


class AcquisitionError(RuntimeError):
    pass


class RealClock:
    now = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


class VirtualClock:
    """Advance simulated time without sleeping or accessing any devices."""

    def __init__(self):
        self.elapsed = 0.0

    def now(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += max(0.0, seconds)


FIELDS = [
    "cycle", "time_s", "force_N", "disp_mm", "cap_F", "diss_factor",
    "speed_mm_min", "phase", "branch", "target_force_N", "motion_command",
    "lcr_status", "lcr_start_s", "lcr_end_s", "force_after_N", "disp_after_mm",
    "stand_after_time_s",
]


class Acquisition:
    def __init__(self, settings, stand, meter, clock=None, abort_file=None):
        self.cfg = settings
        self.stand = stand
        self.meter = meter
        self.clock = clock or RealClock()
        self.abort_file = Path(abort_file) if abort_file else None
        self.rows = 0

    def check_abort(self):
        if self.abort_file and self.abort_file.exists():
            raise RunAborted("Abort file detected; it has not been deleted.")

    def reading(self):
        self.check_abort()
        force, displacement = self.stand.read()
        self.check_abort()
        if not math.isfinite(force) or not math.isfinite(displacement):
            raise AcquisitionError("Non-finite stand reading; no cached value will be substituted.")
        if abs(force) >= self.cfg.max_force_n:
            raise LimitViolation(f"Absolute force limit reached: {force:.6g} N.")
        if not self.cfg.min_displacement_mm < displacement < self.cfg.max_displacement_mm:
            raise LimitViolation(f"Displacement limit reached: {displacement:.6g} mm.")
        return force, displacement

    def log(self, reading, phase, **extra):
        row = dict(self.context)
        row.update(time_s=self.clock.now() - self.started, force_N=reading[0],
                   disp_mm=reading[1], speed_mm_min=self.stand.speed,
                   phase=phase, motion_command=self.stand.motion,
                   lcr_status="not_sampled")
        row.update(extra)
        self.writer.writerow(row)
        self.stream.flush()
        self.rows += 1

    def approach(self, target):
        deadline = self.clock.now() + self.cfg.step_timeout_s
        while True:
            if self.clock.now() >= deadline:
                raise TimeoutError(f"Force target {target:g} N was not reached in time.")
            current = self.reading()
            error = target - current[0]
            self.log(current, "approach")
            if abs(error) <= self.cfg.force_tolerance_n:
                self.stand.stop()
                return
            # Adapt the original bidirectional pulse idea, with a single overall deadline.
            scale = min(1.0, max(0.0, (abs(error) - self.cfg.force_tolerance_n) /
                                (self.cfg.full_pulse_error_n - self.cfg.force_tolerance_n)))
            duration = self.cfg.pulse_min_s + scale * (self.cfg.pulse_max_s - self.cfg.pulse_min_s)
            self.stand.set_speed(self.cfg.speed_mm_min)
            self.check_abort()
            if self.clock.now() >= deadline:
                raise TimeoutError("Target deadline elapsed before the next motion command.")
            self.stand.move(1 if error > 0 else -1)
            pulse_end = min(self.clock.now() + duration, deadline)
            try:
                while self.clock.now() < pulse_end:
                    self.clock.sleep(min(self.cfg.poll_s, pulse_end - self.clock.now()))
                    current = self.reading()
                    self.log(current, "approach")
                    new_error = target - current[0]
                    if abs(new_error) <= self.cfg.force_tolerance_n or error * new_error < 0:
                        break
            finally:
                self.stand.stop()
            self.clock.sleep(self.cfg.settle_s)

    def dwell(self):
        # Confirm a stop through the adapter before the potentially slow LCR call.
        self.stand.stop()
        deadline = self.clock.now() + self.cfg.dwell_s
        while True:
            before = self.reading()
            before_time = self.clock.now() - self.started
            lcr_start = self.clock.now() - self.started
            try:
                capacitance, dissipation = self.meter.read()
                if not math.isfinite(capacitance) or not math.isfinite(dissipation) or capacitance <= 0:
                    raise AcquisitionError("Expected finite positive capacitance and finite dissipation.")
            except Exception:
                self.log(before, "dwell", time_s=before_time, lcr_status="error",
                         lcr_start_s=lcr_start, lcr_end_s=self.clock.now() - self.started)
                raise
            lcr_end = self.clock.now() - self.started
            after = self.reading()
            self.log(before, "dwell", time_s=before_time, cap_F=capacitance,
                     diss_factor=dissipation, lcr_status="ok", lcr_start_s=lcr_start,
                     lcr_end_s=lcr_end, force_after_N=after[0], disp_after_mm=after[1],
                     stand_after_time_s=self.clock.now() - self.started)
            if self.clock.now() >= deadline:
                return
            self.clock.sleep(min(self.cfg.sample_interval_s, deadline - self.clock.now()))

    def run(self, output, mode="simulation"):
        if mode not in {"simulation", "hardware"}:
            raise ValueError("Unknown acquisition mode.")
        self.cfg.validate(hardware=mode == "hardware")
        if any(getattr(device, "simulated", None) != (mode == "simulation")
               for device in (self.stand, self.meter)):
            raise ValueError("Instrument adapters must match the selected acquisition mode.")
        output = Path(output)
        metadata_path = output.with_suffix(".json")
        if output == metadata_path:
            raise ValueError("The data output must not have a .json extension.")
        if output.exists() or metadata_path.exists():
            raise FileExistsError("Choose a new output stem; existing data/metadata will not be overwritten.")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.started = self.clock.now()
        self.context = {"cycle": 0, "branch": "preflight", "target_force_N": ""}
        metadata = {
            "schema_version": 2, "mode": mode,
            "synthetic": mode == "simulation",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "settings": self.cfg.to_dict(), "status": "running", "rows": 0,
            "timing": "Sequential stand/LCR observations, not hardware-triggered synchronization.",
            "shutdown_errors": [],
        }
        error = None
        with output.open("x", newline="", encoding="utf-8") as self.stream, metadata_path.open("x") as meta:
            meta.write(json.dumps(metadata, indent=2) + "\n")
            meta.flush()
            self.writer = csv.DictWriter(self.stream, fieldnames=FIELDS, delimiter="\t")
            self.writer.writeheader()
            try:
                self.check_abort()
                self.stand.open()
                self.stand.stop()
                self.reading()
                self.meter.open()
                for cycle in range(1, self.cfg.cycles + 1):
                    for branch, targets in (
                        ("load", self.cfg.targets_n),
                        ("unload", self.cfg.targets_n[-2::-1]),
                    ):
                        for target in targets:
                            self.context = {"cycle": cycle, "branch": branch, "target_force_N": target}
                            self.approach(target)
                            self.dwell()
                metadata["status"] = "completed"
            except BaseException as exc:
                error = exc
                metadata["status"] = "aborted" if isinstance(exc, (RunAborted, KeyboardInterrupt)) else "failed"
                metadata["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                # Attempt every cleanup action, even if an earlier stop/close fails.
                for label, action in (("stop", self.stand.stop), ("stand_close", self.stand.close),
                                      ("meter_close", self.meter.close)):
                    try:
                        action()
                    except BaseException as exc:
                        metadata["shutdown_errors"].append(f"{label}: {type(exc).__name__}: {exc}")
                if metadata["shutdown_errors"] and error is None:
                    metadata["status"] = "shutdown_error"
                    error = AcquisitionError("Cleanup failed; inspect run metadata.")
                metadata.update(rows=self.rows, elapsed_s=self.clock.now() - self.started)
                meta.seek(0)
                json.dump(metadata, meta, indent=2, allow_nan=False)
                meta.write("\n")
                meta.truncate()
        if error is not None:
            raise error
        return metadata
