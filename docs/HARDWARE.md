# Hardware profile: F305 + 100 N sensor

## Recorded equipment

| Item | Current evidence |
| --- | --- |
| Test frame | Mark-10 F305, confirmed by the project owner |
| Force sensor | 100 N capacity, confirmed by the project owner; exact series/model pending |
| LCR meter | E4980A adapter recovered from existing bench scripts; exact connected unit pending |
| Serial interface | Port, baud setting, firmware and installed PC Control option pending bench verification |
| Computer | Offline checks were run on macOS; the historical bench dependency environment uses Python 3.9 |

The current serial profile targets the Series F ASCII PC Control interface described in the [manufacturer's Series F / EasyMESUR guide, section 10](https://mark-10.com/downloads/product-downloads/manualSeriesF-EasyMESUR.pdf). Support for the installed control panel/software variant has not been established. The guide describes PC Control as an optional function with its own connection/setup requirements.

## Command audit

The profile sends fixed-width command bytes without a line terminator and requires complete CR/LF replies. It uses `i` for mm, `l` for limit mode, `e0003.0` plus `o` for programmed speed, `d`/`u` for movement, and `s`/`p` for stop/report. It checks the force unit and normal load mode before acquisition. Report parsing is deliberately strict and still needs verification against actual replies.

Legacy comments incorrectly identified `c` as manual mode and `v` as a version query. The guide identifies them as cycle mode and upper-limit query; the new adapter does not use either. It does not zero the load/position or overwrite frame travel limits. Existing frame limits and physical limit switches must be checked on the actual setup.

## Before a bench run

Identify the installed interface, sensor subtype, exact response format, force polarity and travel origin. The controller assumes that downward movement increases positive compression force. Verify the physical setup and configure suitable specimen/fixture limits separately from the 100 N sensor capacity. The default 5 N cutoff is illustrative.

Copy `config/example.json` to ignored `config/local.json`; enter addresses and reviewed settings there. Set `hardware_profile_verified` to true only after the profile has actually been checked. The shipped configuration rejects hardware mode before opening a device.

```bash
python -m pip install -r requirements-hardware.txt
python src/run_test.py --mode hardware --config config/local.json --output outputs/bench_run.tsv
```

These commands are documentation for a future bench session; they were not executed here. QCoDeS/pySerial package imports were checked in the existing environment, while a new installation of the hardware stack was not tested. A working VISA backend and appropriate USB driver are separate requirements. See the [QCoDeS E4980A example](https://microsoft.github.io/Qcodes/examples/driver_examples/QCoDeS%20Example%20with%20Keysight%20E4980A%20LCR%20meter.html) and [pySerial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html).

## Stop behavior and limits

One thread owns the stand. Every force/displacement observation is checked; invalid readings abort rather than reusing old values. The runner attempts a stop and both device closes on success, failure and interruption, and records cleanup failures. Stop reporting is checked before each dwell. Blocking LCR reads occur during dwell, not during commanded motion.

Software checks are limited by serial/VISA calls, polling and the operating system. They are not an independent emergency stop or an established overshoot guarantee. The physical emergency stop and appropriate frame limits remain necessary. No automatic homing, zeroing or sample release is performed at the end of a run.
