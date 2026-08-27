# Copyright 2020 Tier IV, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
LiDAR preprocessing and concatenation, in one of two modes.

`pointcloud_backend:=cpu` runs the whole stage on the CPU, `:=cuda` runs it on
the GPU. The **drivers stay on the CPU either way**: Nebula has no CUDA decoder
for Velodyne (only an unmerged, Hesai-only PR), and the Seyond driver is a vendor
CPU binary. That costs less than it sounds, because the host-to-device upload
happens at the preprocessor's input, which is exactly what Autoware's own
`pipeline_mode:=cuda` does with a CPU Nebula driver.

The two modes are whole-stage alternatives, not a menu:

    cpu    <ns>/<raw>  -> crop_box_filter_self   (ego body removed)
                       -> distortion_corrector   (per-point deskew, IMU + twist)
                       -> ring_outlier_filter
                       -> <ns>/pointcloud_before_sync
           ... then PointCloudConcatenateDataSynchronizerComponent

    cuda   <ns>/<raw>  -> CudaPointcloudPreprocessorNode   (all three, one kernel
                          sequence over one device buffer)
                       -> <ns>/pointcloud_before_sync{,/cuda}
           ... then CudaPointCloudConcatenateDataSynchronizerComponent

Mixing halves does not work and is not offered. The CUDA concatenator subscribes
over `cuda_blackboard`, which needs the negotiation topic
(`pointcloud_before_sync/cuda`) that only the CUDA preprocessor publishes; wire a
CPU chain into it and every cloud arrives with a null device pointer. Autoware's
own enum has no `cpu-preprocess + cuda-concat` mode for the same reason. See
docs/research/sensing/autoware-cuda-pointcloud-chain.md.

Only the Velodyne is preprocessed. See PREPROCESSED_LIDARS below.
"""

import os

from ament_index_python.packages import get_package_share_directory
import launch
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.actions import SetLaunchConfiguration
from launch.conditions import IfCondition
from launch.conditions import UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LoadComposableNodes
from launch_ros.descriptions import ComposableNode
from launch_ros.parameter_descriptions import ParameterFile

BACKENDS = ("cpu", "cuda")

# LiDARs that go through preprocessing, as (namespace, raw topic).
#
# The Velodyne only. Nebula publishes `velodyne_points` in the
# `PointXYZIRCAEDT` layout (it is what Autoware renames to `pointcloud_raw_ex`),
# and that layout is what both the distortion corrector and the ring outlier
# filter need: the per-point `time_stamp` says where the vehicle was when each
# point was measured, and `azimuth`/`distance` drive the outlier test.
PREPROCESSED_LIDARS = [("vlp32", "velodyne_points")]

# LiDARs that reach the concatenator untouched, as (namespace, raw topic).
#
# The Seyond Falcon, and NOT by choice. `seyond_ros_driver` registers
# `PointXYZIRC`: x, y, z, intensity, return_type, ring. No azimuth, no
# elevation, no distance, no per-point time. Without a per-point time offset a
# cloud cannot be deskewed by anything, CPU or GPU, so this branch is not merely
# un-accelerated, it is uncorrectable until the driver emits `PointXYZIRCAEDT`.
#
# It still concatenates. The CUDA concatenator accepts a plain `PointCloud2`
# beside a negotiated one and uploads it.
PASSTHROUGH_LIDARS = [("falcon", "iv_points")]

# Output of the preprocessing stage, per LiDAR namespace. Deliberately the same
# name in both modes, so the concatenator's `input_topics` does not depend on the
# backend; in cuda mode a `<topic>/cuda` negotiation companion appears alongside.
PREPROCESSED_TOPIC = "pointcloud_before_sync"

TWIST_TOPIC = "/sensing/vehicle_velocity_converter/twist_with_covariance"
IMU_TOPIC = "/sensing/imu/imu_data"


def get_vehicle_info(context):
    """Derive the ego bounding box from the global vehicle parameters.

    Same derivation as aip_launcher's copy. The keys come from
    `vehicle_info_param_file`, which the sensing launch chain already puts into
    the launch context as global parameters.
    """
    gp = context.launch_configurations.get("ros_params", {})
    if not gp:
        gp = dict(context.launch_configurations.get("global_params", {}))
    p = {}
    p["min_longitudinal_offset"] = -gp["rear_overhang"]
    p["max_longitudinal_offset"] = gp["front_overhang"] + gp["wheel_base"]
    p["min_lateral_offset"] = -(gp["wheel_tread"] / 2.0 + gp["right_overhang"])
    p["max_lateral_offset"] = gp["wheel_tread"] / 2.0 + gp["left_overhang"]
    p["min_height_offset"] = 0.0
    p["max_height_offset"] = gp["vehicle_height"]
    return p


def _param(name, context):
    return ParameterFile(
        param_file=LaunchConfiguration(name).perform(context), allow_substs=True
    )


def make_cpu_preprocessor_nodes(context, ns, raw_topic, vehicle_info, intra_process):
    """Crop box, distortion correction and ring outlier filtering, as three nodes."""
    crop_box_params = {
        "input_frame": LaunchConfiguration("base_frame"),
        "output_frame": LaunchConfiguration("base_frame"),
        "negative": True,
        # Required: the component declares it statically and refuses to
        # construct without it ("Statically typed parameter
        # 'processing_time_threshold_sec' must be initialized.").
        "processing_time_threshold_sec": 0.01,
        "min_x": vehicle_info["min_longitudinal_offset"],
        "max_x": vehicle_info["max_longitudinal_offset"],
        "min_y": vehicle_info["min_lateral_offset"],
        "max_y": vehicle_info["max_lateral_offset"],
        "min_z": vehicle_info["min_height_offset"],
        "max_z": vehicle_info["max_height_offset"],
    }
    extra = [{"use_intra_process_comms": intra_process}]
    return [
        ComposableNode(
            package="autoware_pointcloud_preprocessor",
            plugin="autoware::pointcloud_preprocessor::CropBoxFilterComponent",
            name=f"{ns}_crop_box_filter_self",
            remappings=[
                ("input", f"{ns}/{raw_topic}"),
                ("output", f"{ns}/self_cropped/pointcloud_ex"),
            ],
            parameters=[crop_box_params],
            extra_arguments=extra,
        ),
        ComposableNode(
            package="autoware_pointcloud_preprocessor",
            plugin="autoware::pointcloud_preprocessor::DistortionCorrectorComponent",
            name=f"{ns}_distortion_corrector_node",
            remappings=[
                ("~/input/twist", TWIST_TOPIC),
                ("~/input/imu", IMU_TOPIC),
                ("~/input/pointcloud", f"{ns}/self_cropped/pointcloud_ex"),
                ("~/output/pointcloud", f"{ns}/rectified/pointcloud_ex"),
            ],
            parameters=[_param("distortion_corrector_node_param_path", context)],
            extra_arguments=extra,
        ),
        ComposableNode(
            package="autoware_pointcloud_preprocessor",
            plugin="autoware::pointcloud_preprocessor::RingOutlierFilterComponent",
            name=f"{ns}_ring_outlier_filter",
            remappings=[
                ("input", f"{ns}/rectified/pointcloud_ex"),
                ("output", f"{ns}/{PREPROCESSED_TOPIC}"),
            ],
            parameters=[_param("ring_outlier_filter_node_param_path", context)],
            extra_arguments=extra,
        ),
    ]


def make_cuda_preprocessor_nodes(context, ns, raw_topic, vehicle_info, _intra_process):
    """The same three operations as one GPU node.

    `extra_arguments` is deliberately absent rather than set to false. The node
    cannot run with intra-process comms at all, because cuda_blackboard's
    negotiation topics are transient_local and rclcpp rejects that pairing:

        Component constructor threw an exception:
        intraprocess communication allowed only with volatile durability

    aip_launcher handles it the same way, by commenting the option out.
    """
    preprocessor_params = {
        # The CUDA node takes both crop boxes at once, as two-element lists.
        # We have no mirrors, so the second box repeats the first: giving it a
        # degenerate or zero box would crop nothing, and dropping it changes the
        # expected parameter arity.
        "crop_box.min_x": [vehicle_info["min_longitudinal_offset"]] * 2,
        "crop_box.max_x": [vehicle_info["max_longitudinal_offset"]] * 2,
        "crop_box.min_y": [vehicle_info["min_lateral_offset"]] * 2,
        "crop_box.max_y": [vehicle_info["max_lateral_offset"]] * 2,
        "crop_box.min_z": [vehicle_info["min_height_offset"]] * 2,
        "crop_box.max_z": [vehicle_info["max_height_offset"]] * 2,
        "crop_box.negative": [True, True],
    }
    return [
        ComposableNode(
            package="autoware_cuda_pointcloud_preprocessor",
            plugin="autoware::cuda_pointcloud_preprocessor::CudaPointcloudPreprocessorNode",
            name=f"{ns}_cuda_pointcloud_preprocessor_node",
            parameters=[
                preprocessor_params,
                _param("distortion_corrector_node_param_path", context),
                _param("ring_outlier_filter_node_param_path", context),
                {"enable_ring_outlier_filter": True},
            ],
            remappings=[
                ("~/input/pointcloud", f"{ns}/{raw_topic}"),
                ("~/input/twist", TWIST_TOPIC),
                ("~/input/imu", IMU_TOPIC),
                ("~/output/pointcloud", f"{ns}/{PREPROCESSED_TOPIC}"),
                ("~/output/pointcloud/cuda", f"{ns}/{PREPROCESSED_TOPIC}/cuda"),
            ],
        )
    ]


def make_concat_node(context, backend, intra_process):
    package, plugin = {
        "cpu": (
            "autoware_pointcloud_preprocessor",
            "autoware::pointcloud_preprocessor::PointCloudConcatenateDataSynchronizerComponent",
        ),
        "cuda": (
            "autoware_cuda_pointcloud_preprocessor",
            "autoware::cuda_pointcloud_preprocessor::CudaPointCloudConcatenateDataSynchronizerComponent",
        ),
    }[backend]
    return ComposableNode(
        package=package,
        plugin=plugin,
        name="concatenate_data",
        remappings=[
            ("~/input/twist", TWIST_TOPIC),
            ("output", "concatenated/pointcloud"),
            ("output_info", "concatenated/pointcloud_info"),
        ],
        parameters=[_param("concatenate_and_time_sync_node_param_path", context)],
        # Same reason as the CUDA preprocessor above: absent, not false.
        extra_arguments=(
            [{"use_intra_process_comms": intra_process}] if backend == "cpu" else []
        ),
    )


def launch_setup(context, *args, **kwargs):
    backend = LaunchConfiguration("pointcloud_backend").perform(context)
    if backend not in BACKENDS:
        raise RuntimeError(
            f"pointcloud_backend must be one of {list(BACKENDS)}, got {backend!r}. "
            "Set it with `just launch pointcloud_backend:=cuda`."
        )

    vehicle_info = get_vehicle_info(context)
    intra_process = LaunchConfiguration("use_intra_process")
    make_preprocessor = (
        make_cpu_preprocessor_nodes if backend == "cpu" else make_cuda_preprocessor_nodes
    )

    nodes = []
    for ns, raw_topic in PREPROCESSED_LIDARS:
        nodes += make_preprocessor(context, ns, raw_topic, vehicle_info, intra_process)
    nodes.append(make_concat_node(context, backend, intra_process))

    return [
        LoadComposableNodes(
            composable_node_descriptions=nodes,
            target_container=LaunchConfiguration("pointcloud_container_name"),
            condition=IfCondition(LaunchConfiguration("use_concat_filter")),
        )
    ]


def generate_launch_description():
    launch_arguments = []

    def add_launch_arg(name: str, default_value=None):
        launch_arguments.append(DeclareLaunchArgument(name, default_value=default_value))

    kit = get_package_share_directory("golfcart_sensor_kit_launch")
    stock = get_package_share_directory("autoware_pointcloud_preprocessor")

    add_launch_arg("base_frame", "base_link")
    add_launch_arg("use_multithread", "False")
    add_launch_arg("use_intra_process", "False")
    add_launch_arg("pointcloud_container_name", "pointcloud_container")
    add_launch_arg("use_concat_filter", "True")
    add_launch_arg("pointcloud_backend", "cpu")
    add_launch_arg(
        "concatenate_and_time_sync_node_param_path",
        os.path.join(kit, "config", "concatenate_and_time_sync_node.param.yaml"),
    )
    # Stock Autoware defaults. Both modes read the same two files, so a tuning
    # change cannot apply to only one backend.
    add_launch_arg(
        "distortion_corrector_node_param_path",
        os.path.join(stock, "config", "distortion_corrector_node.param.yaml"),
    )
    add_launch_arg(
        "ring_outlier_filter_node_param_path",
        os.path.join(stock, "config", "ring_outlier_filter_node.param.yaml"),
    )

    set_container_executable = SetLaunchConfiguration(
        "container_executable",
        "component_container",
        condition=UnlessCondition(LaunchConfiguration("use_multithread")),
    )

    set_container_mt_executable = SetLaunchConfiguration(
        "container_executable",
        "component_container_mt",
        condition=IfCondition(LaunchConfiguration("use_multithread")),
    )

    return launch.LaunchDescription(
        launch_arguments
        + [set_container_executable, set_container_mt_executable]
        + [OpaqueFunction(function=launch_setup)]
    )
