# AGENTS.md

本项目是 PX4 真机 OFFBOARD 测试代码。修改时优先保证真机安全，不要为了抽象、清理或重构破坏已验证流程。

## 项目边界

- ROS 版本按 ROS 2 Humble 处理。
- 目标真机目录是 `/home/nvidia/ct`。
- VRPN 是运行依赖，但 `vrpn_ws/` 不提交到本仓库。
- MAVROS 默认使用系统 `/opt/ros/humble` 的版本，不默认 source `mavros2_ws/`。
- 本仓库只维护 `ct_ws/src/ct_bridge` 这个 ROS 包和必要说明文档。

## 运行环境

推荐 source 顺序：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash
```

如果修改了配置或代码，在飞机上重新构建：

```bash
cd /home/nvidia/ct/ct_ws
colcon build --packages-select ct_bridge
```

## Launch 约束

- `comm.launch.py` 只负责启动 VRPN、`mocap_to_mavros` 和 MAVROS。
- `monitor.launch.py` 必须保持只读，不发送任何控制指令。
- `offboard.launch.py` 只启动 `offboard_control`。
- 真机测试时保持 `comm.launch.py` 持续运行；monitor 检查通过后只停止 monitor，再单独启动 OFFBOARD 控制。
- 不要在进入 OFFBOARD 前重启 MAVROS 或 external vision 链路。

## OFFBOARD 安全逻辑

- `offboard_control` 在锁定当前 EKF pose 前不得发布 setpoint。
- 锁定当前 EKF `x/y/z/yaw` 后，先发布当前 pose 约 1 秒，再请求 `OFFBOARD` 和 arm。
- 起飞目标应保持锁定的 `x/y/yaw`，只把 `z` 从当前高度缓升到 `hover_height`。
- `hover_height` 是 ENU 局部坐标中的绝对 `z` 目标，不是相对上升高度。
- 不要把 vision 原点 `(0,0,0)` 当成默认目标点。
- `Ctrl+C` 不是主降落方式，只能作为辅助退出路径：请求 `AUTO.LAND`，并继续发布 setpoint 一段时间。
- 真机测试优先使用遥控器或 QGroundControl 切 LAND/Position 接管。

## 坐标系约束

当前已验证的动捕坐标：

```text
mocap: x=前, y=左, z=上
ENU:   x=右, y=前, z=上
```

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

MAVROS 内部负责 external vision 和 setpoint 的 ENU/NED 转换。不要在 `offboard_control` 里手动把 setpoint 转成 NED。

## 修改要求

- 修改飞行控制逻辑后，至少运行 Python 语法检查。
- 涉及真机行为的修改要同步更新 `README.md`。
- 不要提交 `build/`、`install/`、`log/`、`vrpn_ws/`、`mavros2_ws/` 或压缩包。
- 不要在没有明确理由和验证的情况下改变坐标变换、yaw 符号、MAVROS 节点命名或 plugin allowlist。
