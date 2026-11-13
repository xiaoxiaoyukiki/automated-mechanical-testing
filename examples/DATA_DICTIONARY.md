# Example data

[simulated_force_steps.tsv](simulated_force_steps.tsv) and its [JSON metadata](simulated_force_steps.json) show two simulated loading and unloading cycles. The metadata identifies the run as synthetic. See the [acquisition schema](../docs/ACQUISITION_SCHEMA.md) for fields, units and measurement statuses.

## Reviewing a historical log locally

The replay and audit utilities accept an eight-column tab-separated log. Supply your own file.

| Column | Recorded meaning and unit |
| --- | --- |
| cycle | Cycle identifier |
| time_s | Elapsed time within a cycle in seconds |
| force_N | Force in N |
| disp_mm | Displacement in mm |
| cap_F | Capacitance in F |
| diss_factor | Dimensionless dissipation factor |
| speed_mm_min | Stand speed in mm/min |
| phase | Recorded motion phase |

```bash
python src/replay_measurement.py --input outputs/historical.tsv --output outputs/historical_replay.png
python src/audit_measurement.py --input outputs/historical.tsv --output outputs/legacy_audit.json
```

The audit counts zero and nonfinite readings. The replay omits zero-capacitance rows and reports the exclusion count. Check the acquisition software for the original meaning of zero values.
