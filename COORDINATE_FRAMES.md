# Coordinate Frames

This project uses one explicit transform before data enters MAVROS. After that,
MAVROS performs the standard ROS ENU to MAVLink/PX4 NED conversions.

## Frame Definitions

| Name | Used by | X | Y | Z | Notes |
|------|---------|---|---|---|-------|
| Mocap raw | VRPN `/ct/pose` | Forward | Left | Up | Local room/body test convention used by this project |
| ROS ENU | `/mavros/vision_pose/pose`, `/mavros/local_position/pose`, `/mavros/setpoint_position/local` | Right/East | Forward/North | Up | ROS/MAVROS external interface |
| PX4 NED | PX4 EKF and position controller | Forward/North | Right/East | Down | MAVLink local frame |
| ROS base_link | ROS pose orientation body frame | Forward | Left | Up | What `PoseStamped.pose.orientation` represents before MAVROS |
| PX4 aircraft | PX4 body frame | Forward | Right | Down | MAVROS converts base_link to aircraft internally |

In this project, "Forward" means the marked forward direction in the motion
capture space, not necessarily geographic north.

## Position Transform

`mocap_to_mavros.py` converts mocap position to ROS ENU:

```text
enu_x = -mocap_y
enu_y =  mocap_x
enu_z =  mocap_z
```

Sanity checks:

| Physical motion | Mocap raw change | ROS ENU change | PX4 NED change after MAVROS |
|-----------------|------------------|----------------|-----------------------------|
| Move forward | `x` increases | `y` increases | `x` increases |
| Move right | `y` decreases | `x` increases | `y` increases |
| Move up | `z` increases | `z` increases | `z` decreases |

## Yaw Transform

The mocap yaw is interpreted as:

- `yaw_mocap = 0 deg`: nose points along mocap `+X` (forward)
- `yaw_mocap = +90 deg`: nose points along mocap `+Y` (left)
- `yaw_mocap = -90 deg`: nose points along mocap `-Y` (right)

ROS ENU yaw is interpreted as:

- `yaw_enu = 0 deg`: nose points along ENU `+X` (right/east)
- `yaw_enu = +90 deg`: nose points along ENU `+Y` (forward/north)
- `yaw_enu = +/-180 deg`: nose points along ENU `-X` (left/west)

The conversion is:

```text
yaw_enu = yaw_mocap + 90 deg - yaw_correction
```

Examples with `yaw_correction_deg = 0`:

| Nose direction | yaw_mocap | yaw_enu published to MAVROS |
|----------------|-----------|-----------------------------|
| Forward | `0 deg` | `+90 deg` |
| Left | `+90 deg` | `+180 deg` |
| Right | `-90 deg` | `0 deg` |
| Backward | `+/-180 deg` | `-90 deg` |

`yaw_correction_deg` is a final PX4 yaw trim. If QGroundControl or MAVLink
Inspector shows a constant yaw bias while the aircraft is physically aligned,
set this parameter to the opposite of the observed bias:

```text
PX4 shows +10 deg when it should show 0 deg -> yaw_correction_deg = -10
PX4 shows -10 deg when it should show 0 deg -> yaw_correction_deg = +10
```

## MAVROS Conversions

MAVROS receives ROS ENU `PoseStamped` messages and sends MAVLink/PX4 NED data.
The local MAVROS source in this workspace shows:

- `vision_pose_estimate.cpp` transforms vision position with
  `transform_frame_enu_ned()`.
- `vision_pose_estimate.cpp` transforms vision orientation with
  `transform_orientation_baselink_aircraft()` and then
  `transform_orientation_enu_ned()`.
- `setpoint_position.cpp` transforms local position setpoints with
  `transform_frame_enu_ned()`.
- `local_position.cpp` transforms PX4 `LOCAL_POSITION_NED` back to ROS ENU with
  `transform_frame_ned_enu()`.

So project nodes should publish and consume ROS ENU. They should not manually
convert OFFBOARD setpoints to NED.

## Offboard Control Frame Rule

`offboard_control.py` subscribes to `/mavros/local_position/pose`, which is
already ROS ENU. It locks the current ENU `x`, `y`, `z`, and yaw, then publishes
an ENU setpoint to `/mavros/setpoint_position/local`.

This is intentional:

```text
MAVROS local_position output: ENU
offboard_control target:      ENU
MAVROS setpoint input:        ENU
PX4 internal control:         NED, converted inside MAVROS
```

## Current Orientation Limitation

`mocap_to_mavros.py` publishes yaw-only orientation: roll and pitch are set to
zero. This keeps external vision yaw simple and avoids feeding noisy mocap
roll/pitch into PX4.

If the PX4 EKF is later configured to fuse full external-vision attitude, this
should be revisited. For the current hover workflow, yaw-only external vision is
the intended behavior.

## Pre-Flight Checklist

Before enabling OFFBOARD:

1. Move the aircraft forward: `VISION_POSITION_ESTIMATE.x` should increase.
2. Move the aircraft right: `VISION_POSITION_ESTIMATE.y` should increase.
3. Move the aircraft up: `VISION_POSITION_ESTIMATE.z` should decrease.
4. Rotate the aircraft left/right and confirm the displayed yaw follows the
   physical heading with only a small constant trim error.
5. Confirm `/mavros/local_position/pose` follows `/mavros/vision_pose/pose`
   after EKF fusion delay.
