# CT Bridge 真机测试指南

当前项目先按真机流程维护：Jetson Orin Nano + PX4 飞控 + 动捕 VRPN +
MAVROS + ROS 2 Humble。SITL 仿真暂不作为当前测试路径。

除特别说明外，下面命令默认在项目根目录 `/home/nvidia/ct` 执行。

## 0. 当前验证状态

2026-06-17 已完成真机低高度 OFFBOARD 起飞测试：核心链路持续运行，monitor 检查通过，offboard_control 锁定当前 EKF 位置后进入 OFFBOARD、arm，并缓升悬停成功。

当前测试环境：Jetson nvidia@192.168.2.113，目标目录 /home/nvidia/ct，ROS 2 Humble。运行时使用系统 /opt/ros/humble 的 MAVROS 和 /home/nvidia/ct/vrpn_ws 的 VRPN。

## 0. 安全前提

- 第一次 OFFBOARD 测试不要直接自由飞，优先不装桨检查，再系绳低高度测试。
- 遥控器握在手上，确认能随时切回 STABILIZED 或 Position 等安全模式。
- 先用遥控器普通模式确认飞机本体、姿态环和动力系统正常。
- OFFBOARD 前必须先跑 monitor，确认动捕、MAVROS、EKF 都正常。

## 1. 环境准备

在 Jetson 上进入项目根目录：

```bash
cd /home/nvidia/ct
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
```

如果刚修改过代码：

```bash
cd ct_ws
colcon build --packages-select ct_bridge
cd ..
```

然后加载工作空间：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
```

## 2. 配置检查

主要配置文件：

```text
ct_ws/src/ct_bridge/config/ct_bridge.yaml
```

当前关键配置：

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

mavros:
  ros__parameters:
    plugin_allowlist:
      - sys_status
      - sys_time
      - command
      - imu
      - local_position
      - setpoint_position
      - vision_pose

offboard_control:
  ros__parameters:
    hover_height: 0.23
    takeoff_duration: 2.0
    update_rate: 30.0
    yaw_rad: 0.0
    shutdown_land_hold_sec: 6.0
```

`position_scale` 根据动捕单位设置：

| 动捕单位 | position_scale |
|----------|----------------|
| m | `1.0` |
| cm | `0.01` |
| mm | `0.001` |

## 3. 硬件连接检查

```bash
# PX4 串口
ls /dev/ttyTHS1

# VRPN 服务器
ping 192.168.2.104
```

如果串口不同，修改 `mavros_node.ros__parameters.fcu_url`。

## 4. PX4 外部视觉前提

确认 PX4 当前固件参数已经允许 EKF 融合外部视觉位置/偏航，并且 MAVLink
实例允许和 Jetson 上的 MAVROS 通信。

参数名和位掩码会随 PX4 版本变化，不在这里硬编码。实际检查以当前固件的
EKF2 external vision 文档、QGroundControl 参数页和飞控日志为准。

如果 `/mavros/vision_pose/pose` 有数据但 `/mavros/local_position/pose` 不跟随，
优先排查 PX4 EKF2 外部视觉融合配置。

## 5. 启动核心链路

推荐先启动核心链路，并在整个测试过程中保持它运行：

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

不会启动 `offboard_control`，不会发送飞控控制指令。

不要同时再启动另一个包含 VRPN/MAVROS 的 launch，否则会出现重复节点、
重复串口连接或重复话题发布。

## 6. 飞前 monitor

保持核心链路运行，另开一个终端启动只读 monitor：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge monitor.launch.py
```

也可以直接运行节点，效果相同：

```bash
ros2 run ct_bridge monitor
```

monitor 中应检查：

| 数据流 | 话题 | 预期 |
|--------|------|------|
| Mocap raw | `/ct/pose` | 手动移动飞机时位置和 yaw 连续变化 |
| Vision | `/mavros/vision_pose/pose` | 坐标已从动捕系转换到 ENU |
| EKF | `/mavros/local_position/pose` | 与 Vision 接近，但可能有滤波延迟 |
| FCU | `/mavros/state` | `connected=True`，模式和 armed 状态正常显示 |

如果 `Mocap raw` 没数据，先查 VRPN server、刚体名和网络。
如果 `Vision` 没数据，查 `mocap_to_mavros` 是否启动和 `/ct/pose` 类型。
如果 `EKF` 不跟随 vision，查 PX4 EKF2 外部视觉融合参数。
如果 `FCU connected=False`，查串口、波特率、MAVROS 和 PX4 MAVLink 配置。

## 7. 坐标方向检查

完整坐标定义见 `COORDINATE_FRAMES.md`。

不装桨、不解锁，手持飞机缓慢移动。

期望在 PX4 / MAVLink Inspector 的 `VISION_POSITION_ESTIMATE` NED 坐标中看到：

| 实际动作 | 期望 NED 变化 |
|----------|---------------|
| 向前移动 | X 增加 |
| 向右移动 | Y 增加 |
| 向上抬高 | Z 减小 |

当前代码的坐标链路：

```text
mocap: x=前, y=左, z=上
ENU:   x=右, y=前, z=上
NED:   x=前, y=右, z=下
```

若方向不对，先不要飞，检查 `mocap_to_mavros.py` 中的位置转换。

## 8. 偏航检查

飞机放在地面，机头朝动捕定义的前方。

检查 QGroundControl 或 MAVLink Inspector 中的机头方向是否与实际一致。
如果有固定偏差，调整：

```yaml
mocap_to_mavros:
  ros__parameters:
    yaw_correction_deg: 0.0
```

经验规则：

- 如果 PX4 显示比实际多 `+10 deg`，尝试设 `yaw_correction_deg: -10.0`。
- 如果 PX4 显示比实际少 `10 deg`，尝试设 `yaw_correction_deg: 10.0`。

## 9. OFFBOARD 悬停

确认 monitor 全部正常后，停止 monitor 终端，但保持核心链路终端继续运行。
然后另开终端只启动 `offboard_control`：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
ros2 launch ct_bridge offboard.launch.py
```

更保守的第一次低高度测试：

```bash
ros2 launch ct_bridge offboard.launch.py hover_height:=0.15 takeoff_duration:=4.0
```

当前已验证过的低高度测试可使用：

```bash
ros2 launch ct_bridge offboard.launch.py hover_height:=0.23 takeoff_duration:=4.0
```

不要再启动带 VRPN/MAVROS 的 launch。OFFBOARD 控制任务单独运行，避免进入
OFFBOARD 前重启 MAVROS 和 EKF 外部视觉输入。

预期日志：

```text
Offboard ready: hover_height=0.23 m, takeoff_duration=3.0 s, update_rate=30 Hz
Locked setpoint: x=..., y=..., z=..., yaw=... deg
Requesting OFFBOARD mode
Requesting arm
Armed. Taking off
```

`offboard_control` 会：

1. 锁定前不发布 setpoint，避免把 vision 原点当成目标点。
2. 连续收到约 1 秒 EKF pose 后锁定当前 XY、Z 和 yaw。
3. 先持续发布约 1 秒当前位置目标。
4. 请求 `OFFBOARD`。
5. 请求 arm。
6. 解锁后保持 XY 和 yaw，把高度从当前高度缓升到 `hover_height`。

注意：`hover_height` 是 ENU 绝对高度目标，不是“在当前高度基础上再上升这么多”。

## 10. 降落

优先用遥控器或 QGroundControl 切到 LAND/Position 等安全模式接管。

在启动 OFFBOARD 的终端按 `Ctrl+C` 时，节点会请求 `AUTO.LAND`，并继续发布当前 setpoint 一段时间，避免立刻断流触发 OFFBOARD loss。

预期日志：

```text
Interrupted; requesting land and holding setpoints
AUTO.LAND requested; holding setpoint stream
```

如果 QGC 仍报 OFFBOARD loss 或没有进入自动降落，立即用遥控器切回安全模式并手动接管。

## 11. 常用参数

```bash
# 修改悬停高度
ros2 launch ct_bridge offboard.launch.py hover_height:=0.3

# 延长起飞缓升，减小 Z 阶跃导致的振荡
ros2 launch ct_bridge offboard.launch.py takeoff_duration:=4.0

# 修改动捕缩放、偏航校正、飞控串口：
# 编辑 ct_ws/src/ct_bridge/config/ct_bridge.yaml，然后重新构建/安装并重启核心链路。
ros2 launch ct_bridge comm.launch.py
```

## 12. 当前不维护的内容

`ct_sitl_test.sh` 和旧的 SITL 说明不作为当前真机测试路径。后续如果重新需要
SITL，应单独恢复和验证，不要把 SITL 参数混入真机配置。
