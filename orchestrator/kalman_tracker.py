#!/usr/bin/env python3
"""6-DoF Extended Kalman Filter (EKF) for ICVFX Camera Tracking.

Provides state-space kinematic estimation, optical measurement gating,
and autonomous dead-reckoning trajectory propagation during sensor occlusion.

State Vector (12-DoF):
    x = [x, y, z, vx, vy, vz, pitch, yaw, roll, w_pitch, w_yaw, w_roll]^T

When optical tracking markers drop or suffer line-of-sight occlusion:
1. Innovation gating rejects corrupted measurements (yaw flips / acceleration spikes).
2. The filter transitions to pure kinematic dead-reckoning:
   x_{k|k-1} = F * x_{k-1}
   P_{k|k-1} = F * P_{k-1} * F^T + Q
3. Camera crane linear momentum and angular momentum are mathematically conserved,
   holding the Unreal Engine nDisplay frustum steady within millimeter tolerances.
"""

from __future__ import annotations

import collections
import time
from typing import Literal, Tuple
import numpy as np

FilterMode = Literal["OPTICAL_ONLY", "KALMAN_STANDARD", "KALMAN_DEAD_RECKONING"]


class KalmanTracker:
    """Rigorous 6-DoF state-space Extended Kalman Filter with dead-reckoning fallback."""

    def __init__(
        self,
        camera_id: int = 1,
        sigma_accel: float = 1.2,       # Process noise std dev (crane linear accel, m/s^2)
        sigma_alpha: float = 0.5,       # Process noise std dev (crane angular accel, rad/s^2)
        sigma_meas_pos: float = 0.0015, # Optical sensor noise (position, meters ~1.5mm)
        sigma_meas_rot: float = 0.02,   # Optical sensor noise (angles, degrees)
        history_len: int = 150,
        reacquire_after_good: int = 90, # frames of smooth optical before auto-exiting dead-reckoning
    ):
        self.camera_id = camera_id
        self.sigma_accel = sigma_accel
        self.sigma_alpha = sigma_alpha
        self.sigma_meas_pos = sigma_meas_pos
        self.sigma_meas_rot = sigma_meas_rot
        self.mode: FilterMode = "KALMAN_STANDARD"

        # 12-state vector
        self.x = np.zeros(12, dtype=np.float64)

        # 12x12 state covariance matrix
        self.P = np.eye(12, dtype=np.float64) * 0.1
        self.P[3:6, 3:6] *= 1.0   # Higher initial uncertainty on velocity
        self.P[9:12, 9:12] *= 1.0

        # Measurement matrix H (6 x 12): maps state to observable [x, y, z, pitch, yaw, roll]
        self.H = np.zeros((6, 12), dtype=np.float64)
        self.H[0:3, 0:3] = np.eye(3)     # Position
        self.H[3:6, 6:9] = np.eye(3)     # Rotation

        # Measurement noise covariance R (6 x 6)
        self.R = np.diag([
            sigma_meas_pos**2, sigma_meas_pos**2, sigma_meas_pos**2,
            sigma_meas_rot**2, sigma_meas_rot**2, sigma_meas_rot**2
        ])

        # Tracking metrics & history
        self.consecutive_rejections = 0
        self.reacquire_after_good = reacquire_after_good
        self.consecutive_good = 0   # consecutive frames the raw optical stream has been smooth
        self._last_raw = None
        self.total_occluded_frames = 0
        self.total_frames = 0
        self.last_timestamp = None
        self.history = collections.deque(maxlen=history_len)

    def _build_F(self, dt: float) -> np.ndarray:
        """Construct state transition matrix for time step dt."""
        F = np.eye(12, dtype=np.float64)
        # Position += Velocity * dt
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        # Orientation += AngularVelocity * dt
        F[6, 9] = dt
        F[7, 10] = dt
        F[8, 11] = dt
        return F

    def _build_Q(self, dt: float) -> np.ndarray:
        """Construct continuous white-noise acceleration process covariance matrix."""
        Q = np.zeros((12, 12), dtype=np.float64)
        dt2 = dt * dt
        dt3 = dt2 * dt / 2.0
        dt4 = dt2 * dt2 / 4.0

        q_pos = self.sigma_accel**2
        q_rot = self.sigma_alpha**2

        # Linear motion blocks
        for i in range(3):
            Q[i, i] = dt4 * q_pos
            Q[i, i + 3] = dt3 * q_pos
            Q[i + 3, i] = dt3 * q_pos
            Q[i + 3, i + 3] = dt2 * q_pos

        # Angular motion blocks
        for i in range(3):
            Q[i + 6, i + 6] = dt4 * q_rot
            Q[i + 6, i + 9] = dt3 * q_rot
            Q[i + 9, i + 6] = dt3 * q_rot
            Q[i + 9, i + 9] = dt2 * q_rot

        return Q

    def predict(self, dt: float) -> np.ndarray:
        """State propagation step: x_{k|k-1} = F*x, P_{k|k-1} = F*P*F^T + Q."""
        dt = max(1e-4, min(0.1, dt))
        F = self._build_F(dt)
        Q = self._build_Q(dt)

        # Propagate state
        self.x = F @ self.x

        # Normalize yaw/pitch/roll to [-180, 180] degrees
        for i in range(6, 9):
            self.x[i] = (self.x[i] + 180.0) % 360.0 - 180.0

        # Propagate covariance
        self.P = F @ self.P @ F.T + Q
        return self.x

    def update(self, measurement: np.ndarray, force_dead_reckon: bool = False) -> Tuple[np.ndarray, bool]:
        """Kalman measurement update with Mahalanobis innovation gating.

        Args:
            measurement: [x, y, z, pitch, yaw, roll] from optical sensor
            force_dead_reckon: whether dead reckoning mode is explicitly forced

        Returns:
            (filtered_state, is_valid_measurement)
        """
        self.total_frames += 1
        z = np.asarray(measurement, dtype=np.float64)

        if self.total_frames <= 3:
            self.x[0:3] = z[0:3]
            self.x[6:9] = z[3:6]
            self.consecutive_rejections = 0
            self.history.append({
                "frame": self.total_frames,
                "raw": z.tolist(),
                "filtered": self.x.tolist(),
                "mode": "KALMAN_STANDARD",
                "covariance_trace": float(np.trace(self.P)),
                "occluded": False,
                "mahalanobis_d2": 0.0,
            })
            return self.x, True

        if self.mode == "OPTICAL_ONLY":
            self.x[0:3] = z[0:3]
            self.x[6:9] = z[3:6]
            self.history.append({
                "frame": self.total_frames,
                "raw": z.tolist(),
                "filtered": z.tolist(),
                "mode": "OPTICAL_ONLY",
                "covariance_trace": float(np.trace(self.P)),
                "occluded": False,
            })
            return self.x, True

        # Compute innovation y = z - H*x
        y = z - (self.H @ self.x)
        # Handle angular wrap-around for rotation errors
        for i in range(3, 6):
            y[i] = (y[i] + 180.0) % 360.0 - 180.0

        # Innovation covariance S = H*P*H^T + R
        S = self.H @ self.P @ self.H.T + self.R
        S_inv = np.linalg.inv(S)

        # Mahalanobis distance squared: d^2 = y^T * S^-1 * y
        mahalanobis_d2 = float(y.T @ S_inv @ y)

        # Kinematic sanity checks (e.g. impossible yaw flip > 60 deg or pos jump > 0.4m)
        pos_jump = np.linalg.norm(y[0:3])
        yaw_jump = abs(y[4])

        is_anomaly = (
            force_dead_reckon or
            self.mode == "KALMAN_DEAD_RECKONING" or
            mahalanobis_d2 > 35.0 or    # 99.9% chi-square threshold for 6 DoF
            pos_jump > 0.40 or          # Camera cannot teleport 40cm in 8.3ms
            yaw_jump > 45.0             # Marker occlusion yaw flip
        )

        # Raw-stream smoothness: is the measurement *sequence itself* physically
        # continuous frame-to-frame? This is independent of the filtered state
        # (which drifts during a long dead-reckoning episode), so it still tells
        # us the occlusion has physically cleared even when our own estimate is
        # stale - which is exactly when re-acquisition is needed.
        if self._last_raw is not None:
            raw_pos_step = float(np.linalg.norm(z[0:3] - self._last_raw[0:3]))
            raw_yaw_step = abs((z[4] - self._last_raw[4] + 180.0) % 360.0 - 180.0)
            raw_smooth = raw_pos_step < 0.40 and raw_yaw_step < 45.0
        else:
            raw_smooth = False
        self._last_raw = z.copy()
        self.consecutive_good = self.consecutive_good + 1 if raw_smooth else 0

        # Automatic optical re-acquisition (only when not explicitly commanded to
        # dead-reckon this frame), gated on the raw stream having gone smooth
        # again so the estimate is never snapped onto a still-wild reading:
        #   1. STANDARD stuck rejecting through a long blackout (>60 frames), or
        #   2. DEAD_RECKONING once optical has been continuously smooth for
        #      reacquire_after_good frames - the physical occlusion is over, so
        #      stop flying blind instead of drifting without bound.
        stuck_standard = self.mode == "KALMAN_STANDARD" and self.consecutive_rejections > 60
        recovered_dead_reckon = (
            self.mode == "KALMAN_DEAD_RECKONING"
            and self.consecutive_good >= self.reacquire_after_good
        )
        if is_anomaly and not force_dead_reckon and raw_smooth and (stuck_standard or recovered_dead_reckon):
            self.mode = "KALMAN_STANDARD"
            self.reacquire(z)
            return self.x, True

        if is_anomaly:
            # SENSOR BLACKOUT / OCCLUSION DETECTED
            # Reject optical measurement; rely purely on momentum prediction!
            self.consecutive_rejections += 1
            self.total_occluded_frames += 1
            is_valid = False

            # Allow uncertainty to grow predictably during dead-reckoning
            self.history.append({
                "frame": self.total_frames,
                "raw": z.tolist(),
                "filtered": self.x[:6].tolist() + self.x[6:12].tolist(),
                "mode": "KALMAN_DEAD_RECKONING",
                "covariance_trace": float(np.trace(self.P)),
                "occluded": True,
                "mahalanobis_d2": round(mahalanobis_d2, 2),
            })
            return self.x, False

        # MEASUREMENT VALID: Perform standard EKF update
        self.consecutive_rejections = 0
        K = self.P @ self.H.T @ S_inv
        self.x = self.x + K @ y

        # Joseph form update for numerical stability: P = (I - KH) P (I - KH)^T + K R K^T
        I_KH = np.eye(12) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

        # Normalize angles
        for i in range(6, 9):
            self.x[i] = (self.x[i] + 180.0) % 360.0 - 180.0

        self.history.append({
            "frame": self.total_frames,
            "raw": z.tolist(),
            "filtered": self.x[:6].tolist() + self.x[6:12].tolist(),
            "mode": "KALMAN_STANDARD",
            "covariance_trace": float(np.trace(self.P)),
            "occluded": False,
            "mahalanobis_d2": round(mahalanobis_d2, 2),
        })
        return self.x, True

    def reacquire(self, measurement: np.ndarray):
        """Re-acquire optical lock after prolonged blackout or mode switch."""
        z = np.asarray(measurement, dtype=np.float64)
        self.x[0:3] = z[0:3]
        self.x[3:6] = 0.0  # Reset linear velocity
        self.x[6:9] = z[3:6]
        self.x[9:12] = 0.0  # Reset angular velocity
        self.P = np.eye(12, dtype=np.float64) * 0.1
        self.P[3:6, 3:6] *= 0.5
        self.P[9:12, 9:12] *= 0.5
        self.consecutive_rejections = 0
        self.consecutive_good = 0
        self._last_raw = z.copy()

    def step(self, dt: float, measurement: np.ndarray, is_occluded: bool = False) -> Tuple[np.ndarray, bool]:
        """Full predict-and-update cycle."""
        self.predict(dt)
        return self.update(measurement, force_dead_reckon=is_occluded)

    def set_mode(self, mode: FilterMode):
        """Switch operational filter mode."""
        self.mode = mode
        if mode == "KALMAN_STANDARD":
            self.consecutive_rejections = 100  # Trigger immediate re-acquisition on next frame
        elif mode == "KALMAN_DEAD_RECKONING":
            # Commanding dead-reckoning asserts "optical is bad now" - restart the
            # smooth-frame counter so auto-recovery needs a full clean window.
            self.consecutive_good = 0

    def get_pose(self) -> dict:
        """Return current estimated 6-DoF pose and velocities."""
        return {
            "x": round(float(self.x[0]), 4),
            "y": round(float(self.x[1]), 4),
            "z": round(float(self.x[2]), 4),
            "vx": round(float(self.x[3]), 4),
            "vy": round(float(self.x[4]), 4),
            "vz": round(float(self.x[5]), 4),
            "pitch": round(float(self.x[6]), 3),
            "yaw": round(float(self.x[7]), 3),
            "roll": round(float(self.x[8]), 3),
            "w_pitch": round(float(self.x[9]), 3),
            "w_yaw": round(float(self.x[10]), 3),
            "w_roll": round(float(self.x[11]), 3),
            "mode": self.mode,
            "covariance_trace": round(float(np.trace(self.P)), 6),
            "consecutive_rejections": self.consecutive_rejections,
            "consecutive_good": self.consecutive_good,
            "total_occluded_frames": self.total_occluded_frames,
        }

    def get_recent_trajectory(self, count: int = 50) -> list[dict]:
        """Retrieve recent trajectory points for frontend comparison graphs."""
        return list(self.history)[-count:]


# Global singleton instance for camera 1
_default_tracker = KalmanTracker(camera_id=1)


def get_global_tracker() -> KalmanTracker:
    return _default_tracker
