from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_moveit_rviz_launch


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
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )
    return generate_moveit_rviz_launch(moveit_config)
