cmake_minimum_required(VERSION 3.5)
project(golfcart_sensor_kit_launch)

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # Checks on the camera intrinsics themselves. Every defect they look for was
  # live in this repository and survived months of review, because a
  # plausible-looking matrix reads as a calibration whatever it actually says.
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_camera_calibration test/test_camera_calibration.py)
endif()

ament_auto_package(INSTALL_TO_SHARE
  launch
  data
  config
)
