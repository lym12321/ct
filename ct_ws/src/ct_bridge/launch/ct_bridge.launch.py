#!/usr/bin/env python3
"""Compatibility alias for the communication and vision pipeline."""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("ct_bridge")
    comm_launch = PathJoinSubstitution([pkg_share, "launch", "comm.launch.py"])

    return LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(comm_launch)),
    ])
