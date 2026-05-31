# chess_arm_description

Phase-0 description package for the 6-DOF chess-playing arm: URDF/xacro (arm +
adaptive gripper + `ros2_control`), the standard-board + graveyard world, an RViz
display, and a Gazebo Jetty world. Targets **ROS 2 Lyrical Luth** (Ubuntu 26.04)
with **Gazebo Jetty**.

## Layout

```
urdf/
  arm_params.xacro            # canonical parameters (SI) — single source of truth
  materials.xacro             # visual materials
  inertial_macros.xacro       # box/cylinder inertial macros
  arm.macros.xacro            # link/joint macros + build_arm (base_link .. link6)
  gripper.macros.xacro        # build_gripper (1-DOF parallel jaw + tcp frame)
  scene.macros.xacro          # build_board / build_graveyard (recursive tiles/slots)
  chess_arm.ros2_control.xacro# ros2_control system (mock | gz | real switch)
  chess_arm.urdf.xacro        # TOP: world + arm + gripper + ros2_control [+ scene]
config/
  arm_params.yaml             # mm/deg mirror of arm_params.xacro (software/MoveIt)
  ros2_controllers.yaml       # joint_state_broadcaster + arm + gripper controllers
  board_coordinates.yaml      # generated: world (x,y) of a1..h8 + GY1..GY16
launch/display.launch.py      # rsp + joint_state_publisher_gui + RViz
rviz/view.rviz                # RViz config (fixed frame: world)
worlds/chess.sdf              # Gazebo Jetty world (ground + board + graveyard)
scripts/reachability_check.py # offline reachability proof (no ROS needed)
scripts/gen_board_coordinates.py
```

## Kinematics (verified)

6R, spherical wrist (J4/J5/J6 intersect at the wrist centre). Base on the board
centreline, 330 mm behind the near edge.

| Link | mm | Joint | axis | limits |
|---|---|---|---|---|
| base_height (ground→J1) | 90 | J1_base_yaw | Z | ±180° |
| shoulder_z (J1→J2) | 170 | J2_shoulder_pitch | Y | ±110° |
| upper_arm (J2→J3) | 340 | J3_elbow_pitch | Y | ±160° |
| forearm (J3→wrist centre) | 300 | J4_forearm_roll | Z | ±180° |
| wrist (→flange) | 60 | J5_wrist_pitch | Y | ±120° |
| tool_tip (→grasp) | 110 | J6_wrist_roll | Z | ±360° |

Reach = upper_arm + forearm = **640 mm**. `reachability_check.py` proves all 64
squares + 16 graveyard slots are reachable top-down at grasp (30 mm) and lift
(110 mm) heights — **160/160, worst margin 70.3 mm** (far corners a8/h8).

## Use

```bash
# Offline reachability proof (pure Python; also asserts xacro <-> yaml agree):
python3 scripts/reachability_check.py

# After ROS 2 Lyrical is installed and the workspace is built/sourced:
colcon build --packages-select chess_arm_description && . install/setup.bash

# Expand + validate the URDF:
xacro $(ros2 pkg prefix chess_arm_description)/share/chess_arm_description/urdf/chess_arm.urdf.xacro > /tmp/chess_arm.urdf
check_urdf /tmp/chess_arm.urdf

# RViz display with joint sliders (drive J1..J6 + gripper over the board):
ros2 launch chess_arm_description display.launch.py

# Gazebo Jetty (spawn arm with with_world:=false so the SDF scene isn't duplicated):
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:=$(ros2 pkg prefix chess_arm_description)/share/chess_arm_description/worlds/chess.sdf
```

## Conventions

- World origin = board centre; board top surface at **z = 0**; Z up.
  Files **a→h** along +X, ranks **1→8** along +Y.
- `arm_params.xacro` (SI) and `arm_params.yaml` (mm/deg) hold the same numbers;
  `reachability_check.py` fails if they drift. Edit both, then regenerate
  `board_coordinates.yaml` (`gen_board_coordinates.py`).
- The board + graveyard are robot links only when `with_world:=true` (RViz). For
  MoveIt build with `with_world:=false` and add them as planning-scene collision
  objects; in Gazebo they come from `worlds/chess.sdf`.
