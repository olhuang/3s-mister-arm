#ifndef RL_SESSION_H
#define RL_SESSION_H

#include "rl/rl_protocol.h"

#include "types.h"

#include <stdbool.h>

typedef struct RLObservationV1 RLObservationV1;

typedef enum RLMoveIntent {
    RL_MOVE_NEUTRAL = 0,
    RL_MOVE_UP = 1,
    RL_MOVE_DOWN = 2,
    RL_MOVE_BACK = 3,
    RL_MOVE_FORWARD = 4,
    RL_MOVE_UP_BACK = 5,
    RL_MOVE_UP_FORWARD = 6,
    RL_MOVE_DOWN_BACK = 7,
    RL_MOVE_DOWN_FORWARD = 8,
} RLMoveIntent;

typedef struct RLActionContext {
    u8 last_executed_move_intent;
    u16 last_executed_attack_bits;
    u8 next_scheduled_move_intent;
    u16 next_scheduled_attack_bits;
    u8 frames_until_next_action;
} RLActionContext;

typedef enum RLRemoteActionSubmitResult {
    RL_REMOTE_ACTION_SUBMIT_ACCEPTED = 0,
    RL_REMOTE_ACTION_SUBMIT_LATE = 1,
    RL_REMOTE_ACTION_SUBMIT_DUPLICATE = 2,
    RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH = 3,
} RLRemoteActionSubmitResult;

typedef enum RLExecutionSource {
    RL_EXECUTION_SOURCE_NONE = 0,
    RL_EXECUTION_SOURCE_REMOTE = 1,
    RL_EXECUTION_SOURCE_REPEATED_LAST_ACTION = 2,
    RL_EXECUTION_SOURCE_NEUTRAL_FALLBACK = 3,
    RL_EXECUTION_SOURCE_HUMAN_DEMO = 4,
    RL_EXECUTION_SOURCE_CPU_DEMO = 5,
} RLExecutionSource;

typedef struct RLRemoteDebugState {
    u32 frame_id;
    u64 run_id;
    u32 episode_id;
    u32 next_decision_id;
    u32 obs_sent_count;
    u32 queue_depth;
    u32 queued_count;
    u32 executed_count;
    u32 late_drop_count;
    u32 duplicate_drop_count;
    u32 target_mismatch_count;
    u32 fallback_count;
    u32 transition_export_count;
    u32 transition_format_error_count;
    u32 transition_format_truncation_count;
    u32 transition_evidence_fallback_count;
    u32 episode_attack_active_count;
    u32 episode_attack_contact_count;
    u32 episode_attack_whiff_count;
    u32 combat_attack_started_count;
    u32 combat_attack_finalized_count;
    u32 combat_attack_whiff_count;
    u32 combat_attack_interrupted_count;
    u32 combat_attack_unknown_timeout_count;
    u32 combat_attack_unknown_flush_count;
    u32 combat_attack_unknown_rollover_count;
    u32 combat_attack_dropped_start_count;
    u32 combat_attack_active_self_count;
    u32 combat_attack_active_opp_count;
    u32 model_version_current;
    u8 last_overlay_attack_contact;
    u8 last_overlay_attack_whiff;
    s16 last_delta_self_forward;
    s16 last_delta_opp_forward;
    u8 last_requested_movement_succeeded;
    u8 last_requested_attack_entered_state;
    u8 last_requested_attack_made_contact;
    u8 last_requested_attack_likely_whiffed;
    u8 last_requested_attack_input_started;
    u8 last_requested_attack_became_active;
    u8 last_observed_attack_state_started;
    u8 last_observed_attack_code_changed;
    u8 last_observed_attack_counter_started;
    u8 last_requested_jump_started;
} RLRemoteDebugState;

bool RLSession_IsActive();
s16 RLSession_AgentPlayerIndex();
s16 RLSession_OpponentPlayerIndex();
bool RLSession_OpponentUsesHumanInput();
const char* RLSession_TestMovementLabel();
const RLActionContext* RLSession_GetActionContext();
const RLRemoteDebugState* RLSession_GetRemoteDebugState();
u32 RLSession_GetCurrentFrameId();
bool RLSession_AllocFormatBuffer(void);
void RLSession_FreeFormatBuffer(void);
RLRemoteActionSubmitResult RLSession_SubmitRemoteAction(const RLActionPacket* packet);
bool RLSession_SendRemoteObservationIfDue();
void RLSession_OnObservationFrameEnd(const RLObservationV1* obs);
void RLSession_ApplyVersusOperatorSetup();
void RLSession_ApplyScriptedMovementToBuffers();
void RLSession_ApplyInputOverrideToBuffers();
void RLSession_RecordCpuDemoInput(s16 player, u16 sw);

#endif
