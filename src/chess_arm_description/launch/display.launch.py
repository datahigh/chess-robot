"""RViz display for the chess arm + board/graveyard scene (Phase 0).

Runs xacro at launch -> robot_state_publisher -> joint_state_publisher_gui ->
RViz. Use the GUI sliders to drive J1..J6 + the gripper and eyeball reach over
the board. No controllers/Gazebo here — that is bringup/MoveIt territory.

    ros2 launch chess_arm_description display.launch.py
    ros2 launch chess_arm_description display.launch.py gui:=false
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import (
    Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg = FindPackageShare('chess_arm_description')
    gui = LaunchConfiguration('gui')
    rviz = LaunchConfiguration('rviz')
    hardware_type = LaunchConfiguration('ros2_control_hardware_type')
    with_world = LaunchConfiguration('with_world')

    xacro_file = PathJoinSubstitution([pkg, 'urdf', 'chess_arm.urdf.xacro'])
    rviz_cfg = PathJoinSubstitution([pkg, 'rviz', 'view.rviz'])

    # value_type=str is mandatory for a Command()-sourced robot_description, and
    # each token (incl. spaces) must be its own list element.
    robot_description = ParameterValue(
        Command([
            FindExecutable(name='xacro'), ' ', xacro_file,
            ' ', 'ros2_control_hardware_type:=', hardware_type,
            ' ', 'with_world:=', with_world,
        ]),
        value_type=str)

    return LaunchDescription([
        DeclareLaunchArgument(
            'gui', default_value='true',
            description='Use joint_state_publisher_gui (sliders) vs headless.'),
        DeclareLaunchArgument(
            'ros2_control_hardware_type', default_value='mock_components',
            description='mock_components | gz | real'),
        DeclareLaunchArgument(
            'with_world', default_value='true',
            description='Attach the static board + graveyard scene.'),
        DeclareLaunchArgument(
            'rviz', default_value='true',
            description='Launch RViz (set false for headless).'),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            condition=IfCondition(gui),
        ),
        Node(
            package='joint_state_publisher',
            executable='joint_state_publisher',
            condition=UnlessCondition(gui),
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            output='screen',
            arguments=['-d', rviz_cfg],
            condition=IfCondition(rviz),
        ),
    ])
