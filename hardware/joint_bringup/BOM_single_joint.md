# BOM — Phase-1 Single Wrist-Class Joint

Bill of materials to **order now** for the Phase-1 bring-up: ONE isolated wrist-class joint
(J5 wrist-pitch / J6 wrist-roll class) on the bench. Architecture: gimbal BLDC + 3D-printed
**~9:1 single-stage cycloidal reducer** → **moteus-c1** FOC driver on CAN-FD via **fdcanusb** →
host. Output-side absolute angle from an **AS5047P (14-bit SPI)** reading a diametric magnet on the
joint OUTPUT shaft, wired to the moteus-c1 **AUX2 (JST GH-7, SPI)** port.

Torque is tiny (chess pieces weigh grams); the ~9:1 reduction multiplies motor torque, so the motor
is sized for resolution/smoothness, not load. Everything here matches §3/§9 of `CLAUDE.md`.

> Sourcing is India-based: prefer **Robu.in / Robokits / ThinkRobotics / Robocraze (Bengaluru) /
> 3Ding**. Long-lead **imports from mjbots** (moteus-c1, fdcanusb, terminators, mating connectors)
> ship worldwide — order these FIRST.

---

## Order priority

1. **IMPORTS FIRST (longest lead, ~2-4 wk to India):** moteus-c1, fdcanusb, JST-PH3 CAN-FD
   terminator, mjbots mating-connector kit (XT30U-F, PHR-3, GHR-07V-S + SSHL-002T-P0.2 contacts).
   These gate the whole bring-up.
2. **In parallel:** gimbal BLDC motor, AS5047P breakout + diametric magnet, 24 V PSU + E-stop,
   filament — all locally stocked in India, fast.
3. **As soon as the printer is free:** print the cycloidal reducer (PETG) + bearings/dowels on hand.

---

## Bill of materials

| # | Item | Spec / why | Qty | Sourcing (India local vs import) |
|---|------|-----------|-----|----------------------------------|
| 1 | **moteus-c1** FOC controller | 10-51 V, CAN-FD 5 Mbps (JST PH-3), AUX2 = JST GH-7 SPI/UART/GPIO (3V3 50 mA + 5V 100 mA rails), MOTOR.A/B/C phase out, XT30 power in. The Phase-1 driver. | 1 | **Import** — mjbots.com (`moteus-c1`). Long lead → order first. |
| 2 | **fdcanusb** USB↔CAN-FD adapter | Host bridge; SW terminator **ON by default** (= 120 Ω at host end). Enumerates `/dev/ttyACM*` / `/dev/fdcanusb` (native on Pi 5; on WSL2 attach via `usbipd attach`). | 1 | **Import** — mjbots.com (`fdcanusb`). Order with #1. |
| 3 | **JST-PH3 CAN-FD terminator** (120 Ω) | moteus has **NO onboard CAN termination**. Single-node bench bus needs 2 terminations: fdcanusb (host end) + this physical 120 Ω in the c1's spare PH-3 jack (far end). | 1 | **Import** — mjbots `jst-ph3-can-fd-terminator`. (Substitute: hand-crimp a PHR-3 with a 120 Ω 1/4 W across CAN_H/CAN_L.) |
| 4 | **mjbots mating-connector kit** | XT30U-F (power mate), PHR-3 + SPH-002T (CAN), **GHR-07V-S + SSHL-002T-P0.2** (AUX2 GH-7). Buy from mjbots to guarantee the GH-7 contact match. | 1 set (buy extra contacts) | **Import** — mjbots connector kit. GH-7 + contacts are the hard-to-source part locally. |
| 5 | **Gimbal BLDC motor (wrist-class)** | High pole count (≥14 poles / 7 pp), **low Kv (~70-120 rpm/V)** for fine FOC resolution at low speed, ~24 V capable, small frame. **Candidate A:** GB2208 / GB2804 / GB2805 gimbal motor class (22-28 mm stator, ~12N14P). **Candidate B:** iPower GBM2804 / GBM2208-class. **Spec to match if substituting:** gimbal-wound (high R, low Kv), 3-phase, 14P/12N or similar, ≤24 V, ≤~1 A continuous. Torque is tiny — sized for smoothness, the 9:1 reducer does the rest. | 1 | **India local** — Robu.in / Robokits / Robocraze "gimbal BLDC motor" (GB2208/GBM2804 class). |
| 6 | **AS5047P breakout board** | 14-bit (16384 CPR), 4-wire SPI (CSn/CLK/MISO/MOSI), **3.3 V** part. Reads output-shaft magnet → moteus AUX2. Get a breakout that exposes all 4 SPI pins + VDD/GND and lets you run 3.3 V (tie VDD↔VREG). | 1 | **India local** — Robu.in / ThinkRobotics / Robocraze "AS5047P". (Substitute: AS5047D/AS5048A also supported by moteus `aux.spi.mode`, but AS5047P is the locked choice — keep CPR 16384.) |
| 7 | **Diametric magnet** | Cylindrical **diametrically-magnetized**, AS5047P datasheet reference **~6 mm dia × 2.5-3 mm**, N35H-class. Bond centered/concentric on the joint OUTPUT shaft end, air gap ~0.5-2.5 mm. Buy a few (sizing/gluing attrition). | 3-5 | **India local** — Robu.in / Robocraze "diametric magnet 6mm". Confirm **diametric** (not axial) magnetization. |
| 8 | **24 V bench PSU, ~5-10 A** | Powers the c1 motor rail. Adjustable current limit strongly preferred (first power-on at 1-2 A). 24 V is within the c1 10-51 V range. | 1 | **India local** — Robu.in / Robokits adjustable bench supply. (Lab supply with CC/CV ideal.) |
| 9 | **E-stop / power switch (motor rail)** | Normally-closed E-stop or contactor in the **+24 V V+ line UPSTREAM of the c1 XT30** — cuts the H-bridge supply. Rated ≥10 A. | 1 | **India local** — Robu.in / Robokits "emergency stop switch NC". |
| 10 | **Power wiring: XT30 + leads** | XT30U-F to PSU; 18-20 AWG silicone wire for V+/GND. XT30 is **NOT reverse-polarity protected and NOT anti-spark** — never hot-plug. | 1 set | **India local** — Robu.in XT30 + silicone wire. (XT30U-F mate also in mjbots kit #4.) |
| 11 | **CAN-FD harness (JST-PH3)** | Twisted pair for CAN_H/CAN_L + GND, PHR-3 each end, c1 CAN1 ↔ fdcanusb. ~0.3-0.5 m. | 1 | **India local** crimp (PHR-3 + SPH-002T) or **import** in kit #4. Twist CANH/CANL. |
| 12 | **AUX2 SPI harness (JST GH-7)** | GHR-07V-S + SSHL-002T-P0.2, 7-wire to AS5047P breakout. 26-28 AWG. GH-7 contacts are fine-pitch — crimp carefully or buy pre-crimped from mjbots. | 1 | **Import** (kit #4) for the GH-7 housing+contacts; wire it to local Dupont/JST on the breakout side. |
| 13 | **3V3 SPI jumpers / Dupont** | Breakout-side jumpers for the 5 SPI lines + 3V3 + GND from the GH-7 pigtail to the AS5047P breakout headers. | 1 set | **India local** — Robu.in Dupont/JST jumper kit. |
| 14 | **100 nF decoupling cap (+ optional pull-ups)** | 100 nF X7R close to AS5047P VDD3V3↔GND. Optional: CSn pull-up + CLK/MOSI pull-downs per datasheet if SPI idles floating. | 5 | **India local** — Robu.in passives kit. |
| 15 | **Cycloidal-stage bearings** | Output-shaft support + eccentric-cam bearing(s) for the 3D-printed cycloidal disc. Sizes follow the chosen reference CAD (typ. 6700/6800-series thin-section + a small needle/ball for the eccentric). **TODO: finalize exact bearing IDs/ODs from the printed CAD chosen in #18.** | per CAD | **India local** — Robu.in / Robokits bearings. |
| 16 | **Dowel pins + fasteners** | Hardened dowel pins for the cycloidal output rollers/pins + M3/M2.5 socket-head screws + heat-set inserts for the printed housing. **TODO: exact dowel dia/count = function of #18 CAD.** | per CAD | **India local** — fastener/dowel supplier; heat-set inserts from Robu.in. |
| 17 | **Filament — PETG** | Gear/structure to start (per §3/§9: "Gears in PETG to start"). 1 kg. Print cycloidal disc, ring/pins housing, motor + encoder mounts. | 1 kg | **India local** — 3Ding / 3idea / Robu.in PETG. |
| 18 | **3D-printed cycloidal reducer (print, don't buy)** | **~9:1 single stage** for the wrist joint. Print from reference CAD: **Faze4 cycloidal gearbox** (github.com/PCrnjak/Faze4-Robotic-arm), **OpenCyRe / Atlas** (hackaday.io/project/168259), and **Skyentific** BLDC/cycloidal actuator builds. Adapt the ratio to ~9:1 and the bore to the chosen gimbal motor. | 1 print set | **Self-print** (PETG, #17). CAD = free/open. **TODO: pick one reference + confirm 9:1 lobe count and motor-bore fit before printing.** |
| 19 | *(Optional, later)* **PA-CF / PA6-GF filament + high-temp dryer** | For max precision-retention gears after PETG proof-out (§3/§9). Needs ~70-90 °C dryer (AMS only reaches 65 °C). **Do NOT order for Phase-1** unless PETG backlash proves inadequate. | — | India local (3Ding) + dryer. Defer. |

---

## Notes / assumptions (finalize after parts arrive)

- **Motor exact part = TODO until ordered:** the GB2208 / GBM2804 gimbal class is the target; verify
  pole count and Kv on the actual stocked SKU. Low Kv + high pole count = the spec to hold.
- **Cycloidal bearings/dowels (#15/#16) are CAD-dependent** — cannot finalize IDs/ODs/dowel sizes
  until the reference CAD in #18 is chosen and the motor bore is known.
- **`rotor_to_output_ratio` will be `1/N`** where N is the printed stage's actual lobe ratio
  (target 1/9 = 0.1111111). Confirm N from the chosen CAD, not assumed.
- **Connector strategy:** buy the AUX2 GH-7 housing + SSHL-002T-P0.2 contacts from mjbots (kit #4);
  GH-pitch contacts are the hardest item to source locally and easiest to get pre-matched from the
  same vendor as the c1.
- Wiring/termination/power-on detail lives in `wiring.md` (same directory).
