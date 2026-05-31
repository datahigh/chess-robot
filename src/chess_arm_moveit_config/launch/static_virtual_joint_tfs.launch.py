from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_static_virtual_joint_tfs_launch


def generate_launch_description():
    moveit_config = (
        MoveItConfigsBuilder("chess_arm", package_name="chess_arm_moveit_config")
        .robot_description(
            file_path="config/chess_arm.urdf.xacro",
            mappings={
                "ros2_control_hardware_type": "mock_components",
                "with_world": "false",
            },
        )
        .to_moveit_configs()
    )
    # The chess_arm SRDF declares NO virtual_joint (the URDF roots at the static
    # "world" link via a fixed world->base_link joint, published by RViz/the
    # planning scene), so this generates an empty LaunchDescription. The file is
    # kept because generate_demo_launch includes it when present.
    return generate_static_virtual_joint_tfs_launch(moveit_config)
