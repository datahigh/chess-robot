# Phase-1 wrist joint — bench calibration & tuning procedure

Ordered bench procedure to bring up **one** wrist-class joint: gimbal BLDC +
single-stage **~9:1** cycloidal, onboard encoder (aux1) for commutation, external
**AS5047P on aux2** as the absolute output source.

Every command and register here comes from the moteus 1.0.0 docs/research and the
installed `moteus_tool.py`. **TODO** marks anything that can only be finalized once
hardware is wired/mounted.

> **Prereqs.** moteus python 1.0.0 is installed (lib + `moteus_tool`).
> Config file: [`config/wrist_joint.cfg`](config/wrist_joint.cfg);
> register prose: [`moteus_joint_config.md`](moteus_joint_config.md).
> Helper scripts live in [`bringup/`](bringup/): `connect_check.py` (query),
> `configure_joint.py` (apply config). **TODO:** these helper scripts are authored
> separately; if absent, the equivalent raw `moteus_tool` command is given inline
> at each step.

---

## Safety preamble

- This is a **low-torque** joint — keep `servo.max_current_A` low (2.0 A in the
  cfg). Do not raise it to "fix" a tuning problem; fix the tune.
- A hardware **E-stop** on the motor bus is assumed. `d stop` halts the joint from
  tview; the per-command watchdog (`servo.default_timeout_s` / `timeout_mode 0`)
  unpowers it if CAN traffic drops.
- During `--calibrate` the motor spins **open-loop** and must be **completely
  free** (see step 2).

---

## Step 0 — (WSL2 only) attach the mjcanfd-usb-1x

On WSL2 the mjcanfd-usb-1x (fdcanusb successor) is not visible until it is forwarded from Windows:

```powershell
# Windows host (PowerShell, admin):
usbipd list                      # find the mjcanfd-usb-1x busid
usbipd attach --wsl --busid <id> # forward it into WSL2
```

Then in WSL2 confirm `/dev/ttyACM*` exists. (The moteus transport is still `moteus.Fdcanusb` — the
fdcanusb *protocol* — which the mjcanfd-usb-1x speaks in virtual-serial mode, so the scripts and
`moteus_tool` work unchanged; socketcan via `--can-iface` is the alt.) On the eventual
**Raspberry Pi 5** the adapter is native — no attach. With **no device attached**
the scripts still import/parse cleanly (moteus 1.0.0 installed); only live
`--target` calls fail to find a transport.

---

## Step 1 — Connect and query

```
python3 hardware/joint_bringup/bringup/connect_check.py        # preferred helper
# or, raw:
python3 -m moteus.moteus_tool --target 1 -i                    # read servo info
```

Expected: the tool reports firmware/serial and servo info for **target 1**.

**First power-up only — assign the CAN id.** A factory board answers on its
default id. In tview (`python3 -m moteus_gui.tview --target <discovered>`):

```
conf set id.id 1
conf write
```

Power-cycle; the joint is now **target 1**. (`id.id 1` is also in the cfg for
re-flashing other boards, but the id must be set before the cfg can be addressed
at target 1.)

---

## Step 2 — Motor calibration (gimbal motor)

**Free the motor.** `--calibrate` drives the motor open-loop and needs full,
unobstructed rotation. For a single-stage cycloidal joint, **decouple the motor
from the reducer** if practical, or ensure the joint rotates fully unobstructed.
**TODO(mount):** decide decouple-vs-free-joint once the wrist is assembled.

**Dry run first (optional, recommended).** `--cal-no-update` measures and prints
the report but then **restores the baseline config** (it does NOT commit):

```
python3 -m moteus.moteus_tool --target 1 --calibrate \
    --cal-motor-poles <N> --cal-motor-power 3 --cal-no-update
```

**Commit calibration** (same command, drop `--cal-no-update`):

```
python3 -m moteus.moteus_tool --target 1 --calibrate \
    --cal-motor-poles <N> --cal-motor-power 3
```

Flags, for a small gimbal:

| Flag | Use |
|---|---|
| `--cal-motor-poles <N>` | **Required** for gimbals — the tool will not reliably auto-detect pole count. `N = 2 × pole-pairs`, must be even. **TODO(motor):** read N from the motor's datasheet/spec. |
| `--cal-motor-power 3` | Lower than the 7.5 W default — gentle for the tiny wrist motor (try 2–4 W). |
| `--cal-motor-speed` | Defaults to 12 Hz; leave default. |
| `--cal-bw-hz` | Current-loop bandwidth (default 200 Hz) → `servo.pid_dq.*`, `servo.pid_dq_hz`. Leave default. |

`--calibrate` writes: `motor.poles`, the commutation offset/sign
(`motor_position.sources.0.sign/offset`, `motor.offset.*`, `motor.phase_invert`),
the current loop (`servo.pid_dq.kp/.ki`, `servo.pid_dq_hz`), and
`servo.encoder_filter.*`. High-resistance gimbal windings may push it into
`servo.voltage_mode_control` — it sets/restores that around encoder mapping; let
it. A `moteus-cal-*.log` report is saved. **It does NOT tune the position loop.**

> `--calibrate` only runs with `motor_position.commutation_source == 0` — which is
> what the cfg sets. Do this **before** applying the cfg's output-source settings,
> or at minimum ensure commutation stays on `sources.0`.

---

## Step 3 — Apply the joint config

With calibration committed, apply the geometry / output-source / safety-limit cfg:

```
python3 hardware/joint_bringup/bringup/configure_joint.py      # preferred helper
# or, raw (this file has `#` comments, so use --restore-config, NOT --write-config):
python3 -m moteus.moteus_tool --target 1 \
    --restore-config hardware/joint_bringup/config/wrist_joint.cfg
```

This sets `motor_position.rotor_to_output_ratio 0.111111` (= 1/9), the aux2
AS5047P as `motor_position.output.source 1`, the source cpr/sign/reference, the
conservative limits, and the watchdog, then runs `conf write`. See
[`moteus_joint_config.md`](moteus_joint_config.md) for every register.

> **Order matters.** Apply the cfg **after** `--calibrate`, because the cfg
> deliberately omits cal-derived registers — applying it first then calibrating is
> fine too (cal overwrites its own registers), but never apply a cfg that *omits*
> calibration to an *uncalibrated* board and expect closed-loop motion.
>
> **Why the post-`--calibrate` ordering is load-bearing here:** when
> `output.source != commutation_source` (our exact case — output `1`, commutation
> `0`), `--calibrate` **overwrites** `motor_position.sources.<output.source>.pll_filter_hz`
> with the encoder bandwidth (~`encoder_bw_hz`, default ~80 Hz), clobbering the
> cfg's deliberate `sources.1.pll_filter_hz 10`. Applying `wrist_joint.cfg` **after**
> calibration restores the 10 Hz low-pass on the absolute output encoder; if you
> ever re-run `--calibrate`, re-apply the cfg (or at least that one register).

---

## Step 4 — Mount the AS5047P magnet, verify direction, zero the output

**Magnet.** Mount the diametric magnet centered on the joint **output** shaft,
within the AS5047P air-gap spec. **TODO(mount).**

**Verify direction.** In tview, watch `motor_position.sources.1` and `POSITION`
while turning the joint in its **+angle** direction. If counts/position
**decrease**:

```
conf set motor_position.sources.1.sign -1     # reverse the OUTPUT encoder
conf write
```

Use `sources.1.sign`, **not** `output.sign`: `--calibrate` temporarily forces
`output.sign` to `1` (then restores it), so a `-1` there does not reliably survive
a re-calibration; `sources.1.sign` does. **TODO(mount).**

**Zero the joint.** Hold the joint at its home/reference pose, then:

```
python3 -m moteus.moteus_tool --target 1 --zero-offset         # sets output.offset so current pose = 0
# non-zero datum (newer fw):
python3 -m moteus.moteus_tool --target 1 --set-offset <output_revs>
```

This issues the diagnostic `d cfg-set-output` to write
`motor_position.output.offset` — do not hand-edit it. Because the AS5047P is
absolute and is the `output.reference_source`, the zero **survives power cycles**:
no re-homing. **TODO(mount).**

---

## Step 5 — Tune the position loop (manual, in tview)

`--calibrate` did **not** tune `servo.pid_position.*`. Tune by hand:

1. Start with the cfg values: `kp` low (1.0), `kd = ki = 0`.
2. Command small holds and watch tracking. Either:
   - tview: `d pos <out_rev> 0 <max_torque>` (position in **output revs**), or
   - python: `moteus.Controller.make_position(position=..., velocity=0,
     maximum_torque=..., watchdog_timeout=0.2)`.
3. **Raise `kp`** until the joint is stiff and *just* begins to buzz, then back off
   **~30%**.
4. **Add `kd`** to damp overshoot/ringing (start ~0.05, raise gradually).
5. **Add a small `ki`** (with a sane `ilimit`) **only** if there is residual
   steady-state error.
6. `conf write` when satisfied.

Always halt with `d stop`. The per-command `watchdog_timeout` / `COMMAND_TIMEOUT`
plus `servo.default_timeout_s` will also stop the joint if CAN traffic drops.

**What to plot in tview while tuning:**

| Signal | Source | Look for |
|---|---|---|
| `control_position` | command | the commanded target |
| `position` | aux2 output encoder | tracks `control_position` with minimal lag |
| `position_error` | servo_stats | small, settling, no sustained oscillation |
| `velocity` | — | smooth, no limit-cycle buzz |
| `q_current` | servo_stats | within `servo.max_current_A` |

Goal: `position` tracks `control_position` with minimal error and **no sustained
oscillation**, never hitting `servo.max_current_A`.

---

## Step 6 — Confirm output-shaft position tracks through the 9:1

The whole point of the aux2 AS5047P is that reported `POSITION` is the **true
joint angle after the reduction**. Confirm the ratio and the closed loop together:

1. Command a known output move, e.g. `d pos 0.1 0 <max_torque>` = **0.1 output
   rev = 36°** of joint travel.
2. Measure the **physical** joint rotation (protractor / fixture) — it should be
   ~36°, i.e. tview `POSITION` matches the mechanical angle 1:1 in output revs.
3. The **rotor** turns ~9× that: `ENCODER_0_POSITION` / `motor_position.sources.0`
   advances ~0.9 rev for a 0.1-output-rev move (sanity check of the 1/9 ratio).
4. If physical travel ≠ commanded output revs, the as-built reducer ratio differs
   from 9:1 → update `motor_position.rotor_to_output_ratio` to `1/actual_ratio` and
   re-confirm. **TODO(mount).**
5. Confirm **absoluteness**: note `POSITION`, power-cycle, re-read `POSITION` — it
   should come back the same with no homing (proves `output.reference_source 1` +
   the absolute AS5047P).

---

## Step 7 — Persist & snapshot for version control

```
# already persisted by conf write above; capture the FULL on-device config:
python3 -m moteus.moteus_tool --target 1 --dump-config > \
    hardware/joint_bringup/config/wrist_joint.full.cfg
```

Commit `wrist_joint.full.cfg` (includes the cal-derived registers) so other joints
can be re-flashed from a known-good baseline. Keep the curated
`wrist_joint.cfg` as the human-edited source of design intent.
