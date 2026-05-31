# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Phase-0 CLOSER: run a CONTINUOUS multi-turn LIVE game in simulation.

This brings up the full service graph and plays a scripted game end-to-end,
exercising the real orchestrator state machine (DETECT -> RESOLVE -> ENGINE ->
PLAN -> EXECUTE via MoveIt -> VERIFY) once per human move, with the arm actually
moving in the mock_components sim.

What it starts
--------------
1. The verified MoveIt sim stack, reusing chess_arm_moveit_config EXACTLY as
   game_moveit.launch.py does -- by including ``demo.launch.py``
   (``generate_demo_launch``), which itself wires:
     * robot_state_publisher   (rsp.launch.py)
     * move_group              (move_group.launch.py; OMPL-only, frame 'world',
                                tip 'tcp')
     * ros2_control_node       (controller_manager, mock_components)
     * controller spawners     (joint_state_broadcaster, arm_controller,
                                gripper_controller -- spawn_controllers.launch.py)
     * RViz                    (gated by use_rviz; default false here)
   Reusing demo.launch.py keeps this in lock-step with the moveit_config the
   Setup Assistant produced (the controller param-file fix and the OMPL-only
   restriction both live there).
2. ``chess_arm_brain`` brain_node   -- ResolveHumanMove / GetEngineMove /
                                        PlanPieceActions (python-chess + Stockfish).
3. ``chess_arm_vision`` vision_node -- DetectChanges over the latched
                                        /sim_board_fen ground truth.
4. ``chess_arm_orchestrator`` orchestrator_node -- executor:=moveit,
                                        verify_after_move:=true.  Runs one full
                                        turn per /human_move_done and re-publishes
                                        the post-engine FEN.
5. ``chess_arm_orchestrator`` sim_game_driver -- plays the HUMAN (White) side of
                                        a scripted opening, publishing post-human
                                        FENs and calling /human_move_done per turn.

Run it::

    ros2 launch chess_arm_orchestrator live_game.launch.py
    ros2 launch chess_arm_orchestrator live_game.launch.py use_rviz:=true
    ros2 launch chess_arm_orchestrator live_game.launch.py \
        movetime_ms:=200 elo:=1500 moves:='[e2e4, g1f3, f1c4, b1c3, d2d4]'
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Bring up the live sim stack + brain + vision + orchestrator + driver."""
    use_rviz = LaunchConfiguration('use_rviz')
    movetime_ms = LaunchConfiguration('movetime_ms')
    elo = LaunchConfiguration('elo')
    skill_level = LaunchConfiguration('skill_level')
    moves = LaunchConfiguration('moves')
    service_timeout_sec = LaunchConfiguration('service_timeout_sec')

    args = [
        DeclareLaunchArgument(
            'use_rviz', default_value='false',
            description='start RViz with the MoveIt motion-planning display'),
        DeclareLaunchArgument(
            'movetime_ms', default_value='100',
            description='Stockfish movetime cap in milliseconds (brain_node)'),
        DeclareLaunchArgument(
            'elo', default_value='-1',
            description='Stockfish UCI_Elo (-1 = unset / full strength)'),
        DeclareLaunchArgument(
            'skill_level', default_value='-1',
            description='Stockfish Skill Level 0..20 (-1 = unset)'),
        DeclareLaunchArgument(
            'moves',
            default_value='[e2e4, g1f3, f1c4, b1c3, d2d4]',
            description=(
                'scripted human (White) UCI moves for sim_game_driver; an '
                'illegal scripted move falls back to a legal one so the loop '
                'stays continuous')),
        DeclareLaunchArgument(
            'service_timeout_sec', default_value='15.0',
            description='orchestrator per-service-call timeout (seconds)'),
    ]

    # -- full MoveIt sim stack (move_group, rsp, ros2_control, controllers, --
    # -- rviz) -- reused EXACTLY as game_moveit.launch.py does. demo.launch.py
    # exposes a `use_rviz` boolean arg; we forward ours (default false).
    moveit_demo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('chess_arm_moveit_config'),
                'launch', 'demo.launch.py',
            ])
        ),
        launch_arguments={'use_rviz': use_rviz}.items(),
    )

    # -- brain (authoritative game state + Stockfish) -------------------------
    brain_node = Node(
        package='chess_arm_brain',
        executable='brain_node',
        name='chess_arm_brain',
        output='screen',
        parameters=[{
            'movetime_ms': movetime_ms,
            'elo': elo,
            'skill_level': skill_level,
        }],
    )

    # -- vision (DetectChanges over the latched /sim_board_fen ground truth) ---
    vision_node = Node(
        package='chess_arm_vision',
        executable='vision_node',
        name='chess_arm_vision',
        output='screen',
    )

    # -- orchestrator: real state machine, MoveIt executor, verify on ---------
    orchestrator_node = Node(
        package='chess_arm_orchestrator',
        executable='orchestrator_node',
        name='chess_arm_orchestrator',
        output='screen',
        parameters=[{
            'executor': 'moveit',
            'verify_after_move': True,
            'autostop_on_game_over': True,
            'service_timeout_sec': service_timeout_sec,
        }],
    )

    # -- sim_game_driver: plays the HUMAN side of the scripted game -----------
    sim_game_driver = Node(
        package='chess_arm_orchestrator',
        executable='sim_game_driver',
        name='sim_game_driver',
        output='screen',
        parameters=[{
            'moves': moves,
        }],
    )

    return LaunchDescription(args + [
        moveit_demo,
        brain_node,
        vision_node,
        orchestrator_node,
        sim_game_driver,
    ])
