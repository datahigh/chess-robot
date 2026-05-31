#!/usr/bin/env bash
# ============================================================================
# Install ROS 2 Lyrical Luth + sim/control deps on Ubuntu 26.04 "Resolute".
#
# Idempotent: safe to re-run. Calls sudo internally for apt steps; run as your
# normal user (NOT with sudo) so rosdep init/update touch the right home:
#
#     bash scripts/install_ros_lyrical.sh
#
# Notes baked in for this brand-new distro:
#  - ros-lyrical-desktop is pulled with --no-install-suggests to dodge the
#    `hyperspec` packaging bug (ros2/ros2#1835).
#  - Mirrors may briefly 404 right after release; just re-run if a fetch fails.
# ============================================================================
set -uo pipefail

ROS_DISTRO=lyrical
say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "Run as your normal user (not sudo); the script sudo's as needed."
. /etc/os-release
say "Detected ${PRETTY_NAME:-unknown} (codename ${VERSION_CODENAME:-?})"
[ "${VERSION_CODENAME:-}" = "resolute" ] || \
  echo "WARNING: expected Ubuntu 26.04 'resolute'; continuing anyway."

say "1/7 Locale (UTF-8)"
sudo apt-get update -y
sudo apt-get install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

say "2/7 Prereqs + universe repo"
sudo apt-get install -y software-properties-common curl
sudo add-apt-repository -y universe

say "3/7 ros2-apt-source (adds the ROS 2 apt repo + key)"
if ! dpkg -s ros2-apt-source >/dev/null 2>&1; then
  ROS_APT_SOURCE_VERSION="$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
      | grep -F '"tag_name"' | awk -F'"' '{print $4}')"
  [ -n "$ROS_APT_SOURCE_VERSION" ] || die "Could not resolve ros-apt-source latest release."
  deb="/tmp/ros2-apt-source.deb"
  url="https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${VERSION_CODENAME}_all.deb"
  echo "Fetching $url"
  curl -fsSL -o "$deb" "$url" || die "Download failed (mirror may not have ${VERSION_CODENAME} yet). Re-run later."
  sudo apt-get install -y "$deb"
else
  echo "ros2-apt-source already installed; skipping."
fi
sudo apt-get update -y

say "4/7 ROS 2 ${ROS_DISTRO} desktop (--no-install-suggests avoids the hyperspec bug)"
sudo apt-get install -y --no-install-suggests ros-${ROS_DISTRO}-desktop

say "5/7 Sim + control + this project's runtime deps"
sudo apt-get install -y --no-install-suggests \
  ros-${ROS_DISTRO}-xacro \
  ros-${ROS_DISTRO}-joint-state-publisher \
  ros-${ROS_DISTRO}-joint-state-publisher-gui \
  ros-${ROS_DISTRO}-ros2-control \
  ros-${ROS_DISTRO}-ros2-controllers \
  ros-${ROS_DISTRO}-parallel-gripper-controller \
  ros-${ROS_DISTRO}-ros-gz \
  ros-${ROS_DISTRO}-gz-ros2-control \
  || echo "WARNING: one or more sim/control packages failed (mirror lag?). Re-run later."

say "6/7 Build tooling + rosdep"
sudo apt-get install -y python3-colcon-common-extensions python3-rosdep python3-vcstool build-essential
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init || true
fi
rosdep update || echo "WARNING: rosdep update failed (network?); retry later."

say "7/7 Availability probe (informational)"
probe() { printf '  %-34s ' "$1:"; apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/{print $2}' | grep -q . \
  && apt-cache policy "$1" | awk '/Candidate:/{print $2}' || echo "NOT FOUND"; }
probe ros-${ROS_DISTRO}-desktop
probe ros-${ROS_DISTRO}-ros-gz
probe ros-${ROS_DISTRO}-gz-ros2-control
probe ros-${ROS_DISTRO}-parallel-gripper-controller
echo "  --- MoveIt 2 (watch item; may lag a fresh distro) ---"
probe ros-${ROS_DISTRO}-moveit
probe ros-${ROS_DISTRO}-moveit-setup-assistant

cat <<EOF

DONE. Source ROS in new shells with:
    source /opt/ros/${ROS_DISTRO}/setup.bash
Then build + validate this workspace:
    bash scripts/build_and_verify.sh
EOF
