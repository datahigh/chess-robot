# Order Cart — Phase-1 Single Wrist-Class Joint

**Price snapshot: 2026-05-31** (consolidation pass 2026-06-06). FX used: **USD→INR ≈ 95.0**
(xe.com live, cross-checked). Quantities are for **ONE bench joint** (the Phase-1 scope), not the
full 6-joint arm.

> **Confidence key:** ✓ = read live on the product page today · ~ = snippet / cross-vendor / approx
> (Robu.in blocks automated fetch, so its prices are unconfirmed) · ✗ = unverified placeholder.
> Prices and stock move without notice — re-check at checkout.

---

## ✅ Decisions made

**Pass 1 (2026-05-31):**
1. **CAN adapter → `mjcanfd-usb-1x` ($39).** ADOPTED in place of the discontinued `fdcanusb` (same
   JST-PH3 moteus pinout, USB-C). The moteus python transport stays `moteus.Fdcanusb` (the fdcanusb
   *protocol*, spoken by the mjcanfd-usb-1x in virtual-serial mode), so the bring-up scripts are
   unchanged; socketcan is the alt. Enumerates as `/dev/ttyACM*`.
4. **Bench PSU → INCLUDE** (no bench supply on hand). It's in the total.

**Pass 2 (2026-06-06) — cart consolidation, objective = minimize IMPORT shipments:**
5. **Two import parcels accepted, domestic carts unconstrained.** The moteus stack is mjbots-only
   (parcel 1, mandatory). The encoder front-end is taken **spec-correct from DigiKey** (parcel 2),
   NOT via the domestic substitute — the genuine ams AS5047P board + real JST GH contacts are worth
   the second parcel. Domestic India parts (cheap/fast, don't count against the import goal) funnel
   into one Robu.in cart.
6. **Cycloidal reducer → adopt Faze4 single-stage wrist cycloidal, re-cut to 9:1** (9 disc lobes /
   10 ring pins; single-eccentric law pins = lobes+1, ratio = lobes). Confirms
   `motor_position.rotor_to_output_ratio = 1/9 = 0.111111`. This **resolves the previously-deferred
   bearings/dowels** → they now ride in Cart 3 (see §"Cycloidal mechanicals"). The disc/eccentric/
   housing still need CAD editing (see that section).
7. **Motor → 2804 100 KV gimbal class (GBM2804H-100T), 14 poles, hollow-shaft.** Sets
   `--cal-motor-poles 14`. Available on Robu.in (keeps Cart 3 single-vendor). Brand-name fallback:
   T-Motor GB2208 (Robokits RKI-3511, guaranteed 6 mm bore, Kv 128 — a touch high).

**Net: 3 carts total — mjbots + DigiKey + Robu.in.**

---

## Cart 1 — mjbots (import #1, USD) — the moteus stack, sole source

| BOM | Item | Handle | Unit | Qty | Line | Conf | Notes |
|---|---|---|---:|---:|---:|:--:|---|
| #1 | moteus-c1 FOC controller | `moteus-c1` | $69.00 | 1 | $69.00 | ✓ | 630 in stock. **Box includes** XT30 mate + JST-PH3 housing (w/ crimps) + 1/4″ diametric **rotor** magnet |
| #2 | mjcanfd-usb-1x USB↔CAN-FD | `mjcanfd-usb-1x` | $39.00 | 1 | $39.00 | ✓ | 634 in stock. fdcanusb successor |
| #3 | JST-PH3 CAN-FD terminator (120 Ω) | `jst-ph3-can-fd-terminator` | $5.00 | 2 | $10.00 | ✓ | 1 at the c1 far end + 1 host end. Drop to 1 only if the mjcanfd-usb-1x integrates host-end termination (**VERIFY** on its product page) |
| #7 | Diametric sense magnet 6×2.5 mm N35SH | `diametric-disc-magnet` | $1.50 | 5 | $7.50 | ✓ | output-shaft AS5047P magnet (the c1's bundled magnet is for the rotor, not the output) |

**Cart 1 subtotal ≈ $125.50.** Landed (goods + intl ship ~$30–50 + ~18 % IGST) → **≈ ₹17,000**.

---

## Cart 2 — DigiKey (import #2, USD) — encoder front-end (the mjbots/India gap)

| BOM | Item | Mfr PN | DK PN | Unit | Qty | Line | Conf | Notes |
|---|---|---|---|---:|---:|---:|:--:|---|
| #6 | AS5047P adapter board (solder-ready) | AS5047P ADAPTERBOARD (`AS5047P-TS_EK_AB`) | 4991-AS5047PADAPTERBOARD-ND | $19.40 | 1 | $19.40 | ✓ | 416 in stock. 3.3 V jumper; **magnet NOT incl** (use Cart 1 #7). Fixture the flat PCB over the output magnet |
| #4 | JST GH-7 housing | GHR-07V-S | 455-1597-ND | $0.15 | 3 | $0.45 | ✓ | **verify stock at order time** (Active/backorder) or use Mouser. Cheap → buy spares |
| #4 | JST GH crimp contact | SSHL-002T-P0.2 | 455-1606-1-ND | $0.11 | 15 | $1.65 | ✓ | Datasheet-correct GH (1.25 mm) contact, 28–30 AWG, cut-tape MOQ 1. (`MINI-SSHL-…` is a thicker-insulation sibling — not needed) |

**Cart 2 subtotal ≈ $21.50** + a one-time **GH-1.25 crimp tool** (IWISS/Engineer PA-09/PA-21-class
~$25–40; the SHL contacts are too small to hand-pinch). Standalone DigiKey order is
**freight-dominated** (~$30–45 + ~30 % duty) → landed **≈ ₹7,000–8,500**. DigiKey free-freight
>$500; budget DDP at checkout to avoid a customs hold.

> Domestic-substitute fallback (NOT taken — decision #5 chose spec-correct above) is preserved in the
> Appendix in case DigiKey stock/freight becomes a problem.

---

## Cart 3 — Robu.in (domestic, INR) — everything else, one vendor

Robu.in is the broadest single India vendor (motors, lab PSU, E-stop, wire, filament, passives,
bearings, fasteners) → use it to consolidate the whole domestic side. **Robu.in blocks automated
price fetch**, so prices below are snippet/cross-vendor (`~`) — confirm each at checkout. Items I
could verify live on another India vendor are noted with that vendor + price as a sanity check.

### Electrical / motor / power

| BOM | Item | Spec | ~₹ | Qty | Notes / cross-check |
|---|---|---|---:|---:|---|
| motor | **2804 100 KV gimbal BLDC** (GBM2804H-100T class) | 12N**14P** → `--cal-motor-poles 14`; Kv ~100; hollow shaft (Ø7 OD / Ø5 ID); ≤0.8 A load | ~800–1,000 | 1 | **Hollow-shaft** → cycloidal cam bolts to the rotor face, not a shaft (see mechanicals). Robu generic clone bore = **measure on receipt**. Fallback: T-Motor GB2208 (Robokits RKI-3511, ₹2,474, 6 mm bore, Kv 128) |
| #8 | **24 V bench PSU, 0–30 V / 0–10 A (CC/CV)** | adjustable current limit for first power-on at 1–2 A | ~3,000–10,000 | 1 | Cross-check: OWON SPE3102 ₹9,899 (Robocraze, ✓, 5 left). Any CC/CV lab supply ≥24 V/5 A works |
| #9 | **E-stop, 22 mm latching mushroom (NC)** | switch a contactor coil, not full motor current | ~93–250 | 1 | Cross-check: Robocraze YWBL-WH ₹93 (✓). **Verify a usable NC DC contact on receipt** |
| #10 | **XT30 M+F pair** + ~1 m 18–20 AWG silicone wire | +24 V rail through the E-stop to the c1 XT30 | ~270 | 1 | Cross-check: Robocraftstore XT30 10 cm ₹117 (✓) + bulk silicone wire ~₹150 |
| #12 | **28 AWG silicone hookup wire kit** | AUX2 → AS5047P SPI lines | ~536 | 1 | Cross-check: Tenettech TT-RB-R229090 ₹536 |
| #13 | **Dupont jumper set 120 pc** | bring-up SPI breadboarding | ~135 | 1 | Cross-check: Robocraze ₹135 (✓) |
| #14a | **100 nF MLCC 50 V × 20** | AS5047P VDD decoupling | ~22 | 1 | Cross-check: Robocraze ₹22 (✓) |
| #14b | **Resistor assortment** (150 pc / 30 val) | optional SPI pull-up/down | ~45 | 1 | Cross-check: Robocraze ₹45 (✓) |

### Cycloidal mechanicals (now resolved — Faze4 → 9:1, decision #6)

Single-stage 9:1 = **9 disc lobes / 10 ring pins**. Bearings are Faze4 "Tier A" small-bearing sizing
(adequate for a grams payload — the 45/50 mm output rings in larger designs are overkill). Mini
bearings (MR-series) and **hardened** dowels may not be on Robu → **Amazon.in is the single fallback**
for just these (still domestic, fast). All sizes are bore × OD × width (mm).

| BOM | Item | Size / spec | ~₹ ea | Qty | Notes |
|---|---|---|---:|---:|---|
| #15a | **688-2RS** eccentric-cam bearing | 8 × 16 × 5 | ~50–90 | 2 | Load-critical purchase. 2× for anti-phase twin-disc balance |
| #15b | **MR126-2RS** input/output support | 6 × 12 × 4 | ~50–90 | 2 | |
| #15c | **MR63-2RS** ring-pin rollers (optional) | 3 × 6 × 2.5 | ~40–70 | 10 | Optional — or run bare 3 mm steel pins in the PETG ring |
| #16d | **3 mm hardened dowel pins** | DIN 6325, 3 × 16–20 | ~10–25 | 12 | 10 ring pins (P=10) + spares; +5–6 if you use a separate D-type output-pin circle. **Ground/hardened**, not SS304 cut rod (straightness ⇒ backlash) |
| #16a | **M3 SHCS assortment (12.9)** | 8 / 15 / 20 / 25 mm | ~250–450 | ~16 | Housing stack + motor mount |
| #16c | **M3 brass heat-set inserts** | M3×5×4 (Ruthex M3×5.7 equiv) | ~700/100 | 1 pack | Cross-check: dc3d.in ₹700/100 (✓). For PETG housings |
| #16b | **M2.5 SHCS + nut set** | — | ~199–224 | 1 | AS5047P PCB / small brackets |

### Fabrication

| BOM | Item | Spec | ~₹ | Qty | Notes |
|---|---|---|---:|---:|---|
| #17a | **Bambu PETG HF 1 kg** | workhorse: cycloidal disc/ring/cam/carrier + mounts + housing. **2 spools** — you iterate (print→measure backlash→reprint). Mid-tone/matte for visible gear detail. RFID auto-detect in AMS | ~2,000 | 2 | Genuine Bambu — IDEAL3D / 3idea / Robu (bundle w/ the Cart-4 printer order) |
| #17b | **Bambu PLA Basic 1 kg** | printer calibration + fixtures/jigs + test-joint holder — prove out cheap before committing PETG to gears | ~1,750 | 1 | Genuine Bambu; RFID auto-detect in AMS |
| #18 | **Cycloidal reducer print** | self-print from edited Faze4 CAD | ₹0 | — | See CAD-edit note below |

**Cart 3 subtotal (core): ≈ ₹12,500–18,500** (dominated by the bench PSU; ±the PSU model you pick;
incl. ~₹5,750 Bambu filament). Without a bench PSU (if one is acquired elsewhere): ≈ ₹9,500–10,500.

---

## Cart 4 — Bambu Lab P2S Combo (domestic, capital tool)

Required to fabricate the cycloidal reducer + motor/encoder mounts + joint housing (BOM #17/#18 are
self-printed). One-time tool, used across **all** phases — not a per-joint consumable, hence its own
line outside the joint subtotal.

| Item | Spec | ~₹ | Qty | Notes |
|---|---|---:|---:|---|
| **Bambu Lab P2S Combo** (w/ AMS 2 Pro) | enclosed CoreXY, 256³ build, 300 °C hotend, hardened nozzle, ~50 °C chamber, 4-filament AMS | ~1,02,999 | 1 | **IDEAL3D** (ideal3d.in) — **authorized** Bambu dealer, in stock, Chennai (local service). Get DOA/return window in writing + warranty registered to the serial. Avoid 3Ding (not on Bambu's authorized list → warranty risk) |

> **AMS routing for this project:** print PETG structure via the AMS or external spool (either is
> fine); feed **TPU (Fin-Ray fingers) and any PA-CF/PA6-GF gears from the EXTERNAL spool, bypassing
> the AMS** — flexibles jam the AMS path and abrasives wear it. The AMS is for PLA/PETG.
>
> Deferred (do NOT buy for Phase 1): high-temp filament dryer + PA-CF/PA6-GF filament — only if you
> later upgrade the gears past PETG. The AMS 2 Pro dries to ~65 °C (good for PETG/PLA, **not enough
> for nylon** → still need the dedicated 70–90 °C dryer). PETG (in Cart 3) is all Phase 1 needs.
> TPU (Fin-Ray fingers) is a Phase-4 item, not Phase 1.

---

## Cart 5 — Phase-1 bench tools (domestic: Amazon.in primary / Robu.in)

Full toolbox assumed empty. Consolidated to **11 line items** (from 16 tools) via one no-junk
soldering kit; tool "header pins / encoder leads" needs **no buy** — solder the AS5047P leads
directly to the Cart-3 28 AWG silicone wire. Amazon.in/Robu block automated fetch → prices are
snippet/cross-vendor (`~`); verify at checkout.

| Covers | Item / SKU | ~₹ | Conf | Notes |
|---|---|---:|:--:|---|
| iron+solder+flux, cutters+stripper, tweezers, heat-shrink, insert-tip | **Plusivo Soldering Kit w/ Diagonal Cutter** (220–230 V **India plug**) | ~1,300 | ~ | Box: 60 W adjustable iron + stand, 5 tips (incl. conical → seats heat-set inserts), solder, flux/paste, desolder pump, diagonal cutter + mini stripper, 2× ESD tweezers, heat-shrink kit, hookup wire. **Buy the India-plug variant, not 110 V.** No junk padding |
| helping hands | **PCB holder / helping-hands** (third-hand) | ~600 | ~ | For the small AS5047P board while soldering |
| multimeter | **Meco 108B+ TRMS** (6000-count) | ~1,550 | ✓ | Needs true low-Ω + lead-null to read ~14 Ω motor phase R; bottom-tier ₹250 meters can't. Cheaper alt: Kusam-Meco KM-108 ~₹1,200 |
| hex keys | **Taparia KBHM 9L** ball-end set | ~725 | ✓ | Includes 2.0 / 2.5 / 3.0 mm for the M2.5/M3 SHCS |
| thread-locker | **Loctite 243** (blue, 10 mL) | ~550 | ~ | Removable; eccentric/motor set screws |
| calipers | **Generic 150 mm digital caliper** (0.01 mm) | ~1,200 | ~ | Cycloidal clearances/backlash/bore/magnet. Genuine Mitutoyo 500-196-20 ~₹8–9.5k if you want certified accuracy (display res is enough for assembly) |
| angle gauge | **Magnetic digital angle gauge** (±0.2°, 4×90°) | ~1,600 | ~ | Step-6 ±1° physical accuracy check; magnetic base sticks to a steel joint face |
| feeler gauges | **32-blade feeler set** (0.02–1.0 mm) | ~320 | ✓ | Sets the 0.5–2.5 mm AS5047P air gap (stack blades >1 mm) |
| magnifier | **Headband LED magnifier** (interchangeable lenses) | ~550 | ✓ | GH crimps + board soldering |
| ESD | **ESD wrist strap + anti-static mat combo** | ~850 | ~ | moteus + AS5047P are static-sensitive |
| USB-C cable | **USB-C↔USB-C, 1 m, DATA-rated** | ~350 | ✓ | mjcanfd-usb-1x USB-CDC enumeration — **must be data-capable, not charge-only** |

**Cart 5 subtotal ≈ ₹9,545** (generic caliper) / **≈ ₹17,000** (genuine Mitutoyo caliper).
Already covered elsewhere: GH-1.25 crimp tool (Cart 2); AS5047P encoder leads → Cart-3 silicone wire.

---

## Cycloidal CAD — order-ready vs needs-editing (decision #6)

Adopt **Faze4** (github.com/PCrnjak/Faze4-Robotic-arm) — single-stage, wrist-scale, editable disc
STEP + full BOM, built on small India-stock bearings + 3 mm steel dowels. Re-cut its 11:1 wrist disc
to **9:1 (9 lobes / 10 pins)**.

- **Order-ready now (no CAD):** all Cart-3 bearings, 3 mm hardened dowels, M3 SHCS + M3 inserts.
- **Requires CAD editing (Fusion/SolidWorks on the provided STEP):**
  1. Regenerate the cycloidal disc to **9 lobes / 10 ring pins** at the chosen pin-circle/pin dia.
  2. Replace the NEMA 5 mm-shaft eccentric with a **cam that bolts to the gimbal-motor outrunner
     rotor face** (the 2804 is hollow-shaft — you drive through the rotor bell, and the Ø5 bore is
     free for a coaxial output-encoder through-shaft if desired). Eccentricity carries from the disc
     generator; seat the **688 (Ø8)** race on the offset.
  3. Re-cut the housing motor face from the NEMA bolt pattern to the **28 mm-stator gimbal boss**.
  4. Add a **6 mm dia × 2.5 mm diametric AS5047P magnet pocket** on the output axis (copy OpenCyRe's
     integrated-encoder geometry — hackaday.io/project/168498 — as the reference).
- **Rejected references:** OpenCyRe (no BOM, NEMA-belt input — but mine it for the encoder-mount
  geometry), timxuti (great 11:1 but needs its custom-wound motor), Skyentific (paywalled, planetary
  not cyclo), Printables 9:1 NEMA17 (all-plastic, no pins/encoder — ratio sanity-check only).

---

## Rough grand total — one Phase-1 joint (3 carts)

| Cart | Source | Est. landed |
|---|---|---:|
| 1 | mjbots (moteus stack) | ≈ ₹17,000 |
| 2 | DigiKey (encoder front-end + crimp tool) | ≈ ₹7,000–8,500 |
| 3 | Robu.in (motor, PSU, mechanicals, Bambu filament, passives) | ≈ ₹12,500–18,500 |
| | **JOINT PARTS — 2 imports + 1 domestic** | **≈ ₹36,500–44,000 (~$385–465)** |
| 4 | Bambu Lab P2S Combo, IDEAL3D (one-time tool, all phases) | ≈ ₹1,02,999 |
| 5 | Amazon.in/Robu (one-time bench tools) | ≈ ₹9,500–17,000 |
| | **TOTAL incl. printer + tools** | **≈ ₹1,49,000–1,64,000 (~$1,570–1,725)** |
| | *memo: if a 24 V supply is acquired free/elsewhere* | *−₹9,900* |

**Cost drivers:** the P2S printer (one-time, ₹72k), the bench PSU, moteus-c1 + adapter
($108 ≈ ₹10,300), and import freight/duty (two parcels). The cycloidal mechanicals + bench tools add
modestly; the tools and printer are one-time (amortize across all six joints / all phases).

---

## Appendix A — domestic encoder-substitute (FALLBACK, not taken)

Decision #5 chose the spec-correct DigiKey path (Cart 2). If DigiKey stock/freight becomes a problem,
this collapses to **one import (mjbots only)** by sourcing the encoder front-end in India:

| Replaces | Buy | Vendor / link | ₹ | Critical note |
|---|---|---|---:|---|
| Cart 2 AS5047P | **NMotion NCoder5047** | Amazon.in `B0992F16QQ` | ~700–1,500 | Datasheet-confirmed **3.3 V + exact SPI pinout**. Magnet NOT bundled |
| Cart 1 #7 magnet | **Patel D-6-3-N52-D** (6×3 mm) | patelmagnets.com | 115 | Must be **"Magnetization Direction: Diameter"** (diametric, not axial) |
| Cart 2 GH-7 | **JST-GH 1.25 kit** (7-pin housing + pre-crimped leads, no tool) | Amazon.in `B0CKZCFC54` / `B0D796WG12` | ~999 | Must say **"JST-GH 1.25"** (not "JST-XH 1.25" — XH is 2.5 mm, won't latch) |

Spec-safe domestic combo ≈ ₹2,300, no crimp tool — but the generic boards vary (some 5 V-only); the
spec-correct ams board is the reason decision #5 kept the DigiKey parcel.

## Appendix B — semikart.in (does NOT consolidate this build)

semikart aggregates Mouser/TME/element14 feeds (INR+GST) but (1) every `/product/` page is
DataDome bot-blocked — no live price/stock readable; (2) it's missing the two parts that matter —
**GHR-07V-S** is not listed (only 03V/09V) and the **AS5047P solder-ready breakout** URL is dead
(only the bare TSSOP-14 IC). Keep the 3-cart plan; semikart adds nothing here.

> Re-validate every price at checkout; this is a dated snapshot. India-local prices marked `~` are
> snippet/cross-vendor because Robu.in blocks automated fetch — open the listing to confirm.
