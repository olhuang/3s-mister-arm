#include "rl/rl_protocol.h"

#include <string.h>

static u32 fnv1a_update_u8(u32 hash, u8 value) {
    hash ^= value;
    return hash * 16777619u;
}

static u32 fnv1a_update_u16(u32 hash, u16 value) {
    hash = fnv1a_update_u8(hash, (u8)(value & 0xFFu));
    return fnv1a_update_u8(hash, (u8)((value >> 8) & 0xFFu));
}

static u32 fnv1a_update_u32(u32 hash, u32 value) {
    hash = fnv1a_update_u8(hash, (u8)(value & 0xFFu));
    hash = fnv1a_update_u8(hash, (u8)((value >> 8) & 0xFFu));
    hash = fnv1a_update_u8(hash, (u8)((value >> 16) & 0xFFu));
    return fnv1a_update_u8(hash, (u8)((value >> 24) & 0xFFu));
}

RLSessionConfig RLProtocol_DefaultConfig(void) {
    RLSessionConfig config;
    memset(&config, 0, sizeof(config));
    config.protocol_version = RL_PROTOCOL_VERSION;
    config.observation_schema_version = RL_OBSERVATION_SCHEMA_VERSION;
    config.action_schema_version = RL_ACTION_SCHEMA_VERSION;
    config.action_encoding_mode = RL_ACTION_ENCODING_RELATIVE_MOVE_WITH_ATTACK_BITS;
    config.decision_interval_frames = 4;
    config.action_hold_frames = 4;
    config.candidate_k_delay_frames = 4;
    config.feature_flags = RL_PROTOCOL_FEATURE_RELATIVE_MOVEMENT | RL_PROTOCOL_FEATURE_FIXED_HOLD;
    config.config_hash = RLProtocol_ComputeConfigHash(&config);
    return config;
}

u32 RLProtocol_ComputeConfigHash(const RLSessionConfig* config) {
    if (config == NULL) {
        return 0;
    }

    u32 hash = 2166136261u;
    hash = fnv1a_update_u16(hash, config->protocol_version);
    hash = fnv1a_update_u16(hash, config->observation_schema_version);
    hash = fnv1a_update_u16(hash, config->action_schema_version);
    hash = fnv1a_update_u16(hash, config->action_encoding_mode);
    hash = fnv1a_update_u8(hash, config->decision_interval_frames);
    hash = fnv1a_update_u8(hash, config->action_hold_frames);
    hash = fnv1a_update_u8(hash, config->candidate_k_delay_frames);
    hash = fnv1a_update_u8(hash, config->reserved0);
    return fnv1a_update_u32(hash, config->feature_flags);
}

bool RLProtocol_ConfigTimingSupported(const RLSessionConfig* config) {
    if (config == NULL) {
        return false;
    }
    if (config->decision_interval_frames == 0 || config->decision_interval_frames > 30) {
        return false;
    }
    if (config->action_hold_frames == 0 || config->action_hold_frames > 30) {
        return false;
    }
    if (config->candidate_k_delay_frames == 0 || config->candidate_k_delay_frames > 30) {
        return false;
    }
    return true;
}

RLSessionAckStatus RLProtocol_ValidateAck(const RLSessionHello* hello, const RLSessionAck* ack) {
    if (hello == NULL || ack == NULL || ack->magic != RL_PROTOCOL_MAGIC) {
        return RL_SESSION_ACK_REJECT_PROTOCOL_VERSION;
    }
    if (ack->session_nonce != hello->session_nonce) {
        return RL_SESSION_ACK_REJECT_NONCE;
    }
    if (ack->protocol_version != RL_PROTOCOL_VERSION || hello->config.protocol_version != RL_PROTOCOL_VERSION) {
        return RL_SESSION_ACK_REJECT_PROTOCOL_VERSION;
    }
    if (hello->config.observation_schema_version != RL_OBSERVATION_SCHEMA_VERSION) {
        return RL_SESSION_ACK_REJECT_OBSERVATION_SCHEMA;
    }
    if (hello->config.action_schema_version != RL_ACTION_SCHEMA_VERSION) {
        return RL_SESSION_ACK_REJECT_ACTION_SCHEMA;
    }
    if (hello->config.action_encoding_mode != RL_ACTION_ENCODING_RELATIVE_MOVE_WITH_ATTACK_BITS) {
        return RL_SESSION_ACK_REJECT_ACTION_ENCODING;
    }
    if (!RLProtocol_ConfigTimingSupported(&hello->config)) {
        return RL_SESSION_ACK_REJECT_TIMING_CONFIG;
    }
    if ((hello->config.feature_flags & RL_PROTOCOL_FEATURE_RELATIVE_MOVEMENT) == 0) {
        return RL_SESSION_ACK_REJECT_FEATURE_FLAGS;
    }
    if (hello->config.config_hash != RLProtocol_ComputeConfigHash(&hello->config) ||
        ack->accepted_config_hash != hello->config.config_hash) {
        return RL_SESSION_ACK_REJECT_CONFIG_HASH;
    }
    if (ack->status != RL_SESSION_ACK_ACCEPTED) {
        return (RLSessionAckStatus)ack->status;
    }
    return RL_SESSION_ACK_ACCEPTED;
}

static u32 percentile_from_sorted_samples(const u32* sorted_samples_us, size_t sample_count, u32 percentile) {
    if (sorted_samples_us == NULL || sample_count == 0) {
        return 0;
    }
    size_t index = ((sample_count * percentile) + 99u) / 100u;
    if (index == 0) {
        index = 1;
    }
    index--;
    if (index >= sample_count) {
        index = sample_count - 1;
    }
    return sorted_samples_us[index];
}

void RLProtocol_ProbeStatsFromSortedSamples(const u32* sorted_samples_us, size_t sample_count, RLProbeStats* out_stats) {
    if (out_stats == NULL) {
        return;
    }

    memset(out_stats, 0, sizeof(*out_stats));
    if (sorted_samples_us == NULL || sample_count == 0) {
        return;
    }

    out_stats->sample_count = (u32)sample_count;
    out_stats->min_us = sorted_samples_us[0];
    out_stats->max_us = sorted_samples_us[sample_count - 1];
    out_stats->p50_us = percentile_from_sorted_samples(sorted_samples_us, sample_count, 50);
    out_stats->p95_us = percentile_from_sorted_samples(sorted_samples_us, sample_count, 95);
    out_stats->p99_us = percentile_from_sorted_samples(sorted_samples_us, sample_count, 99);
    out_stats->jitter_us = out_stats->p95_us >= out_stats->p50_us ? out_stats->p95_us - out_stats->p50_us : 0;
}
