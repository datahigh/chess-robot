# Phase 1 — Single-Actuator Bring-Up Kit (wrist-class joint)

Everything needed to build, configure, calibrate, tune, and **prove** ONE joint of the arm before
replicating it across all six (Phase 2). This is the *least-risky-first* joint: a **wrist-class
joint** (the J5 wrist-pitch / J6 wrist-roll class) — small gimbal BLDC, low torque, **single-stage
~9:1 cycloidal reducer**, minimal stored energy, run isolated on the bench.

## Locked decisions for this joint

| Item | Choice | Why |
|---|---|---|
| Joint | Wrist-class (J5/J6) bench joint | Least-risky first: low torque, low ratio, little stored energy |
| Motor | Gimbal BLDC (GB2208 / GBM2804 class) | High pole count, low Kv; torque is tiny (pieces weigh grams) and the 9:1 multiplies it |
| Controller | **moteus-c1** over **mjcanfd-usb-1x** (CAN-FD) | fdcanusb successor (discontinued); same JST-PH3 pinout |
| Reduction | 3D-printed **~9:1** single-stage cycloidal | `rotor_to_output_ratio = 1/9 = 0.111111` (output-per-rotor) |
| Commutation source | **onboard** encoder (aux1), `sources.0`, rotor-referenced | FOC must commutate off the rotor, never the geared output |
| Output position source | **AS5047P** (14-bit SPI) on **aux2**, `sources.1`, output-referenced | Absolute joint angle after the gearbox → homing-free across power cycles |
| Limits | `max_current_A 2.0`, `servopos ±0.2 rev (±72°)`, watchdog 0.5 s | Deliberately conservative for a low-torque bench joint |

## File map

```
hardware/joint_bringup/
├── README.md                  ← you are here (run order + acceptance gate)
├── BOM_single_joint.md        single-joint bill of materials (India sourcing + import-first priority)
├── wiring.md                  ASCII wiring diagram, AUX2↔AS5047P SPI pin table, CAN/term, power-on + E-stop checklist
├── config/
│   └── wrist_joint.cfg         moteus_tool --restore-config file (gear ratio, AS5047P-on-aux2, conservative limits)
├── moteus_joint_config.md     prose: every register in the .cfg, conventions, the commutation/output split
├── calibration_and_tuning.md  ordered bench procedure (connect → calibrate → apply cfg → zero → tune → verify)
└── bringup/
    ├── requirements.txt        moteus 1.0.0 (pulls python-can, aioserial)
    ├── connect_check.py        connect + query mode/fault/position/temp (no motion)
    ├── configure_joint.py      apply wrist_joint.cfg via moteus_tool --restore-config
    └── step_repeatability_test.py   ACCEPTANCE test (accuracy / repeatability / backlash → PASS/FAIL)
```

## What to do NOW (no hardware required)

1. **Tooling is installed** — `moteus` 1.0.0 (lib + `moteus_tool`) is on this box. (Re-create with
   `pip install --user --break-system-packages -r bringup/requirements.txt`.)
2. **Order the BOM** — see [`BOM_single_joint.md`](BOM_single_joint.md). Import the long-lead items
   first (moteus-c1, mjcanfd-usb-1x, JST-PH3 terminator(s), and the GH-7 AUX2 connector via
   DigiKey/Mouser); the
   India-local parts (gimbal motor, AS5047P + diametric magnet, 24 V PSU, NC E-stop, PETG) in
   parallel.
3. **Print the ~9:1 cycloidal reducer** — reference CAD (Faze4 / OpenCyRe / Skyentific) per the BOM.
4. **Dry-run the scripts** — they import and run their no-device modes cleanly:
   ```
   python3 bringup/configure_joint.py --dry-run
   python3 bringup/step_repeatability_test.py --plan-only --min-deg -30 --max-deg 30
   ```

## Bring-up run order (once wired)

Follow [`wiring.md`](wiring.md) **§ Safe power-on order + E-stop checklist** first (power applied
last; E-stop in the +24 V rail), then [`calibration_and_tuning.md`](calibration_and_tuning.md):

1. **Connect / query** — `python3 bringup/connect_check.py` (or `moteus_tool -i`). Assign `id.id`.
2. **Sanity-check the AS5047P before commutating** — hand-rotate the OUTPUT shaft, confirm a clean
   0→1 rev sweep, no dropouts.
3. **Calibrate the motor** — `moteus_tool --calibrate --cal-motor-poles <N> --cal-motor-power 2`
   (gimbal motor; keep the joint free / current-limited). Writes `motor.poles`, current loop,
   commutation offset/sign — **not** the position loop.
4. **Apply the joint config** — `python3 bringup/configure_joint.py`
   **(must be AFTER `--calibrate`** — `--calibrate` clobbers `sources.1.pll_filter_hz`; applying the
   cfg afterward restores the 10 Hz absolute-encoder low-pass).
5. **Mount the magnet, verify direction, zero the output** — `moteus_tool --zero-offset`; reverse
   direction with `sources.1.sign` if needed (not `output.sign`).
6. **Tune the position loop** by hand in tview — `servo.pid_position.kp` low → stiff → back off ~30%,
   add `kd`, add `ki` only for residual error.
7. **Run the acceptance test** (below).

## Acceptance gate — when is this joint "done"?

Run the acceptance test and require **PASS** before replicating the design for Phase 2:

```
python3 bringup/step_repeatability_test.py --target 1 \
    --min-deg -30 --max-deg 30 --steps 5 --repeats 4 \
    --repeatability-deg 0.5 --accuracy-deg 1.0 --csv wrist_accept.csv
```

**PASS criteria** (starting thresholds — tighten as the mechanism improves):
- **Repeatability** (spread of repeated visits to the same target) **≤ 0.5° at the output shaft.**
- **Accuracy** (settled vs commanded, mean) **|error| ≤ 1.0°.**
- **Backlash** (approach-from-below vs approach-from-above) is **reported** and tracked; it informs
  gear/compensation work and does not by itself fail the run unless `--fail-on-backlash` is set.

Rationale: the gripper (compliant Fin-Ray) tolerates a few mm at the TCP over a 57 mm square. A
0.5° error at the short wrist lever (~170 mm) is ~1.5 mm; this is the per-joint budget that, stacked
across six joints and the planner, must still center a piece. Refine the numbers once the full-arm
error budget is measured in Phase 2.

The test logs commanded vs measured (AS5047P-backed) output position to CSV and prints per-target
stats so repeatability/backlash trends are visible across tuning iterations.

## Caveats / hardware-blocked TODOs

- **CAN adapter — `mjcanfd-usb-1x` (fdcanusb successor):** the fdcanusb is discontinued; we use the
  mjcanfd-usb-1x (same JST-PH3 moteus pinout, USB-C). The moteus python transport is still
  `moteus.Fdcanusb` — that's the fdcanusb *protocol*, which the mjcanfd-usb-1x speaks in its USB-CDC
  (virtual-serial) mode, so the bring-up scripts run **unchanged**; socketcan
  (`moteus.PythonCan` / `moteus_tool --can-iface`) is the alternative. The adapter enumerates as
  `/dev/ttyACM*` (not `/dev/fdcanusb`). VERIFY whether it integrates host-end CAN termination (the
  fdcanusb did); if not, add a 2nd JST-PH3 terminator.
- **WSL2:** the adapter does **not** appear until `usbipd attach --busid <id> --wsl` is run from
  Windows; then it enumerates as `/dev/ttyACM*`. On the deployment **Raspberry
  Pi 5** it enumerates natively — no usbipd. All scripts import/parse with **no** device present and
  fail fast (exit 2) with a clear message on a live run when none is attached.
- **Cannot be finalized until parts arrive (marked TODO in the files):**
  - exact gimbal-motor SKU → `--cal-motor-poles N`;
  - as-built cycloidal ratio → `rotor_to_output_ratio = 1/N`;
  - the AUX2 A/B/C/D → SCK/MISO/MOSI/CS pin mapping and the CAN PH-3 silk order — **meter against
    the moteus-c1 rendered-pinout SVG before crimping** (research-derived, not officially published);
  - `motor_position.output.source` index — read from a live `--dump-config` once the source is added;
  - `output.offset` (joint zero) → set via `--zero-offset` after mounting;
  - `servopos.position_min/max` → set to the real mechanical sweep (and update
    `--servopos-limit-deg` in the acceptance test to match);
  - position-loop gains → hand-tuned in tview.

## Next (after this joint passes)

Phase 2 — replicate across all six joints on the CAN-FD bus and bring up the custom
`ros2_control` hardware_interface (sim and real share the MoveIt2 stack already validated in Phase 0).
