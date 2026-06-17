# AGENTS.md

This file records work done in this session so future Claude Code sessions can
pick up where this one left off.  It is NOT a CLAUDE.md — that file should be
generated separately with `/init`.

---

## Date: 2026-06-17

## What was done

### 1. Unified config + launch system

The project originally required 3 separate terminals (VRPN, mocap_to_mavros,
MAVROS) plus a 4th for offboard.  The user wanted a single launch file.

**Changes:**
- **`config/ct_bridge.yaml`** — expanded to be the **single source of truth**
  for all parameters: VRPN (server, port, frame_id, refresh rates), mocap
  transform (scale, yaw correction), offboard control (height, ramp dur.,
  rate), monitor (check rate, warn thresholds), and MAVROS (FCU/GCS URLs).
  Each section uses `ros__parameters` so ROS 2 parameter-file loading works.
- **`launch/ct_bridge.launch.py`** — unified launch.  Starts VRPN + mocap_to_mavros
  + MAVROS unconditionally.  `start_offboard:=true` optionally starts the
  offboard_control node.  All parameters loaded from YAML with CLI overrides.
- **`launch/monitor.launch.py`** — safety/test mode.  Includes core pipeline
  (VRPN + mocap + MAVROS) + starts the `monitor` node.  No offboard.
- **`launch/offboard.launch.py`** — **deleted** (merged into ct_bridge.launch.py).

### 2. New monitor node for pre-flight checks

**`ct_bridge/monitor.py`** — subscribes to `/ct/pose`,
`/mavros/vision_pose/pose`, `/mavros/local_position/pose`, `/mavros/state`
and prints a live-updating diagnostic block (ANSI cursor-up).  Shows position,
yaw, message rate, age, and FCU state.  Configured via `monitor` section in YAML.

### 3. Offboard control fixes (oscillation investigation)

The user reported **strong attitude oscillations during offboard flight at
0.23 m target height**, while Position mode (RC) was fine.

**Root causes found and fixed:**

| # | Problem | Fix |
|---|---------|-----|
| 1 | **Z setpoint was a step change** (0 → hover_height at arming). PX4 position controller overshoots → limit cycle. | Added linear Z ramp after arm (`takeoff_duration` param, default 2 s) |
| 2 | **XY locked on the very first EKF pose callback**, before EKF had converged with vision data. | Wait ~1 s of consecutive readings before locking (`_required_lock_count`) |
| 3 | **Yaw setpoint was identity quaternion** (w=1). In ENU this means nose East, but the drone actually faces North. ~90° yaw error at arming → yaw controller fights → couples into pitch/roll. | Lock current EKF orientation on XY lock; only use explicit `yaw_rad` if non-zero |
| 4 | **`header.stamp` was never set** (always 0). Could confuse PX4 timeout logic. | Set `header.stamp = now.to_msg()` every publish |
| 5 | **`_land()` blocked with `spin_until_future_complete`** (2 s timeout) inside a spinning node. | Changed to fire-and-forget `call_async()` |
| 6 | **`_wait_for_services()` blocked constructor** indefinitely. | Removed; check `service_is_ready()` before each call |

### 4. Shared geometry utilities extracted

**`ct_bridge/geometry_utils.py`** — `normalize_angle`, `quat_to_yaw`, `yaw_to_quat`,
`lerp`.  Previously these were duplicated between `mocap_to_mavros.py` (module-level)
and `offboard_control.py` (static method with inline import — a code smell).
Both files now import from `geometry_utils`.

### 5. `/simplify` review applied

Four review agents (Reuse, Simplification, Efficiency, Altitude) were run;
all high/medium findings were applied (duplicated state removed, import-in-method
fixed, dead `elif pass` branch removed, clock called once per tick, etc.).

---

## Coordinate frame chain (VERIFIED correct)

```
mocap (x=前, y=左, z=上)
   ↓ mocap_to_mavros.py: enu_x=-mocap_y, enu_y=mocap_x, enu_z=mocap_z
   ↓ yaw_enu = yaw_mocap + 90° - yaw_correction
ENU (x=右, y=前, z=上)  →  published to /mavros/vision_pose/pose
   ↓ MAVROS: transform_frame_enu_ned() [= swap x,y + negate z]
   ↓ MAVROS: transform_orientation_enu_ned(baselink_aircraft(q))
NED (x=前, y=右, z=下)  →  VISION_POSITION_ESTIMATE → PX4 EKF2
   ↓ PX4 internally: LOCAL_POSITION_NED
   ↓ MAVROS local_position.cpp: transform_frame_ned_enu()
ENU → /mavros/local_position/pose (read by offboard_control)
   ↓ offboard_control publishes ENU setpoint to /mavros/setpoint_position/local
   ↓ MAVROS setpoint_position.cpp: transform_frame_enu_ned()
NED → SET_POSITION_TARGET_LOCAL_NED → PX4 position controller
```

**Key insight**: ENU yaw = 90° means nose points North.  mocap yaw=0 → need +90°
to get ENU yaw=90°.  The `/mavros/local_position/pose` orientation is in ENU
frame and can be locked directly as the setpoint orientation (same frame).

---

## Package structure (final)

```
ct_ws/src/ct_bridge/
├── config/ct_bridge.yaml          # ALL config (vrpn, mocap, offboard, monitor, mavros)
├── launch/comm.launch.py          # persistent VRPN + mocap_to_mavros + MAVROS pipeline
├── launch/ct_bridge.launch.py     # compatibility alias for comm.launch.py
├── launch/monitor.launch.py       # read-only monitor only, NO comm/offboard
├── launch/offboard.launch.py      # OFFBOARD control task only
├── ct_bridge/__init__.py
├── ct_bridge/geometry_utils.py    # normalize_angle, quat_to_yaw, yaw_to_quat, lerp
├── ct_bridge/mocap_to_mavros.py   # mocap → ENU transform + yaw correction
├── ct_bridge/offboard_control.py  # offboard takeoff + hover (with Z ramp, yaw lock)
├── ct_bridge/monitor.py           # pre-flight diagnostics display
├── setup.py                       # 3 entry points: mocap_to_mavros, offboard_control, monitor
└── package.xml
```

External packages (not modified):
- `vrpn_client_ros` (vrpn_ws) — mocap tracker → ROS2 topics
- `mavros` (mavros2_ws or /opt/ros/humble) — ROS2 ↔ MAVLink bridge

---

## Quick reference

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/ct/vrpn_ws/install/setup.bash
source /home/nvidia/ct/ct_ws/install/setup.bash

# Build
cd /home/nvidia/ct/ct_ws && colcon build --packages-select ct_bridge

# Core pipeline only (NO offboard)
ros2 launch ct_bridge comm.launch.py

# Read-only pre-flight monitor, in another terminal
ros2 launch ct_bridge monitor.launch.py

# OFFBOARD task only, after monitor checks pass
ros2 launch ct_bridge offboard.launch.py hover_height:=0.23 takeoff_duration:=4.0
```

---

## Known issues / unresolved

1. **PX4 yaw jumps from 0 to -π on slight CCW rotation** — the user mentioned this
   but after verifying the mocap→MAVROS transform chain, the issue was traced to
   PX4 EKF2's internal yaw fusion, not the ct_bridge coordinate transform.  Not
   yet investigated on the PX4 side.

2. **The Z ramp restart on disarmed/re-armed** — if the drone disarms mid-flight
   and re-arms, the ramp restarts from `target.pose.position.z` (which at that
   point is some intermediate height).  This is an edge case the current code
   does not handle but is very unlikely in normal operation.

---

## Later cleanup in this session

The user asked to simplify the code for real hardware first and ignore SITL for
now.

**Changes:**
- Rewrote `ct_bridge/offboard_control.py` into a smaller timer-driven state
  machine:
  - subscribes to real `mavros_msgs/msg/State` on `/mavros/state`
  - creates MAVROS service clients once
  - uses `service_is_ready()` instead of the previous fake `_service_ready()`
  - retries OFFBOARD and arm requests from the main timer, throttled to 1 Hz
  - keeps Z ramp and current-yaw lock behavior
  - sends `AUTO.LAND` on Ctrl+C from the `KeyboardInterrupt` handler and spins
    briefly so the async request can be sent before shutdown
- Fixed `ct_bridge/monitor.py` to subscribe to `mavros_msgs/msg/State` directly
  and removed unused state/imports.
- Rewrote `config/ct_bridge.yaml` so ROS 2 parameters are keyed by actual node
  names: `vrpn_client_node`, `mocap_to_mavros`, `mavros_node`,
  `offboard_control`, and `monitor`.
- Simplified both launch files by removing unused imports and sharing a single
  `config_file` substitution.
- Removed stale root-level `mocap_to_mavros.py`; the real node lives under
  `ct_ws/src/ct_bridge/ct_bridge/`.
- Removed unused `std_msgs` dependency from `package.xml`.

No build or runtime test was run in this cleanup pass.

### Documentation updated after cleanup

- Rewrote `CLAUDE.md` to describe the current real-flight-only workflow:
  Jetson + ROS 2 Humble + VRPN + MAVROS + PX4 OFFBOARD.
- Rewrote `TESTING.md` as a真机 test checklist: hardware checks, monitor checks,
  coordinate/yaw verification, OFFBOARD hover, landing, and common launch
  overrides.
- Removed the old SITL-first instructions from the active docs. `ct_sitl_test.sh`
  is now documented as not part of the current maintained test path.

### Coordinate frame documentation

- Added `COORDINATE_FRAMES.md` with the explicit mocap → ROS ENU → PX4 NED
  chain, yaw examples, MAVROS conversion notes, and pre-flight sanity checks.
- Linked `COORDINATE_FRAMES.md` from `CLAUDE.md` and `TESTING.md`.
- Rechecked the current code against local MAVROS source:
  - `mocap_to_mavros.py` is the only project file that transforms mocap data.
  - `offboard_control.py` correctly consumes and publishes ROS ENU; it does not
    manually convert setpoints to NED.
  - MAVROS handles ENU/NED and base_link/aircraft conversion internally for
    both vision pose and local setpoints.

### Test flow reviewed

- Updated `TESTING.md` and `CLAUDE.md` to recommend the safer real-flight test
  sequence:
  1. start `ct_bridge.launch.py` without offboard and keep VRPN/MAVROS/vision
     running;
  2. run `ros2 run ct_bridge monitor` in a separate terminal for checks;
  3. stop only monitor;
  4. start `ros2 run ct_bridge offboard_control` with the installed params file.
- Left the one-shot `ct_bridge.launch.py start_offboard:=true` path documented as
  a quick path, not the preferred first real-flight test.
- Added a PX4 external-vision fusion prerequisite before starting the core
  pipeline.

### Communication launch split

The user asked for a dedicated launch file that only starts the persistent
communication/data pipeline; monitor, tests, and control tasks should run
separately.

**Changes:**
- Added `launch/comm.launch.py`:
  - starts `vrpn_client_node`
  - starts `mocap_to_mavros`
  - starts `mavros_node`
  - loads only `config/ct_bridge.yaml`
  - does not start monitor or offboard control
- Changed `launch/monitor.launch.py` to start only the read-only `monitor`
  node. It no longer starts VRPN, mocap conversion, or MAVROS.
- Changed `launch/ct_bridge.launch.py` into a compatibility alias for
  `comm.launch.py`; it no longer has `start_offboard`.
- Updated `TESTING.md` and `CLAUDE.md` so the recommended flow is:
  1. `ros2 launch ct_bridge comm.launch.py`
  2. `ros2 launch ct_bridge monitor.launch.py`
  3. `ros2 run ct_bridge offboard_control ...`

### Final real-flight update

- User completed a successful real hardware low-altitude OFFBOARD takeoff test on 2026-06-17.
- Confirmed runtime target: Jetson nvidia@192.168.2.113, /home/nvidia/ct, ROS 2 Humble.
- Important offboard safety behavior now documented and implemented: offboard_control publishes no setpoint until it has locked the current EKF pose; after locking it streams the current pose for about 1 second before requesting OFFBOARD and arm. This prevents sending vision-frame origin (0,0,0) as an effective target when the aircraft is not physically at the origin.
- Current successful flow: run comm.launch.py continuously, run monitor.launch.py for checks, stop monitor only, then run offboard.launch.py separately.

### Ctrl+C landing fix after first flight

- User observed that pressing Ctrl+C after a successful OFFBOARD test did not reliably switch to LAND; QGC reported OFFBOARD timeout and the aircraft descended abruptly.
- Root cause: the old KeyboardInterrupt path sent one async AUTO.LAND request, spun only about 0.5 seconds, then destroyed the node. If PX4 had not accepted AUTO.LAND before setpoint streaming stopped, PX4 hit OFFBOARD loss failsafe.
- Fix: offboard_control now has a landing_requested state. On Ctrl+C it stops requesting OFFBOARD/arm, keeps publishing the current setpoint, retries AUTO.LAND at 1 Hz, and holds the process alive for shutdown_land_hold_sec seconds (default 6.0).
- Practical guidance: prefer RC/QGC LAND or Position takeover for real tests; Ctrl+C is now safer but still should be watched in QGC.

### Session close summary

- Real-flight result: low-altitude OFFBOARD takeoff and hover succeeded after the comm/monitor/offboard split, ROS 2 Humble source order, MAVROS node naming fix, plugin allowlist fix, current-EKF lock, yaw lock, and Z ramp.
- Critical preflight rule: keep comm.launch.py running continuously; use monitor.launch.py only for read-only checks; stop monitor only; then start offboard.launch.py or offboard_control separately. Do not restart MAVROS or vision input right before OFFBOARD.
- Critical setpoint rule: never publish an effective origin target before locking current EKF pose. The current offboard_control returns without publishing until lock, then streams current pose before requesting OFFBOARD/arm.
- Critical landing lesson: Ctrl+C is not a primary landing method. The node now keeps setpoint streaming and retries AUTO.LAND for shutdown_land_hold_sec, but real tests should still use RC/QGC LAND or Position takeover as the primary safe exit.
- Git state: repository initialized on branch main; files are staged for the initial commit, but commit is blocked until local git user.name and user.email are configured.
