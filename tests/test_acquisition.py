import csv
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from testing_platform.configuration import Settings
from testing_platform.core import Acquisition, AcquisitionError, LimitViolation, RunAborted, VirtualClock
from testing_platform.instruments import E4980QCodes, F305Serial, SimulatedLCR, SimulatedStand, parse_reading


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run.tsv"
        self.cfg = replace(Settings(), cycles=1, targets_n=(0.0, 0.2, 0.4), dwell_s=0.03)
        self.clock = VirtualClock()
        self.stand = SimulatedStand(self.clock)
        self.meter = SimulatedLCR(self.stand, self.clock)

    def run_engine(self, **kwargs):
        return Acquisition(self.cfg, self.stand, self.meter, self.clock, **kwargs).run(self.output)

    def metadata(self):
        return json.loads(self.output.with_suffix(".json").read_text())

    def assert_closed(self):
        self.assertEqual(self.stand.direction, 0)
        self.assertTrue(self.stand.closed)
        self.assertTrue(self.meter.closed)

    def test_complete_cycle_has_distinct_missing_and_valid_measurements(self):
        result = self.run_engine()
        with self.output.open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["synthetic"])
        self.assertEqual({r["branch"] for r in rows}, {"load", "unload"})
        self.assertTrue(any(r["lcr_status"] == "not_sampled" for r in rows))
        self.assertTrue(any(r["lcr_status"] == "ok" for r in rows))
        for row in rows:
            if row["lcr_status"] == "not_sampled":
                self.assertEqual(row["cap_F"], "")
            else:
                self.assertGreater(float(row["cap_F"]), 0)
                self.assertEqual(row["motion_command"], "STOP")
                self.assertLessEqual(float(row["lcr_start_s"]), float(row["lcr_end_s"]))
                self.assertLessEqual(float(row["lcr_end_s"]), float(row["stand_after_time_s"]))
        self.assert_closed()

    def test_preexisting_abort_file_prevents_open_and_is_preserved(self):
        abort = Path(self.temp.name) / "ABORT"
        abort.touch()
        with self.assertRaises(RunAborted):
            self.run_engine(abort_file=abort)
        self.assertTrue(abort.exists())
        self.assertFalse(self.stand.opened)
        self.assertEqual(self.metadata()["status"], "aborted")
        self.assert_closed()

    def test_abort_during_motion_stops_and_closes(self):
        abort = Path(self.temp.name) / "ABORT"
        original = self.stand.read

        def read():
            result = original()
            if self.stand.direction:
                abort.touch()
            return result

        self.stand.read = read
        with self.assertRaises(RunAborted):
            self.run_engine(abort_file=abort)
        self.assertEqual(self.metadata()["status"], "aborted")
        self.assert_closed()

    def test_nonfinite_force_never_reuses_previous_value(self):
        self.stand.read = lambda: (float("nan"), 0.0)
        with self.assertRaises(AcquisitionError):
            self.run_engine()
        self.assertEqual(self.metadata()["status"], "failed")
        self.assert_closed()

    def test_force_limit_during_motion_stops_and_closes(self):
        original = self.stand.read
        self.stand.read = lambda: (6.0, 0.1) if self.stand.direction else original()
        with self.assertRaises(LimitViolation):
            self.run_engine()
        self.assert_closed()

    def test_travel_limit_stops_without_finishing_pulse(self):
        self.cfg = replace(self.cfg, max_displacement_mm=0.005)
        with self.assertRaises(LimitViolation):
            self.run_engine()
        self.assert_closed()

    def test_unreachable_target_has_overall_timeout(self):
        self.cfg = replace(self.cfg, step_timeout_s=0.2)
        self.stand.read = lambda: (0.0, 0.0)
        with self.assertRaises(TimeoutError):
            self.run_engine()
        self.assertEqual(self.metadata()["status"], "failed")
        self.assert_closed()

    def test_lcr_error_occurs_at_rest_and_does_not_log_zero(self):
        def fail():
            self.assertEqual(self.stand.direction, 0)
            raise OSError("Injected LCR disconnect")

        self.meter.read = fail
        with self.assertRaises(OSError):
            self.run_engine()
        with self.output.open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(rows[-1]["lcr_status"], "error")
        self.assertEqual(rows[-1]["cap_F"], "")
        self.assert_closed()

    def test_keyboard_interrupt_in_read_still_closes_both_devices(self):
        def interrupt():
            raise KeyboardInterrupt()

        self.stand.read = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_engine()
        self.assertEqual(self.metadata()["status"], "aborted")
        self.assert_closed()

    def test_zero_lcr_result_is_an_error_with_blank_data(self):
        self.meter.read = lambda: (0.0, 0.0)
        with self.assertRaises(AcquisitionError):
            self.run_engine()
        with self.output.open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(rows[-1]["lcr_status"], "error")
        self.assertEqual(rows[-1]["cap_F"], "")
        self.assert_closed()

    def test_partial_startup_failure_still_closes_both_devices(self):
        def fail():
            raise OSError("Injected VISA connection error")

        self.meter.open = fail
        with self.assertRaises(OSError):
            self.run_engine()
        self.assert_closed()

    def test_stop_failure_does_not_skip_close_actions(self):
        def fail():
            raise OSError("Injected stop transport failure")

        self.stand.stop = fail
        with self.assertRaises(OSError):
            self.run_engine()
        self.assertTrue(self.stand.closed)
        self.assertTrue(self.meter.closed)
        self.assertTrue(self.metadata()["shutdown_errors"])

    def test_existing_output_and_metadata_are_not_replaced(self):
        self.output.write_text("Preserve this file")
        with self.assertRaises(FileExistsError):
            self.run_engine()
        self.assertEqual(self.output.read_text(), "Preserve this file")
        self.assertFalse(self.stand.opened)

    def test_existing_metadata_prevents_device_open(self):
        self.output.with_suffix(".json").write_text("{}")
        with self.assertRaises(FileExistsError):
            self.run_engine()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.stand.opened)

    def test_invalid_target_is_rejected_before_device_open(self):
        self.cfg = replace(self.cfg, targets_n=(0.0, 6.0))
        with self.assertRaises(ValueError):
            self.run_engine()
        self.assertFalse(self.stand.opened)

    def test_default_config_cannot_open_hardware(self):
        engine = Acquisition(self.cfg, self.stand, self.meter, self.clock)
        with self.assertRaises(ValueError):
            engine.run(self.output, mode="hardware")
        self.assertFalse(self.stand.opened)

    def test_simulation_mode_rejects_a_real_adapter_before_open(self):
        stand = F305Serial(self.cfg, self.clock)
        engine = Acquisition(self.cfg, stand, self.meter, self.clock)
        with self.assertRaises(ValueError):
            engine.run(self.output)
        self.assertIsNone(stand.connection)
        self.assertFalse(self.output.exists())


class AdapterTests(unittest.TestCase):
    def test_f305_initialization_preserves_limits_and_uses_limit_mode(self):
        class Serial:
            def __init__(self): self.writes = []
            def reset_input_buffer(self): pass
            def write(self, value):
                self.writes.append(value)
                return len(value)
            def read_until(self, *args, **kwargs):
                return {b"p": b"SL\r\n", b"A": b"N\r\n", b"S": b"Normal\r\n"}[self.writes[-1]]
        serial = Serial()
        stand = F305Serial(Settings(), VirtualClock(), serial_factory=lambda *args, **kwargs: serial)
        stand.open()
        self.assertEqual(serial.writes, [b"s", b"p", b"i", b"l", b"p", b"A", b"S"])
        self.assertFalse(any(cmd[:1] in (b"g", b"h", b"R", b"z", b"c", b"v") for cmd in serial.writes))

    def test_error_codes_and_wrong_units_cannot_be_parsed_as_force(self):
        for response in ("*10", "OVER", "nan", "10 mm", "1 N extra", "1e999 N"):
            with self.subTest(response=response), self.assertRaises(AcquisitionError):
                parse_reading(response, "N")
        self.assertEqual(parse_reading("+1.25 N", "N"), 1.25)

    def test_serial_uses_fixed_width_commands_and_rejects_unconfirmed_stop(self):
        class Serial:
            def __init__(self):
                self.writes = []
                self.reply = b"SL\r\n"
            def write(self, value):
                self.writes.append(value)
                return len(value)
            def reset_input_buffer(self):
                pass
            def read_until(self, *args, **kwargs):
                return self.reply

        serial = Serial()
        stand = F305Serial(Settings(), VirtualClock())
        stand.connection = serial
        stand.set_speed(3.0)
        stand.stop()
        self.assertEqual(serial.writes, [b"e0003.0", b"o", b"s", b"p"])
        serial.reply = b"DL\r\n"
        with self.assertRaises(AcquisitionError):
            stand.stop()
        self.assertEqual(stand.motion, "STOP_REQUESTED")

    def test_serial_timeout_does_not_accept_partial_numeric_value(self):
        class Serial:
            def write(self, data): return len(data)
            def reset_input_buffer(self): pass
            def read_until(self, *args, **kwargs): return b"1.0"
        stand = F305Serial(Settings(), VirtualClock())
        stand.connection = Serial()
        with self.assertRaises(AcquisitionError):
            stand.read()

    def test_lcr_status_field_is_checked_instead_of_discarded(self):
        class Meter:
            def __init__(self):
                self.writes = []
                self.status = 1
            def write(self, value): self.writes.append(value)
            def ask(self, query):
                return "1" if query == "*OPC?" else f"6e-12,0.003,{self.status}"
        adapter = E4980QCodes(Settings())
        adapter.meter = Meter()
        with self.assertRaises(AcquisitionError):
            adapter.read()
        adapter.meter.status = 0
        self.assertEqual(adapter.read(), (6e-12, 0.003))
        self.assertEqual(adapter.meter.writes[:2], [":INITiate:IMMediate", "*TRG"])


if __name__ == "__main__":
    unittest.main()
