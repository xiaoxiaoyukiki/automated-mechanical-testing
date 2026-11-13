# Acquisition schema v2

New force-step output is separate from the historical eight-column excerpt. A run writes a tab-separated data file and a same-stem JSON metadata file. Existing files are not overwritten. The sidecar identifies `mode`, `synthetic`, settings, completion/abort/failure status and cleanup errors.

| Field | Meaning |
| --- | --- |
| cycle | One-based cycle number |
| time_s | Monotonic elapsed run time at the first stand observation |
| force_N / disp_mm | Force and displacement before the LCR observation, in N / mm |
| cap_F / diss_factor | Capacitance in F and dimensionless dissipation; blank if not sampled or failed |
| speed_mm_min | Most recently commanded speed; not a measured velocity |
| phase | `approach` or `dwell` |
| branch | `load` or `unload` |
| target_force_N | Requested force target; actual force can relax after motion stops |
| motion_command | Adapter's last motion state or reported stop; not independently measured position/velocity |
| lcr_status | `not_sampled`, `ok` or `error` |
| lcr_start_s / lcr_end_s | Host timestamps bracketing the LCR operation |
| force_after_N / disp_after_mm | Stand readings after a successful LCR observation |
| stand_after_time_s | Time of that second stand observation |

Approach rows do not make LCR calls: capacitance/dissipation are blank and status is `not_sampled`. Dwell stops the crosshead before measuring. Acquisition errors produce an `error` row when possible and abort the run; they are not encoded as a valid zero capacitance. This positive-capacitance workflow also rejects nonpositive and nonfinite LCR results.

The LCR adapter uses an explicitly initiated bus-triggered measurement, waits for completion, and retains the formatted result's status field. Trigger behavior, status semantics, command support and actual timing remain part of bench validation. Software timestamps describe observation order, not a synchronized sensor sample or the instrument's internal integration interval.

The illustrative simulation uses a 10 N/mm unilateral spring and `C = (5.8 + 0.1 F_N) pF`, with fixed dissipation 0.003. These arbitrary model parameters are not measured sensor properties. Synthetic outputs must keep their JSON sidecar and simulation labeling when plotted or shared.
