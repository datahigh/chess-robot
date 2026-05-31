# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Bring up the FULL MoveIt stack + brain + vision so the arm can move in sim.

This is the launch file behind ``play_sim_game`` (and the MoveIt executor in the
orchestrator): it starts a live ``move_group`` against the mock_components sim,
then the application nodes the game loop needs.

What it brings up (by including chess_arm_moveit_config's ``demo.launch.py``,
which itself wires the verified stack):

* robot_state_publisher       (rsp.launch.py)
* move_group                  (move_group.launch.py; OMPL-only, planning frame
                               'world', tip link 'tcp')
* ros2_control_node           (controller_manager with mock_components)
* controller spawners         (joint_state_broadcaster, arm_controller,
                               gripper_controller -- spawn_controllers.launch.py)
* RViz                        (moveit_rviz.launch.py; gated by use_rviz)

plus, on top of the MoveIt stack:

* chess_arm_brain  brain_node   (python-chess board + Stockfish; serves
                                 ResolveHumanMove / GetEngineMove /
                                 PlanPieceActions)
* chess_arm_vision vision_node  (serves DetectChanges; Phase 0 stub)

Reusing demo.launch.py (rather than re-assembling move_group + rsp +
spawn_controllers + ros2_control_node by hand) keeps this in lock-step with the
moveit_config the Setup Assistant produced: the controller param-file fix and
the OMPL-only restriction both live there.

Run it::

    ros2 launch chess_arm_orchestrator game_moveit.launch.py
    ros2 launch chess_arm_orchestrator game_moveit.launch.py use_rviz:=true
    ros2 launch chess_arm_orchestrator game_moveit.launch.py movetime_ms:=200 elo:=1500

Then drive the arm through the scripted pick/place loop::

    ros2 run chess_arm_orchestrator play_sim_game
    ros2 run chess_arm_orchestrator play_sim_game all          # every special case

Or run the orchestrator state machine against this stack::

    ros2 run chess_arm_orchestrator orchestrator_node --ros-args -p executor:=moveit
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Bring up the MoveIt sim stack + brain + vision for arm-side play."""
    use_rviz = LaunchConfiguration('use_rviz')
    movetime_ms = LaunchConfiguration('movetime_ms')
    elo = LaunchConfiguration('elo')
    skill_level = LaunchConfiguration('skill_level')

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
    ]

    # -- full MoveIt stack (move_group, rsp, ros2_control, controllers, rviz) --
    # demo.launch.py exposes a `use_rviz` boolean arg (default true); we forward
    # ours (default false) so play_sim_game runs headless unless asked.
    moveit_demo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('chess_arm_moveit_config'),
                'launch', 'demo.launch.py',
            ])
        ),
        launch_arguments={'use_rviz': use_rviz}.items(),
    )

    # -- application nodes the game loop needs --------------------------------
    # brain_node params match its declarations: movetime_ms / skill_level / elo.
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

    vision_node = Node(
        package='chess_arm_vision',
        executable='vision_node',
        name='chess_arm_vision',
        output='screen',
    )

    return LaunchDescription(args + [moveit_demo, brain_node, vision_node])
