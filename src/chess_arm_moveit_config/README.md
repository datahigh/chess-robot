# chess_arm_moveit_config

MoveIt 2 configuration for the `chess_arm` 6-DOF arm + gripper. Hand-authored
(not Setup-Assistant-generated) to target **ROS 2 Lyrical** with MoveIt built
from source (see `../../scripts/build_moveit_from_source.sh`).

## Layout

```
config/
  chess_arm.urdf.xacro      # thin wrapper -> chess_arm_description (with_world:=false)
  chess_arm.srdf            # groups (arm, gripper), states, end-effector, collision matrix
  kinematics.yaml           # arm group: KDL (kdl_kinematics_plugin) — trac_ik not built
  joint_limits.yaml         # velocity (from arm_params) + acceleration caps
  ompl_planning.yaml        # OMPL pipeline (only OMPL is built from source)
  pilz_cartesian_limits.yaml# required by MoveItConfigsBuilder even though Pilz is unused
  moveit_controllers.yaml   # MoveIt -> ros2_control: arm=FollowJointTrajectory, gripper=ParallelGripperCommand
  ros2_controllers.yaml     # controller_manager + arm_controller (JTC) + gripper_controller (parallel)
  initial_positions.yaml    # J1..J6 = 0
launch/  demo, move_group, moveit_rviz, rsp, spawn_controllers, static_virtual_joint_tfs
```

## Planning groups

- **arm** — kinematic chain `base_link -> tcp` (6 DOF: J1..J6). `tcp` is the grasp
  frame; KDL solves IK for it. Named state `home` = all zeros.
- **gripper** — `gripper_left_joint` only (`gripper_right_joint` is a URDF mimic,
  marked `<passive_joint>`). Named states `open` (0.020) / `closed` (0.0).
- No `<virtual_joint>`: the URDF already roots at `world` (fixed to `base_link`).

## Run

```bash
source /opt/ros/lyrical/setup.bash
source ~/ws_moveit2/install/setup.bash            # source-built MoveIt
source <repo>/install/setup.bash                  # this workspace
ros2 launch chess_arm_moveit_config demo.launch.py            # with RViz MotionPlanning
ros2 launch chess_arm_moveit_config demo.launch.py use_rviz:=false   # headless
```

**Verified (headless):** move_group comes up, all three controllers activate, and
a joint-space plan-and-execute request to `/move_action` for the `arm` group
returns SUCCESS with a real trajectory (mock_components hardware).

## Lyrical-specific deviations from a stock Setup-Assistant config — DO NOT "fix" back

1. **`move_group.launch.py` / `moveit_rviz.launch.py` pin `.planning_pipelines(pipelines=["ompl"])`.**
   Only OMPL is built from source on Lyrical. Without this, the builder auto-loads
   pilz/chomp/stomp and `move_group` aborts loading the absent pilz plugin.
2. **`spawn_controllers.launch.py` is custom and passes `--param-file ros2_controllers.yaml`
   to each spawner.** On Lyrical's ros2_control the controller_manager loads only its
   own section (controller *types*); the per-controller `joints`/`joint` params are not
   auto-forwarded, so the stock `generate_spawn_controllers_launch` leaves controllers
   with empty params and they fail to initialize.
3. **`chess_arm.srdf` collision matrix** was generated with `moveit_setup_assistant
   collisions_updater` (sampling), plus a manual `link3 <-> link6` disable: the
   zero-offset spherical wrist makes the forearm and flange collision cylinders abut,
   so they clip when J5 pitches (needed for top-down grasps). Regenerate with
   `collisions_updater` if the wrist geometry changes.
4. Gripper uses `parallel_gripper_action_controller/GripperActionController`
   (`ParallelGripperCommand`), the Lyrical replacement for the removed
   `position_controllers/GripperActionController`.
