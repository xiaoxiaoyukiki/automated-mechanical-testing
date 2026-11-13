"""Plot an existing measurement log without importing instrument-control code."""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if not rows:
        raise ValueError("The measurement file has no rows.")

    valid = []
    zero_count = 0
    nonfinite_count = 0
    for row in rows:
        values = [float(row[key]) for key in ("time_s", "force_N", "cap_F")]
        if not all(math.isfinite(value) for value in values):
            nonfinite_count += 1
            continue
        if values[2] == 0:
            zero_count += 1
            continue
        valid.append((int(row["cycle"]), *values, row["phase"]))
    if not valid:
        raise ValueError("No finite, nonzero-capacitance rows are available.")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for cycle in sorted({row[0] for row in valid}):
        group = [row for row in valid if row[0] == cycle]
        axes[0].plot(
            [row[1] for row in group],
            [row[3] * 1e12 for row in group],
            linewidth=0.8,
            label=f"Cycle {cycle}",
        )
        loading = [row for row in group if row[4] == "precision_down"]
        axes[1].plot(
            [row[2] for row in loading],
            [row[3] * 1e12 for row in loading],
            linewidth=0.8,
            label=f"Cycle {cycle}",
        )
    axes[0].set(xlabel="Recorded elapsed time (s)", ylabel="Capacitance (pF)")
    axes[1].set(xlabel="Force (N)", ylabel="Capacitance (pF)")
    axes[0].set_title("Measured data replay")
    axes[1].set_title("Recorded precision-down phase")
    for axis in axes:
        axis.legend(frameon=False)
        axis.spines[["top", "right"]].set_visible(False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    summary = {
        "input": args.input.as_posix(),
        "rows": len(rows),
        "plotted_rows": len(valid),
        "excluded_zero_capacitance_rows": zero_count,
        "excluded_nonfinite_rows": nonfinite_count,
        "cycles": sorted({row[0] for row in valid}),
        "processing": "No smoothing, peak rescaling, time warping or resampling.",
        "hardware_access": False,
    }
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
