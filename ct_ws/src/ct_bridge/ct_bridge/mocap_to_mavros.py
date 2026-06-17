#!/usr/bin/env python3
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped

from ct_bridge.geometry_utils import normalize_angle, quat_to_yaw, yaw_to_quat


class MocapToMavros(Node):
    def __init__(self):
        super().__init__("mocap_to_mavros")

        self.declare_parameter("input_topic", "/ct/pose")
        self.declare_parameter("output_topic", "/mavros/vision_pose/pose")

        # 0.01 = cm to m, 0.001 = mm to m, 1.0 = m to m
        self.declare_parameter("position_scale", 0.01)

        # 这个 correction 是加到 PX4/MAVLink Inspector 里最终 yaw 上的修正量。
        # 如果机头朝前时 Inspector yaw = +10 deg，就设 -10。
        # 如果机头朝前时 Inspector yaw = -10 deg，就设 +10。
        self.declare_parameter("yaw_correction_deg", 0.0)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.scale = float(self.get_parameter("position_scale").value)
        self.yaw_correction = math.radians(
            float(self.get_parameter("yaw_correction_deg").value)
        )

        self.sub = self.create_subscription(
            PoseStamped,
            self.input_topic,
            self.cb_pose,
            qos_profile_sensor_data,
        )

        self.pub = self.create_publisher(
            PoseStamped,
            self.output_topic,
            10,
        )

        self.get_logger().info(
            f"{self.input_topic} -> {self.output_topic}, "
            f"scale={self.scale}, "
            f"yaw_correction_deg={math.degrees(self.yaw_correction):.2f}"
        )

    def cb_pose(self, msg: PoseStamped):
        out = PoseStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = "map"

        # ------------------------------------------------------------
        # Position transform
        #
        # 原始 mocap:
        #   x = 前
        #   y = 左
        #   z = 上
        #
        # MAVROS 输入 ENU:
        #   x = 右
        #   y = 前
        #   z = 上
        #
        # 所以：
        #   enu_x = -mocap_y
        #   enu_y =  mocap_x
        #   enu_z =  mocap_z
        # ------------------------------------------------------------
        out.pose.position.x = -msg.pose.position.y * self.scale
        out.pose.position.y =  msg.pose.position.x * self.scale
        out.pose.position.z =  msg.pose.position.z * self.scale

        # ------------------------------------------------------------
        # Yaw-only orientation
        #
        # 原始 mocap yaw:
        #   yaw_mocap = 0    表示机头朝 mocap +X，也就是前方
        #   yaw_mocap = +90  表示机头朝 mocap +Y，也就是左方
        #   yaw_mocap = -90  表示机头朝 mocap -Y，也就是右方
        #
        # MAVROS 输入 ENU 中：
        #   yaw_enu = +90 deg 表示机头朝 ENU +Y，也就是前方
        #
        # 因此：
        #   yaw_enu = yaw_mocap + 90deg - yaw_correction
        #
        # 注意 yaw_correction 的符号设计：
        #   它等效于加到最终 PX4 yaw 上。
        #   如果 Inspector 里机头朝前时 yaw = +10deg，
        #   就设置 yaw_correction_deg = -10。
        # ------------------------------------------------------------
        yaw_mocap = quat_to_yaw(msg.pose.orientation)

        yaw_enu = (
            yaw_mocap
            + math.radians(90.0)
            - self.yaw_correction
        )
        yaw_enu = normalize_angle(yaw_enu)

        # 只发布 yaw，roll/pitch 固定为 0
        out.pose.orientation = yaw_to_quat(yaw_enu)

        self.pub.publish(out)


def main():
    rclpy.init()
    node = MocapToMavros()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
