"""Run a synthetic force-step demo by default; hardware requires explicit configuration."""

import argparse
import json
import sys
from pathlib import Path

from testing_platform.configuration import Settings
from testing_platform.core import Acquisition, RealClock, RunAborted, VirtualClock
from testing_platform.instruments import E4980QCodes, F305Serial, SimulatedLCR, SimulatedStand


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/example.json")
    parser.add_argument("--mode", choices=("simulation", "hardware"), default="simulation")
    parser.add_argument("--output", type=Path, required=True, help="New TSV path; existing files are never replaced.")
    parser.add_argument("--abort-file", type=Path, default=Path("ABORT"),
                        help="Stop when this file exists (default: ABORT); stale files are not removed.")
    args = parser.parse_args()
    try:
        cfg = Settings.load(args.config)
        cfg.validate(hardware=args.mode == "hardware")
        clock = VirtualClock() if args.mode == "simulation" else RealClock()
        if args.mode == "simulation":
            stand = SimulatedStand(clock)
            meter = SimulatedLCR(stand, clock)
        else:
            stand = F305Serial(cfg, clock)
            meter = E4980QCodes(cfg)
        result = Acquisition(cfg, stand, meter, clock, args.abort_file).run(args.output, args.mode)
        print(json.dumps({"status": result["status"], "mode": args.mode,
                          "synthetic": result["synthetic"], "rows": result["rows"],
                          "output": str(args.output)}, indent=2))
        return 0
    except (KeyboardInterrupt, RunAborted) as exc:
        print(f"Run aborted: {exc}", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
