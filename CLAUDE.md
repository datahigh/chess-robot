# CLAUDE.md — Chess-Playing Robot Arm

> **Purpose:** Project memory / instructions for Claude Code. It captures every decision and
> all context from the planning conversation so a Claude Code session can continue the build.
> Place this at the repo root (Claude Code reads `CLAUDE.md` automatically as project memory).
> A fuller planning doc, `chess-robot-arm-build-plan.md`, is a useful companion — add it too.

---

## 1. What we're building

A from-scratch **6-DOF articulated robot arm** that plays physical chess against the user on an
**unmodified standard board with standard pieces**. A camera reads the human's move, **Stockfish**
decides the reply, and the arm picks and places the piece (and clears captures to a side
"graveyard"). The arm plays the human; difficulty is adjustable.

---

## 2. Priorities & constraints (READ FIRST)

- **Optimize for: optimal / reliable / efficient.** Learning is secondary.
- The user is a **senior embedded engineer** and will rely on Claude Code for the coding. Be
  technical; don't over-explain basics. Explain trade-offs when making engineering choices.
- **Budget:** effectively unlimited — but don't spend on capability the project doesn't need.
- **Sourcing is India-based.** Local: Robu.in, Robokits, ThinkRobotics, Robocraze (Bengaluru),
  3Ding/3idea. Import: mjbots / ODrive (ship worldwide).
- **HARD CONSTRAINT — no modification to a standard board or standard pieces.** This is *why*
  the design uses a camera (not a sensor grid) and an adaptive gripper (not an electromagnet).
  Do not propose solutions that require embedding magnets/steel/RFID in pieces or the board.

---

## 3. Locked architecture (do NOT re-litigate without asking)

| Subsystem | Decision |
|---|---|
| Manipulator | Articulated **6-DOF arm**, built from scratch |
| Joint actuation | **BLDC motors + 3D-printed cycloidal reducers** |
| Motor control | **moteus-c1** FOC drivers (one per joint) on a **CAN-FD** bus |
| Pi ↔ CAN bridge | **mjcanfd-usb-1x** (USB↔CAN-FD; successor to the now-discontinued fdcanusb — same JST-PH3 moteus pinout, USB-C, socketcan + fdcanusb-compatible virtual-serial); pi3hat is an alternative |
| Joint feedback | moteus onboard encoder (motor side) **+ output-side absolute magnetic encoder** (AS5047/MT6701) per joint → absolute joint angle, no homing |
| Robotics software | **ROS2 (Lyrical Luth — the Ubuntu 26.04 Tier-1 LTS, supported to 2031) + MoveIt2** for IK/planning; **custom `ros2_control` hardware_interface (C++)** bridging to moteus over CAN; RViz + **Gazebo Jetty** (`gz-sim`) for sim |
| Move detection | **Overhead fixed camera + classic OpenCV.** Engine holds authoritative game state; vision only detects *which squares changed* each turn |
| End-effector | **Adaptive Fin Ray fingers (TPU)** on one servo (PCA9685 / PWM) |
| Brain | **Raspberry Pi 5 (8GB) + active cooler**, Ubuntu 26.04 (arm64) + ROS2 Lyrical. Runs vision + planning + engine. Hard real-time motor control lives on the moteus boards, NOT the Pi |
| Chess engine | **Stockfish** (UCI), strength-limited, movetime-capped |
| Board / pieces | Standard tournament Staunton (~50 cm board, ~5.7 cm squares), **UNMODIFIED** |
| Fabrication | Bambu Lab **P2S** (or **A1** budget). Gears in **PETG to start**; optional **PA-CF/PA6-GF** (needs a high-temp dryer, ~70–90 °C; the AMS only reaches 65 °C) |

---

## 4. Key parameters & technical approach

**Arm:** joints J1 base-yaw, J2 shoulder-pitch, J3 elbow-pitch, J4 forearm-roll, J5 wrist-pitch,
J6 wrist-roll. **Target reach ~500–650 mm.** Payload is tiny (<0.5 kg — pieces weigh grams).
Mount the arm beside/behind the board with a **graveyard zone** to one side for captured pieces.

**Move detection / chess logic (the key idea):** because the engine tracks the game from the
opening position, the camera only needs to find the *changed squares* each turn; the move is then
resolved by **matching the change pattern against the legal moves** (via `python-chess`). This
means **never classifying piece type by vision**. Handle the special cases explicitly: capture
(destination changes colour), castling (king+rook, 4 squares), en passant (3 squares), promotion
(default queen, or prompt; needs a spare queen fetched from the graveyard). After the arm moves,
**re-read the board to verify** its own placement before handing the turn back.

**Vision pipeline:** fixed overhead camera → calibrate intrinsics (checkerboard) → homography
from 4 board corners to a top-down 8×8 grid → per-square occupancy diff between turns.

**Engine config:** Stockfish via UCI; `UCI_LimitStrength=true` + `UCI_Elo` (1320–3190), or
`Skill Level` 0–20; cap thinking time with `go movetime <ms>`. Stockfish runs fine on the Pi 5.

**Motion stack:** MoveIt2 plans collision-free pick→lift→traverse→place→retract (plus a
capture-clearing move first when needed). A stock controller (`joint_trajectory_controller`)
feeds the **custom `ros2_control` hardware_interface**, whose `read()`/`write()` map to the moteus
CAN bus. (Only this hardware_interface and the firmware-adjacent glue are custom — we use ROS2 and
MoveIt2 as-is.)

**Safety:** conservative per-joint current/velocity limits, software workspace limits (never reach
off the table or self-collide), and a hardware E-stop assumed on the motor bus.

---

## 5. Development environment

- **WSL2 (Ubuntu 26.04 "Resolute")** on Windows. ROS2 **Lyrical Luth** (Tier-1 LTS for 26.04,
  supported to 2031) + **MoveIt2**; sim via RViz + **Gazebo Jetty** (`gz-sim`). Python 3.12–3.14;
  default RMW `rmw_fastrtps_cpp`.
- **Install path (Ubuntu 26.04):** native `apt install ros-lyrical-desktop` (add the
  `ros2-apt-source` repo first; pass `--no-install-suggests` to dodge the `hyperspec` packaging
  bug; the brand-new mirror may 404 transiently as it syncs). Available & used as binaries:
  `ros-lyrical-{desktop,ros2-control,ros2-controllers,parallel-gripper-controller,ros-gz,gz-ros2-control}`.
- **MoveIt 2 has no Lyrical binaries**, so it is **built from source** in a dedicated workspace
  `~/ws_moveit2` via `scripts/build_moveit_from_source.sh` (moveit2 `main`; targeted 28-pkg subset:
  move_group, OMPL, kinematics, planning_interface, Setup Assistant, simple_controller_manager,
  configs_utils + deps; `moveit_py`/servo/benchmarks/demo-configs skipped). It needed **4
  fresh-distro patches, all captured in that script**: (1) `CMAKE_POLICY_VERSION_MINIMUM=3.5` for
  OSQP's old CMake min; (2) raise moveit's `octomap` cap to `<1.11.0` (Ubuntu ships 1.10.0);
  (3) inject a compat shim for `ament_target_dependencies` (REMOVED in Lyrical, used by ~93 moveit
  files) via `-DCMAKE_PROJECT_INCLUDE_BEFORE`; (4) drop the header-only `boost_system` component
  from every `find_package(Boost …)` (incl. installed ConfigExtras). **Source order:**
  `source /opt/ros/lyrical/setup.bash` then `source ~/ws_moveit2/install/setup.bash`.
- The Phase-0 `chess_arm_description` stack is **built & validated on Lyrical** (colcon build clean,
  `xacro`+`check_urdf` pass both configs, RViz/TF FK confirmed: world→tcp = [0,-0.330,1.070] at zero pose).
- **`chess_arm_moveit_config` is built & validated on Lyrical** (hand-authored; planning groups
  `arm` base_link→tcp + `gripper`; KDL IK; OMPL). Headless `demo.launch.py use_rviz:=false` brings up
  move_group + all controllers, and a `/move_action` plan-and-execute for `arm` returns SUCCESS.
  Three Lyrical-specific deviations are documented in that package's README and MUST be kept:
  (1) launch files pin `.planning_pipelines(["ompl"])` (only OMPL built → else move_group aborts on
  pilz); (2) custom `spawn_controllers.launch.py` passes `--param-file` (Lyrical ros2_control no longer
  auto-forwards per-controller params); (3) SRDF collision matrix via `collisions_updater` + a manual
  `link3↔link6` disable (zero-offset wrist cylinders clip when J5 pitches for top-down grasps).
- **`chess_arm_interfaces` + `chess_arm_brain` + `chess_arm_vision` + `chess_arm_orchestrator` built
  & validated on Lyrical.** `chess_arm_interfaces` = rosidl srv/msg (ResolveHumanMove, GetEngineMove,
  PlanPieceActions, DetectChanges, PieceAction). `chess_arm_brain` = pure-Python python-chess +
  Stockfish library (resolve human move from changed squares; engine reply; decompose a move into
  ordered pick/place `PieceAction`s — capture→graveyard, castle=king+rook, en-passant clears the
  pawn behind the destination, promotion=remove-pawn+place-from-graveyard — with world xyz from
  `board_coordinates.yaml`) + a thin rclpy node. `chess_arm_vision` = occupancy-diff Phase-0 stub
  (changed squares from before/after FEN; real OpenCV later). `chess_arm_orchestrator` = state-machine
  node (WAIT→DETECT→RESOLVE→ENGINE→PLAN→EXECUTE→VERIFY) with a pluggable executor (DryRunExecutor now;
  **MoveItExecutor is a STUB/TODO** to wire in the game-loop step) + a standalone `dry_run`.
  **54 unit tests pass** (all special-move decompositions, move resolution, engine, vision diff);
  `python3 -m chess_arm_orchestrator.dry_run` plays full scenario games end-to-end; all 3 nodes start
  and advertise their services. Runtime deps: **python-chess** (`pip install --user --break-system-packages chess`)
  + **stockfish** (`apt`; binary at `/usr/games/stockfish` — add `/usr/games` to PATH for the engine).
- **Game loop wired & validated in sim (Phase-0 §8.5 execution criterion MET).** `MoveItExecutor`
  (in `chess_arm_orchestrator/executors.py`) turns each PieceAction into a top-down move_group
  pick/place (approach→open→grasp→close→lift→traverse→place→release→retract: /move_action pose goals
  on the `tcp` link with a downward orientation + free-yaw, plus the parallel-gripper action).
  `ros2 run chess_arm_orchestrator play_sim_game …` (against `launch/game_moveit.launch.py`, which
  brings up move_group + brain + vision) physically executes **all 6 move types — 6/6 PASS**:
  normal, capture, castle, en passant, promotion, capture-promotion (each ~7–26 s of real sim motion,
  board advancing correctly). Gotchas captured for future work: (a) the executor's
  `_spin_until_complete` must NOT spin (nested-executor deadlock) — the node is spun in a background
  thread and the futures are polled; (b) on Lyrical `ParallelGripperCommand.Goal.command` is a
  `sensor_msgs/JointState` (set `.name`+`.position`, not `.position`/`.max_effort`).
- **LIVE LOOP DONE — PHASE 0 COMPLETE.** The continuous multi-turn loop runs through
  `orchestrator_node` (`executor:=moveit`) via `launch/live_game.launch.py` + `sim_game_driver`:
  a scripted human side drives turns, and per turn the orchestrator does vision DetectChanges →
  brain ResolveHumanMove → GetEngineMove → PlanPieceActions → MoveItExecutor (real move_group
  pick/place) → verify. VALIDATED: 5/5 turns deadlock-free, INCLUDING two engine CAPTURES the arm
  cleared to the graveyard (GY1, GY2). Threading/contract fixes that make it work (KEEP THEM):
  (a) MultiThreadedExecutor with /human_move_done on its own MutuallyExclusiveCallbackGroup and the
  four service clients on a ReentrantCallbackGroup; `_call_sync` polls `call_async` futures (never
  nested-spins). (b) MoveItExecutor action clients on a ReentrantCallbackGroup, and it also waits for
  `/arm_controller/follow_joint_trajectory` to avoid CONTROL_FAILED (-4) on the startup race. (c)
  `GetEngineMove` PEEKS (no push) while `PlanPieceActions` decomposes-THEN-pushes (else decompose
  rejects the already-played move). (d) the sim driver strips ROS args (`remove_ros_args`) and joins
  its spin thread before destroy. Between runs, kill ALL prior nodes (incl. the Python brain/vision/
  orchestrator/driver) or stale latched `/sim_board_fen` pollutes the next run.
  NEXT (Phase 1+): Gazebo Jetty physics with real piece/board models, then hardware (BLDC + 3D-printed
  cycloidal joints + moteus over CAN-FD via the custom ros2_control hardware_interface).
- **PHASE 1 STARTED — single-actuator bring-up KIT authored (no hardware bought yet).** Scope chosen
  by the user: "prepare the bring-up kit" + the single-joint BOM/wiring (so parts can be ordered AND
  the software is ready to run on connection). First joint = **least-risky wrist-class (J5/J6) bench
  joint**; output encoder = **AS5047P (14-bit SPI) on moteus-c1 aux2**; onboard encoder stays the
  commutation source; ~9:1 single-stage cycloidal (`rotor_to_output_ratio = 1/9 = 0.111111`,
  output-per-rotor fraction); conservative limits (`max_current_A 2.0`, `servopos ±0.2 rev/±72°`,
  watchdog 0.5 s). **moteus 1.0.0** installed via pip (`--user --break-system-packages`; lib +
  `moteus_tool`, `Fdcanusb` transport). Kit lives in **`hardware/joint_bringup/`** (standalone Python,
  NOT a ROS package — ros2_control comes in Phase 2): `README.md` (run order + acceptance gate),
  `BOM_single_joint.md` (India sourcing, import-first), `wiring.md` (AUX2↔AS5047P SPI pin table +
  power-on/E-stop checklist), `config/wrist_joint.cfg` (`moteus_tool --restore-config` format, 32
  register lines), `moteus_joint_config.md`, `calibration_and_tuning.md`, and
  `bringup/{connect_check,configure_joint,step_repeatability_test}.py` + `requirements.txt`. The
  acceptance gate = `step_repeatability_test.py` (logs commanded vs AS5047P output position to CSV;
  PASS = repeatability ≤0.5° AND |accuracy| ≤1.0° at the output, backlash reported). Built via a
  workflow then ADVERSARIALLY VERIFIED: **zero hallucinated registers, zero hallucinated moteus-API
  calls** (checked vs the moteus reference + the *installed* `moteus_tool.py` source), all 3 scripts
  `py_compile` + run `--help`/`--dry-run`/`--plan-only` clean with NO device; 6 doc-accuracy nits all
  fixed (e.g. `aux2.spi.rate_hz` 12 MHz default — there is no `motor_position.spi.rate_hz`; the
  50k–400k range is `i2c.i2c_hz`; `output.sign` is only *temporarily* forced to 1 during
  `--calibrate` then restored — reverse direction via `sources.1.sign`; `--cal-voltage` is deprecated
  → use `--cal-motor-power`; `--calibrate` clobbers `sources.1.pll_filter_hz` so the cfg MUST be
  applied AFTER calibration; added a real `--servopos-limit-deg` abort guard to the acceptance test).
  CAN ADAPTER DECISION (2026-05-31): the originally-specced **fdcanusb is discontinued** (mjbots
  marks it deprecated + out of stock); adopted the **mjcanfd-usb-1x** ($39) successor — same JST-PH3
  moteus pinout, USB-C. The moteus python transport is still `moteus.Fdcanusb` (that is the fdcanusb
  *protocol*, which the mjcanfd-usb-1x speaks in USB-CDC virtual-serial mode), so the bring-up
  scripts are UNCHANGED; socketcan (`moteus.PythonCan` / `moteus_tool --can-iface`) is the alt.
  GOTCHA: on WSL2 the adapter needs `usbipd attach --busid <id> --wsl` before its serial device
  (typically `/dev/ttyACM*`) appears; native on the Pi 5. VERIFY whether the mjcanfd-usb-1x
  integrates host-end CAN termination (the fdcanusb did) — budget 2× JST-PH3 terminators if not.
  HARDWARE-BLOCKED TODOs (marked in the files): motor SKU→`--cal-motor-poles`,
  as-built ratio→`rotor_to_output_ratio`, AUX2 A/B/C/D→SCK/MISO/MOSI/CS + CAN PH-3 silk order (METER
  vs the c1 rendered-pinout SVG before crimping), `output.source` index (from live `--dump-config`),
  `output.offset` (via `--zero-offset`), real `servopos` sweep, and the hand-tuned position gains.
- **PHASE-1 SOURCING FINALIZED (2026-06-06) — full orderable cart in `hardware/joint_bringup/ORDER_CART.md`.**
  Key locks (also synced into `BOM_single_joint.md`):
  - **Motor LOCKED → 2804 100 KV gimbal (GBM2804H-100T), 12N14P, hollow-shaft (Ø7 OD / Ø5 ID).** Sets
    `--cal-motor-poles 14` (resolves the motor-SKU TODO). Hollow shaft ⇒ the cycloidal cam **bolts to
    the rotor face**, not a shaft (Ø5 bore free for a coaxial encoder pass-through). Fallback: T-Motor
    GB2208 (Robokits RKI-3511, 6 mm bore, Kv 128). Verify pole count + bore on receipt.
  - **Cycloidal CAD LOCKED → adopt Faze4 single-stage wrist cyclo, re-cut to 9:1 = 9 disc lobes / 10
    ring pins** (single-eccentric law: pins = lobes+1, ratio = lobes), confirming `rotor_to_output_ratio
    = 1/9 = 0.111111` (resolves the ratio TODO). Bearings resolved (Faze4 "Tier-A"): **688-2RS** (8×16×5)
    ×2 cam + **MR126-2RS** (6×12×4) ×2 support + optional **MR63-2RS** (3×6×2.5) ×10 rollers; **3 mm
    DIN 6325 hardened dowels**; M3 SHCS + heat-set inserts. **CAD edits still needed:** regen disc to
    9/10, gimbal-rotor-face eccentric cam, re-cut housing motor face, add a 6 mm diametric AS5047P
    magnet pocket (ref OpenCyRe hackaday.io/project/168498).
  - **Output magnet → DOMESTIC** (Patel `D-6-3-N52-D`, 6×3 mm **diametric** — not axial), moved off
    mjbots (no reason to import a commodity magnet).
  - **Both IMPORT carts bought FULL-PROJECT (×6) in one parcel each** (freight/duty is per-parcel):
    mjbots = 6× moteus-c1 + adapter + 2 terminators + **`power_dist r4.5b`** ($149, 1×XT90→6×XT30,
    soft-start for the multi-driver bus); DigiKey = 6× AS5047P + 6× GH-7 sets + 1 crimp tool. Domestic
    Cart 3 (motor/magnet/mechanicals/PSU/passives) stays Phase-1, scales ×6 later (no freight penalty).
  - **Printer → Bambu P2S Combo (AMS 2 Pro) from IDEAL3D** (authorized Bambu dealer — buy authorized
    so warranty registers to the serial; avoid non-authorized sellers for Bambu). Filament: Bambu
    **PETG HF** (gears/structure) + **PLA Basic** (calibration/jigs). AMS routing: feed **TPU + PA-CF/
    PA6-GF from the external spool**, not the AMS; the AMS dries only ~65 °C (nylon still needs the
    deferred 70–90 °C dryer). Plus a Phase-1 **bench-tool kit** (soldering kit + DMM + calipers etc.).
  - **pi3hat REJECTED** — physically incompatible with the locked Pi 5 (Pi 5 moved GPIO/SPI behind the
    new RP1 I/O controller; pi3hat's direct-register driver targets the Pi 4 BCM2711). The USB
    `mjcanfd-usb-1x` is host-agnostic (works on Pi 5 + WSL2) and a single CAN-FD bus carries all 6 nodes.
  - Order-now total ≈ **₹2.20–2.38 L** (both imports full-arm + Phase-1 domestic + printer + tools).
- The colcon workspace lives **in this repo** (`<repo>/src/...`, already on the Linux fs — not
  `/mnt/c/...`, whose 9p bridge is much slower for colcon builds).
- Languages: **Python** (vision, chess, orchestration), **C++** (`ros2_control` hardware_interface),
  **URDF/xacro** (robot + world description).
- Build with **colcon**; simulate with **RViz + Gazebo**.

---

## 6. How to work (instructions for Claude Code)

- **Simulation-first.** Everything must run in RViz/Gazebo before any hardware. Phase 0 is pure sim.
- **Keep the §3 decisions fixed** unless the user explicitly changes them. Ask before swapping a
  major component, changing the architecture, or adding heavy dependencies.
- **The engine is the source of truth** for game state; vision only detects changed squares.
- **Write modular ROS2 packages**, document as you go, prefer readable over clever, and keep
  hardware-specific code isolated behind the `ros2_control` interface so sim and real share code.
- **Safety always:** never generate motion that exits the board workspace or self-collides; start
  motion testing at low speed; respect joint limits.
- Use clear commit-sized steps and explain trade-offs when you make engineering decisions.

---

## 7. Roadmap (we are starting at **Phase 0**)

- **Phase 0 — Simulate (CURRENT).** URDF + MoveIt2 + RViz/Gazebo; validate reach/coverage; build
  the software stack (vision stub, chess/engine, motion, orchestration) entirely in sim. No hardware.
- **Phase 1 — One actuator.** Build a single BLDC + cycloidal joint with its output encoder + moteus;
  calibrate and tune; prove accuracy/repeatability before replicating. *(Order FOC drivers and
  3D-print these parts in parallel with Phase 0.)*
- **Phase 2 — Full arm.** Assemble all six joints on the CAN bus; bring up the real
  `ros2_control` hardware_interface; tune until piece placement is centred and repeatable.
- **Phase 3 — Vision.** Mount/calibrate the overhead camera; reliable occupancy + move inference
  under real lighting.
- **Phase 4 — Game loop.** Integrate vision → chess → engine → MoveIt → arm, with capture/castle/
  en passant/promotion + self-verification. Play full games.
- **Phase 5 — Polish.** Motion smoothness, clock/turn button, adjustable difficulty, enclosure.

---

## 8. Phase 0 — concrete first steps (current focus)

1. **Create the workspace:** colcon workspace `src/` at the repo root (Linux fs), source ROS2 Lyrical Luth.
2. **Scaffold packages:**
   - `chess_arm_description` — xacro/URDF of the 6-DOF arm (links, joints, limits) + a **board model
     (~50 cm, 5.7 cm squares)** and a **graveyard tray** placed in the world.
   - `chess_arm_moveit_config` — MoveIt2 config (Setup Assistant): planning groups (`arm`, `gripper`),
     IK solver (KDL or TRAC-IK), SRDF, `ros2_control` with **mock/Gazebo hardware** for sim.
   - `chess_arm_bringup` — launch files for the sim (RViz + Gazebo + controllers).
   - `chess_arm_brain` — `python-chess` board + Stockfish (UCI); maps detected move → engine reply →
     target square → pick/place poses.
   - `chess_arm_vision` — vision node (Phase 0: stub that reads board state from sim; later OpenCV).
   - `chess_arm_orchestrator` — state machine: wait-for-move → detect → engine → plan pick-place via
     MoveIt → execute → verify.
3. **Build & validate reachability:** in RViz, command the gripper to the centre of **all 64 squares
   + the graveyard**; confirm IK solutions exist with margin. Tune base placement / link lengths
   until full coverage.
4. **Play in sim:** drive a simulated "human move" (script or virtual board) through the full loop
   in Gazebo.
5. **Phase 0 done when:** the simulated arm plays a **full legal game end-to-end** (including a
   capture, castling, en passant, and a promotion) with all squares + graveyard reachable.

---

## 9. Bill of materials (condensed — for parallel sourcing; see build plan for detail)

- Raspberry Pi 5 8GB + active cooler + PSU + storage (local)
- 6× moteus-c1 FOC drivers + 1× mjcanfd-usb-1x USB-CAN-FD adapter + mjbots `power_dist r4.5b`
  (1×XT90→6×XT30, soft-start) (import, mjbots; fdcanusb successor). **pi3hat rejected — Pi-5-incompatible (RP1).**
- 6× gimbal BLDC motors (**2804 100 KV / GBM2804H-100T, 14P, hollow-shaft**); 6× **AS5047P** output
  encoders (DigiKey ams board) + 6× diametric magnets (Patel `D-6-3-N52-D`)
- 24 V ~10 A PSU; overhead camera (Pi Cam 3 or USB webcam)
- Bearings (688-2RS / MR126-2RS / MR63-2RS), 3 mm DIN 6325 dowels, fasteners, extrusion/frame;
  gripper servo + PCA9685; CAN wiring (JST-PH3), E-stop
- Filament: PETG (structure + gears) + TPU (fingers); optional PA-CF/PA6-GF for gears
- 3D printer: Bambu Lab **P2S Combo** (AMS 2 Pro) from IDEAL3D (authorized); + high-temp dryer
  **only if** printing nylon/CF gears (the AMS dries only ~65 °C)

---

## 10. References

- **Reference arms:** Atlas + OpenCyRe cycloidal reducer (hackaday.io/project/168259); Faze4
  cycloidal gearbox CAD (github.com/PCrnjak/Faze4-Robotic-arm); CM6 QDD-BLDC
  (hackaday.io/project/180588); Skyentific (YouTube) for BLDC/cycloidal actuator builds.
- **Software:** ROS2 + MoveIt2 docs; `ros2_control` hardware-interface guide; `python-chess`;
  Stockfish UCI options.
- **Motor control:** github.com/mjbots/moteus (firmware + C++/Python libs); mjbots.com.

---

## 11. Open items / assumptions to confirm with the user

- Board size assumed standard tournament (~50 cm, 5.7 cm squares) → arm reach ~500–650 mm.
- Printer: P2S recommended; A1 is the budget fallback (PETG-only gears).
- Gears: start in PETG; only move to PA-CF/PA6-GF (with a high-temp dryer) for max precision-retention.
- Arm base placement and camera mounting geometry to be finalized in Phase 0 (reachability).
- Promotion handling: spare queen in the graveyard vs prompting the user.
