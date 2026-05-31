# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Bring up the full Phase-0 game loop: brain + vision + orchestrator.

Starts the three application nodes that play a game in sim:

* chess_arm_brain   brain_node       (python-chess board + Stockfish; serves
  ResolveHumanMove / GetEngineMove / PlanPieceActions)
* chess_arm_vision  vision_node      (serves DetectChanges; Phase 0 stub)
* chess_arm_orchestrator orchestrator_node (the state machine; default
  executor = dry_run)

Trigger a turn after each human move with::

    ros2 service call /human_move_done std_srvs/srv/Trigger {}

Arguments::

    ros2 launch chess_arm_orchestrator game.launch.py executor:=dry_run
    ros2 launch chess_arm_orchestrator game.launch.py elo:=1500 movetime_ms:=200

MoveIt/Gazebo are NOT launched here -- pick executor:=moveit (a stub today) and
wire move_group in the Phase 4 integration step.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Build the launch description for the brain/vision/orchestrator trio."""
    executor = LaunchConfiguration('executor')
    elo = LaunchConfiguration('elo')
    skill = LaunchConfiguration('skill')
    movetime_ms = LaunchConfiguration('movetime_ms')

    args = [
        DeclareLaunchArgument(
            'executor', default_value='dry_run',
            description="orchestrator executor: 'dry_run' or 'moveit'"),
        DeclareLaunchArgument(
            'elo', default_value='0',
            description='Stockfish UCI_Elo (0 = unlimited strength)'),
        DeclareLaunchArgument(
            'skill', default_value='-1',
            description='Stockfish Skill Level 0..20 (-1 = unset)'),
        DeclareLaunchArgument(
            'movetime_ms', default_value='100',
            description='engine movetime cap in milliseconds'),
    ]

    brain_node = Node(
        package='chess_arm_brain',
        executable='brain_node',
        name='chess_arm_brain',
        output='screen',
        parameters=[{
            'elo': elo,
            'skill': skill,
            'movetime_ms': movetime_ms,
        }],
    )

    vision_node = Node(
        package='chess_arm_vision',
        executable='vision_node',
        name='chess_arm_vision',
        output='screen',
    )

    orchestrator_node = Node(
        package='chess_arm_orchestrator',
        executable='orchestrator_node',
        name='chess_arm_orchestrator',
        output='screen',
        parameters=[{
            'executor': executor,
        }],
    )

    return LaunchDescription(args + [brain_node, vision_node, orchestrator_node])
