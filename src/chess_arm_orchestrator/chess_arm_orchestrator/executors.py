# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Pluggable executors that carry out a list of PieceActions.

An :class:`Executor` is the seam between the (sim/hardware-agnostic) game-loop
orchestration and the thing that actually moves the arm.  Today the default is
:class:`DryRunExecutor`, which only logs.  :class:`MoveItExecutor` drives a real
``move_group`` pick/place over each PieceAction in simulation (mock_components)
and -- unchanged -- on real hardware behind the same ``ros2_control`` interface.

The executor consumes either
:class:`chess_arm_orchestrator.piece_actions.PieceActionData` (no ROS) or
``chess_arm_interfaces/msg/PieceAction`` (ROS) -- both expose the same field
names (``action_type``, ``from_square``, ``to_square``, ``from_xyz``,
``to_xyz``, ``piece``), so the executor code is identical for both.  This keeps
the dry-run and the ROS node sharing one execution contract.
"""

from __future__ import annotations

from typing import Sequence

from chess_arm_orchestrator.piece_actions import ACTION_NAMES


def _action_name(action) -> str:
    return ACTION_NAMES.get(action.action_type, f'UNKNOWN({action.action_type})')


def _fmt_point(pt) -> str:
    return f'({pt.x:+.3f},{pt.y:+.3f},{pt.z:.3f})'


def describe_action(action) -> str:
    """Return a one-line summary of a PieceAction(Data) or ROS message."""
    piece = f' piece={action.piece}' if getattr(action, 'piece', '') else ''
    return (
        f'{_action_name(action):<20} '
        f'{action.from_square:>4} {_fmt_point(action.from_xyz)} -> '
        f'{action.to_square:>4} {_fmt_point(action.to_xyz)}{piece}')


class Executor:
    """Base class: execute an ordered list of PieceActions, return success."""

    def __init__(self, logger=None):
        # ``logger`` is an optional rclpy logger (or anything with .info/.warn).
        self._logger = logger

    # -- logging shims (work with rclpy logger or plain print) --------------

    def _info(self, msg: str) -> None:
        if self._logger is not None:
            self._logger.info(msg)
        else:
            print(msg)

    def _warn(self, msg: str) -> None:
        if self._logger is not None:
            self._logger.warning(msg)
        else:
            print('WARN: ' + msg)

    def execute(self, actions: Sequence) -> bool:
        """Execute every action in order; return True iff all succeeded."""
        raise NotImplementedError


class DryRunExecutor(Executor):
    """Logs each PieceAction and reports success without moving anything.

    This is the default executor for Phase 0 / dry-run validation: it proves
    the orchestration produces a sane, ordered action sequence end-to-end.
    """

    def execute(self, actions: Sequence) -> bool:
        """Log each action and return True."""
        actions = list(actions)
        if not actions:
            self._warn('DryRunExecutor: empty action list (nothing to do)')
            return True
        self._info(f'DryRunExecutor: executing {len(actions)} action(s):')
        for i, action in enumerate(actions, start=1):
            self._info(f'  [{i}/{len(actions)}] {describe_action(action)}')
        return True


# ---------------------------------------------------------------------------
# Real MoveIt executor: drives move_group + the gripper action controller.
# ---------------------------------------------------------------------------
#
# Geometry recap (world frame, metres):
#   * board surface z = 0.0
#   * grasp height    z = GRASP_Z  (0.030) -- piece is gripped/released here
#   * approach height z = LIFT_Z   (0.110) -- safe transit height above pieces
#   * the tool (tcp link) must point straight DOWN for every grasp/place.  The
#     downward orientation is 180 deg about world X => quaternion (1,0,0,0),
#     i.e. tool +Z axis is mapped to world -Z.  We leave the yaw (rotation about
#     the vertical tool axis) free via a wide z-axis tolerance: J6 supplies it,
#     and pieces are rotationally symmetric for grasping.
#
# Pick-and-place choreography per PieceAction (from_xyz -> to_xyz), all
# tool-down (see the module docstring / task spec):
#   1) move tcp to FROM-approach   (from x,y at LIFT_Z)
#   2) gripper OPEN
#   3) move tcp DOWN to FROM-grasp (from xyz, GRASP_Z)
#   4) gripper CLOSE
#   5) move tcp UP to FROM-approach (lift)
#   6) move tcp to TO-approach     (to x,y at LIFT_Z)
#   7) move tcp DOWN to TO-grasp   (to xyz, GRASP_Z)
#   8) gripper OPEN (release)
#   9) move tcp UP to TO-approach  (retract)
#
# Every PieceAction type (PICK_PLACE / CLEAR_CAPTURE / MOVE_ROOK /
# CLEAR_EN_PASSANT / REMOVE_PROMOTED_PAWN / PLACE_PROMOTION) is the SAME
# from->to transfer; to_square may be a graveyard slot whose xyz is already
# carried in to_xyz.


class MoveItExecutor(Executor):
    """Drive MoveIt ``move_group`` pick/place over each PieceAction.

    Uses two action clients on the (injected) rclpy ``Node``:

    * ``/move_action`` (``moveit_msgs/action/MoveGroup``) -- plan + execute a
      Cartesian goal for the ``arm`` group's ``tcp`` link, expressed as a tight
      position sphere constraint plus a downward orientation constraint with a
      free-yaw tolerance.
    * ``/gripper_controller/gripper_cmd``
      (``control_msgs/action/ParallelGripperCommand``) -- open/close the jaw.

    Both action clients are created on ONE ReentrantCallbackGroup so their
    goal-response/result callbacks can be serviced concurrently while this
    executor polls the futures; goals are sent asynchronously and the executor
    blocks on each result via the node's (background) executor.

    Returns ``False`` (and logs) on the first failed sub-motion so the
    orchestrator can abort the turn and re-read the board rather than corrupting
    the game; ``True`` only when every action's full choreography completes.
    """

    # Planning frame and target link (from the SRDF: arm chain base_link->tcp,
    # planning frame "world").
    PLANNING_FRAME = 'world'
    TCP_LINK = 'tcp'
    ARM_GROUP = 'arm'

    # Heights (metres) -- mirror board_coordinates.yaml grasp_z / lift_z.
    GRASP_Z = 0.030
    LIFT_Z = 0.110

    # Gripper jaw positions (metres) -- SRDF named states "open"/"closed".
    GRIPPER_OPEN = 0.020
    GRIPPER_CLOSED = 0.0
    GRIPPER_JOINT = 'gripper_left_joint'
    GRIPPER_MAX_EFFORT = 10.0

    # Goal tolerances / planning knobs.
    POSITION_SPHERE_RADIUS = 0.01       # m -- tight position window for tcp
    ORI_XY_TOLERANCE = 0.1              # rad -- keep the tool pointing down
    ORI_YAW_TOLERANCE = 3.2            # rad -- free rotation about tool axis
    NUM_PLANNING_ATTEMPTS = 10
    ALLOWED_PLANNING_TIME = 5.0        # s
    VEL_SCALING = 0.8
    ACC_SCALING = 0.8

    SERVER_WAIT_TIMEOUT = 10.0         # s -- per action server
    GOAL_RESPONSE_TIMEOUT = 10.0       # s -- accept/reject
    RESULT_TIMEOUT = 60.0              # s -- plan + execute one motion

    def __init__(self, logger=None, node=None):
        super().__init__(logger=logger)
        if node is None:
            raise ValueError(
                'MoveItExecutor requires a rclpy Node (for action clients '
                'and logging); pass node=<Node>.')
        self._node = node
        if logger is None:
            # Prefer the node's logger when one was not supplied explicitly.
            self._logger = node.get_logger()

        # Imported here so this module stays importable without a ROS env
        # (the dry-run path / unit tests never construct a MoveItExecutor).
        from rclpy.action import ActionClient
        from rclpy.callback_groups import ReentrantCallbackGroup
        from control_msgs.action import ParallelGripperCommand
        from moveit_msgs.action import MoveGroup

        self._ParallelGripperCommand = ParallelGripperCommand
        self._MoveGroup = MoveGroup

        # Both action clients live on ONE ReentrantCallbackGroup so their
        # goal-response / result callbacks can be serviced concurrently (on
        # other threads) while this executor polls the futures.  This keeps the
        # executor safe under both the orchestrator's MultiThreadedExecutor and
        # play_sim_game's background spin thread.
        self._cb_group = ReentrantCallbackGroup()
        self._move_client = ActionClient(
            node, MoveGroup, '/move_action', callback_group=self._cb_group)
        self._gripper_client = ActionClient(
            node, ParallelGripperCommand, '/gripper_controller/gripper_cmd',
            callback_group=self._cb_group)
        # The arm trajectory controller's action server only appears once the
        # controller is ACTIVE. Waiting for it avoids CONTROL_FAILED (-4) when a
        # move_group goal is executed before arm_controller has finished
        # spawning -- a real startup race in the all-in-one live launch.
        from control_msgs.action import FollowJointTrajectory
        self._traj_client = ActionClient(
            node, FollowJointTrajectory,
            '/arm_controller/follow_joint_trajectory',
            callback_group=self._cb_group)

        self._servers_ready = False

    # -- server readiness ----------------------------------------------------

    def _ensure_servers(self) -> bool:
        """Wait (once) for both action servers; cache the result."""
        if self._servers_ready:
            return True
        ok = True
        if not self._move_client.wait_for_server(
                timeout_sec=self.SERVER_WAIT_TIMEOUT):
            self._warn(
                'MoveItExecutor: /move_action server unavailable after '
                f'{self.SERVER_WAIT_TIMEOUT:.0f}s -- is move_group running?')
            ok = False
        if not self._gripper_client.wait_for_server(
                timeout_sec=self.SERVER_WAIT_TIMEOUT):
            self._warn(
                'MoveItExecutor: /gripper_controller/gripper_cmd server '
                f'unavailable after {self.SERVER_WAIT_TIMEOUT:.0f}s -- is the '
                'gripper controller spawned?')
            ok = False
        if not self._traj_client.wait_for_server(
                timeout_sec=self.SERVER_WAIT_TIMEOUT):
            self._warn(
                'MoveItExecutor: /arm_controller/follow_joint_trajectory server '
                f'unavailable after {self.SERVER_WAIT_TIMEOUT:.0f}s -- is '
                'arm_controller active? (move_group execution needs it)')
            ok = False
        self._servers_ready = ok
        return ok

    # -- spin helper ---------------------------------------------------------

    def _spin_until_complete(self, future, timeout_sec) -> bool:
        """Block until ``future`` resolves, returning True iff it completed.

        Does NOT spin here: the node MUST be serviced by a background executor
        (the orchestrator's MultiThreadedExecutor, or play_sim_game's background
        spin thread). We simply poll the future, which avoids the spin-inside-
        spin / nested-executor deadlocks that arise when this is called from a
        thread that is itself being spun, or with multiple action clients on the
        node. The caller is responsible for spinning the node elsewhere.
        """
        import time

        deadline = time.monotonic() + float(timeout_sec)
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        return future.done()

    def _send_and_wait(self, client, goal, label: str, result_timeout: float):
        """Send ``goal`` to ``client``, block for the result, return it or None.

        Returns the action *result* message on success, or ``None`` if the goal
        was rejected, timed out, or the action did not complete.  Logging is
        left to the caller (which knows how to interpret the result type).
        """
        send_future = client.send_goal_async(goal)
        if not self._spin_until_complete(
                send_future, self.GOAL_RESPONSE_TIMEOUT):
            self._warn(f'{label}: timed out waiting for goal acceptance')
            return None
        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self._warn(f'{label}: goal REJECTED by the action server')
            return None

        result_future = goal_handle.get_result_async()
        if not self._spin_until_complete(result_future, result_timeout):
            self._warn(f'{label}: timed out waiting for the result')
            return None
        wrapper = result_future.result()
        if wrapper is None:
            self._warn(f'{label}: no result returned')
            return None
        return wrapper.result

    # -- arm motion ----------------------------------------------------------

    def move_arm_to_pose(self, x: float, y: float, z: float) -> bool:
        """Plan AND execute a tool-down move of ``tcp`` to (x, y, z) in world.

        Builds a single ``MoveGroup`` goal for the ``arm`` group whose one goal
        :class:`Constraints` carries a tight position-sphere constraint and a
        downward orientation constraint (free yaw).  Returns True iff the result
        error code is SUCCESS.
        """
        from geometry_msgs.msg import Point, Pose, Quaternion
        from moveit_msgs.msg import (
            BoundingVolume,
            Constraints,
            MoveItErrorCodes,
            OrientationConstraint,
            PositionConstraint,
        )
        from shape_msgs.msg import SolidPrimitive

        # --- position constraint: a small sphere centred on the target -----
        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [self.POSITION_SPHERE_RADIUS]  # [SPHERE_RADIUS]

        region = BoundingVolume()
        region.primitives = [sphere]
        target_pose = Pose()
        target_pose.position = Point(x=float(x), y=float(y), z=float(z))
        # Identity orientation for the region pose; the actual tool orientation
        # is enforced by the OrientationConstraint below.
        target_pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        region.primitive_poses = [target_pose]

        pos_con = PositionConstraint()
        pos_con.header.frame_id = self.PLANNING_FRAME
        pos_con.link_name = self.TCP_LINK
        pos_con.constraint_region = region
        pos_con.weight = 1.0

        # --- orientation constraint: tool points straight down, free yaw ---
        ori_con = OrientationConstraint()
        ori_con.header.frame_id = self.PLANNING_FRAME
        ori_con.link_name = self.TCP_LINK
        # 180 deg about world X -> tool +Z maps to world -Z (straight down).
        ori_con.orientation = Quaternion(x=1.0, y=0.0, z=0.0, w=0.0)
        ori_con.absolute_x_axis_tolerance = self.ORI_XY_TOLERANCE
        ori_con.absolute_y_axis_tolerance = self.ORI_XY_TOLERANCE
        ori_con.absolute_z_axis_tolerance = self.ORI_YAW_TOLERANCE
        ori_con.weight = 1.0

        goal_constraints = Constraints()
        goal_constraints.position_constraints = [pos_con]
        goal_constraints.orientation_constraints = [ori_con]

        goal = self._MoveGroup.Goal()
        req = goal.request
        req.group_name = self.ARM_GROUP
        req.num_planning_attempts = self.NUM_PLANNING_ATTEMPTS
        req.allowed_planning_time = self.ALLOWED_PLANNING_TIME
        req.max_velocity_scaling_factor = self.VEL_SCALING
        req.max_acceleration_scaling_factor = self.ACC_SCALING
        req.goal_constraints = [goal_constraints]

        # plan_only=False -> plan AND execute on the trajectory controller.
        goal.planning_options.plan_only = False
        goal.planning_options.replan = False

        result = self._send_and_wait(
            self._move_client,
            goal,
            f'move_arm_to_pose({x:+.3f},{y:+.3f},{z:.3f})',
            self.RESULT_TIMEOUT,
        )
        if result is None:
            return False
        code = result.error_code.val
        if code == MoveItErrorCodes.SUCCESS:
            return True
        self._warn(
            f'move_arm_to_pose({x:+.3f},{y:+.3f},{z:.3f}) FAILED: '
            f'MoveItErrorCode {code}')
        return False

    # -- gripper -------------------------------------------------------------

    def set_gripper(self, position: float) -> bool:
        """Command the parallel gripper jaw to ``position`` (metres).

        The ``ParallelGripperCommand`` goal carries a ``sensor_msgs/JointState``
        (``command``): we set the controlled joint name + target position and,
        when supported, an effort.  Returns True iff the goal succeeds.
        """
        goal = self._ParallelGripperCommand.Goal()
        # command is a sensor_msgs/JointState on this build.
        goal.command.name = [self.GRIPPER_JOINT]
        goal.command.position = [float(position)]
        # Provide an effort cap when the field exists (it does on JointState).
        try:
            goal.command.effort = [float(self.GRIPPER_MAX_EFFORT)]
        except Exception:  # noqa: BLE001 - tolerate field-shape differences
            pass

        result = self._send_and_wait(
            self._gripper_client,
            goal,
            f'set_gripper({position:.3f})',
            self.RESULT_TIMEOUT,
        )
        if result is None:
            return False
        # GripperActionController result exposes reached_goal/stalled; treat a
        # returned result as success unless it explicitly reports failure.
        reached = getattr(result, 'reached_goal', True)
        stalled = getattr(result, 'stalled', False)
        if reached or stalled:
            return True
        self._warn(
            f'set_gripper({position:.3f}) did not reach goal '
            f'(reached_goal={reached}, stalled={stalled})')
        return False

    def open(self) -> bool:
        """Open the gripper (jaw to GRIPPER_OPEN)."""
        return self.set_gripper(self.GRIPPER_OPEN)

    def close(self) -> bool:
        """Close the gripper (jaw to GRIPPER_CLOSED)."""
        return self.set_gripper(self.GRIPPER_CLOSED)

    # -- one pick-and-place transfer ----------------------------------------

    @staticmethod
    def _xyz(point):
        """Return (x, y, z) from a geometry_msgs/Point or a Point-like obj."""
        return float(point.x), float(point.y), float(point.z)

    def _transfer(self, action) -> bool:
        """Run the 9-step tool-down pick->place choreography for one action."""
        fx, fy, fz = self._xyz(action.from_xyz)
        tx, ty, tz = self._xyz(action.to_xyz)
        # Grasp z comes from the action's xyz; approaches override z to LIFT_Z.
        grasp_from_z = fz if fz else self.GRASP_Z
        grasp_to_z = tz if tz else self.GRASP_Z

        steps = (
            ('FROM-approach', lambda: self.move_arm_to_pose(fx, fy, self.LIFT_Z)),
            ('gripper OPEN', self.open),
            ('FROM-grasp (down)', lambda: self.move_arm_to_pose(fx, fy, grasp_from_z)),
            ('gripper CLOSE', self.close),
            ('FROM-lift (up)', lambda: self.move_arm_to_pose(fx, fy, self.LIFT_Z)),
            ('TO-approach', lambda: self.move_arm_to_pose(tx, ty, self.LIFT_Z)),
            ('TO-grasp (down)', lambda: self.move_arm_to_pose(tx, ty, grasp_to_z)),
            ('gripper OPEN (release)', self.open),
            ('TO-retract (up)', lambda: self.move_arm_to_pose(tx, ty, self.LIFT_Z)),
        )

        n = len(steps)
        for i, (label, step) in enumerate(steps, start=1):
            self._info(f'    step {i}/{n}: {label}')
            if not step():
                self._warn(
                    f'    step {i}/{n} ({label}) FAILED -- aborting transfer')
                return False
        return True

    # -- public entry point --------------------------------------------------

    def execute(self, actions: Sequence) -> bool:
        """Execute every PieceAction's pick/place transfer in order.

        Returns False (after logging) on the first failed sub-motion; True only
        when every action completes its full choreography.
        """
        actions = list(actions)
        if not actions:
            self._warn('MoveItExecutor: empty action list (nothing to do)')
            return True

        if not self._ensure_servers():
            self._warn('MoveItExecutor: action servers not ready -- aborting')
            return False

        self._info(f'MoveItExecutor: executing {len(actions)} action(s):')
        for i, action in enumerate(actions, start=1):
            self._info(f'  [{i}/{len(actions)}] {describe_action(action)}')
            if not self._transfer(action):
                self._warn(
                    f'MoveItExecutor: action [{i}/{len(actions)}] '
                    f'({_action_name(action)}) FAILED -- aborting turn')
                return False
        self._info('MoveItExecutor: all actions completed')
        return True


def make_executor(name: str, logger=None, node=None) -> Executor:
    """Build an executor by parameter value ('dry_run' or 'moveit').

    ``node`` is required for the 'moveit' executor (action clients + logging);
    'dry_run' ignores it.
    """
    name = (name or 'dry_run').strip().lower()
    if name in ('dry_run', 'dryrun', 'dry-run'):
        return DryRunExecutor(logger=logger)
    if name in ('moveit', 'move_it', 'move-it'):
        return MoveItExecutor(logger=logger, node=node)
    raise ValueError(f"unknown executor {name!r}; expected 'dry_run' or 'moveit'")
