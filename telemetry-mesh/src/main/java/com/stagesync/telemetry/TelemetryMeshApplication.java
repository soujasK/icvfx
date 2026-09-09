package com.stagesync.telemetry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafkaStreams;

/**
 * Sprint 2: Stage Telemetry Event Mesh.
 *
 * Decouples the high-frequency C++ ingest daemons (Sprint 1) from downstream
 * analytics and observability (Sprint 3) via three Kafka topics:
 *
 *   stage.tracking.raw        - continuous 120Hz normalized coordinate stream, partitioned by camera_id
 *   stage.ptp.drift           - sub-millisecond timing delta reports
 *   stage.kinematic.anomalies - filtered topic: invariant breaches only
 *
 * and computes 500ms sliding-window P95/P99 jitter + packet-continuity
 * aggregates via Kafka Streams, exported to Grafana Cloud Mimir over the
 * Prometheus remote-write protocol.
 */
@SpringBootApplication
@EnableKafkaStreams
public class TelemetryMeshApplication {
    public static void main(String[] args) {
        SpringApplication.run(TelemetryMeshApplication.class, args);
    }
}
