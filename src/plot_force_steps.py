"""Plot schema-v2 acquisition output while preserving its simulation label."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(args.input.with_suffix(".json").read_text())
    if metadata.get("schema_version") != 2 or not isinstance(metadata.get("synthetic"), bool):
        raise ValueError("A schema-v2 run metadata file with an explicit synthetic flag is required.")
    with args.input.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for cycle in sorted({int(r["cycle"]) for r in rows if int(r["cycle"]) > 0}):
        group = [r for r in rows if int(r["cycle"]) == cycle]
        line, = axes[0].plot([float(r["time_s"]) for r in group],
                             [float(r["force_N"]) for r in group], label=f"Cycle {cycle}")
        for branch, marker in (("load", "o"), ("unload", "x")):
            dwell = [r for r in group if r["branch"] == branch and r["lcr_status"] == "ok"]
            axes[1].scatter([float(r["force_N"]) for r in dwell],
                            [float(r["cap_F"]) * 1e12 for r in dwell],
                            color=line.get_color(), marker=marker, s=20,
                            label=f"Cycle {cycle}, {branch}")
    axes[0].set(xlabel="Elapsed time (s)", ylabel="Force (N)")
    axes[1].set(xlabel="Force before LCR read (N)", ylabel="Capacitance (pF)")
    for axis in axes:
        axis.legend(frameon=False, fontsize=8)
        axis.spines[["top", "right"]].set_visible(False)
    title = "SIMULATION: illustrative spring/capacitance model" if metadata["synthetic"] else "Recorded force-step run"
    fig.suptitle(title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
