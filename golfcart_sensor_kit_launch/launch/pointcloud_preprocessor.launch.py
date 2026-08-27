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


import os

from ament_index_python.packages import get_package_share_directory
import launch
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.actions import SetLaunchConfiguration
from launch.conditions import IfCondition
from launch.conditions import UnlessCondition
from launch.substitutions import EnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LoadComposableNodes
from launch_ros.descriptions import ComposableNode
from launch_ros.parameter_descriptions import ParameterFile


# Concatenator implementations, keyed by `pointcloud_backend`.
#
# Both take the same parameter file, the same node name and the same remappings,
# so switching is a package/plugin swap and nothing downstream sees a difference
# in topic names. The CUDA one is a registered composable
# (`ament_index/resource_index/rclcpp_components/autoware_cuda_pointcloud_preprocessor`),
# so it loads into the same container as the CPU one rather than needing a
# process of its own.
#
# Measure before believing this helps. On the 2026-08-25 bundles, concatenation
# cost 12.5 ms median when both LiDARs made the window, against a 510 ms median
# pipeline latency, so the compute this moves to the GPU is ~2% of the delay.
# See docs/research/sensing/lidar-pipeline-starvation.md.
CONCAT_IMPL = {
    "cpu": (
        "autoware_pointcloud_preprocessor",
        "autoware::pointcloud_preprocessor::PointCloudConcatenateDataSynchronizerComponent",
    ),
    "cuda": (
        "autoware_cuda_pointcloud_preprocessor",
        "autoware::cuda_pointcloud_preprocessor::CudaPointCloudConcatenateDataSynchronizerComponent",
    ),
}


def launch_setup(context, *args, **kwargs):
    concatenate_and_time_sync_node_param = ParameterFile(
        param_file=LaunchConfiguration("concatenate_and_time_sync_node_param_path").perform(
            context
        ),
        allow_substs=True,
    )

    backend = LaunchConfiguration("pointcloud_backend").perform(context)
    if backend not in CONCAT_IMPL:
        raise RuntimeError(
            f"pointcloud_backend must be one of {sorted(CONCAT_IMPL)}, got {backend!r}. "
            "It is set from the POINTCLOUD_BACKEND environment variable "
            "(config/sensors.conf), not from a launch argument."
        )
    concat_package, concat_plugin = CONCAT_IMPL[backend]

    # set concat filter as a component
    concat_component = ComposableNode(
        package=concat_package,
        plugin=concat_plugin,
        name="concatenate_data",
        remappings=[
            ("~/input/twist", "/sensing/vehicle_velocity_converter/twist_with_covariance"),
            ("output", "concatenated/pointcloud"),
            ("output_info", "concatenated/pointcloud_info"),
        ],
        parameters=[concatenate_and_time_sync_node_param],
        extra_arguments=[{"use_intra_process_comms": LaunchConfiguration("use_intra_process")}],
    )

    # load concat or passthrough filter
    concat_loader = LoadComposableNodes(
        composable_node_descriptions=[concat_component],
        target_container=LaunchConfiguration("pointcloud_container_name"),
        condition=IfCondition(LaunchConfiguration("use_concat_filter")),
    )

    return [concat_loader]


def generate_launch_description():
    launch_arguments = []

    def add_launch_arg(name: str, default_value=None):
        launch_arguments.append(DeclareLaunchArgument(name, default_value=default_value))

    add_launch_arg("base_frame", "base_link")
    add_launch_arg("use_multithread", "False")
    add_launch_arg("use_intra_process", "False")
    add_launch_arg("pointcloud_container_name", "pointcloud_container")
    add_launch_arg("use_concat_filter", "True")
    # cpu | cuda. Defaulted from the environment rather than left to the caller
    # because nothing between golfcart.launch.yaml and here forwards an unknown
    # launch argument: see the comment in sensing.launch.xml.
    add_launch_arg("pointcloud_backend", EnvironmentVariable("POINTCLOUD_BACKEND", default_value="cpu"))
    add_launch_arg(
        "concatenate_and_time_sync_node_param_path",
        os.path.join(
            get_package_share_directory("golfcart_sensor_kit_launch"),
            "config",
            "concatenate_and_time_sync_node.param.yaml",
        ),
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
