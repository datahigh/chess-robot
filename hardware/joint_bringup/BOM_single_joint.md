# BOM — Phase-1 Single Wrist-Class Joint

Bill of materials to **order now** for the Phase-1 bring-up: ONE isolated wrist-class joint
(J5 wrist-pitch / J6 wrist-roll class) on the bench. Architecture: gimbal BLDC + 3D-printed
**~9:1 single-stage cycloidal reducer** → **moteus-c1** FOC driver on CAN-FD via the
**mjcanfd-usb-1x** adapter (fdcanusb successor) → host. Output-side absolute angle from an **AS5047P (14-bit SPI)** reading a diametric magnet on the
joint OUTPUT shaft, wired to the moteus-c1 **AUX2 (JST GH-7, SPI)** port.

Torque is tiny (chess pieces weigh grams); the ~9:1 reduction multiplies motor torque, so the motor
is sized for resolution/smoothness, not load. Everything here matches §3/§9 of `CLAUDE.md`.

> Sourcing is India-based: prefer **Robu.in / Robokits / ThinkRobotics / Robocraze (Bengaluru) /
> 3Ding**. Long-lead **imports** — from mjbots (moteus-c1, mjcanfd-usb-1x, terminators) and from
> DigiKey/Mouser (the GH-7 AUX2 connector, the AS5047P breakout) — ship worldwide; order these FIRST.

---

## Order priority

1. **IMPORTS FIRST (longest lead, ~2-4 wk to India):** moteus-c1 + mjcanfd-usb-1x + JST-PH3 CAN-FD
   terminator(s) from mjbots; the GH-7 AUX2 connector (GHR-07V-S + GH crimp contacts) and the
   AS5047P breakout from DigiKey/Mouser. These gate the whole bring-up. (The c1 box already includes
   a mating XT30 + a JST-PH3 housing, so no separate CAN/power mating kit is needed.)
2. **In parallel:** gimbal BLDC motor, AS5047P breakout + diametric magnet, 24 V PSU + E-stop,
   filament — all locally stocked in India, fast.
3. **As soon as the printer is free:** print the cycloidal reducer (PETG) + bearings/dowels on hand.

---

## Bill of materials

| # | Item | Spec / why | Qty | Sourcing (India local vs import) |
|---|------|-----------|-----|----------------------------------|
| 1 | **moteus-c1** FOC controller | 10-51 V, CAN-FD 5 Mbps (JST PH-3), AUX2 = JST GH-7 SPI/UART/GPIO (3V3 50 mA + 5V 100 mA rails), MOTOR.A/B/C phase out, XT30 power in. The Phase-1 driver. | 1 | **Import** — mjbots.com (`moteus-c1`). Long lead → order first. |
| 2 | **mjcanfd-usb-1x** USB↔CAN-FD adapter | Host bridge (fdcanusb successor; fdcanusb is discontinued). USB-C, same JST-PH3 moteus pinout, socketcan + fdcanusb-compatible virtual-serial. Enumerates `/dev/ttyACM*` (native on Pi 5; on WSL2 attach via `usbipd attach`). | 1 | **Import** — mjbots.com (`mjcanfd-usb-1x`, ~$39). Order with #1. |
| 3 | **JST-PH3 CAN-FD terminator** (120 Ω) | moteus has **NO onboard CAN termination**. Bus needs 120 Ω at each end: this in the c1's spare PH-3 jack (far end) + the host end. **VERIFY** whether the mjcanfd-usb-1x integrates host-end termination (the fdcanusb did); if not, buy **2**. | 1-2 | **Import** — mjbots `jst-ph3-can-fd-terminator` (~$5). (Substitute: hand-crimp a PHR-3 with a 120 Ω 1/4 W across CAN_H/CAN_L.) |
| 4 | **GH-7 AUX2 connector** (GHR-07V-S housing + GH crimp contacts) | The only mating connector you must buy separately — the c1 box already includes the XT30 + JST-PH3 mates. **Sold out at mjbots**, not on semikart → **import from DigiKey/Mouser**. Confirm the exact GH (1.25 mm) contact PN on the housing's page (`SSHL-002T-P0.2` vs `MINI-SSHL-002T-P0.2`). Buy ~10-15 contacts (tiny) + 2-3 spare housings. | 1 set | **Import** — DigiKey/Mouser (GHR-07V-S + contacts). See `ORDER_CART.md` for PNs/prices. |
| 5 | **Gimbal BLDC motor (wrist-class)** | High pole count (≥14 poles / 7 pp), **low Kv (~70-120 rpm/V)** for fine FOC resolution at low speed, ~24 V capable, small frame. **Candidate A:** GB2208 / GB2804 / GB2805 gimbal motor class (22-28 mm stator, ~12N14P). **Candidate B:** iPower GBM2804 / GBM2208-class. **Spec to match if substituting:** gimbal-wound (high R, low Kv), 3-phase, 14P/12N or similar, ≤24 V, ≤~1 A continuous. Torque is tiny — sized for smoothness, the 9:1 reducer does the rest. | 1 | **India local** — Robu.in / Robokits / Robocraze "gimbal BLDC motor" (GB2208/GBM2804 class). |
| 6 | **AS5047P breakout board** | 14-bit (16384 CPR), 4-wire SPI (CSn/CLK/MISO/MOSI), **3.3 V** part. Reads output-shaft magnet → moteus AUX2. Get a solder-ready breakout exposing all 4 SPI pins + VDD/GND, run at 3.3 V (tie VDD↔VREG). **Scarce in India** (no clean local listing; semikart has only the bare IC) → **import**. | 1 | **Import** — DigiKey/Mouser (ams adapter board) or a generic AS5047P breakout (Amazon US). See `ORDER_CART.md` for PNs/prices. Keep AS5047P (locked); CPR 16384. |
| 7 | **Diametric magnet** | Cylindrical **diametrically-magnetized**, AS5047P datasheet reference **~6 mm dia × 2.5-3 mm**, N35H-class. Bond centered/concentric on the joint OUTPUT shaft end, air gap ~0.5-2.5 mm. Buy a few (sizing/gluing attrition). | 3-5 | **India local** — Robu.in / Robocraze "diametric magnet 6mm". Confirm **diametric** (not axial) magnetization. |
| 8 | **24 V bench PSU, ~5-10 A** | Powers the c1 motor rail. Adjustable current limit strongly preferred (first power-on at 1-2 A). 24 V is within the c1 10-51 V range. | 1 | **India local** — Robu.in / Robokits adjustable bench supply. (Lab supply with CC/CV ideal.) |
| 9 | **E-stop / power switch (motor rail)** | Normally-closed E-stop or contactor in the **+24 V V+ line UPSTREAM of the c1 XT30** — cuts the H-bridge supply. Rated ≥10 A. | 1 | **India local** — Robu.in / Robokits "emergency stop switch NC". |
| 10 | **Power wiring: XT30 + leads** | XT30U-F to PSU; 18-20 AWG silicone wire for V+/GND. XT30 is **NOT reverse-polarity protected and NOT anti-spark** — never hot-plug. | 1 set | **India local** — Robu.in XT30 + silicone wire. (XT30U-F mate also in mjbots kit #4.) |
| 11 | **CAN-FD harness (JST-PH3)** | Twisted pair for CAN_H/CAN_L + GND, PHR-3 each end, c1 CAN1 ↔ mjcanfd-usb-1x. ~0.3-0.5 m. The c1 box includes one PH-3 housing; the mjcanfd-usb-1x ships with its CAN cabling. | 1 | **From the box** (c1 PH-3 + adapter cable), or India-local crimp (PHR-3 + SPH-002T). Twist CANH/CANL. |
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
