"""Spawn the ros2_control controllers for the chess_arm MoveIt demo.

NOTE: moveit_configs_utils.generate_spawn_controllers_launch spawns controllers
WITHOUT a --param-file. On ROS 2 Lyrical's ros2_control, the controller_manager
loads only its own `controller_manager:` section (controller *types*); the
top-level per-controller param sections (`arm_controller:`, `gripper_controller:`)
are NOT auto-forwarded, so controllers come up with empty `joints`/`joint` and
fail to initialize. We therefore spawn each controller with
`--param-file config/ros2_controllers.yaml` so its node loads its own section.
"""
from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    controllers_yaml = PathJoinSubstitution(
        [FindPackageShare("chess_arm_moveit_config"), "config", "ros2_controllers.yaml"]
    )
    # joint_state_broadcaster needs no params; arm_controller + gripper_controller do.
    controllers = ["joint_state_broadcaster", "arm_controller", "gripper_controller"]
    return LaunchDescription([
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=[c, "--param-file", controllers_yaml],
            output="screen",
        )
        for c in controllers
    ])
