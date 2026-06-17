#!/usr/bin/env python3
"""Launch the read-only pre-flight monitor only."""

from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("ct_bridge")
    config_file = PathJoinSubstitution([pkg_share, "config", "ct_bridge.yaml"])

    monitor_node = Node(
        package="ct_bridge",
        executable="monitor",
        name="monitor",
        output="screen",
        parameters=[config_file],
    )

    return LaunchDescription([monitor_node])
