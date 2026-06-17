#!/usr/bin/env python3
"""
monitor.py — Pre-flight diagnostic display.

Subscribes to /ct/pose (mocap raw), /mavros/vision_pose/pose,
/mavros/local_position/pose, and /mavros/state, and prints a live-updating
diagnostic block so you can verify data flows before enabling offboard control.

No offboard commands are ever sent — this node is read-only.
"""
import sys
import rclpy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from ct_bridge.geometry_utils import quat_to_yaw


class Monitor(Node):
    def __init__(self):
        super().__init__("monitor")

        self.declare_parameter("check_rate", 2.0)
        self.declare_parameter("warning_no_data_sec", 2.0)

        self._check_rate = float(self.get_parameter("check_rate").value)
        self._warn_threshold = float(self.get_parameter("warning_no_data_sec").value)

        # Latest messages and timestamps
        self._mocap_msg: PoseStamped | None = None
        self._vision_msg: PoseStamped | None = None
        self._ekf_msg: PoseStamped | None = None
        self._fcu_connected = False
        self._fcu_armed = False
        self._fcu_mode = "?"

        self._mocap_time: rclpy.time.Time | None = None
        self._vision_time: rclpy.time.Time | None = None
        self._ekf_time: rclpy.time.Time | None = None

        # Subscribers
        self._sub_mocap = self.create_subscription(
            PoseStamped,
            "/ct/pose",
            self._cb_mocap,
            qos_profile_sensor_data,
        )
        self._sub_vision = self.create_subscription(
            PoseStamped,
            "/mavros/vision_pose/pose",
            self._cb_vision,
            qos_profile_sensor_data,
        )
        self._sub_ekf = self.create_subscription(
            PoseStamped,
            "/mavros/local_position/pose",
            self._cb_ekf,
            qos_profile_sensor_data,
        )
        self._sub_state = self.create_subscription(
            State,
            "/mavros/state",
            self._cb_state,
            qos_profile_sensor_data,
        )

        self._timer = self.create_timer(1.0 / self._check_rate, self._tick)

        self.get_logger().info(
            f"Monitor started (check_rate={self._check_rate:.1f} Hz, "
            f"warn_no_data={self._warn_threshold:.1f} s)"
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _cb_mocap(self, msg: PoseStamped):
        self._mocap_msg = msg
        self._mocap_time = self.get_clock().now()

    def _cb_vision(self, msg: PoseStamped):
        self._vision_msg = msg
        self._vision_time = self.get_clock().now()

    def _cb_ekf(self, msg: PoseStamped):
        self._ekf_msg = msg
        self._ekf_time = self.get_clock().now()

    def _cb_state(self, msg: State):
        self._fcu_connected = msg.connected
        self._fcu_armed = msg.armed
        self._fcu_mode = msg.mode

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _age(self, stamp_time) -> float:
        """Return age in seconds of a stored timestamp, or -1 if None."""
        if stamp_time is None:
            return -1.0
        now = self.get_clock().now()
        return (now - stamp_time).nanoseconds * 1e-9

    def _fmt(self, name: str, pose: PoseStamped | None, age: float) -> str:
        if pose is None:
            return f"  {name:10s}  NO DATA"
        p = pose.pose.position
        yaw_deg = 0.0
        if pose.pose.orientation.w != 0.0 or pose.pose.orientation.z != 0.0:
            yaw_deg = quat_to_yaw(pose.pose.orientation)
            yaw_deg = yaw_deg * 180.0 / 3.141592653589793

        age_str = f"{age:.2f}s" if age >= 0 else "?"
        warn = " ⚠" if age > self._warn_threshold else ""
        return (
            f"  {name:10s} "
            f"x={p.x:7.3f} y={p.y:7.3f} z={p.z:7.3f} "
            f"yaw={yaw_deg:7.1f}° "
            f"age={age_str}{warn}"
        )

    def _tick(self):
        mocap_age = self._age(self._mocap_time)
        vision_age = self._age(self._vision_time)
        ekf_age = self._age(self._ekf_time)

        lines = [
            "\033[2J\033[H",  # clear screen, home cursor
            "╔══════════════════════════════════════════════════════════════════════╗",
            "║  CT Bridge Monitor                                                  ║",
            "╠══════════════════════════════════════════════════════════════════════╣",
            "║  Source          x(m)     y(m)     z(m)    yaw(°)   age             ║",
            "╠══════════════════════════════════════════════════════════════════════╣",
            self._fmt("Mocap raw", self._mocap_msg, mocap_age),
            self._fmt("Vision", self._vision_msg, vision_age),
            self._fmt("EKF", self._ekf_msg, ekf_age),
            "╠══════════════════════════════════════════════════════════════════════╣",
            f"  FCU: connected={self._fcu_connected}, armed={self._fcu_armed}, mode={self._fcu_mode}",
            "╚══════════════════════════════════════════════════════════════════════╝",
        ]

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()


def main():
    rclpy.init()
    node = Monitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
