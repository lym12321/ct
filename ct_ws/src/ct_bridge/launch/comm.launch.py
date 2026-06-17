#!/usr/bin/env python3
"""Launch the persistent communication and vision pipeline."""

from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("ct_bridge")
    config_file = PathJoinSubstitution([pkg_share, "config", "ct_bridge.yaml"])

    vrpn_node = Node(
        package="vrpn_client_ros",
        executable="vrpn_client_node",
        name="vrpn_client_node",
        output="screen",
        parameters=[config_file],
    )

    mocap_to_mavros_node = Node(
        package="ct_bridge",
        executable="mocap_to_mavros",
        name="mocap_to_mavros",
        output="screen",
        parameters=[config_file],
    )

    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        parameters=[config_file],
    )

    return LaunchDescription([
        vrpn_node,
        mocap_to_mavros_node,
        mavros_node,
    ])
