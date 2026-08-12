# Golf Cart Sensor Kit

This package provides the sensor kit description and launch files for the Golf Cart autonomous vehicle platform. It enables integration of various sensors with the Autoware autonomous driving stack.

## Overview

The Golf Cart sensor kit consists of:

1. **Sensor Kit Description**: URDF models and calibration files describing the physical arrangement of sensors on the vehicle
2. **Sensor Launch Files**: ROS2 launch configurations for different types of sensors
3. **Sensor Integration**: Integration with Autoware's perception stack

## Components

### 1. Golf Cart Sensor Kit Description

Located in `golfcart_sensor_kit_description/`, this package contains:

- URDF models for the sensor kit (`urdf/sensor_kit.xacro`, `urdf/sensors.xacro`)
- Calibration parameters for sensor positioning (`config/sensor_kit_calibration.yaml`)
- Sensor-specific calibration data (`config/sensors_calibration.yaml`)

The sensor kit provides mounting points and calibration for:
- LiDAR sensors
- Cameras (three GMSL cameras, one ZED X)
- IMU (Xsens MTi over CAN, or the ZED X built-in IMU)
- GNSS receivers

### 2. Golf Cart Sensor Kit Launch

Located in `golfcart_sensor_kit_launch/`, this package contains launch files for:

#### LiDAR Sensors

Supported LiDAR models:
- Blickfeld Cube1 LiDAR
- Seyond Robin-W Solid-State LiDAR
- Velodyne 32C LiDAR (via optional configuration)

Launch files:
- `launch/lidar.launch.xml`: Main launch file for LiDAR sensors
- `launch/seyond_start.py`: Launch file for Seyond LiDAR integration

#### Camera Sensors

Two camera sets on two machines, selected by `camera_model`:
- `gscam` — three GMSL cameras (left, right, rear) on the Advantech
- `zedx` — one ZED X stereo camera on the orin
- `none` — no cameras

Launch files:
- `launch/camera.launch.xml`: single entry point, dispatches on `camera_model`
- `launch/zed.launch.xml`: ZED X driver, container, and its `robot_state_publisher`

Configuration:
- `config/camera_{left,right,rear}.yaml`: gscam device and pipeline settings
- `config/zed.param.yaml`: ZED overrides, layered over the vendor defaults

See [docs/design/zed_camera_integration.md](../../../docs/design/zed_camera_integration.md).

#### IMU Sensors

Two sources, selected by `imu_source`:
- `xsens` — Xsens MTi over CAN, wired to the Advantech (driver launched here)
- `zed` — the ZED X built-in IMU (published by the ZED node on the orin)

Launch files:
- `launch/imu.launch.xml`: source selection plus `imu_corrector` and
  `gyro_bias_estimator`, which run for either source

#### GNSS Sensors

Supported GNSS receivers:
- Garmin GPS (default)
- u-blox GPS
- Septentrio GNSS

Launch files:
- `launch/gnss.launch.xml`: Launch file for GNSS receivers with coordinate transformation

#### Combined Sensing Launch

The `sensing.launch.xml` file provides a combined launch configuration for all sensors:
- Launches all sensor drivers (LiDAR, camera, IMU, GNSS)
- Configures topic remapping for Autoware integration
- Sets up vehicle velocity conversion for odometry

## Usage

### Launching All Sensors

To launch all sensors:

```bash
ros2 launch golfcart_sensor_kit_launch sensing.launch.xml
```

### Launching Specific Sensors

To launch only specific sensors:

```bash
# LiDAR only
ros2 launch golfcart_sensor_kit_launch lidar.launch.xml

# Camera only
ros2 launch golfcart_sensor_kit_launch camera.launch.xml

# IMU only
ros2 launch golfcart_sensor_kit_launch imu.launch.xml

# GNSS only
ros2 launch golfcart_sensor_kit_launch gnss.launch.xml
```

### Configuration

Each sensor can be configured through launch arguments:

#### LiDAR Configuration

```bash
# Specify LiDAR model (cube1 or robin-w)
ros2 launch golfcart_sensor_kit_launch lidar.launch.xml lidar_model:=cube1

# Specify LiDAR IP address
ros2 launch golfcart_sensor_kit_launch lidar.launch.xml host_ip:=192.168.26.1
```

#### Camera Configuration

```bash
# Three GMSL cameras (Advantech)
ros2 launch golfcart_sensor_kit_launch camera.launch.xml camera_model:=gscam

# ZED X (orin)
ros2 launch golfcart_sensor_kit_launch camera.launch.xml camera_model:=zedx
```

#### IMU Configuration

```bash
# Xsens MTi over CAN (default)
ros2 launch golfcart_sensor_kit_launch imu.launch.xml imu_source:=xsens

# ZED X built-in IMU - the ZED node must be running on the orin
ros2 launch golfcart_sensor_kit_launch imu.launch.xml imu_source:=zed
```

Through the full stack these are reached by environment variable, since the
Autoware sensing launch chain forwards only a fixed set of arguments:

```bash
CAMERA_MODEL=gscam IMU_SOURCE=zed just launch
```

#### GNSS Configuration

```bash
# Specify GNSS receiver type (garmin, ublox, or septentrio)
ros2 launch golfcart_sensor_kit_launch gnss.launch.xml gnss_receiver:=ublox
```

## Integration with Autoware

The sensor kit integrates with Autoware through the following topics:

### LiDAR Topics
- `/lidar/points_raw`: Raw pointcloud data from the LiDAR sensors

### Camera Topics
- `/sensing/camera/{left,right,rear}/image_raw/compressed`: GMSL cameras
- `/sensing/camera/zed/rgb/color/rect/image`: rectified colour image from the
  ZED X. On a stereo ZED the RGB channel is the left camera, and the image is
  stamped `zed_left_camera_frame_optical`
- `/sensing/camera/zed/rgb/color/rect/camera_info`: matching intrinsics

### IMU Topics
- `/sensing/camera/zed/imu/data`: ZED X built-in IMU, calibrated, with orientation
- `/sensing/imu/imu_data`: Corrected IMU data for localization, from whichever
  source `imu_source` selects

### GNSS Topics
- `/sensing/gnss/pose`: GNSS position in map frame
- `/sensing/gnss/pose_with_covariance`: GNSS position with uncertainty information

## Sensor Calibration

Sensor positions and orientations are defined in:
- `golfcart_sensor_kit_description/config/sensor_kit_calibration.yaml`

To update sensor calibration:
1. Measure the physical positions of sensors relative to the base link
2. Update the calibration file with the new measurements
3. Rebuild the package to apply changes

## Diagnostic Features

The sensor kit includes diagnostic features:
- Diagnostic aggregator for monitoring sensor health
- Dummy diagnostic publishers for testing
- Configuration of diagnostic parameters in `config/diagnostic_aggregator/`
