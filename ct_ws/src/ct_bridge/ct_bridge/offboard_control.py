#!/usr/bin/env python3
"""PX4 OFFBOARD takeoff and hover using MAVROS local position setpoints."""

import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from ct_bridge.geometry_utils import lerp, quat_to_yaw, yaw_to_quat


class OffboardControl(Node):
    def __init__(self):
        super().__init__("offboard_control")

        self.declare_parameter("hover_height", 0.23)
        self.declare_parameter("takeoff_duration", 2.0)
        self.declare_parameter("update_rate", 30.0)
        self.declare_parameter("yaw_rad", 0.0)
        self.declare_parameter("shutdown_land_hold_sec", 6.0)

        self._hover_height = float(self.get_parameter("hover_height").value)
        self._takeoff_duration = max(
            0.1, float(self.get_parameter("takeoff_duration").value)
        )
        self._update_rate = float(self.get_parameter("update_rate").value)
        self._yaw_rad = float(self.get_parameter("yaw_rad").value)
        self._shutdown_land_hold_sec = max(1.0, float(self.get_parameter("shutdown_land_hold_sec").value))

        self._state = State()
        self._target = PoseStamped()
        self._target.header.frame_id = "map"
        self._target.pose.orientation.w = 1.0

        self._locked = False
        self._lock_count = 0
        self._required_lock_count = max(1, int(self._update_rate))
        self._setpoint_stream_count = 0
        self._required_stream_count = max(1, int(self._update_rate))
        self._lock_z = 0.0
        self._locked_yaw = 0.0

        self._takeoff_start = None
        self._last_mode_request = None
        self._last_arm_request = None
        self._landing_requested = False
        self._last_land_request = None

        self._set_mode_client = self.create_client(SetMode, "/mavros/set_mode")
        self._arming_client = self.create_client(CommandBool, "/mavros/cmd/arming")

        self.create_subscription(
            PoseStamped,
            "/mavros/local_position/pose",
            self._on_pose,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            State,
            "/mavros/state",
            self._on_state,
            qos_profile_sensor_data,
        )
        self._setpoint_pub = self.create_publisher(
            PoseStamped,
            "/mavros/setpoint_position/local",
            10,
        )
        self.create_timer(1.0 / self._update_rate, self._tick)

        self.get_logger().info(
            "Offboard ready: "
            f"hover_height={self._hover_height:.2f} m, "
            f"takeoff_duration={self._takeoff_duration:.1f} s, "
            f"update_rate={self._update_rate:.0f} Hz"
        )

    def _on_pose(self, msg: PoseStamped):
        if self._locked:
            return

        self._lock_count += 1
        if self._lock_count < self._required_lock_count:
            return

        self._target.pose.position.x = msg.pose.position.x
        self._target.pose.position.y = msg.pose.position.y
        self._target.pose.position.z = msg.pose.position.z
        self._lock_z = msg.pose.position.z
        self._locked_yaw = (
            quat_to_yaw(msg.pose.orientation)
            if abs(self._yaw_rad) < 1e-9
            else self._yaw_rad
        )
        self._target.pose.orientation = yaw_to_quat(self._locked_yaw)
        self._locked = True

        self.get_logger().info(
            f"Locked setpoint: x={self._target.pose.position.x:.3f}, "
            f"y={self._target.pose.position.y:.3f}, "
            f"z={self._lock_z:.3f}, "
            f"yaw={math.degrees(self._locked_yaw):.1f} deg"
        )

    def _on_state(self, msg: State):
        self._state = msg

    def _tick(self):
        now = self.get_clock().now()

        if not self._locked:
            return

        if self._landing_requested:
            self._request_land(now)
        elif self._state.connected and self._setpoint_stream_count >= self._required_stream_count:
            self._ensure_offboard(now)
            self._ensure_armed(now)
            self._update_takeoff(now)

        self._target.header.stamp = now.to_msg()
        self._setpoint_pub.publish(self._target)
        self._setpoint_stream_count += 1

    def _ensure_offboard(self, now):
        if self._state.mode == "OFFBOARD":
            return
        if not self._set_mode_client.service_is_ready():
            return
        if not self._request_due(now, self._last_mode_request):
            return

        req = SetMode.Request()
        req.custom_mode = "OFFBOARD"
        self._set_mode_client.call_async(req)
        self._last_mode_request = now
        self.get_logger().info("Requesting OFFBOARD mode")

    def _ensure_armed(self, now):
        if self._state.mode != "OFFBOARD" or self._state.armed:
            return
        if not self._arming_client.service_is_ready():
            return
        if not self._request_due(now, self._last_arm_request):
            return

        req = CommandBool.Request()
        req.value = True
        self._arming_client.call_async(req)
        self._last_arm_request = now
        self.get_logger().info("Requesting arm")

    def _update_takeoff(self, now):
        if not self._state.armed:
            self._takeoff_start = None
            return

        if self._takeoff_start is None:
            self._takeoff_start = now
            self.get_logger().info("Armed. Taking off")

        elapsed = (now - self._takeoff_start).nanoseconds * 1e-9
        t = min(elapsed / self._takeoff_duration, 1.0)
        self._target.pose.position.z = lerp(self._lock_z, self._hover_height, t)

    @staticmethod
    def _request_due(now, last_request) -> bool:
        if last_request is None:
            return True
        return (now - last_request).nanoseconds * 1e-9 >= 1.0

    def land(self):
        self._landing_requested = True
        self._request_land(self.get_clock().now(), force=True)

    def _request_land(self, now, force: bool = False):
        if self._state.mode == "AUTO.LAND":
            return
        if not self._set_mode_client.service_is_ready():
            self.get_logger().error("set_mode service not ready; cannot request land")
            return
        if not force and not self._request_due(now, self._last_land_request):
            return

        req = SetMode.Request()
        req.custom_mode = "AUTO.LAND"
        self._set_mode_client.call_async(req)
        self._last_land_request = now
        self.get_logger().info("AUTO.LAND requested; holding setpoint stream")


def main():
    rclpy.init()
    node = OffboardControl()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Interrupted; requesting land and holding setpoints")
        node.land()
        deadline = time.monotonic() + node._shutdown_land_hold_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
