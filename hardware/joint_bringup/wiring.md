# Wiring — Phase-1 Single Wrist-Class Joint

Wiring guide for ONE bench joint: 24 V PSU → E-stop → **moteus-c1**; c1 3-phase → **gimbal BLDC**;
c1 **AUX2 (JST GH-7, SPI)** → **AS5047P** output-side encoder; c1 **CAN1 (JST PH-3)** → **mjcanfd-usb-1x**
→ host USB-C (the mjcanfd-usb-1x is the fdcanusb successor; same JST-PH3 moteus pinout). All pin
claims trace to the wiring research findings (mjbots c1 KiCad schematic
`hw/c1/aux2.kicad_sch`, rendered pinout SVG, `docs/reference/pinouts.md`, mjbots config reference,
AS5047P datasheet). Items the research flagged as derived (not published one-line) are marked
**VERIFY**.

---

## Block diagram

```
                    +-------------------+
                    |   24 V BENCH PSU  |   (5-10 A, current-limited; set 1-2 A for first power-on)
                    |   V+ ----o   o----+----------------------+
                    |          E-STOP (NC, in V+ line)         |   <-- cuts MOTOR rail only
                    |   GND ------------+--------------------+ |
                    +-------------------+                    | |
                                                             | |  V+ / GND
                                                       +-----v-v-----------------------+
                                                       |        moteus-c1              |
   gimbal BLDC (3-phase)  <----- MOTOR.A / .B / .C ----|  POWER: XT30 (XT30PW-M)       |
   (GB2208 / GBM2804 class)      (order arbitrary;     |  (10-51 V; NOT rev-pol prot.; |
                                  --calibrate detects) |   NEVER hot-plug)             |
                                                       |                               |
   AS5047P breakout (3.3 V) <==== AUX2 (JST GH-7) =====|  AUX2  (SPI: SCK/MISO/MOSI/CS |
   (14-bit SPI, output shaft)     7-wire SPI + 3V3+GND |        + 3V3 50mA + 5V 100mA) |
        ^                                              |                               |
        | diametric magnet on                          |  CAN1 (JST PH-3) ==> mjcanfd-usb-1x ==USB-C==> host
        | JOINT OUTPUT shaft                           |  CAN2 (JST PH-3) ==> 120 Ohm terminator
        | (after 9:1 cycloidal)                        +-------------------------------+
        |
   [ 9:1 cycloidal reducer ] <--- motor shaft

   CAN-FD bus termination (single-node bench): 120 Ohm at EACH end.
     JST-PH3 120 Ohm terminator in c1 CAN2 jack = 120 Ohm at FAR end
     HOST end: VERIFY whether the mjcanfd-usb-1x integrates termination (the fdcanusb did);
               if not, add a 2nd JST-PH3 120 Ohm terminator at the adapter end
```

---

## AUX2 → AS5047P SPI pin table (JST GH-7)

moteus-c1 **AUX2** = JST **GH-7** (housing GHR-07V-S, contacts SSHL-002T-P0.2). Pin order from
net-tracing `hw/c1/aux2.kicad_sch` (**top pin = Pin 1**). The AS5047P runs at **3.3 V** — power it
from Pin 6 (+3V3), **never** Pin 7 (+5V).

| GH-7 pin | c1 net (STM32) | moteus config role | → AS5047P pin | Notes |
|----------|----------------|--------------------|---------------|-------|
| 1 | GND | ground | GND | |
| 2 | AUX2P_D (PB7) | `aux2.pins.3` = mode **2** (SPI CS) | **CSn** | chip select |
| 3 | AUX2P_C (PA11 / SPI2_MOSI) | `aux2.pins.2` = mode **1** (SPI) | **MOSI** | host→encoder |
| 4 | AUX2P_B (PA10 / SPI2_MISO) | `aux2.pins.1` = mode **1** (SPI) | **MISO** | encoder→host |
| 5 | AUX2P_A (PF1 / SPI2_SCK) | `aux2.pins.0` = mode **1** (SPI) | **CLK (SCK)** | clock |
| 6 | +3V3 (50 mA max) | power | **VDD3V3 / VDD** | tie VDD↔VREG for 3.3 V op (datasheet) |
| 7 | +5V (100 mA max) | — | **leave unconnected** | do NOT power the 3.3 V AS5047P from 5 V |

**VERIFY against the moteus-c1 pinout page** before crimping: the A/B/C/D → SCK/MISO/MOSI/CS mapping
is **derived** (KiCad schematic + shared STM32 SPI2 mux: PF1=SCK, PA10=MISO, PA11=MOSI, PB7=CS +
the COPI/CIPO/CLK SVG labels). mjbots does not publish a one-line "AS5047P CLK→Pin5" table for the
c1. Meter the AUX2 jack against
`https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/c1/moteus-c1-pinout-rendered.svg`
to confirm A=SCK / B=MISO / C=MOSI / D=CS. moteus reads whatever the three `aux2.pins.0/1/2`
(SCK/MISO/MOSI) + `aux2.pins.3` (CS) are wired to — what matters is matching AS5047P CLK→pin.0,
MISO→pin.1, MOSI→pin.2, CSn→pin.3 in this order.

**AS5047P breakout extras:** 100 nF X7R close to VDD3V3↔GND. If the SPI lines float when idle, add
the datasheet's CSn pull-up + CLK/MOSI pull-downs.

### AS5047P moteus config (set via `moteus_tool -c` then `conf write`)

```
conf set aux2.spi.mode 2              # 2 = AS5047P (CPR 16384)
conf set aux2.spi.rate_hz 6000000     # start 1-6 MHz on long wrist harness; raise only if clean
conf set aux2.pins.0.mode 1           # A / SCK  = SPI
conf set aux2.pins.1.mode 1           # B / MISO = SPI
conf set aux2.pins.2.mode 1           # C / MOSI = SPI
conf set aux2.pins.3.mode 2           # D / CS   = SPI CS

conf set motor_position.sources.0.aux_number 2   # AS5047P is on AUX2
conf set motor_position.sources.0.type 1         # 1 = SPI
conf set motor_position.sources.0.cpr 16384      # 14-bit
conf set motor_position.sources.0.reference 1    # 1 = OUTPUT (post-gearbox)
conf set motor_position.output.source <idx>      # TODO: index of the AS5047P source (verify w/ dump-config)
conf set motor_position.rotor_to_output_ratio 0.1111111   # 1/9 for the ~9:1 reducer (TODO: set to 1/N of actual printed lobe count)
# Keep commutation on the ONBOARD rotor encoder — do NOT point commutation_source at the AS5047P.
```

> `aux2.spi.rate_hz` has a **12 MHz default** and no documented min/max in the config reference (the
> 50000-400000 range in the docs is for `aux[12].i2c.i2c_hz`, the I2C bus — **not** SPI; there is no
> `motor_position.spi.rate_hz` register). The AS5047P tolerates ~10 MHz. **Start low (1-6 MHz)** on a
> long wrist harness and raise only if the encoder reads clean — intermittent SPI noise masquerades
> as encoder faults.

---

## CAN-FD connector (JST PH-3)

moteus-c1 has **two parallel CAN-FD PH-3 jacks** (CAN1/CAN2) and **NO onboard termination**.

| c1 CAN PH-3 pin (per c1 schematic order) | → mjcanfd-usb-1x | Notes |
|------------------------------------------|-----------------|-------|
| CAN_H | CANH | twisted pair w/ CAN_L; do NOT cross |
| GND | GND | |
| CAN_L | CANL | |

- **CAN1 jack →** mjcanfd-usb-1x (CANH↔CANH, CANL↔CANL, GND↔GND).
- **CAN2 jack →** 120 Ω JST-PH3 terminator (far-bus-end termination).
- **Host end:** **VERIFY** whether the mjcanfd-usb-1x integrates 120 Ω termination (the fdcanusb's
  SW terminator was ON by default). If it does not, plug a 2nd JST-PH3 120 Ω terminator at the
  adapter end.
- Result: the required **120 Ω at both ends**. With only one termination, 5 Mbps CAN-FD may work for
  <0.5 m but is not guaranteed.

**VERIFY against the moteus-c1 pinout page** (`docs/reference/pinouts.md` / rendered c1 SVG, URL
above) that the PH-3 silk order on your board matches CAN_H / GND / CAN_L before crimping — match
silk to silk, never cross CANH/CANL.

---

## Power distribution — mjbots power_dist r4.5b (full arm; optional on the bench)

For the **Phase-1 single joint**, the block diagram above is enough: PSU → E-stop (NC in V+) →
XT30 → c1. The **`power_dist r4.5b`** (bought full-project, `ORDER_CART.md` Cart 1) is the
**Phase-2 / full-arm power hub** — it replaces the bare PSU→XT30 link and feeds all six controllers
from one supply with **soft-start** (no XT inrush arc). You may also use it on the bench from day one
(one XT30 out → the c1) for the soft-start + a proper illuminated on/off rocker.

```
24 V PSU --XT90--> [ power_dist r4.5b ] --6x XT30--> 6x moteus-c1 (one each)
                          |  PH-4 switch (SWP/SWG): illuminated rocker / E-stop loop
                          |  2x PH-3 CAN-FD (power telemetry) -> joins the moteus bus
```

**Connectors / ratings:**
- **XT90-M input** — from the 24 V PSU. Rated **10–44 V (≤10S)** — 24 V is fine; **45 A cont / 80 A peak**.
- **6× XT30-F outputs** (parallel) — one to each c1 XT30 power input. **Max downstream capacitance
  4000 µF** (six c1 are well under this). Quiescent draw ~300 µA.
- **2× JST PH-3 CAN-FD** — the power_dist is itself a **CAN node** (reports input voltage / power /
  energy + switch state). Daisy-chain it onto the **same moteus CAN-FD bus**; the bus still
  terminates **120 Ω at the two physical ends** — the power_dist is just one more node, so count it
  when deciding which two ends carry the terminators.
- **1× JST PH-4 switch (SWP / SWG)** — the on/off control. mjbots ships an **illuminated rocker +
  PH-4 harness** for this.

**Soft-start:** engaging the PH-4 switch **pre-charges the downstream bulk capacitance gradually**
before connecting full power — this is what removes the XT inrush spark. (The single-joint "never
hot-plug the XT30" hazard is largely tamed once everything sits behind the power_dist's pre-charge.)

**E-stop integration — READ THIS:**
- The PH-4 switch is a **soft switch**, and the power_dist's **"Lock time" register can HOLD output
  power for up to ~3277 s after switch-off** (a graceful-shutdown feature for the host). So opening
  the PH-4 switch is **NOT guaranteed to be an instantaneous cut** unless lock time is 0/disabled —
  do not treat it as an emergency stop by default.
- For a true **E-stop**, choose one:
  1. **(Recommended) Hard disconnect upstream** — keep a NC E-stop / contactor in the **XT90 +V
     input**; it physically removes power regardless of firmware (mirrors the single-joint E-stop rule).
  2. **Soft E-stop via PH-4** — wire the NC E-stop into the SWP/SWG loop **and set Lock time = 0** so
     switch-off cuts immediately. Convenient (reuses the rocker) but firmware-dependent.
- Either way, **verify the motors go dead on E-stop before any calibration spin.**
- Optional: `p force on/off/disable` diagnostic commands drive the bus on/off over CAN for software
  power control.

**VERIFY (per this doc's standard):** the PH-4 **SWP/SWG pin order** + rocker-harness wiring; the
**default Lock-time** value (confirm 0 if you rely on PH-4 as E-stop); and the PH-3 CAN silk order
(CAN_H / GND / CAN_L) — all against the mjbots power_dist reference before connecting.

---

## Magnet mounting

- **Diametrically-magnetized** cylindrical magnet (AS5047P datasheet ref ~6 mm dia, N35H-class)
  bonded to the **END of the JOINT OUTPUT shaft** — i.e. AFTER the ~9:1 cycloidal reduction, so the
  encoder reads true post-gearbox joint angle (homing-free).
- **Centered and concentric** on the rotation axis, magnet face square to and facing the AS5047P
  package center.
- **Air gap ~0.5-2.5 mm** (per datasheet). If the read is noisy: re-center, reduce gap, or lower
  `aux2.spi.rate_hz`.
- Confirm the magnet is **diametric**, not axial — axial magnetization will not produce a valid
  angle.

---

## Safe power-on order + E-stop checklist

> **Golden rule: power is applied LAST. The E-stop sits in the +24 V motor rail UPSTREAM of the c1
> XT30 and cuts the H-bridge supply.**

1. **Build mechanically, unpowered.** Joint assembled, magnet bonded centered on the output shaft,
   AS5047P PCB mounted at the target air gap.
2. **Crimp + meter the AUX2 harness** (GH-7 ↔ AS5047P) per the pin table. **Confirm NO 3V3↔GND
   short** and full continuity BEFORE plugging into the c1.
3. **Crimp the CAN harness** (c1 CAN1 ↔ mjcanfd-usb-1x, twisted pair, not crossed). Plug the **120 Ω
   terminator into CAN2.** VERIFY host-end termination on the mjcanfd-usb-1x (add a 2nd terminator if absent).
4. **Crimp the 3-phase motor leads** to MOTOR.A/B/C (order arbitrary — `--calibrate` auto-detects).
5. **Wire the power rail with the E-stop (NC) in series on V+** upstream of the c1 XT30. Crimp the
   XT30. **Do NOT connect the XT30 to the board yet.**
6. **Connect all data/signal with power OFF:** AUX2 into the c1 AUX2 jack, CAN into CAN1, terminator
   into CAN2, mjcanfd-usb-1x USB-C into host. *(WSL2: `usbipd attach --busid <id> --wsl` so the
   adapter's `/dev/ttyACM*` appears; native on the Pi 5.)*
7. **POWER LAST.** E-stop reachable. **Triple-check XT30 polarity** (not reverse-polarity protected,
   not anti-spark — reverse or hot-plug destroys the board). PSU OFF, set **current limit 1-2 A**,
   connect the XT30 (never hot-plug), then switch the PSU ON.
8. **Comms, no motion:** `python3 -m moteus.moteus_tool -i` (autodiscovers the c1 over the mjcanfd-usb-1x).
9. **Write the AUX2/SPI + motor_position config** (above) via `moteus_tool -c`; `conf write` to flash.
10. **Sanity-check the encoder BEFORE commutating:** hand-rotate the OUTPUT shaft, read the AUX2 SPI
    position; confirm a clean 0→1 rev sweep, no dropouts. (Adjust gap/centering or lower
    `aux2.spi.rate_hz` if noisy.)
11. **Calibrate the motor:** `python3 -m moteus.moteus_tool --calibrate --cal-motor-poles <N>
    --cal-motor-power 2` — low `--cal-motor-power` (2-4 W, below the 7.5 W default) for the tiny
    gimbal motor; keep the joint free to move / current-limited. *(`--cal-voltage` is deprecated;
    `calibration_and_tuning.md` is the single source of truth for the calibration command.)*
12. **Set safety limits** (`servopos.position_min`/`position_max` to the joint sweep, e.g. -0.4/0.4
    rev; `servo.max_position_slip` e.g. 0.05; conservative current/velocity), `conf write`, then
    command tiny low-speed position moves and verify the AS5047P output angle tracks through the
    9:1 reduction. **Hand on the E-stop for all first motion.**

### E-stop behavior
- E-stop is **normally-closed in the +24 V V+ line**: tripping it removes the H-bridge supply →
  motor de-energizes immediately. Logic/CAN can be powered separately if you want telemetry to
  survive an E-stop; otherwise it kills everything.
- Verify the E-stop **before** first calibration spin: trip it and confirm the motor goes dead.

---

## Reference URLs (verify-against)

- c1 pinout (rendered): `https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/c1/moteus-c1-pinout-rendered.svg`
- CAN termination policy / mating hardware: `https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/pinouts.md`
- AUX2 SPI encoder config worked example (MA600): `https://blog.mjbots.com/2025/02/27/configuring-an-off-axis-ma600-encoder-with-moteus/`
- moteus config reference: `https://mjbots.github.io/moteus/reference/configuration/`
- AS5047P datasheet: `https://look.ams-osram.com/m/d05ee39221f9857/original/AS5047P-DS000324.pdf`
- power_dist r4.5b (XT90 in / 6× XT30 / PH-4 switch / PH-3 CAN, soft-start, Lock-time):
  `https://github.com/mjbots/power_dist` (docs/reference.md) · `https://mjbots.com/products/mjbots-power-dist-r4-5b`
