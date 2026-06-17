# CT Bridge

CT Bridge 是一个用于室内动捕真机测试的 ROS 2 Humble 包。它把 VRPN 动捕位姿转换成 MAVROS external vision，送给 PX4 EKF2，并提供一个低高度 OFFBOARD 定点起飞/悬停控制节点。

当前已在 Jetson + PX4 真机上完成低高度 OFFBOARD 起飞和悬停测试。验证环境：

```text
飞机电脑：nvidia@192.168.2.113
项目目录：/home/nvidia/ct
ROS 版本：ROS 2 Humble
```

## 仓库内容

```text
ct_ws/src/ct_bridge/
├── config/ct_bridge.yaml          # 统一配置
├── ct_bridge/mocap_to_mavros.py   # 动捕位姿 -> MAVROS vision pose
├── ct_bridge/monitor.py           # 只读飞前监控
├── ct_bridge/offboard_control.py  # OFFBOARD 起飞/悬停控制
├── launch/comm.launch.py          # VRPN + mocap_to_mavros + MAVROS
├── launch/monitor.launch.py       # 只启动 monitor
└── launch/offboard.launch.py      # 只启动 OFFBOARD 控制
```

`vrpn_ws/` 和 `mavros2_ws/` 是外部工作区，不提交到本仓库。

## 依赖

飞机电脑上需要：

- ROS 2 Humble
- MAVROS 和 `mavros_msgs`
- `vrpn_client_ros`
- PX4 已配置 EKF2 融合 external vision 位置/偏航
- 可访问的 VRPN 动捕服务器

VRPN 是必须的运行依赖。当前验证环境中，`vrpn_client_ros` 单独编译在：

```bash
/home/nvidia/ct/vrpn_ws
```

MAVROS 使用系统 ROS 安装里的版本：

```bash
/opt/ros/humble
```

运行时推荐 source 顺序：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
```

不要 source 有问题或过期的自编译 MAVROS 工作区。

## 构建

在飞机电脑上执行：

```bash
cd /home/nvidia/ct/ct_ws
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
colcon build --packages-select ct_bridge
source install/setup.bash
```

## 配置

主配置文件：

```text
ct_ws/src/ct_bridge/config/ct_bridge.yaml
```

关键配置示例：

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

`position_scale` 按动捕单位设置：

| 动捕单位 | `position_scale` |
| --- | --- |
| m | `1.0` |
| cm | `0.01` |
| mm | `0.001` |

## 真机测试流程

### 1. 启动通讯链路

保持这个终端一直运行：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge comm.launch.py
```

这个 launch 会启动：

- `vrpn_client_node`
- `mocap_to_mavros`
- `mavros_node`

它不会启动 OFFBOARD 控制。

### 2. 飞前 monitor 检查

另开终端：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge monitor.launch.py
```

monitor 中应确认：

- `/ct/pose` 有动捕数据。
- `/mavros/vision_pose/pose` 有转换后的 vision 数据。
- `/mavros/local_position/pose` 跟随 vision，位置和 yaw 接近。
- `/mavros/state` 显示 `connected=True`。
- 原点附近没有位置或 yaw 跳变。

检查通过后只停止 monitor，保持 `comm.launch.py` 继续运行。

### 3. 启动 OFFBOARD

另开第三个终端：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge offboard.launch.py hover_height:=0.23 takeoff_duration:=4.0
```

更保守的第一次测试可以用：

```bash
ros2 launch ct_bridge offboard.launch.py hover_height:=0.15 takeoff_duration:=4.0
```

`offboard_control` 的行为：

1. 锁定当前 EKF 位姿前不发布 setpoint，避免把 vision 原点当成目标点。
2. 连续收到约 1 秒 `/mavros/local_position/pose` 后锁定当前 `x/y/z/yaw`。
3. 先持续发布约 1 秒当前位置目标。
4. 请求 `OFFBOARD`。
5. 请求 arm。
6. 保持锁定的 `x/y/yaw`，把 `z` 从当前高度缓升到 `hover_height`。

注意：`hover_height` 是 ENU 局部坐标中的绝对 `z` 目标，不是“在当前高度基础上再上升这么多”。

## 降落和退出

真机测试时，主要安全退出方式应是遥控器或 QGroundControl 切到 LAND / Position 等安全模式。

在 OFFBOARD 终端按 `Ctrl+C` 时，节点会请求 `AUTO.LAND`，继续发布当前 setpoint，并在 `shutdown_land_hold_sec` 秒内重试 LAND 请求。这可以降低立即触发 OFFBOARD loss 的概率，但它仍然只是辅助退出路径。

预期日志：

```text
Interrupted; requesting land and holding setpoints
AUTO.LAND requested; holding setpoint stream
```

如果 QGC 仍报 OFFBOARD loss，或飞机没有进入 LAND，应立刻用遥控器/QGC 接管。

## 坐标系

当前动捕坐标定义：

```text
mocap: x=前, y=左, z=上
```

`mocap_to_mavros` 发布 ROS ENU：

```text
enu_x = -mocap_y
enu_y =  mocap_x
enu_z =  mocap_z

yaw_enu = yaw_mocap + 90 deg - yaw_correction
```

MAVROS 内部负责 external vision 和 setpoint 的 ENU/NED 转换。

从上往下看，飞机逆时针旋转时，动捕 yaw 增大；当前转换链路已按这个方向验证。

## 已验证状态

2026-06-17，低高度真机 OFFBOARD 起飞和悬停测试成功。成功流程是：

```text
comm.launch.py 持续运行 -> monitor.launch.py 检查 -> 停止 monitor -> offboard.launch.py 起飞
```

关键经验：

- VRPN 需要单独安装/编译，但不提交进本仓库。
- 不要在进入 OFFBOARD 前重启 MAVROS 或 external vision 链路。
- OFFBOARD 目标必须先锁定当前 EKF 位置，不能默认发 `(0,0,0)`。
- `Ctrl+C` 不是主降落方式，真机上仍应优先用遥控器/QGC 接管。
