"""Report legacy zero/non-finite records without changing the source data."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def audit(path):
    phases = defaultdict(Counter)
    cycles = defaultdict(list)
    totals = Counter()
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            phase = row["phase"]
            cap, diss = float(row["cap_F"]), float(row["diss_factor"])
            force, disp = float(row["force_N"]), float(row["disp_mm"])
            flags = {"rows": True, "zero_capacitance": cap == 0,
                     "paired_zero_capacitance_and_dissipation": cap == 0 and diss == 0,
                     "nonfinite": not all(math.isfinite(v) for v in (cap, diss, force, disp))}
            for key, value in flags.items():
                totals[key] += int(value)
                phases[phase][key] += int(value)
            cycles[int(row["cycle"])].append(float(row["time_s"]))
    return {
        "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "totals": dict(totals), "by_phase": {k: dict(v) for k, v in sorted(phases.items())},
        "by_cycle": {str(k): {"rows": len(v), "first_time_s": v[0], "last_time_s": v[-1],
                               "time_reversals_within_cycle": sum(b < a for a, b in zip(v, v[1:]))}
                     for k, v in sorted(cycles.items())},
        "interpretation": "Paired zeros are observed, but their meaning is not encoded in this legacy schema. Do not infer sensor failure or zero capacitance without the originating acquisition implementation.",
        "data_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["totals"], indent=2))


if __name__ == "__main__":
    main()
