# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 提供项目开发指引。

当前目标是 Jetson Orin Nano 上位机控制 PX4 真机，在动捕室内通过
MAVROS 进入 OFFBOARD 模式并做定点悬停。当前先不维护 SITL 仿真流程。

## 构建

在 Jetson 上执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/nvidia/ct/ct_ws
colcon build --packages-select ct_bridge
source install/setup.bash
```

## 运行

推荐真机测试时保持核心链路持续运行，再单独启动 monitor 或 offboard 控制。

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash

# 只启动核心链路：VRPN + mocap_to_mavros + MAVROS
ros2 launch ct_bridge comm.launch.py
```

另开终端做飞前检查：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge monitor.launch.py
```

确认正常后，停止 monitor，保持核心链路运行，再另开终端启动 OFFBOARD：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge offboard.launch.py hover_height:=0.23 takeoff_duration:=4.0
```

`ct_bridge.launch.py` 保留为通讯链路的兼容别名。monitor、测试任务和
OFFBOARD 控制任务都应单独运行，避免进入 OFFBOARD 前重启 MAVROS 和外部视觉输入。

## 架构

数据和控制链路：

```text
VRPN /ct/pose
  -> mocap_to_mavros
  -> /mavros/vision_pose/pose
  -> MAVROS
  -> PX4 EKF2
  -> /mavros/local_position/pose
  -> offboard_control
  -> /mavros/setpoint_position/local
  -> MAVROS
  -> PX4 position controller
```

核心节点：

- `mocap_to_mavros`：将动捕位姿转换成 MAVROS 期望的 ENU 位姿，发布到
  `/mavros/vision_pose/pose`。
- `monitor`：只读飞前检查节点，显示 `/ct/pose`、vision pose、EKF pose 和
  `/mavros/state`。
- `offboard_control`：锁定当前 EKF 的 XY 和 yaw，发送 ENU 位置设定点，请求
  `OFFBOARD`，请求解锁，解锁后把 Z 从当前高度线性缓升到 `hover_height`。
- `geometry_utils.py`：共享 yaw/quaternion 和插值工具。

外部包：

- `vrpn_client_ros`：动捕服务器到 ROS 2 话题。
- `mavros`：ROS 2 和 PX4 MAVLink 桥接。

## 配置

所有运行参数集中在 `ct_ws/src/ct_bridge/config/ct_bridge.yaml`。这是标准
ROS 2 参数文件，顶层 key 必须和节点名一致：

```yaml
vrpn_client_node:
  ros__parameters:
    server: "192.168.2.104"
    port: 3883

mocap_to_mavros:
  ros__parameters:
    position_scale: 0.01
    yaw_correction_deg: 0.0

mavros_node:
  ros__parameters:
    fcu_url: "serial:///dev/ttyTHS1:921600"
    gcs_url: "udp://@192.168.2.106:14550"

offboard_control:
  ros__parameters:
    hover_height: 0.23
    takeoff_duration: 2.0
    update_rate: 30.0
    yaw_rad: 0.0
    shutdown_land_hold_sec: 6.0
```

`comm.launch.py` 只加载这个 YAML，不启动 monitor 或 offboard。通讯链路参数
修改后需要重新构建/安装配置并重启 `comm.launch.py`。

## 坐标系

完整坐标定义和检查方法见 `COORDINATE_FRAMES.md`。

| 环节 | 坐标系 | x | y | z |
|------|-------|---|---|---|
| 动捕原始 | 前/左/上 | 前 | 左 | 上 |
| mocap_to_mavros 输出 | ENU | 右 | 前 | 上 |
| MAVROS 发给 PX4 | NED | 前 | 右 | 下 |
| MAVROS local_position 输出 | ENU | 右 | 前 | 上 |
| offboard_control 设定点 | ENU | 右 | 前 | 上 |

位置转换：

```text
enu_x = -mocap_y
enu_y =  mocap_x
enu_z =  mocap_z
```

偏航转换：

```text
yaw_enu = yaw_mocap + 90 deg - yaw_correction
```

`offboard_control` 默认不强行给固定 yaw，而是在锁定位置时使用当前 EKF
orientation。只有 `yaw_rad` 非 0 时才显式覆盖。

## offboard_control 行为

当前实现是一个简单的 timer-driven 状态机：

- 锁定当前位置前不发布 setpoint，避免把 vision 原点 `(0,0,0)` 发成有效目标。
- 收到约 1 秒连续 `/mavros/local_position/pose` 后锁定当前 XY、Z 和 yaw。
- 锁定后先连续发布约 1 秒当前位置目标，再开始请求 `OFFBOARD`。
- FCU connected 且已锁点后，每 1 秒尝试请求一次 `OFFBOARD`。
- 进入 `OFFBOARD` 后，每 1 秒尝试请求一次 arm。
- 解锁后执行 Z 轴缓升：`lock_z -> hover_height`，持续 `takeoff_duration` 秒。
- `Ctrl+C` 时进入 landing_requested 状态：停止请求 OFFBOARD/arm，继续发布当前 setpoint，按 1 Hz 重试 `AUTO.LAND`，默认保持 `shutdown_land_hold_sec=6.0` 秒后退出。

预期日志大致为：

```text
Offboard ready: hover_height=0.23 m, takeoff_duration=2.0 s, update_rate=30 Hz
Locked setpoint: x=..., y=..., z=..., yaw=... deg
Requesting OFFBOARD mode
Requesting arm
Armed. Taking off
```

## 已验证状态

2026-06-17 真机低高度 OFFBOARD 起飞测试成功。测试使用 ROS 2 Humble、`comm.launch.py` 持续运行通讯链路、`monitor.launch.py` 做飞前检查、`offboard.launch.py` 单独启动控制任务。

## 安全原则

- 第一次真机 OFFBOARD 测试必须不装桨或系绳分阶段验证。
- 先运行 monitor，确认动捕、vision pose、EKF pose 和 FCU 状态均正常。
- 遥控器必须能随时切回手动安全模式，例如 STABILIZED 或 Position。
- 低高度测试优先增加 `takeoff_duration`，不要让 Z 设定点阶跃。
