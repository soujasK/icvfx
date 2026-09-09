package com.stagesync.telemetry.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Wire-compatible with the JSON lines the Sprint 1 C++ kinematic engine
 * writes to stage.tracking.raw.jsonl / stage.ptp.drift.jsonl /
 * stage.kinematic.anomalies.jsonl. In production those JSONL sinks are
 * replaced by a Kafka producer inside the C++ daemon (e.g. librdkafka);
 * the schema is unchanged, only the transport is.
 */
public final class TelemetryEvents {

    private TelemetryEvents() {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TrackingRaw(
            String topic,
            int camera_id,
            long rx_ns,
            double pitch_deg,
            double yaw_deg,
            double roll_deg,
            double pos_x_m,
            double pos_y_m,
            double pos_z_m,
            int zoom,
            int focus,
            String traceparent
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PtpDrift(
            String topic,
            int camera_id,
            long rx_ns,
            double jitter_ms,
            int consecutive_violations,
            boolean alert,
            String traceparent
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record KinematicAnomaly(
            String topic,
            int camera_id,
            long rx_ns,
            String reason,
            double accel_mps2,
            double yaw_delta_deg,
            double pos_x_m,
            double pos_y_m,
            double pos_z_m,
            String traceparent
    ) {}
}
