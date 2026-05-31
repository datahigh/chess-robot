#!/usr/bin/env bash
# ============================================================================
# Build the workspace and validate chess_arm_description on ROS 2 Lyrical.
# Run after install_ros_lyrical.sh, from the repo root, as your normal user:
#
#     bash scripts/build_and_verify.sh
#
# Does NOT need sudo. Expands the xacro in both configurations and runs
# check_urdf + the reachability proof. Safe to re-run.
# ============================================================================
set -uo pipefail

ROS_DISTRO=lyrical
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ] || die "ROS ${ROS_DISTRO} not found. Run scripts/install_ros_lyrical.sh first."
# ROS setup scripts reference unbound vars; relax nounset around the source.
set +u; source "/opt/ros/${ROS_DISTRO}/setup.bash"; set -u
cd "$REPO"

say "colcon build (chess_arm_description)"
colcon build --packages-select chess_arm_description --symlink-install || die "colcon build failed."
set +u; source "$REPO/install/setup.bash"; set -u

SHARE="$(ros2 pkg prefix chess_arm_description)/share/chess_arm_description"
XACRO="$SHARE/urdf/chess_arm.urdf.xacro"

say "Expand + check_urdf: RViz scene (with_world:=true, mock_components)"
xacro "$XACRO" with_world:=true ros2_control_hardware_type:=mock_components > /tmp/chess_arm_scene.urdf \
  || die "xacro failed (scene/mock)."
check_urdf /tmp/chess_arm_scene.urdf || die "check_urdf failed (scene)."

say "Expand + check_urdf: MoveIt/Gazebo config (with_world:=false, gz)"
xacro "$XACRO" with_world:=false ros2_control_hardware_type:=gz > /tmp/chess_arm_gz.urdf \
  || die "xacro failed (gz/no-world)."
check_urdf /tmp/chess_arm_gz.urdf || die "check_urdf failed (gz)."

say "Reachability proof"
python3 "$SHARE/../chess_arm_description/scripts/reachability_check.py" 2>/dev/null \
  || python3 "$REPO/src/chess_arm_description/scripts/reachability_check.py" \
  || die "reachability check failed."

cat <<EOF

ALL CHECKS PASSED. Launch the RViz display (drag joint sliders over the board):
    source $REPO/install/setup.bash
    ros2 launch chess_arm_description display.launch.py
EOF
