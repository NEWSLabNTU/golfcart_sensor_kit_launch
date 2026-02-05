from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.actions import SetEnvironmentVariable

# from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    # para_dir = os.path.join(get_package_share_directory('localizer'), 'config', 'localizer.yaml')
    return LaunchDescription(
        [
            # set log color
            SetEnvironmentVariable(name='RCUTILS_COLORIZED_OUTPUT', value='1'),

            DeclareLaunchArgument(
                'lidar_name',
                default_value='falcon',
                description='lidar name'
            ),

            DeclareLaunchArgument(
                'frame_id',
                default_value='innovusion',
                description='ros frame id'
            ),

            DeclareLaunchArgument(
                'replay_rosbag',
                default_value='False',
                description='replay rosbag flag'
            ),

            DeclareLaunchArgument(
                'packets_mode',
                default_value='False',
                description='packets topic enable/disable'
            ),

            DeclareLaunchArgument(
                'aggregate_num',
                default_value='10',
                description='aggregate packets num'
            ),

            DeclareLaunchArgument(
                'device_ip',
                default_value='172.168.1.10',
                description='lidar ip'
            ),

            DeclareLaunchArgument(
                'port',
                default_value='8010',
                description='recv data from tcp port(like 8010)'
            ),

            DeclareLaunchArgument(
                'reflectance_mode',
                default_value='True',
                description='set lidar point cloud reflect mode, True or False'
            ),

            DeclareLaunchArgument(
                'multiple_return',
                default_value='1',
                description='set lidar point cloud multiple return mode, 1/2/3'
            ),

            DeclareLaunchArgument(
                'pcap_file',
                default_value='',
                description='Path to pcap file'
            ),

            DeclareLaunchArgument(
                'udp_port',
                default_value='8010',
                description='recv data from udp port(like 8010), or use tcp as default(-1)'
            ),

            DeclareLaunchArgument(
                'packet_rate',
                default_value='10000',
                description='play packet rate, default is 20, 0 means play as fast as possible, e.g, 15000 means play at 1.5x speed'
            ),

            DeclareLaunchArgument(
                'file_rewind',
                default_value='0',
                description='file rewind, 0 means no rewind, < 0 means rewind infinity times'
            ),

            DeclareLaunchArgument(
                'name_value_pairs',
                default_value='',
                description='name value pairs, e.g., "name1=value1,name2=value2"'
            ),

            DeclareLaunchArgument(
                'output_topic',
                default_value='iv_points',
                description='output topic name'
            ),

            DeclareLaunchArgument(
                'lidar_log_limit',
                default_value='info',
                description='limit log from lidar'
            ),

            DeclareLaunchArgument(
                'max_range',
                default_value='2000.0',
                description='ros point cloud max range'
            ),

            DeclareLaunchArgument(
                'min_range',
                default_value='0.4',
                description='ros point cloud min range'
            ),

            DeclareLaunchArgument(
                'coordinate_mode',
                default_value='0',
                description='ros point cloud coordinate mode, 0/1/2/3/4'
            ),

            DeclareLaunchArgument(
                'continue_live',
                default_value='1',
                description=''
            ),

            Node(
                package="innovusion",
                executable="publisher",
                parameters=[
                    {'packets_mode': LaunchConfiguration('packets_mode')},
                    {'aggregate_num': LaunchConfiguration('aggregate_num')},
                    {'replay_rosbag': LaunchConfiguration('replay_rosbag')},
                    {"lidar_name": LaunchConfiguration('lidar_name')},
                    {"frame_id": LaunchConfiguration('frame_id')},
                    {'device_ip': LaunchConfiguration('device_ip')},
                    {'port': LaunchConfiguration('port')},
                    {"reflectance_mode": LaunchConfiguration('reflectance_mode')},
                    {"multiple_return": LaunchConfiguration('multiple_return')},
                    {'pcap_file': LaunchConfiguration('pcap_file')},
                    {'packet_rate': LaunchConfiguration('packet_rate')},
                    {'file_rewind': LaunchConfiguration('file_rewind')},
                    {'udp_port': LaunchConfiguration('udp_port')},
                    {"output_topic": LaunchConfiguration('output_topic')},
                    {"lidar_log_limit": LaunchConfiguration('lidar_log_limit')},
                    {"max_range": LaunchConfiguration('max_range')},
                    {"min_range": LaunchConfiguration('min_range')},
                    {'name_value_pairs': LaunchConfiguration('name_value_pairs')},
                    {"coordinate_mode": LaunchConfiguration('coordinate_mode')},
                    {"continue_live": LaunchConfiguration('continue_live')},
                ],
            ),
        ]
    )
