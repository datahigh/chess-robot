from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_move_group_launch


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
        # Restrict to OMPL: only ompl is built from source on Lyrical. Without
        # this, the builder auto-loads pilz/chomp/stomp and move_group aborts
        # trying to load the (absent) pilz_industrial_motion_planner plugin.
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )
    return generate_move_group_launch(moveit_config)
