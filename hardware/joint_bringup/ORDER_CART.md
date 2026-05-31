# Order Cart — Phase-1 Single Wrist-Class Joint

**Price snapshot: 2026-05-31.** FX used: **USD→INR ≈ 95.0** (xe.com live, cross-checked).
Quantities are for **ONE bench joint** (the Phase-1 scope), not the full 6-joint arm.

> **Confidence key:** ✓ = read live on the product page today · ~ = snippet / cross-vendor / approx
> (Robu.in blocks automated fetch, so its prices are unconfirmed) · ✗ = unverified placeholder / CAD-pending.
> Prices and stock move without notice — re-check at checkout.

---

## ✅ Decisions made (2026-05-31)

1. **CAN adapter → `mjcanfd-usb-1x` ($39).** ADOPTED in place of the discontinued `fdcanusb` (same
   JST-PH3 moteus pinout, USB-C). §3 / BOM / kit docs updated. The moteus python transport stays
   `moteus.Fdcanusb` (the fdcanusb *protocol*, spoken by the mjcanfd-usb-1x in virtual-serial mode),
   so the bring-up scripts are unchanged; socketcan is the alt. Enumerates as `/dev/ttyACM*`.
2. **GH-7 AUX2 connector → IMPORT** (sold out at mjbots, not on semikart): GHR-07V-S housing + GH
   crimp contacts from **DigiKey/Mouser**. *(Exact PNs/prices being finalized — see Cart A.)*
3. **AS5047P breakout → IMPORT** (scarce in India, semikart only has the bare IC): solder-ready
   breakout from **DigiKey/Mouser** (ams adapter board) or Amazon US. *(Exact PN/price being
   finalized — see Cart A.)*
4. **Bench PSU → INCLUDE** the OWON SPE3102 (₹9,899) — no bench supply on hand. It's in the total.

---

## Cart A — Imports (USD): mjbots + DigiKey

### A1 · mjbots (the moteus stack — sole source)

| BOM | Item | Handle | Unit | Qty | Line | Conf | Notes |
|---|---|---|---:|---:|---:|:--:|---|
| #1 | moteus-c1 FOC controller | `moteus-c1` | $69.00 | 1 | $69.00 | ✓ | 630 in stock. **Box includes** XT30 mate + JST-PH3 housing (w/ crimps) + 1/4″ diametric **rotor** magnet |
| #2 | mjcanfd-usb-1x USB↔CAN-FD | `mjcanfd-usb-1x` | $39.00 | 1 | $39.00 | ✓ | 634 in stock. fdcanusb successor |
| #3 | JST-PH3 CAN-FD terminator (120 Ω) | `jst-ph3-can-fd-terminator` | $5.00 | 1–2 | $5–10 | ✓ | 1 at the c1 far end; buy **2** unless the mjcanfd-usb-1x integrates host-end termination (VERIFY) |
| #7 | Diametric sense magnet 6×2.5 mm N35SH | `diametric-disc-magnet` | $1.50 | 5 | $7.50 | ✓ | output-shaft AS5047P magnet. **Skip if** you pick an AS5047P board that bundles a magnet (see A2 note) |

**A1 subtotal ≈ $120.50–125.50.**

### A2 · DigiKey (GH-7 connector + AS5047P breakout — the mjbots/India gaps)

| BOM | Item | Mfr PN | DK PN | Unit | Qty | Line | Conf | Notes |
|---|---|---|---|---:|---:|---:|:--:|---|
| #4 | JST GH-7 housing | GHR-07V-S | 455-1597-ND | $0.15 | 3 | $0.45 | ✓ | **0 stock today** (Active/backorder) → verify at order time or use Mouser. Cheap → buy spares |
| #4 | JST GH crimp contact | SSHL-002T-P0.2 | 455-1606-1-ND | $0.11 | 15 | $1.65 | ✓ | Datasheet-correct GH contact (28–30 AWG), cut-tape MOQ 1. (`MINI-SSHL-002T-P0.2` / 455-1607-1-ND is a thicker-insulation sibling — not needed) |
| #6 | AS5047P adapter board (solder-ready) | AS5047P ADAPTERBOARD (`AS5047P-TS_EK_AB`) | 4991-AS5047PADAPTERBOARD-ND | $19.40 | 1 | $19.40 | ✓ | 416 in stock, Active (constrained, no backorder). 3.3 V jumper; **magnet NOT incl** (use #7). Fixture the flat PCB over the magnet |

**A2 subtotal ≈ $21.50** + a one-time **GH-1.25 crimp tool** (JST WC-160 is pricey; an IWISS/Engineer
PA-09/PA-21-class crimper ~$25–40, or source locally) — the SHL contacts are too small to hand-pinch.

> **Avoid the 2nd import parcel (recommended):** A2's goods are only ~$21 but a standalone DigiKey
> order is **freight-dominated** (~$30–45 + ~30 % duty). To skip it entirely:
> - **AS5047P:** a domestic **Amazon.in** breakout (ASIN B0DLJ6XDNM, ~₹1,000–1,500, **includes a
>   magnet** + right-angle pins) or the **Tindie SmallRobots AS5047P board** ($17, SPI + ABZ,
>   **includes a 6×2.5 mm magnet**) — either removes the DigiKey board **and** the mjbots #7 magnet.
>   Verify clean SPI + 3.3 V operation before relying on it.
> - **GH-7 cable:** a **Pixhawk-style GH 1.25 mm 7-pin pre-crimped cable** (Amazon.in / Robu,
>   domestic) — no crimp tool, no DigiKey. Confirm it is 7-pin GH1.25.
>
> The spec-correct path is A2 as listed; the domestic path is cheaper and faster to India.

**Cart A landed (two import parcels):** A1 (mjbots ~$120) + intl ship (~$30–50) + ~18 % IGST/customs
→ **≈ $180 (₹17,000)**; A2 (DigiKey ~$21 + crimp tool), freight-dominated → **≈ $70–90
(₹6,500–8,500)** unless you take the domestic path below. DigiKey free-freight >$500; budget DDP at
checkout to avoid a customs hold.

### A3 · Domestic-optimized substitutes (skip the DigiKey A2 parcel) — where to buy in India

All URLs verified to resolve (zero fabricated listings); Amazon.in/Flipkart prices marked `~` are
estimates (Amazon.in blocked the live price read — confirm at checkout).

| Replaces | Buy (recommended) | Vendor / link | ₹ | Conf | Critical note |
|---|---|---|---:|:--:|---|
| #6 AS5047P board | **NMotion NCoder5047** | Amazon.in `B0992F16QQ` | ~700–1,500 | spec ✓ / price ~ | Datasheet-confirmed **3.3 V + exact SPI pinout** (no 5 V risk). Magnet NOT bundled → buy magnet below |
| #7 magnet | **Patel D-6-3-N52-D** (6×3 mm) | patelmagnets.com | 115 | ✓ | Must be the **"Magnetization Direction: Diameter"** part — Patel's lookalike 6×3 **axial** disc (~₹15) will NOT work |
| #4 GH-7 connector | **JST-GH 1.25 kit** (7-pin housing + pre-crimped leads → push-in, no tool) | Amazon.in Kidisoii `B0CKZCFC54` or JTSINERU `B0D796WG12` | ~999 | spec ✓ / price ~ | Must say **"JST-GH 1.25"**. Avoid the flyrobo "JST-**XH** 1.25" 7-pin lead (mislabeled — XH is 2.5 mm; may not latch in the GH-7 socket) |
| crimp tool | **PEBA Micro** (optional) | Amazon.in `B0D7PKLBZT` | ~1,200–2,200 | spec ✓ / price ~ | Rated "GH 1.25 / AWG 32–22" (genuinely fits, not a Dupont tool). **Not needed** with the pre-crimped GH kit |

- *Flipkart Meukron AS5047P (`itmaf7be6956a2c4`, **₹1,227** live-confirmed, includes a diametric
  magnet)* is the only board with a confirmed price + bundled magnet — **but its spec sheet says 5 V**,
  no explicit 3.3 V → verify 3.3 V/regulator before trusting it on the moteus AUX2 bus.

**Domestic combo total (spec-safe): NCoder5047 (~₹1,200) + Patel magnet (₹115) + GH kit (~₹999) ≈
₹2,300, no crimp tool** — replaces the entire A2 DigiKey parcel (₹6,500–8,500) **and** the mjbots #7
magnet. (Robu/Robocraze/ThinkRobotics/Robokits/IndiaMART carry no AS5047P breakout, confirmed.)

---

## Cart B — India-local (INR)

| BOM | Item | Vendor | SKU | Unit ₹ | Qty | Line ₹ | Conf | Notes |
|---|---|---|---|---:|---:|---:|:--:|---|
| motor | T-Motor GB2208 125 KV gimbal | Robokits | RKI-3511 | 2,474 | 1 | 2,474 | ~ | 12N14P, 125 KV — spec ✓. Price ₹2,474 (page 403; ₹2,448 in notes unverified). Hollow shaft → needs printed rotor adapter |
| #8 | 24 V bench PSU 0–30 V/0–10 A (CC/CV) | Robocraze | OWON SPE3102 | 9,899 | 1 | 9,899 | ✓ | Only 5 left. Included per decision #4 (no supply on hand) |
| #9 | E-stop, 22 mm latching mushroom | Robocraze | YWBL-WH | 93 | 1 | 93 | ✓ | **Verify a usable NC contact on receipt** (page says "DPST", AC-rated); for DC, switch a contactor coil, not full motor current |
| #10 | XT30 M+F pair w/ 10 cm 14 AWG leads | Robocraftstore | XT30 M+F 10cm | 117 | 1 | 117 | ✓ | Leads only 10 cm → also buy ~1 m 18–20 AWG silicone wire |
| #10b | 18–20 AWG silicone wire ~1 m (PSU rail) | Robu/local | — | ~150 | 1 | ~150 | ✗ | Bulk lead for the +24 V/GND rail through the E-stop |
| #12 | 28 AWG silicone hookup wire kit (25 m) | Robu.in | TT-RB-R229090 | 536 | 1 | 536 | ~ | AUX2→AS5047P SPI lines. Price via Tenettech (same SKU); Robu 403 |
| #13 | Dupont jumper set 120 pcs | Robocraze | — | 135 | 1 | 135 | ✓ | Bring-up/breadboard SPI lines. 50 in stock |
| #14a | 100 nF MLCC 50 V × 20 | Robocraze | 100KPF pack | 22 | 1 | 22 | ✓ | AS5047P VDD decoupling (dielectric not stated X7R; fine for decoupling) |
| #14b | Resistor assortment 150 pc / 30 val | Robocraze | resistor-box | 45 | 1 | 45 | ✓ | Optional SPI pull-up/pull-down |
| #16c | M3 brass heat-set inserts × 100 | dc3d.in | M3×5×4 mm | 700 | 1 | 700 | ✓ | For PETG joint housings (useful regardless of CAD) |
| #17 | eSUN PETG 1.75 mm 1 kg | Robu.in | eSUN PETG 1kg | 1,344 | 1 | 1,344 | ~ | Structure + gears starter. Snippet price; Robu 403 |

**Cart B subtotal (core, as above): ≈ ₹15,515.**
**Without the bench PSU (if already owned): ≈ ₹5,616.**
*(The AS5047P breakout moved to Cart A2 imports — DigiKey ams board, or the domestic Amazon.in /
Tindie alternative noted there.)*

*Optional / spares (not in subtotal):* #11 JST-PH crimp kit (Robocraze, **₹1,399** ✓) — **only if** you
need a custom CAN harness or spares; the c1 box already ships one PH-3 housing. ⚠️ live page shows a
PH-2.0-vs-XH-2.54 pitch inconsistency — **verify 2.0 mm pitch** before relying on it; only 2 left.

---

## Deferred — CAD-pending (do NOT order until the cycloidal reducer CAD #18 is chosen)

Exact bore/OD/width, screw lengths, dowel sizes, and per-joint quantities depend on the chosen
reference CAD (Faze4 / OpenCyRe / Skyentific). Representative picks + ballparks only:

| BOM | Item | Representative | Ballpark ₹ | Conf | Notes |
|---|---|---|---:|:--:|---|
| #15 | Cycloidal-stage bearings | 6802ZZ 15×24×5 (NSK, RS India) | 2,531/ea ✓ but **OOS** | ✗ | NSK is 30–50× generic; for proto use generic 6802ZZ (Amazon.in ~₹50–90 ea). Final sizes from CAD |
| #16a | M3 SHCS assortment (12.9) | Robu 100-pc kit | ~250–450 | ✗ | Robu 403; price unverified. CAD-pending lengths |
| #16b | M2.5 SHCS + nut set | EasyMech 12-pc | ~199–224 | ~ | For the encoder PCB / small brackets |
| #16d | Dowel pins ~3 mm **hardened** | DIN 6325 (MISUMI/Unbrako) | TBD | ✗ | **Spec gap:** local EasyMech is SS304 (not hardened/ground). Use DIN 6325 for real locating duty |
| #18 | Cycloidal reducer (~9:1) | **self-print, PETG** | ₹0 | — | Print from Faze4/OpenCyRe/Skyentific CAD; confirm 9:1 lobe count + motor bore first |

---

## Semikart.in check (2026-05-31) — does NOT consolidate this build

semikart.in aggregates global-distributor feeds (Mouser/TME/element14) with INR+GST, but it fails
on two counts here:

1. **Un-priceable by automated check:** every `/product/` page returns a DataDome "Confirm you are
   not bot" challenge — no live price/stock/MOQ/lead readable. Items are mostly re-sold import feeds
   (TME Poland, Mouser US) → import lead time + often request-a-quote.
2. **Missing the two parts that matter:** **JST GHR-07V-S** (the 7-pin AUX2 housing, sold out at
   mjbots) is NOT listed (only GHR-03V-S / GHR-09V-S); the **AS5047P solder-ready breakout**
   (`AS5047P-TS_EK_AB`) is a DEAD URL — only the **bare IC** (`AS5047P-ATSM`, TSSOP-14, needs a
   custom PCB) is listed. Neither gap is closed.

| BOM | On semikart? | Verdict |
|---|---|---|
| #4 GH-7 housing (GHR-07V-S) | ✗ not listed | DigiKey/Mouser or SemiNest.in |
| #4 GH contact | ~ MINI-SSHL-002T-P0.2 listed (unread) | use DigiKey `SSHL-002T-P0.2` (datasheet-correct GH contact); MINI is a thicker-insulation sibling |
| #11 CAN PHR-3 + SPH-002T | ✗ not listed | c1 box has a PH-3; else Robocraze/DigiKey |
| #10 XT30PW-M/F | ~ listed (import feed, unread) | cheaper/faster at Robocraftstore (₹117) |
| #6 AS5047P breakout | ✗ (only bare IC; breakout URL dead) | import breakout (Mouser/DigiKey/Amazon US) |
| #14a 100 nF | ~ proper X7R listed (MOQ-reel risk) | Robocraze ₹22 fine |
| #14b resistors | ✗ (URLs fabricated; MPNs real) | Robocraze ₹45 |
| #8 bench PSU | ~ weak (36V/5A; one hit was an LCR meter) | OWON SPE3102 (₹9,899) better |
| #9 E-stop | ~ industrial IDEC, discontinued, ~₹6.9k | local 22 mm mushroom (₹93) far better |
| #1 c1 · motor · #7 magnet · #17 filament · #15 bearings · #16 fasteners | ✗ structurally absent | keep mjbots / Robokits / 3Ding |

**Conclusion:** keep the multi-vendor cart above; semikart adds nothing for this build.

---

## Rough grand total — one Phase-1 joint

| Bucket | Est. |
|---|---:|
| Cart A1 — mjbots landed (goods ~$120 + ship + ~18 % duty) | ≈ ₹17,000 |
| Cart A2 — DigiKey landed (GH-7 + AS5047P board + crimp tool; freight-dominated) | ≈ ₹7,000–8,500 |
| Cart B — India-local core (incl. ₹9,899 bench PSU) | ≈ ₹15,515 |
| **TOTAL — spec-correct path (2 import parcels)** | **≈ ₹40,000 (~$420)** |
| **TOTAL — domestic-optimized (AS5047P + GH cable bought in India, no DigiKey parcel)** | **≈ ₹33,000 (~$350)** |
| *memo: if you already owned a 24 V supply* | *−₹9,900 → ₹23k–30k* |

You chose to include the PSU (no supply on hand), so the with-PSU totals apply.

**Cost drivers:** the bench PSU (₹9,899), moteus-c1 + adapter ($108 ≈ ₹10,300), and import
freight/duty (two parcels — collapsing to one via the domestic path saves ~₹6–7k). The CAD-pending
mechanical parts add only a few hundred ₹ once sized; connectors/passives are noise.

> Re-validate every price at checkout; this is a dated snapshot. Most India-local prices marked `~`
> are snippet/cross-vendor because Robu.in blocks automated fetch — open the listing to confirm.
