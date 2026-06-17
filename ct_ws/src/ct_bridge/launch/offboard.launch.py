#!/usr/bin/env python3
"""Launch only the OFFBOARD control task."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("ct_bridge")
    config_file = PathJoinSubstitution([pkg_share, "config", "ct_bridge.yaml"])

    declare_hover_height = DeclareLaunchArgument(
        "hover_height", default_value="0.23"
    )
    declare_takeoff_duration = DeclareLaunchArgument(
        "takeoff_duration", default_value="2.0"
    )
    declare_shutdown_land_hold_sec = DeclareLaunchArgument(
        "shutdown_land_hold_sec", default_value="6.0"
    )

    offboard_node = Node(
        package="ct_bridge",
        executable="offboard_control",
        name="offboard_control",
        output="screen",
        parameters=[
            config_file,
            {
                "hover_height": LaunchConfiguration("hover_height"),
                "takeoff_duration": LaunchConfiguration("takeoff_duration"),
                "shutdown_land_hold_sec": LaunchConfiguration("shutdown_land_hold_sec"),
            },
        ],
    )

    return LaunchDescription([
        declare_hover_height,
        declare_takeoff_duration,
        declare_shutdown_land_hold_sec,
        offboard_node,
    ])
