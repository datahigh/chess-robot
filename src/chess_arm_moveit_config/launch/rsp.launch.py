from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_rsp_launch

from launch.substitutions import LaunchConfiguration


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
    return generate_rsp_launch(moveit_config)


# Keep the import referenced for linters that flag unused imports; the substitution
# is also useful if a maintainer later wants to parameterize the hardware type.
_ = LaunchConfiguration
