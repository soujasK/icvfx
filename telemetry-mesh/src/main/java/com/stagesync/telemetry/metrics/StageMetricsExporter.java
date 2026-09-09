package com.stagesync.telemetry.metrics;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.stagesync.telemetry.config.KafkaTopicConfig;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Bridges Kafka Streams aggregate output onto the exact Micrometer/Prometheus
 * metric names Phase 3's Grafana Mimir dashboards read:
 *
 *   freed_packet_jitter_seconds        (gauge, P99 target < 1.0ms)
 *   ptp_grandmaster_offset_nanoseconds (gauge, target +-500ns)
 *   kinematic_jerk_violations_total    (counter)
 *
 * Scraped by Grafana Agent at /actuator/prometheus and remote_write'd to
 * Grafana Cloud Mimir (see observability/grafana-agent.river).
 */
@Component
public class StageMetricsExporter {

    private final MeterRegistry registry;
    private final ObjectMapper mapper = new ObjectMapper();
    private final Map<Integer, AtomicReference<Double>> jitterP99ByCamera = new ConcurrentHashMap<>();
    private final Map<Integer, AtomicReference<Double>> grandmasterOffsetByCamera = new ConcurrentHashMap<>();
    private final Map<Integer, Counter> jerkViolationCounters = new ConcurrentHashMap<>();

    public StageMetricsExporter(MeterRegistry registry) {
        this.registry = registry;
    }

    @KafkaListener(topics = "stage.ptp.drift.window-agg", groupId = "stage-metrics-exporter")
    public void onJitterWindowAggregate(String json) {
        try {
            var node = mapper.readTree(json);
            int cameraId = node.get("cameraId").asInt();
            double p99Ms = node.get("p99JitterMs").asDouble();

            jitterP99ByCamera.computeIfAbsent(cameraId, id -> {
                AtomicReference<Double> ref = new AtomicReference<>(0.0);
                registry.gauge("freed_packet_jitter_seconds", Tags.of("camera_id", String.valueOf(id)),
                        ref, r -> r.get());
                return ref;
            }).set(p99Ms / 1000.0); // ms -> seconds, matches the metric name's unit suffix

            // Grandmaster offset is not directly observable from jitter alone in
            // this simulated pipeline; production wires this from the PTP
            // hardware clock's own offset counter. Exposed here as a
            // placeholder gauge so the dashboard panel + alert rule exist
            // end-to-end even before that wiring lands.
            grandmasterOffsetByCamera.computeIfAbsent(cameraId, id -> {
                AtomicReference<Double> ref = new AtomicReference<>(0.0);
                registry.gauge("ptp_grandmaster_offset_nanoseconds", Tags.of("camera_id", String.valueOf(id)),
                        ref, r -> r.get());
                return ref;
            });
        } catch (Exception ignored) {
            // Malformed aggregate record; Kafka Streams' LogAndContinue handler
            // already logs the underlying deserialization failure upstream.
        }
    }

    @KafkaListener(topics = KafkaTopicConfig.TOPIC_KINEMATIC_ANOMALIES, groupId = "stage-metrics-exporter")
    public void onKinematicAnomaly(String json) {
        try {
            var node = mapper.readTree(json);
            int cameraId = node.get("camera_id").asInt();
            jerkViolationCounters.computeIfAbsent(cameraId, id ->
                    Counter.builder("kinematic_jerk_violations_total")
                            .tag("camera_id", String.valueOf(id))
                            .register(registry)
            ).increment();
        } catch (Exception ignored) {
        }
    }
}
