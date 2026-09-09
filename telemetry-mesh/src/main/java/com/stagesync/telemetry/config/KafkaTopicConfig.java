package com.stagesync.telemetry.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

/**
 * Declares the three stage telemetry topics from Phase 2 of the plan.
 * Partition count is chosen so each camera_id's packet ordering is
 * preserved within a partition (consumers key on camera_id).
 */
@Configuration
public class KafkaTopicConfig {

    public static final String TOPIC_TRACKING_RAW = "stage.tracking.raw";
    public static final String TOPIC_PTP_DRIFT = "stage.ptp.drift";
    public static final String TOPIC_KINEMATIC_ANOMALIES = "stage.kinematic.anomalies";

    @Bean
    public NewTopic trackingRawTopic() {
        return TopicBuilder.name(TOPIC_TRACKING_RAW)
                .partitions(8)   // one partition per expected concurrent stage camera
                .replicas(3)
                .config("retention.ms", String.valueOf(60 * 60 * 1000)) // 1h hot retention
                .build();
    }

    @Bean
    public NewTopic ptpDriftTopic() {
        return TopicBuilder.name(TOPIC_PTP_DRIFT)
                .partitions(8)
                .replicas(3)
                .config("retention.ms", String.valueOf(24 * 60 * 60 * 1000)) // 24h for post-mortem
                .build();
    }

    @Bean
    public NewTopic kinematicAnomaliesTopic() {
        return TopicBuilder.name(TOPIC_KINEMATIC_ANOMALIES)
                .partitions(4)
                .replicas(3)
                .config("retention.ms", String.valueOf(7L * 24 * 60 * 60 * 1000)) // 7d, low volume
                .build();
    }
}
