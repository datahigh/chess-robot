# Chess-Playing Robot Arm — Build Blueprint

A from-scratch, 6-DOF articulated robot arm that plays physical chess against you on an
**unmodified** board with **standard pieces**, using a camera to read your moves and
Stockfish to decide its own.

---

## 1. The architecture you chose

| Decision | Choice | Why |
|---|---|---|
| Manipulator | Articulated **6-DOF arm**, built from scratch | Most capable / most "real robot" |
| Joint actuation | **BLDC motors + cycloidal reducers** | Smooth, precise, quiet |
| Motor control | **Off-the-shelf FOC drivers** (moteus / ODrive) over CAN-FD | Reliable, mature, less risk than custom FOC |
| Robotics software | **ROS2 + MoveIt2** (IK, planning, sim) | Industry-standard, well-supported |
| Move detection | **Overhead camera + classic computer vision** | No board/piece modification |
| End-effector | **Adaptive (Fin Ray) fingers** + one servo | Tolerates camera/placement error |
| Brain | **Raspberry Pi 5 (8GB) + active cooler** | Runs the whole stack; speed is a non-issue |
| Chess engine | **Stockfish** (UCI), strength-limited | Strongest open engine, adjustable to be beatable |

**Guiding principle:** optimal / reliable / efficient first, learning second.

---

## 2. How one move works (the end-to-end loop)

1. **You move** a piece and press a "my-move-done" button (or tap the screen).
2. **Vision** captures the board and compares it to the previous state → finds which
   squares changed.
3. **Chess logic** (python-chess) matches the changed squares against the list of *legal*
   moves → uniquely identifies your move (this is what makes vision easy — the engine
   constrains the answer).
4. **Stockfish** receives the updated position and returns its reply within a fixed time
   budget (e.g., 0.5 s) at your chosen strength.
5. **MoveIt2** plans a collision-free pick-and-place trajectory (plus a capture-clearing
   move first, if needed).
6. **ros2_control → CAN-FD → FOC drivers** execute the joint trajectory; the **adaptive
   gripper** lifts and places the piece.
7. **Vision verifies** the arm's move landed correctly, then waits for you again.

The compute steps take tens-to-hundreds of milliseconds; the visible move time is
dominated by the **physical arm motion (a few seconds)**, identical regardless of the brain.

---

## 3. Subsystem designs

### 3a. Mechanical (the arm)

- **Configuration:** classic 6-axis — J1 base yaw, J2 shoulder pitch, J3 elbow pitch,
  J4 forearm roll, J5 wrist pitch, J6 wrist roll.
- **Reach:** a standard tournament board is ~50 × 50 cm (≈5.7 cm squares). Mount the arm
  behind/beside the board with a small **capture "graveyard" zone** to one side. Target
  **~500–650 mm reach** so the farthest corner + the graveyard are comfortably inside the
  workspace (comparable to Thor ≈625 mm or AR4 ≈600 mm).
- **Payload is tiny:** chess pieces weigh tens of grams, so torque/payload requirements are
  modest — this lets you use **small gimbal BLDC motors** and **modest cycloidal ratios**,
  keeping cost and mass down. The gravity joints (J2, J3) need the most torque.
- **Structure:** 3D-printed links (PETG for stiffness/heat tolerance; PLA acceptable for a
  desktop unit). Print cycloidal gearboxes in PETG with good tolerances.

**Proven reference designs to adapt instead of starting from a blank sheet:**
- **Atlas** (Damian Lickindorf) — 6-DOF with 3D-printed **hollow-shaft cycloidal reducers**
  ("OpenCyRe"), ODrive BLDC + CAN, heading into ROS/MoveIt. Closest match to your spec.
  → hackaday.io/project/168259
- **Faze4** (Petar Crnjak / Source Robotics) — 6-axis with mature **3D-printed cycloidal
  gearboxes** (steppers, but the gearbox CAD is excellent). → github.com/PCrnjak/Faze4-Robotic-arm
- **CM6** (CMI Robotics) — 6-axis **quasi-direct-drive BLDC** with low-ratio gearboxes.
  → hackaday.io/project/180588
- **Skyentific** (YouTube) — superb tutorials on building BLDC/cycloidal robot actuators.

### 3b. Actuation & electronics

- **Motors:** 6× small **gimbal BLDC** motors (high pole count = smooth at low speed),
  e.g., a GBM/GIM-class motor or the mjbots `mj5208`. Sized to the (light) joint torques.
- **Reducers:** 6× **3D-printed cycloidal** drives (10:1–40:1 depending on joint).
  > Design note: high-ratio cycloidal is *not* easily backdrivable — but for chess you want
  > **precision and stiffness, not compliance**, so that's exactly right here. (This is the
  > opposite trade-off from a human-collaborative arm.)
- **FOC drivers:** **moteus-c1** is the sweet spot — ~$69 each, 38×38 mm, CAN-FD, integrated
  absolute magnetic encoder, open firmware, C++/Python/Arduino libraries. (Alternatives:
  moteus-n1/r4.11 for more current, or **ODrive S1 / ODrive Micro**.) One driver per joint.
- **Absolute joint angle (no homing dance):** the driver's onboard encoder reads the
  *motor* shaft. Add a cheap **output-side magnetic encoder** (AS5047 / MT6701 + a magnet)
  per joint on the driver's AUX input so the arm knows its true joint angles at power-on
  ("instant cold start"). ODrive's dual-encoder support does the same. (Simplest fallback:
  homing limit switches at startup.)
- **Pi ↔ motors bridge:** an **fdcanusb** (USB ↔ CAN-FD) adapter is the simplest — all six
  drivers sit on one daisy-chained CAN-FD bus (plenty for chess move rates). The **mjbots
  pi3hat** is an alternative if you want multiple buses + an IMU on the Pi.
- **Gripper:** Fin Ray fingers (TPU) on **one hobby/geared servo**, driven via a **PCA9685**
  servo board (I²C) from the Pi, or a spare Pi PWM pin.
- **Power:** a **24 V, ~10 A** PSU for the motor bus; the Pi runs from its own 5 V/5 A USB-C
  supply.
- **Safety (do not skip):** a hardware **E-stop** that cuts motor-bus power, conservative
  per-joint current/velocity limits in the driver config, and software workspace limits so
  the arm can never reach off the table or into itself.

### 3c. Compute & software

- **OS:** Ubuntu 26.04 (ARM64) on the Pi 5 → **ROS2 (Lyrical Luth, Tier-1 LTS for 26.04)** + **MoveIt2**.
- **ROS2 node graph:**
  - `vision_node` — camera → board state → detected move (OpenCV).
  - `chess_brain_node` — python-chess board + Stockfish (UCI); turns detected move into the
    engine's reply and a target square.
  - `arm_controller` — uses **MoveIt2** to plan pick-and-place; commands joints via
    **`ros2_control`**.
  - `hardware_interface` — *the one piece of low-level code you write*: a `ros2_control`
    plugin whose `read()` pulls joint angles from the encoders over CAN-FD and `write()`
    sends position/torque targets to the moteus drivers. (You are **not** rebuilding ROS2 or
    MoveIt2 — just this adapter.)
- **Simulation first:** build the arm's **URDF** and validate motion in **RViz/Gazebo**
  before any hardware exists.

### 3d. Vision (the part that lets you keep standard pieces)

- **Camera:** a fixed **overhead camera** on a frame looking straight down at the board —
  Raspberry Pi Camera Module 3 (autofocus) or a decent USB webcam. A global shutter is *not*
  needed because the scene is static between turns.
- **Calibration (once):** camera intrinsics via a checkerboard; then a **homography** from
  the four board corners → a clean top-down 8×8 grid.
- **Per-turn detection:** capture before/after your move, diff each square (brightness /
  occupancy / mean colour) → identify the **changed squares**.
- **Move inference:** feed the changed-square pattern to python-chess and match against the
  current **legal moves**. Because only legal moves are possible, the pattern almost always
  resolves to a single move. This cleanly handles:
  - normal move (from empties, to fills),
  - **capture** (destination changes colour),
  - **castling** (king+rook, 4 squares — matches one legal castling move),
  - **en passant** (3 squares change),
  - **promotion** (destination piece changes — default to queen, or prompt you).
- **Self-verification:** after the arm moves, re-read the board to confirm its own piece
  landed on the right square before handing the turn back.
- **You never have to classify piece *type* by vision** — the engine tracks identities from
  the opening position. That's what keeps this tractable with unmodified pieces.

### 3e. Chess logic

- **Stockfish** via UCI; **python-chess** maintains the authoritative board and supplies
  legal moves + special-move handling.
- **Make it beatable:** `setoption name UCI_LimitStrength value true` +
  `setoption name UCI_Elo value <1320–3190>`, or `Skill Level 0–20`, and cap thinking time
  (`go movetime 500`). Stockfish runs comfortably on the Pi 5.

### 3f. Fabrication & materials (3D printing)

The 3D printer is **required** for this build — it produces almost the entire arm. A
well-calibrated FDM machine matters more than an expensive one; the cycloidal gears are the
most tolerance-sensitive parts you'll print.

**What prints in what material:**

| Part | Material | Why |
|---|---|---|
| Cycloidal discs, pin-ring, eccentric cam, output carrier | PETG (PETG-CF / nylon for durability) | Stiff, low-creep, handles meshing loads + heat near motors |
| Arm links / housings (base, shoulder, upper arm, forearm, wrist) | PETG | Stiff and heat-tolerant; better than PLA near motors |
| Motor & encoder mounts, magnet holders | PETG | Dimensional stability keeps alignment |
| Fin Ray gripper fingers | TPU (~95A) | Flexibility *is* the compliance that absorbs placement error |
| Camera mount, graveyard tray, jigs, cable guides | PLA or PETG | Non-structural; PLA is fine here |

**Print-tolerance tips for the cycloidal drives (the make-or-break parts):**
- **Calibrate first** — dial in flow / extrusion multiplier and run a tolerance test before
  printing gears; cycloidal meshing is unforgiving of over-extrusion.
- **Tune XY size compensation** ("horizontal expansion") so pin holes and disc lobes hit spec
  — FDM printers tend to print holes undersized.
- **Layer height 0.1–0.15 mm** on gear faces, **≥3 perimeters**, **40–60% infill** for stiffness.
- **Print gears flat** (lobe profile in the XY plane) so layer steps don't degrade the tooth
  geometry.
- **Use real bearings** at the cam/output and **steel dowel pins** for the ring where loads
  concentrate — don't rely on printed pins there.
- **Expect iteration** — print one joint's gearbox, measure backlash, adjust clearances,
  reprint; get one perfect before replicating six.
- **Optional upgrade** — PETG-CF or nylon (PA-CF) noticeably improves gear stiffness and
  longevity if you want it.

**Recommended printer:**
- **Bambu Lab P2S** *(recommended)* — an enclosed CoreXY (256 mm³ build, 300 °C hotend,
  hardened steel nozzle + extruder gear as standard, ~50 °C adaptive heated chamber). It
  prints PETG and TPU effortlessly **and** handles engineering filaments — nylon and
  carbon/glass-filled (PA-CF, PA6-GF, PET-CF) — out of the box, so you can print the cycloidal
  gears in stiffer, lower-creep, more wear-resistant material for accuracy that holds up over
  many games. The Combo adds an AMS with active filament drying (useful — nylon is
  hygroscopic). ~₹72,000 standalone / ~₹100,000 Combo; stocked by Indian Bambu dealers
  (3Ding, 3idea).
- **Bambu Lab A1** *(budget option)* — open-frame, ~₹30,000–40,000. Prints PETG and TPU
  beautifully, which is **all this build strictly needs**; it just can't reliably do nylon/CF
  (the open frame warps), so you'd keep the gears in PETG and re-check backlash a bit more
  often over the arm's life.
- **Either way, start with PETG gears.** Only move to PA-CF/PA6-GF if you want maximum
  precision-retention — that capability is the main reason to choose the P2S over the A1.

**If you go the nylon/CF gear route — drying matters:**
- The AMS (including the Combo's AMS 2 Pro) only dries to ~65 °C, which **cannot fully dry
  nylon/PA-CF/GF** (those need ~75–80 °C). Pair the printer with a **dedicated high-temp
  filament dryer** (~₹5,000–10,000, reaches ~70–90 °C) for the gear material.
- **Workflow:** dry the nylon in the dedicated dryer, then feed it **straight into the printer
  from the dryer (external spool), bypassing the AMS**, for the gear prints; reserve the AMS
  for multi-colour PLA/PETG work. Store PA sealed with desiccant between uses.
- The **P2S Combo** (printer + AMS 2 Pro, ~₹100k) is worth it only if you also want
  multi-colour / auto multi-spool feeding for other projects — it does **not** help with nylon
  drying. For the chess arm alone, **standalone P2S + a high-temp dryer** is the leaner, fully
  capable setup.

---

## 4. Bill of materials (India-aware, rough)

Local items: **Robu.in, Robokits, ThinkRobotics** (Pi, cooler, camera, extrusion, bearings,
fasteners, filament). Import items: **mjbots / ODrive** (ship worldwide in ~1 business day;
budget customs duty). Costs are indicative ranges.

| Item | Qty | Source | Approx cost (₹) |
|---|---|---|---|
| Raspberry Pi 5 8GB + official Active Cooler + PSU + storage | 1 | Robu/ThinkRobotics (local) | 12,000–18,000 |
| moteus-c1 FOC drivers (~$69 ea) | 6 | mjbots (import) | 35,000–40,000 + duty |
| fdcanusb CAN-FD adapter (~$100) | 1 | mjbots (import) | ~8,500 + duty |
| Gimbal BLDC motors | 6 | import / local drone stock | 6,000–18,000 |
| Output magnetic encoders (AS5047/MT6701 + magnets) | 6 | local/import | 2,000–5,000 |
| 24 V ~10 A power supply | 1 | local | 2,000–4,000 |
| Overhead camera (Pi Cam 3 or webcam) | 1 | local | 3,000–6,000 |
| Bearings, aluminium spacers, fasteners, extrusion/frame | — | local | 5,000–10,000 |
| Gripper servo + PCA9685 + TPU | — | local | 1,000–2,000 |
| Wiring (JST-PH3 / CAN), E-stop, misc | — | local | 5,000–10,000 |
| Filament: PETG (structure + gears) + TPU (fingers); PA-CF/PA6-GF optional for gears | — | local | 2,000–6,000 |
| **3D printer** — Bambu Lab **P2S** (Combo if you want multi-colour; **A1** budget); skip if owned | 1 | local (3Ding / 3idea) | 30,000–100,000 |
| High-temp filament dryer *(only if printing nylon/CF gears; the AMS can't dry these)* | 1 | local | 5,000–10,000 |

**Rough total:** ~₹1.5–2.3 lakh with the P2S (≈₹1.1–1.7 lakh with the A1), plus ~₹5–10k for a
high-temp dryer if you print nylon/CF gears, and import duties on the FOC drivers — within your
"no real limit" budget. *Budget alternative:* **SimpleFOC** boards instead of moteus/ODrive cut
driver cost sharply, at the price of reliability and more DIY tuning.

---

## 5. Build roadmap (de-risked, in order)

**Phase 0 — Simulate.** Model the arm in URDF; get it moving in RViz/MoveIt2 (and Gazebo).
No hardware. Validate reach and that it covers all 64 squares + graveyard.

**Phase 1 — One actuator.** Build a single BLDC + cycloidal joint with its encoder + moteus.
Calibrate, tune the position loop, prove accuracy and repeatability. *This is your
make-or-break learning unit — get it solid before replicating.*

**Phase 2 — Full arm.** Print and assemble all six joints on the daisy-chained CAN bus.
Bring up `ros2_control` + your `hardware_interface`; confirm MoveIt2 plans run on real
hardware. Measure end-to-end placement accuracy; tune until a piece lands centred in a
square every time.

**Phase 3 — Vision.** Mount the overhead camera; calibrate; get reliable per-square
occupancy detection and move inference under your actual lighting.

**Phase 4 — Integrate the game loop.** Wire vision → python-chess → Stockfish → MoveIt2 →
arm, including capture-clearing, castling, en passant, promotion, and self-verification.
Play full games.

**Phase 5 — Polish.** Speed/accel tuning for smooth motion, a clock/turn button, adjustable
difficulty, and a tidy enclosure.

---

## 6. Key risks & notes

- **Placement accuracy is the crux.** Cycloidal backlash + structural flex + camera error
  stack up. Mitigate with: output-side encoders (close the loop after the gearbox), stiff
  printed links, the **adaptive gripper** (absorbs a few mm), and vision verification.
- **Cycloidal print quality** drives smoothness — expect iteration on tolerances/clearances.
- **Lighting** matters for vision: aim for even, diffuse light and avoid hard shadows from
  the arm; calibrate occupancy thresholds in-situ.
- **Promotion needs a spare queen** in the graveyard the arm can fetch (or just prompt you).
- **Safety:** keep the E-stop in reach, set conservative limits, and test motion in sim and
  at low speed first.

---

## 7. Resources

- ROS2 + MoveIt2 docs; `ros2_control` hardware-interface guide.
- python-chess (board state, legal moves) + Stockfish UCI options.
- moteus: github.com/mjbots/moteus (firmware, C++/Python libs) + mjbots.com store.
- Reference arms: Atlas (hackaday.io/project/168259), Faze4 (github.com/PCrnjak/Faze4-Robotic-arm),
  CM6 (hackaday.io/project/180588), Skyentific (YouTube, BLDC actuator builds).
