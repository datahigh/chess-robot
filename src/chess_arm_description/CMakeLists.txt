cmake_minimum_required(VERSION 3.10)
project(chess_arm_description)

find_package(ament_cmake REQUIRED)

# Pure description package: install data trees so they resolve via FindPackageShare.
install(
  DIRECTORY urdf meshes launch rviz config worlds
  DESTINATION share/${PROJECT_NAME}
)

# Stand-alone helper scripts (runnable via `ros2 run chess_arm_description <script>`).
install(
  PROGRAMS
    scripts/reachability_check.py
    scripts/gen_board_coordinates.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()  # MUST be last
