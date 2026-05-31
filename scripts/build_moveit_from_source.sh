#!/usr/bin/env bash
# ============================================================================
# Build MoveIt 2 from source for ROS 2 Lyrical (no binaries published yet).
#
# Lyrical has no moveit2 branch; it is the newest distro (forked from Rolling),
# so we build the `main` branch in a DEDICATED workspace (~/ws_moveit2), kept
# separate from the chess-robot workspace. chess_arm_moveit_config overlays it.
#
# Fresh-distro reality (2026-05): four MoveIt deps have rosdep entries but no
# published Lyrical binary, so we source-build the three we need
#   - geometric_shapes  (ros-planning/geometric_shapes @ ros2)  -> moveit_core
#   - osqp_vendor       (tier4/osqp_vendor @ main)              -> moveit_core
#   - ompl              (ompl/ompl @ main, v1.7)                -> moveit_planners_ompl
# and SKIP the one we do not need (warehouse_ros_sqlite -> trajectory_cache).
# We also skip the `position_controllers` key (removed on Lyrical), which only
# the panda/fanuc demo configs and hybrid_planning reference.
#
# Run from anywhere as your normal user (sudo only for the deps step):
#     bash scripts/build_moveit_from_source.sh
# Tune for your RAM with MOVEIT_WORKERS / MOVEIT_MAKE_JOBS.
# ============================================================================
set -uo pipefail

ROS_DISTRO=lyrical
export COLCON_WS="${COLCON_WS:-$HOME/ws_moveit2}"
WORKERS="${MOVEIT_WORKERS:-3}"        # packages built in parallel
MAKE_JOBS="${MOVEIT_MAKE_JOBS:-4}"    # compile jobs per package (workers*jobs ~ RAM/1.5GB)

# Targeted build: move_group + OMPL + IK + RViz plugin + Setup Assistant +
# controller manager + config utils, and their deps. Excludes servo,
# benchmarks, hybrid_planning, trajectory_cache, moveit_py, and demo robot
# configs (none needed for the chess arm; keeps the build lean).
TARGETS="moveit_ros_move_group moveit_planners_ompl moveit_kinematics \
moveit_ros_visualization moveit_setup_assistant moveit_simple_controller_manager \
moveit_configs_utils moveit_ros_planning_interface"

say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "Run as your normal user (not sudo)."
[ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ] || die "ROS ${ROS_DISTRO} not found; run install_ros_lyrical.sh first."
set +u; source "/opt/ros/${ROS_DISTRO}/setup.bash"; set -u

mkdir -p "$COLCON_WS/src"
cd "$COLCON_WS/src"

say "1/4 Sources: moveit2 (main) + companion + source-only deps"
[ -d moveit2 ] || git clone https://github.com/moveit/moveit2.git -b main || die "clone moveit2 failed"
for repo in moveit2/moveit2.repos $(f="moveit2/moveit2_${ROS_DISTRO}.repos"; test -r "$f" && echo "$f"); do
  vcs import --skip-existing < "$repo" || die "vcs import failed"
done
[ -d geometric_shapes ] || git clone --depth 1 -b ros2 https://github.com/ros-planning/geometric_shapes.git || die "clone geometric_shapes failed"
[ -d osqp_vendor ]      || git clone --depth 1 -b main https://github.com/tier4/osqp_vendor.git           || die "clone osqp_vendor failed"
[ -d ompl ]             || git clone --depth 1 -b main https://github.com/ompl/ompl.git                   || die "clone ompl failed"

# Local patch (idempotent): Ubuntu 26.04 ships octomap 1.10.0, but moveit2 main
# pins find_package(octomap 1.9.7...<1.10.0). No breaking OcTree API change
# 1.9->1.10, so raise the ceiling to <1.11.0 in the two packages that cap it.
for f in moveit2/moveit_core/CMakeLists.txt moveit2/moveit_ros/occupancy_map_monitor/CMakeLists.txt; do
  sed -i 's#octomap 1\.9\.7\.\.\.<1\.10\.0#octomap 1.9.7...<1.11.0#' "$f"
done
# Boost 1.90 (Ubuntu 26.04): boost_system is header-only with no component config,
# so find_package(Boost ... system) errors -- including in INSTALLED ConfigExtras
# files that downstream packages read via find_package(). Remove the 'system'
# Boost component from every find_package(Boost ...) block (multi-line aware)
# across moveit2; nothing links Boost::system explicitly.
python3 - "$COLCON_WS/src/moveit2" <<'PY'
import re, sys, glob, os
root = sys.argv[1]
files = set()
for pat in ('**/CMakeLists.txt', '**/*.cmake'):
    files.update(glob.glob(os.path.join(root, pat), recursive=True))
def fix(m):
    b = m.group(0)
    if re.search(r'\bBoost\b', b) and re.search(r'\bsystem\b', b):
        return re.sub(r'[ \t]*\bsystem\b', '', b)
    return b
for fn in files:
    s = open(fn).read()
    n = re.sub(r'find_package\s*\([^)]*\)', fix, s, flags=re.DOTALL)
    if n != s:
        open(fn, 'w').write(n)
PY

# Lyrical REMOVED the long-deprecated ament_target_dependencies macro that moveit2
# main still uses in ~93 CMakeLists. Inject the pre-removal implementation globally
# via CMAKE_PROJECT_INCLUDE_BEFORE (added to the colcon --cmake-args below). Its only
# helper, ament_libraries_deduplicate, still ships in Lyrical.
mkdir -p "$COLCON_WS/lyrical_compat"
[ -f "$COLCON_WS/lyrical_compat/ament_target_dependencies.cmake" ] || \
  curl -fsSL -o "$COLCON_WS/lyrical_compat/ament_target_dependencies.cmake" \
    "https://raw.githubusercontent.com/ament/ament_cmake/jazzy/ament_cmake_target_dependencies/cmake/ament_target_dependencies.cmake" \
  || die "failed to fetch ament_target_dependencies compat shim"

say "2/4 Dependencies (sudo apt) — skipping unbuilt/unneeded keys"
sudo apt-get install -y libboost-all-dev
sudo rosdep init 2>/dev/null || true
rosdep update || echo "WARNING: rosdep update failed; continuing"
rosdep install -r --from-paths src --ignore-src --rosdistro "${ROS_DISTRO}" -y \
  --skip-keys "warehouse_ros_sqlite position_controllers" \
  || echo "WARNING: review unresolved rosdep keys above (expected: none beyond skipped)."

say "3/4 colcon build (Release, workers=${WORKERS}, make -j${MAKE_JOBS}); targeted subset"
cd "$COLCON_WS"
export MAKEFLAGS="-j ${MAKE_JOBS}"
# CMake 4.x (Ubuntu 26.04) removed compat with cmake_minimum_required < 3.5.
# osqp_vendor builds bundled OSQP 0.6.3 (old minimum) via ExternalProject; this
# env var propagates to that inner cmake so it configures. Harmless for modern pkgs.
export CMAKE_POLICY_VERSION_MINIMUM=3.5
# shellcheck disable=SC2086
colcon build \
  --packages-up-to ${TARGETS} \
  --parallel-workers "${WORKERS}" \
  --event-handlers desktop_notification- status- \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
    "-DCMAKE_PROJECT_INCLUDE_BEFORE=${COLCON_WS}/lyrical_compat/ament_target_dependencies.cmake" \
  || die "colcon build failed; inspect log/latest_build/ for the first failing package."

say "4/4 Done"
cat <<EOF
MoveIt 2 built. Source it (after base ROS) where MoveIt is needed:
    source /opt/ros/${ROS_DISTRO}/setup.bash
    source ${COLCON_WS}/install/setup.bash
chess_arm_moveit_config will overlay this.
EOF
