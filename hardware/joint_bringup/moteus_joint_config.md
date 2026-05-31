# moteus-c1 config — Phase-1 wrist-class joint

Prose reference for every register in [`config/wrist_joint.cfg`](config/wrist_joint.cfg).
Subject: one bench joint — small **gimbal BLDC** + single-stage **~9:1 cycloidal**
reducer, **onboard encoder (aux1)** as the rotor/commutation source and an external
**AS5047P (14-bit SPI) on aux2** as the absolute **output-shaft** position source.

All register names and enum values below are taken from the moteus 1.0.0 config
reference and confirmed against the installed `moteus_tool.py`. Anything that can
only be finalized after the hardware exists is marked **TODO**.

---

## 0. Two encoders, two jobs (read this first)

The moteus-c1 tracks **two independent position sources** for this joint:

| Source | Index | Port | Role | `reference` | Set by |
|---|---|---|---|---|---|
| Onboard encoder (rotor side) | `sources.0` | aux1 | **Commutation** — FOC needs rotor angle | `0` (rotor) | us + `--calibrate` |
| External AS5047P (joint side) | `sources.1` | aux2 | **Output position** — true joint angle after the 9:1 | `1` (output) | us |

The motor commutates off the **fast, rotor-side** onboard encoder. The number we
care about for chess motion — the actual joint angle — comes from the **absolute
AS5047P on the output shaft**, selected via `motor_position.output.source = 1`.
Because that encoder is absolute and is the `output.reference_source`, the joint
angle is known the instant it powers on: **no homing**.

Why not commutate off the output encoder? Through a 9:1 reducer the output encoder
moves 1/9 as fast and carries reducer backlash/wind-up — useless for FOC timing.
Also, `moteus_tool --calibrate` **only runs when `commutation_source == 0`**
(explicit `RuntimeError` otherwise in the local source), so the commutation source
must be `sources.0`.

---

## 1. Register table

| Register | Value | Meaning / why this value |
|---|---|---|
| `id.id` | `1` | CAN node id of this controller. Each joint's moteus-c1 gets a unique id; this wrist joint is **target 1**. |
| `motor_position.rotor_to_output_ratio` | `0.111111` | Gear scale = **output revs per rotor rev** = `1/9`. A reducer is **<1** (docs: 4× → `0.25`). After this is set, all positions/velocities are in **output-shaft revolutions**. **TODO(mount):** set to `1/actual_ratio` once the printed reducer's true ratio is known. |
| `motor_position.commutation_source` | `0` | Index of the source that drives commutation = onboard encoder. Must be `0` (auto-cal requirement). |
| `motor_position.sources.0.type` | `1` | `1 = SPI`. Onboard AS5047P is SPI. |
| `motor_position.sources.0.aux_number` | `1` | Onboard encoder lives on **aux1**. |
| `motor_position.sources.0.cpr` | `16384` | Onboard AS5047P counts/rev = `2^14`. |
| `motor_position.sources.0.reference` | `0` | `0 = rotor`-referenced (commutation is rotor side). |
| `aux2.spi.mode` | `2` | `2 = AS5047P (CPR 16384)` on aux2. **Not `0`** — `0` is the onboard encoder and is aux1-only. |
| `aux2.spi.rate_hz` | `12000000` | 12 MHz SPI clock; AS5047P tolerates the default. |
| `motor_position.sources.1.type` | `1` | `1 = SPI`. External AS5047P on aux2. |
| `motor_position.sources.1.aux_number` | `2` | Output encoder is wired to **aux2** (ABS connector). |
| `motor_position.sources.1.cpr` | `16384` | AS5047P 14-bit → `2^14` counts/rev. |
| `motor_position.sources.1.reference` | `1` | `1 = output`-referenced — this is the joint-side encoder. |
| `motor_position.sources.1.pll_filter_hz` | `10` | Low 3 dB cutoff of the source's tracking/PLL filter; moteus_tool uses 10 Hz for absolute sources. |
| `motor_position.sources.1.offset` | `0` | Integer raw-count offset before scaling. Reported = `(raw + offset) * sign / cpr`. Joint zero is set via `output.offset`, not here. |
| `motor_position.sources.1.sign` | `1` | `+1`/`-1` direction of the output encoder. **Use this to reverse joint direction** (see §3). **TODO(mount):** verify, flip to `-1` if reversed. |
| `motor_position.output.source` | `1` | Index of the source used as the **output** position = the aux2 AS5047P. |
| `motor_position.output.sign` | `1` | **Keep `1`.** `--calibrate` temporarily forces this to `1` during absolute-encoder mapping, then restores it; reverse direction via `sources.1.sign` so it survives calibration. |
| `motor_position.output.reference_source` | `1` | Index of the source providing the **absolute output reference** = the aux2 AS5047P → homing-free joint angle (`-1` = none). |
| `motor_position.output.offset` | `0.0` | Output-rev offset = joint zero/datum. **Placeholder — do NOT hand-edit.** Set via `--zero-offset` after mounting (§3, **TODO(mount)**). |
| `servo.max_current_A` | `2.0` | Hard phase-current cap. Low for the tiny gimbal / minimal stored energy. |
| `servo.max_velocity` | `1.0` | Velocity cap in **output revs/s** (post-ratio). Conservative bench value. |
| `servo.max_power_W` | `20.0` | Power ceiling; the lower of this and the board profile applies. |
| `servo.max_voltage` | `30.0` | Input over-voltage fault threshold; set above the 24 V supply with margin. **TODO(supply):** match the real bus voltage. |
| `servopos.position_min` | `-0.2` | Min control position in **output revs** (~ −72°). Software workspace floor. **TODO(mount):** real travel. NaN disables. |
| `servopos.position_max` | `0.2` | Max control position in **output revs** (~ +72°). **TODO(mount):** real travel. |
| `servo.default_timeout_s` | `0.5` | Command watchdog: time since last command before entering `timeout_mode`. |
| `servo.timeout_mode` | `0` | `0 = stopped` (unpowered) on timeout. Safest for a bench joint. |
| `servo.pid_position.kp` | `1.0` | Position-loop P gain (Nm per output rev). **START LOW.** **TODO(tune).** |
| `servo.pid_position.kd` | `0.05` | Position-loop D gain (Nm per output rev/s) — damps kp ringing. **TODO(tune).** |
| `servo.pid_position.ki` | `0.0` | Position-loop I gain. Leave `0`; add only for steady-state error. **TODO(tune).** |
| `servo.pid_position.ilimit` | `0.0` | Anti-windup clamp on the position integrator; raise only if `ki` > 0. |

---

## 2. The gear-ratio convention (the one that bites people)

`motor_position.rotor_to_output_ratio` is **"the number of times the output turns
for each revolution of the rotor."** For a reduction it is therefore a **fraction
< 1**:

```
9:1 reducer  ->  output turns 1/9 per rotor turn  ->  0.111111
4:1 reducer  ->  0.25   (verbatim docs example)
```

It is **NOT** `9.0`. The local `moteus_tool` migration code confirms this register
is the direct successor of the old `motor.unwrapped_position_scale`
(output-per-rotor scale). Once it is set, **every** position/velocity register —
`servopos.position_min/max`, `servo.max_velocity`, `COMMAND_POSITION`, the
diagnostic `d pos` — is interpreted in **output-shaft revolutions**. A joint that
swings ±72° is ±0.2 output rev.

**TODO(mount):** the printed cycloidal ratio is fixed by the pin-wheel / lobe
counts. If the as-built reducer is not exactly 9:1, set this to `1/actual_ratio`.

---

## 3. Setting joint zero and direction

**Direction.** Reverse the joint with `motor_position.sources.1.sign = -1`, never
with `output.sign`. During `--calibrate`, `moteus_tool` reads your `output.sign`,
**temporarily forces it to `1`** for the duration of the absolute-encoder
current-mode mapping, and **restores the original value in a `finally` block**
(`moteus_tool.py`). So `output.sign = -1` is not permanently "broken" — it is just
overridden during calibration; relying on it to set direction is fragile because a
re-`--calibrate` re-touches it. Use `sources.1.sign` instead, which survives.
Verify by turning the joint in its +angle direction and watching `POSITION` /
`sources.1` counts increase in tview. **TODO(mount).**

**Zero / datum.** `motor_position.output.offset` defines the output `0` point. It
is **not** hand-edited — it is written by the diagnostic command `d cfg-set-output`,
which `moteus_tool` issues for you:

```
python3 -m moteus.moteus_tool --target 1 --zero-offset        # sets offset so current pose = 0
python3 -m moteus.moteus_tool --target 1 --set-offset <rev>   # sets a non-zero datum (newer fw)
```

Old firmware only supports offset `0.0`. Because the AS5047P is absolute and is the
`output.reference_source`, this datum **survives power cycles** — no re-homing.
**TODO(mount):** run `--zero-offset` after the magnet is mounted and the joint is
held at its home pose.

---

## 4. What is deliberately NOT in `wrist_joint.cfg`

These are written by `moteus_tool --calibrate` and must already be on the device
**before** applying `wrist_joint.cfg`. They are motor/encoder-measurement results,
not design choices, so they are not version-controlled in this file:

- `motor.poles` — from `--cal-motor-poles N` (gimbal motors require it explicitly).
- `motor_position.sources.0.sign`, `motor_position.sources.0.offset` — commutation
  encoder mapping from `--calibrate`.
- `motor.offset.*`, `motor.phase_invert`, `aux1.hall.polarity` — cal results.
- `servo.pid_dq.kp`, `servo.pid_dq.ki`, `servo.pid_dq_hz` — current loop, from
  `--cal-bw-hz` (default 200 Hz).
- `servo.encoder_filter.enabled/.kp/.ki` — onboard-encoder tracking filter, from
  `--calibrate` (`--encoder-bw-hz`).
- `servo.voltage_mode_control` — set/restored by `--calibrate` for high-resistance
  gimbal windings; let the tool manage it.

The **position loop** (`servo.pid_position.*`) IS in the cfg but is **hand-tuned**
— `--calibrate` does not touch it.

---

## 5. Pinout / wiring notes

- **aux2 (ABS connector)** carries the SPI bus to the external AS5047P: CLK/SCK,
  MOSI, MISO, CS, plus 3V3 (or 5V where provided) and GND. **TODO(wiring):** the
  fetched docs did **not** list the moteus-c1 aux2 pin order verbatim — confirm
  against the moteus-c1 hardware page / board silk before wiring. **Do not assume
  pin order.**
- On aux2, set the CLK/MOSI/MISO pins to `aux2.pins.X.mode = 1` (SPI) and the CS
  pin to `mode = 2` (SPI CS). These per-pin modes are board-layout specific and so
  are left as a **TODO(wiring)** rather than hard-coded in the cfg.
- The AS5047P needs a **diametrically-magnetized magnet centered on the joint
  OUTPUT shaft**, within the AS5047P air-gap spec.
- The onboard encoder stays on **aux1** as the rotor-side commutation source.
- **CAN-FD:** moteus-c1 JST-PH3 connectors daisy-chain from the mjcanfd-usb-1x (fdcanusb successor);
  terminate the bus ends; this joint's `id.id = 1`.

---

## 6. Applying the file

```
# --restore-config strips `#` comments, prepends `conf set`, then `conf write`:
python3 -m moteus.moteus_tool --target 1 --restore-config config/wrist_joint.cfg
```

Use `--restore-config` (not the verbatim `--write-config`) for this file because it
contains `#` comments. Snapshot the full on-device config after tuning:

```
python3 -m moteus.moteus_tool --target 1 --dump-config > config/wrist_joint.full.cfg
```
