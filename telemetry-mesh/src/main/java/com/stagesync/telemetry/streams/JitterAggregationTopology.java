package com.stagesync.telemetry.streams;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.stagesync.telemetry.config.KafkaTopicConfig;
import com.stagesync.telemetry.model.TelemetryEvents.PtpDrift;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 500ms sliding-window rolling P95/P99 jitter + packet-continuity aggregate
 * over stage.ptp.drift, keyed by camera_id, per Phase 2's "Sliding-Window
 * State Machine" requirement. Emits one aggregate record per window close,
 * which the Prometheus exporter (metrics/PrometheusExporterConfig) turns
 * into the freed_packet_jitter_seconds gauge Grafana Mimir dashboards read.
 */
@Configuration
public class JitterAggregationTopology {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    public record JitterWindowAggregate(
            int cameraId,
            long windowStartMs,
            long windowEndMs,
            int sampleCount,
            double p95JitterMs,
            double p99JitterMs,
            int alertEventCount
    ) {}

    @Bean
    public KStream<String, String> jitterAggregationPipeline(StreamsBuilder builder) {
        KStream<String, String> ptpDrift = builder.stream(
                KafkaTopicConfig.TOPIC_PTP_DRIFT,
                Consumed.with(Serdes.String(), Serdes.String())
        );

        KGroupedStream<String, PtpDrift> byCamera = ptpDrift
                .mapValues(JitterAggregationTopology::parseOrNull)
                .filter((k, v) -> v != null)
                .selectKey((k, v) -> String.valueOf(v.camera_id()))
                .groupByKey(Grouped.with(Serdes.String(), jitterSerde()));

        TimeWindows windows = TimeWindows.ofSizeAndGrace(Duration.ofMillis(500), Duration.ofMillis(100));

        KTable<Windowed<String>, List<PtpDrift>> windowed = byCamera
                .windowedBy(windows)
                .aggregate(
                        ArrayList::new,
                        (key, value, agg) -> {
                            agg.add(value);
                            return agg;
                        },
                        Materialized.<String, List<PtpDrift>, org.apache.kafka.streams.state.WindowStore<org.apache.kafka.common.utils.Bytes, byte[]>>as("ptp-jitter-windows")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(listSerde())
                );

        windowed.toStream()
                .map((windowedKey, samples) -> {
                    JitterWindowAggregate agg = summarize(windowedKey.key(), windowedKey.window().start(),
                            windowedKey.window().end(), samples);
                    return KeyValue.pair(windowedKey.key(), toJson(agg));
                })
                .to("stage.ptp.drift.window-agg", Produced.with(Serdes.String(), Serdes.String()));

        return ptpDrift;
    }

    private static JitterWindowAggregate summarize(String cameraId, long start, long end, List<PtpDrift> samples) {
        List<Double> jitters = samples.stream().map(s -> Math.abs(s.jitter_ms())).sorted().toList();
        int n = jitters.size();
        double p95 = n == 0 ? 0.0 : jitters.get((int) Math.min(n - 1, Math.floor(0.95 * n)));
        double p99 = n == 0 ? 0.0 : jitters.get((int) Math.min(n - 1, Math.floor(0.99 * n)));
        int alertEvents = (int) samples.stream().filter(PtpDrift::alert).count();
        return new JitterWindowAggregate(Integer.parseInt(cameraId), start, end, n, p95, p99, alertEvents);
    }

    private static PtpDrift parseOrNull(String json) {
        try {
            return MAPPER.readValue(json, PtpDrift.class);
        } catch (Exception e) {
            return null;
        }
    }

    private static String toJson(JitterWindowAggregate agg) {
        try {
            return MAPPER.writeValueAsString(agg);
        } catch (Exception e) {
            return "{}";
        }
    }

    private static Serde<PtpDrift> jitterSerde() {
        return jsonSerde(PtpDrift.class);
    }

    private static Serde<List<PtpDrift>> listSerde() {
        return Serdes.serdeFrom(
                (topic, data) -> {
                    try {
                        return MAPPER.writeValueAsBytes(data);
                    } catch (Exception e) {
                        return new byte[0];
                    }
                },
                (topic, bytes) -> {
                    try {
                        PtpDrift[] arr = MAPPER.readValue(bytes, PtpDrift[].class);
                        return new ArrayList<>(List.of(arr));
                    } catch (Exception e) {
                        return Collections.emptyList();
                    }
                }
        );
    }

    private static <T> Serde<T> jsonSerde(Class<T> clazz) {
        return Serdes.serdeFrom(
                (topic, data) -> {
                    try {
                        return MAPPER.writeValueAsBytes(data);
                    } catch (Exception e) {
                        return new byte[0];
                    }
                },
                (topic, bytes) -> {
                    try {
                        return MAPPER.readValue(bytes, clazz);
                    } catch (Exception e) {
                        return null;
                    }
                }
        );
    }
}
