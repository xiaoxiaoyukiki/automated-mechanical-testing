# Validation record

Date: 2026-11-04. No physical instrument was opened, controlled or moved.

## Executed checks

- 22 tests passed on Python 3.13.5 and on the existing Python 3.9 bench environment.
- The default synthetic run completed two load/unload cycles and wrote 991 data rows plus metadata.
- A new isolated Python 3.13.5 environment successfully installed `requirements.txt` and ran acquisition simulation, plotting and historical-data replay.
- The new environment resolved Matplotlib 3.9.4, NumPy 2.5.4 and Pillow 13.0.0. These are observations from this installation, not a universal dependency lock.

## Failure behavior exercised

Tests inject nonfinite force, overload, travel-limit violation, a stuck force target, LCR disconnect, partial startup failure, keyboard interruption, an existing/mid-run abort file, stop-command failure, truncated/error serial replies and a non-normal LCR status. They verify stopped simulated motion, resource closure, retained errors and preservation of existing output. Another check prevents a real adapter from being used under a simulation label.

## What these results establish

They validate software behavior with simulated or injected responses and demonstrate the offline installation/run commands. They do not establish physical stopping distance, loop bandwidth, force-control accuracy, true sampling rate, calibration, serial response compatibility or LCR trigger compatibility on the bench. Hardware dependencies were imported in the existing environment; installing the complete hardware stack in a new environment was not tested.

The F305 and 100 N capacity were confirmed by the project owner. The exact sensor subtype, installed control option, firmware and actual test-stand photograph are pending. Bench validation is pending.

## Initial release check on 2026-11-13

A clean copy of the staged files passed all 22 tests, generated 991 simulated records and rendered the demonstration plot. The offline environment also passed the dependency check.
