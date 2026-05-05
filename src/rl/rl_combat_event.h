#ifndef RL_COMBAT_EVENT_H
#define RL_COMBAT_EVENT_H

#include "types.h"

#include <stdbool.h>

#define RL_COMBAT_EVIDENCE_BITMASK_VERSION 1u

#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_ATTACK_INPUT_STARTED 0u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_ATTACK_BECAME_ACTIVE 1u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_ATTACK_ENTERED_STATE 2u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_ATTACK_MADE_CONTACT 3u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_ATTACK_LIKELY_WHIFFED 4u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_JUMP_STARTED 5u
#define RL_COMBAT_EVIDENCE_BIT_REQUESTED_MOVEMENT_SUCCEEDED 6u
#define RL_COMBAT_EVIDENCE_BIT_OBSERVED_ATTACK_STATE_STARTED 7u
#define RL_COMBAT_EVIDENCE_BIT_OBSERVED_ATTACK_CODE_CHANGED 8u
#define RL_COMBAT_EVIDENCE_BIT_OBSERVED_ATTACK_COUNTER_STARTED 9u
#define RL_COMBAT_EVIDENCE_BIT_OVERLAY_ATTACK_EVENT_FINALIZED 10u
#define RL_COMBAT_EVIDENCE_BIT_OVERLAY_ATTACK_CONTACT 11u
#define RL_COMBAT_EVIDENCE_BIT_OVERLAY_ATTACK_WHIFF 12u
#define RL_COMBAT_EVIDENCE_BIT_SELF_ATTACK_STARTED 13u
#define RL_COMBAT_EVIDENCE_BIT_OPP_ATTACK_STARTED 14u
#define RL_COMBAT_EVIDENCE_BIT_SELF_AIRBORNE_STARTED 15u
#define RL_COMBAT_EVIDENCE_BIT_OPP_AIRBORNE_STARTED 16u
#define RL_COMBAT_EVIDENCE_BIT_SELF_ENTERED_HIT_STOP 17u
#define RL_COMBAT_EVIDENCE_BIT_OPP_ENTERED_HIT_STOP 18u
#define RL_COMBAT_EVIDENCE_BIT_SELF_ENTERED_CONTACT_STATE 19u
#define RL_COMBAT_EVIDENCE_BIT_OPP_ENTERED_CONTACT_STATE 20u
#define RL_COMBAT_EVIDENCE_BIT_SELF_ENTERED_DAMAGE_STATE 21u
#define RL_COMBAT_EVIDENCE_BIT_OPP_ENTERED_DAMAGE_STATE 22u
#define RL_COMBAT_EVIDENCE_BIT_SELF_THROW_STARTED 23u
#define RL_COMBAT_EVIDENCE_BIT_OPP_THROW_CAUGHT_STARTED 24u

#define RL_COMBAT_EVIDENCE_V1_USED_LO_MASK 0x01ffffffu
#define RL_COMBAT_EVIDENCE_V1_USED_HI_MASK 0x00000000u

#define RL_COMBAT_EVENT_ID_NONE 0ull
#define RL_COMBAT_ATTACK_EVENT_RING_CAP 32u
#define RL_COMBAT_ATTACK_MIN_WHIFF_FRAMES 12u
#define RL_COMBAT_ATTACK_MAX_PENDING_FRAMES 96u
#define RL_COMBAT_ATTACK_PROJECTILE_MAX_PENDING_FRAMES 180u

typedef enum RLCombatEventSide {
    RL_COMBAT_EVENT_SIDE_NONE = 0,
    RL_COMBAT_EVENT_SIDE_SELF = 1,
    RL_COMBAT_EVENT_SIDE_OPPONENT = 2,
} RLCombatEventSide;

typedef enum RLCombatAttackEventStatus {
    RL_COMBAT_ATTACK_EVENT_EMPTY = 0,
    RL_COMBAT_ATTACK_EVENT_ACTIVE = 1,
    RL_COMBAT_ATTACK_EVENT_FINALIZED = 2,
} RLCombatAttackEventStatus;

typedef enum RLCombatAttackEventResult {
    RL_COMBAT_ATTACK_RESULT_PENDING = 0,
    RL_COMBAT_ATTACK_RESULT_WHIFF = 1,
    RL_COMBAT_ATTACK_RESULT_INTERRUPTED = 2,
    RL_COMBAT_ATTACK_RESULT_UNKNOWN = 3,
} RLCombatAttackEventResult;

typedef enum RLCombatAttackFinalizeReason {
    RL_COMBAT_ATTACK_FINALIZE_NONE = 0,
    RL_COMBAT_ATTACK_FINALIZE_EXPLICIT = 1,
    RL_COMBAT_ATTACK_FINALIZE_EPISODE_FLUSH = 2,
    RL_COMBAT_ATTACK_FINALIZE_SUPERSEDED_BY_NEW_START = 3,
    RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW = 4,
    RL_COMBAT_ATTACK_FINALIZE_BASIC_INTERRUPTED = 5,
    RL_COMBAT_ATTACK_FINALIZE_BASIC_UNKNOWN_TIMEOUT = 6,
} RLCombatAttackFinalizeReason;

typedef struct RLCombatAttackEventStart {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide side;
    u8 character_id;
    u16 routine_1;
    u16 routine_2;
    u16 current_attack;
    u8 kind_of_waza;
    u8 projectile_like;
    u16 policy_action_id;
    u16 policy_sub_action_id;
    u16 policy_action_step;
} RLCombatAttackEventStart;

typedef struct RLCombatAttackEvent {
    RLCombatAttackEventStatus status;
    RLCombatAttackEventResult result;
    RLCombatAttackFinalizeReason finalize_reason;
    u64 event_id;
    u64 run_id;
    u32 episode_id;
    u32 start_decision_id;
    u32 start_frame;
    u32 end_decision_id;
    u32 end_frame;
    RLCombatEventSide side;
    u8 character_id;
    u16 routine_1;
    u16 routine_2;
    u16 current_attack;
    u8 kind_of_waza;
    u8 projectile_like;
    u8 saw_actor_attack_state_active;
    u8 saw_target_contact_or_damage;
    u8 saw_projectile;
    u8 saw_throw;
    u16 policy_action_id;
    u16 policy_sub_action_id;
    u16 policy_action_step;
} RLCombatAttackEvent;

typedef struct RLCombatAttackEventUpdate {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide side;
    u8 actor_attack_state_active;
    u8 actor_interrupted;
    u8 target_contact_or_damage;
    u8 projectile_active_for_side;
    u8 throw_active_for_side;
} RLCombatAttackEventUpdate;

typedef struct RLCombatEventStats {
    u64 run_id;
    u32 episode_id;
    u64 next_event_id;
    u32 attack_started_count;
    u32 attack_finalized_count;
    u32 attack_unknown_flush_count;
    u32 attack_unknown_rollover_count;
    u32 attack_whiff_count;
    u32 attack_interrupted_count;
    u32 attack_unknown_timeout_count;
    u32 attack_dropped_start_count;
    u32 attack_active_self_count;
    u32 attack_active_opponent_count;
    u32 episode_flush_count;
    u32 episode_switch_flush_count;
} RLCombatEventStats;

void RLCombatEvent_ResetRun(u64 run_id);
void RLCombatEvent_BeginEpisode(u64 run_id, u32 episode_id);
void RLCombatEvent_FlushEpisode(u64 run_id, u32 episode_id, u32 frame_id, u32 decision_id);
const RLCombatAttackEvent* RLCombatEvent_StartAttack(const RLCombatAttackEventStart* start);
bool RLCombatEvent_FinalizeAttack(u64 event_id,
                                  RLCombatAttackEventResult result,
                                  RLCombatAttackFinalizeReason reason,
                                  u32 frame_id,
                                  u32 decision_id);
u32 RLCombatEvent_FinalizeActiveSide(u64 run_id,
                                     u32 episode_id,
                                     RLCombatEventSide side,
                                     RLCombatAttackEventResult result,
                                     RLCombatAttackFinalizeReason reason,
                                     u32 frame_id,
                                     u32 decision_id);
u32 RLCombatEvent_UpdateActiveAttacks(const RLCombatAttackEventUpdate* update);
const RLCombatAttackEvent* RLCombatEvent_FindAttack(u64 event_id);
const RLCombatEventStats* RLCombatEvent_GetStats(void);

#endif
