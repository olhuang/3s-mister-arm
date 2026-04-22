#ifndef RL_PROTOCOL_H
#define RL_PROTOCOL_H

#include "types.h"

#include <stdbool.h>
#include <stddef.h>

#define RL_PROTOCOL_VERSION 1u
#define RL_OBSERVATION_SCHEMA_VERSION 1u
#define RL_ACTION_SCHEMA_VERSION 1u
#define RL_PROTOCOL_MAGIC 0x33524C41u /* 3RLA */
#define RL_PROTOCOL_FEATURE_RELATIVE_MOVEMENT 0x00000001u
#define RL_PROTOCOL_FEATURE_FIXED_HOLD 0x00000002u

typedef enum RLActionEncodingMode {
    RL_ACTION_ENCODING_RELATIVE_MOVE_WITH_ATTACK_BITS = 1,
} RLActionEncodingMode;

typedef struct RLSessionConfig {
    u16 protocol_version;
    u16 observation_schema_version;
    u16 action_schema_version;
    u16 action_encoding_mode;
    u8 decision_interval_frames;
    u8 action_hold_frames;
    u8 candidate_k_delay_frames;
    u8 reserved0;
    u32 feature_flags;
    u32 config_hash;
} RLSessionConfig;

typedef struct RLSessionHello {
    u32 magic;
    u64 session_nonce;
    RLSessionConfig config;
} RLSessionHello;

typedef struct RLSessionAck {
    u32 magic;
    u64 session_nonce;
    u32 accepted_config_hash;
    u16 protocol_version;
    u16 status;
} RLSessionAck;

typedef enum RLSessionAckStatus {
    RL_SESSION_ACK_ACCEPTED = 0,
    RL_SESSION_ACK_REJECT_PROTOCOL_VERSION = 1,
    RL_SESSION_ACK_REJECT_OBSERVATION_SCHEMA = 2,
    RL_SESSION_ACK_REJECT_ACTION_SCHEMA = 3,
    RL_SESSION_ACK_REJECT_ACTION_ENCODING = 4,
    RL_SESSION_ACK_REJECT_TIMING_CONFIG = 5,
    RL_SESSION_ACK_REJECT_FEATURE_FLAGS = 6,
    RL_SESSION_ACK_REJECT_CONFIG_HASH = 7,
    RL_SESSION_ACK_REJECT_NONCE = 8,
} RLSessionAckStatus;

typedef struct RLProbeStats {
    u32 sample_count;
    u32 p50_us;
    u32 p95_us;
    u32 p99_us;
    u32 min_us;
    u32 max_us;
    u32 jitter_us;
} RLProbeStats;

typedef struct RLActionPacket {
    u32 magic;
    u16 version;
    u16 flags;
    u64 session_nonce;
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
    u16 action_wire;
    u16 reserved0;
    u32 model_version;
} RLActionPacket;

RLSessionConfig RLProtocol_DefaultConfig(void);
u32 RLProtocol_ComputeConfigHash(const RLSessionConfig* config);
bool RLProtocol_ConfigTimingSupported(const RLSessionConfig* config);
RLSessionAckStatus RLProtocol_ValidateAck(const RLSessionHello* hello, const RLSessionAck* ack);
void RLProtocol_ProbeStatsFromSortedSamples(const u32* sorted_samples_us, size_t sample_count, RLProbeStats* out_stats);

#endif
