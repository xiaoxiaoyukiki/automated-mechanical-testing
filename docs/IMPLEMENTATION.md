# Implementation and source selection

The original local collection contained an older combined controller and newer QCoDeS force-step programs. The older combined version used an unresolved vendor binding, concurrent serial readers, unbounded force-target loops and cached readings after read failures. It was not selected as the runnable entry point.

The current organization adapts the newer program's direction-aware pulse concept and Mark-10/QCoDeS division into small modules. It adds a validated configuration object, a single acquisition owner, one deadline per force target, a separate stopped dwell, status-bearing logs, explicit simulation, output preservation and failure-path tests. Device communication and control timing were changed, so historical success of the source programs does not validate this refactor.

| File | Responsibility |
| --- | --- |
| `src/run_test.py` | CLI; simulation by default; explicit hardware mode |
| `src/testing_platform/configuration.py` | Settings and validation before I/O |
| `src/testing_platform/core.py` | Force-target pulses, dwell, logging and cleanup |
| `src/testing_platform/instruments.py` | Synthetic spring/LCR, F305 and QCoDeS adapters |
| `src/replay_measurement.py` | Historical measured-data visualization |
| `src/audit_measurement.py` | Non-destructive legacy-data audit |
| `src/plot_force_steps.py` | V2 output plots with required simulation/measurement labeling |
| `tests/test_acquisition.py` | Failure behavior and protocol-response tests with injected adapters |

The simulation, tests and interface organization were added during portfolio preparation. Bench validation of the revised acquisition workflow is pending.
