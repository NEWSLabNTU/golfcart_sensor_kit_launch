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
- Cameras (ZED X Mini)
- IMU (MPU9250)
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

Supported camera models:
- ZED X Mini stereo camera

Launch files:
- `launch/camera.launch.xml`: Launch file for ZED cameras

#### IMU Sensors

Supported IMU models:
- MPU9250 Inertial Measurement Unit

Launch files:
- `launch/imu.launch.xml`: Launch file for MPU9250 IMU with bias correction

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
# Specify camera model
ros2 launch golfcart_sensor_kit_launch camera.launch.xml camera_model:=zedxm
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
- `/camera/zedxm/rgb/image_rect_color`: Color images from ZED camera
- `/camera/zedxm/depth/depth_registered`: Depth images from ZED camera

### IMU Topics
- `/sensing/imu/imu_data`: Corrected IMU data for localization

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
