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
#define RL_COMBAT_PROJECTILE_EVENT_RING_CAP 16u
#define RL_COMBAT_THROW_EVENT_RING_CAP 16u
#define RL_COMBAT_ATTACK_MIN_WHIFF_FRAMES 12u
#define RL_COMBAT_ATTACK_FAST_WHIFF_FALLBACK_FRAMES 20u
#define RL_COMBAT_ATTACK_MAX_PENDING_FRAMES 96u
#define RL_COMBAT_ATTACK_PROJECTILE_MAX_PENDING_FRAMES 180u
#define RL_COMBAT_PROJECTILE_MAX_PENDING_FRAMES 240u
#define RL_COMBAT_PROJECTILE_MISSING_FINALIZE_FRAMES 2u
#define RL_COMBAT_THROW_MIN_WHIFF_FRAMES 8u
#define RL_COMBAT_THROW_SUCCESS_CONFIRM_FRAMES 8u
#define RL_COMBAT_THROW_MAX_PENDING_FRAMES 45u

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
    RL_COMBAT_ATTACK_FINALIZE_PROJECTILE_CLAIMED = 7,
} RLCombatAttackFinalizeReason;

typedef enum RLCombatProjectileEventStatus {
    RL_COMBAT_PROJECTILE_EVENT_EMPTY = 0,
    RL_COMBAT_PROJECTILE_EVENT_ACTIVE = 1,
    RL_COMBAT_PROJECTILE_EVENT_FINALIZED = 2,
} RLCombatProjectileEventStatus;

typedef enum RLCombatProjectileResult {
    RL_COMBAT_PROJECTILE_RESULT_PENDING = 0,
    RL_COMBAT_PROJECTILE_RESULT_HIT = 1,
    RL_COMBAT_PROJECTILE_RESULT_BLOCKED = 2,
    RL_COMBAT_PROJECTILE_RESULT_EXPIRED = 3,
    RL_COMBAT_PROJECTILE_RESULT_UNKNOWN = 4,
} RLCombatProjectileResult;

typedef enum RLCombatProjectileFinalizeReason {
    RL_COMBAT_PROJECTILE_FINALIZE_NONE = 0,
    RL_COMBAT_PROJECTILE_FINALIZE_EPISODE_FLUSH = 1,
    RL_COMBAT_PROJECTILE_FINALIZE_DISAPPEARED = 2,
    RL_COMBAT_PROJECTILE_FINALIZE_CONTACT = 3,
    RL_COMBAT_PROJECTILE_FINALIZE_TIMEOUT = 4,
} RLCombatProjectileFinalizeReason;

typedef enum RLCombatThrowEventStatus {
    RL_COMBAT_THROW_EVENT_EMPTY = 0,
    RL_COMBAT_THROW_EVENT_ACTIVE = 1,
    RL_COMBAT_THROW_EVENT_FINALIZED = 2,
} RLCombatThrowEventStatus;

typedef enum RLCombatThrowResult {
    RL_COMBAT_THROW_RESULT_PENDING = 0,
    RL_COMBAT_THROW_RESULT_SUCCESS = 1,
    RL_COMBAT_THROW_RESULT_WHIFF = 2,
    RL_COMBAT_THROW_RESULT_UNKNOWN = 3,
} RLCombatThrowResult;

typedef enum RLCombatThrowFinalizeReason {
    RL_COMBAT_THROW_FINALIZE_NONE = 0,
    RL_COMBAT_THROW_FINALIZE_EPISODE_FLUSH = 1,
    RL_COMBAT_THROW_FINALIZE_SUPERSEDED_BY_NEW_START = 2,
    RL_COMBAT_THROW_FINALIZE_TARGET_CAUGHT = 3,
    RL_COMBAT_THROW_FINALIZE_WHIFF_WINDOW = 4,
    RL_COMBAT_THROW_FINALIZE_UNKNOWN_TIMEOUT = 5,
    RL_COMBAT_THROW_FINALIZE_TECH_ESCAPE = 6,
} RLCombatThrowFinalizeReason;

typedef enum RLCombatContactMatchSource {
    RL_COMBAT_CONTACT_MATCH_SOURCE_NONE = 0,
    RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK = 1,
    RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE = 2,
    RL_COMBAT_CONTACT_MATCH_SOURCE_THROW = 3,
    RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN = 4,
} RLCombatContactMatchSource;

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
    u8 fast_whiff_fallback;
    u16 engine_action_id;
    u16 engine_sub_action_id;
    u16 engine_routine_1;
    u16 engine_routine_2;
    u16 engine_current_attack;
    u16 engine_lag_frames;
    u8 engine_kind_of_waza;
    u8 engine_label_source;
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
    u8 whiff_eligible;
    u8 fast_whiff_fallback;
    u16 engine_action_id;
    u16 engine_sub_action_id;
    u16 engine_routine_1;
    u16 engine_routine_2;
    u16 engine_current_attack;
    u16 engine_lag_frames;
    u8 engine_kind_of_waza;
    u8 engine_label_source;
    u8 saw_target_contact_or_damage;
    u8 saw_target_hit_stop;
    u8 saw_target_contact_state;
    u8 saw_target_damage_state;
    u8 saw_target_hp_delta;
    u8 saw_target_stun_delta;
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
    u8 target_entered_hit_stop;
    u8 target_entered_contact_state;
    u8 target_entered_damage_state;
    u8 target_hp_delta;
    u8 target_stun_delta;
    u8 projectile_active_for_side;
    u8 throw_active_for_side;
} RLCombatAttackEventUpdate;

typedef struct RLCombatProjectileEventUpdate {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide owner_side;
    u8 any_projectile_active;
    u8 projectile_active_for_side;
    s16 projectile_rel_x;
    s16 projectile_rel_y;
    s16 projectile_vel_x;
    s16 projectile_time_to_self;
    u8 target_guard;
    u8 target_block_reaction;
    u8 target_contact_or_damage;
    u8 target_entered_hit_stop;
    u8 target_entered_contact_state;
    u8 target_entered_damage_state;
    u8 target_hp_delta;
    u8 target_stun_delta;
} RLCombatProjectileEventUpdate;

typedef struct RLCombatProjectileEvent {
    RLCombatProjectileEventStatus status;
    RLCombatProjectileResult result;
    RLCombatProjectileFinalizeReason finalize_reason;
    u64 event_id;
    u64 parent_attack_event_id;
    u64 run_id;
    u32 episode_id;
    u32 start_decision_id;
    u32 start_frame;
    u32 end_decision_id;
    u32 end_frame;
    RLCombatEventSide owner_side;
    s16 spawn_rel_x;
    s16 spawn_rel_y;
    s16 spawn_vel_x;
    s16 spawn_time_to_self;
    s16 last_rel_x;
    s16 last_rel_y;
    s16 last_vel_x;
    s16 last_time_to_self;
    u16 engine_action_id;
    u16 engine_sub_action_id;
    u8 engine_label_source;
    u8 missing_frames;
    u8 saw_target_guard;
    u8 saw_target_block_reaction;
    u8 saw_target_contact_or_damage;
    u8 saw_target_hit_stop;
    u8 saw_target_contact_state;
    u8 saw_target_damage_state;
    u8 saw_target_hp_delta;
    u8 saw_target_stun_delta;
} RLCombatProjectileEvent;

typedef struct RLCombatThrowEventStart {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide owner_side;
    u8 character_id;
    u16 routine_1;
    u16 routine_2;
    u16 current_attack;
    u8 kind_of_waza;
} RLCombatThrowEventStart;

typedef struct RLCombatThrowEventUpdate {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide owner_side;
    u8 owner_throw_active;
    u8 opposing_throw_active;
    u8 opposing_throw_started;
    u8 throw_escape;
    u8 throw_escape_started;
    u8 target_caught;
    u8 target_caught_started;
    u8 actor_interrupted;
    u8 target_contact_or_damage;
    u8 target_entered_hit_stop;
    u8 target_entered_contact_state;
    u8 target_entered_damage_state;
    u8 target_hp_delta;
    u8 target_stun_delta;
} RLCombatThrowEventUpdate;

typedef struct RLCombatThrowEvent {
    RLCombatThrowEventStatus status;
    RLCombatThrowResult result;
    RLCombatThrowFinalizeReason finalize_reason;
    u64 event_id;
    u64 run_id;
    u32 episode_id;
    u32 start_decision_id;
    u32 start_frame;
    u32 end_decision_id;
    u32 end_frame;
    RLCombatEventSide owner_side;
    u8 character_id;
    u16 routine_1;
    u16 routine_2;
    u16 current_attack;
    u8 kind_of_waza;
    u8 saw_owner_throw_active;
    u8 saw_opposing_throw;
    u8 saw_throw_escape;
    u8 saw_target_caught;
    u8 saw_target_caught_started;
    u8 saw_actor_interrupted;
    u8 saw_target_contact_or_damage;
    u8 saw_target_hit_stop;
    u8 saw_target_contact_state;
    u8 saw_target_damage_state;
    u8 saw_target_hp_delta;
    u8 saw_target_stun_delta;
    u8 contact_match_recorded;
} RLCombatThrowEvent;

typedef struct RLCombatContactMatchUpdate {
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 frame_id;
    RLCombatEventSide source_side;
    u8 target_entered_hit_stop;
    u8 target_entered_contact_state;
    u8 target_entered_damage_state;
    u8 target_hp_delta;
    u8 target_stun_delta;
    u8 target_throw_caught;
    u8 attack_candidate;
    u8 projectile_candidate;
    u8 throw_candidate;
} RLCombatContactMatchUpdate;

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
    u32 attack_started_self_count;
    u32 attack_started_opponent_count;
    u32 attack_finalized_self_count;
    u32 attack_finalized_opponent_count;
    u32 attack_whiff_self_count;
    u32 attack_whiff_opponent_count;
    u32 attack_interrupted_self_count;
    u32 attack_interrupted_opponent_count;
    u32 attack_unknown_timeout_self_count;
    u32 attack_unknown_timeout_opponent_count;
    u32 attack_unknown_flush_self_count;
    u32 attack_unknown_flush_opponent_count;
    u32 attack_unknown_rollover_self_count;
    u32 attack_unknown_rollover_opponent_count;
    u32 attack_dropped_start_self_count;
    u32 attack_dropped_start_opponent_count;
    u32 attack_unknown_timeout_contact_self_count;
    u32 attack_unknown_timeout_contact_opponent_count;
    u32 attack_unknown_timeout_contact_hit_stop_self_count;
    u32 attack_unknown_timeout_contact_hit_stop_opponent_count;
    u32 attack_unknown_timeout_contact_state_self_count;
    u32 attack_unknown_timeout_contact_state_opponent_count;
    u32 attack_unknown_timeout_damage_state_self_count;
    u32 attack_unknown_timeout_damage_state_opponent_count;
    u32 attack_unknown_timeout_hp_delta_self_count;
    u32 attack_unknown_timeout_hp_delta_opponent_count;
    u32 attack_unknown_timeout_stun_delta_self_count;
    u32 attack_unknown_timeout_stun_delta_opponent_count;
    u32 attack_unknown_timeout_projectile_self_count;
    u32 attack_unknown_timeout_projectile_opponent_count;
    u32 attack_unknown_timeout_throw_self_count;
    u32 attack_unknown_timeout_throw_opponent_count;
    u32 attack_unknown_timeout_projectile_like_self_count;
    u32 attack_unknown_timeout_projectile_like_opponent_count;
    u32 attack_unknown_timeout_not_whiff_self_count;
    u32 attack_unknown_timeout_not_whiff_opponent_count;
    u32 attack_active_self_count;
    u32 attack_active_opponent_count;
    u32 projectile_started_count;
    u32 projectile_finalized_count;
    u32 projectile_hit_count;
    u32 projectile_blocked_count;
    u32 projectile_expired_count;
    u32 projectile_unknown_count;
    u32 projectile_dropped_start_count;
    u32 projectile_started_self_count;
    u32 projectile_started_opponent_count;
    u32 projectile_finalized_self_count;
    u32 projectile_finalized_opponent_count;
    u32 projectile_hit_self_count;
    u32 projectile_hit_opponent_count;
    u32 projectile_blocked_self_count;
    u32 projectile_blocked_opponent_count;
    u32 projectile_expired_self_count;
    u32 projectile_expired_opponent_count;
    u32 projectile_unknown_self_count;
    u32 projectile_unknown_opponent_count;
    u32 projectile_dropped_start_self_count;
    u32 projectile_dropped_start_opponent_count;
    u32 projectile_active_self_count;
    u32 projectile_active_opponent_count;
    u32 throw_started_count;
    u32 throw_finalized_count;
    u32 throw_success_count;
    u32 throw_whiff_count;
    u32 throw_unknown_count;
    u32 throw_dropped_start_count;
    u32 throw_started_self_count;
    u32 throw_started_opponent_count;
    u32 throw_finalized_self_count;
    u32 throw_finalized_opponent_count;
    u32 throw_success_self_count;
    u32 throw_success_opponent_count;
    u32 throw_whiff_self_count;
    u32 throw_whiff_opponent_count;
    u32 throw_unknown_self_count;
    u32 throw_unknown_opponent_count;
    u32 throw_dropped_start_self_count;
    u32 throw_dropped_start_opponent_count;
    u32 throw_active_self_count;
    u32 throw_active_opponent_count;
    u32 contact_match_total_count;
    u32 contact_match_attack_self_count;
    u32 contact_match_attack_opponent_count;
    u32 contact_match_projectile_self_count;
    u32 contact_match_projectile_opponent_count;
    u32 contact_match_throw_self_count;
    u32 contact_match_throw_opponent_count;
    u32 contact_match_unknown_self_count;
    u32 contact_match_unknown_opponent_count;
    u32 episode_flush_count;
    u32 episode_switch_flush_count;
    u32 lifetime_attack_started_count;
    u32 lifetime_attack_finalized_count;
    u32 lifetime_attack_unknown_flush_count;
    u32 lifetime_attack_unknown_rollover_count;
    u32 lifetime_attack_whiff_count;
    u32 lifetime_attack_interrupted_count;
    u32 lifetime_attack_unknown_timeout_count;
    u32 lifetime_attack_dropped_start_count;
    u32 lifetime_projectile_started_count;
    u32 lifetime_projectile_finalized_count;
    u32 lifetime_projectile_hit_count;
    u32 lifetime_projectile_blocked_count;
    u32 lifetime_projectile_expired_count;
    u32 lifetime_projectile_unknown_count;
    u32 lifetime_projectile_dropped_start_count;
    u32 lifetime_throw_started_count;
    u32 lifetime_throw_finalized_count;
    u32 lifetime_throw_success_count;
    u32 lifetime_throw_whiff_count;
    u32 lifetime_throw_unknown_count;
    u32 lifetime_throw_dropped_start_count;
    u32 lifetime_episode_flush_count;
    u32 lifetime_episode_switch_flush_count;
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
u32 RLCombatEvent_UpdateProjectiles(const RLCombatProjectileEventUpdate* update);
const RLCombatThrowEvent* RLCombatEvent_StartThrow(const RLCombatThrowEventStart* start);
u32 RLCombatEvent_UpdateThrows(const RLCombatThrowEventUpdate* update);
bool RLCombatEvent_RecordContactMatch(const RLCombatContactMatchUpdate* update);
bool RLCombatEvent_HasActiveThrowForSide(u64 run_id, u32 episode_id, RLCombatEventSide side);
bool RLCombatEvent_HasRecentNonWhiffThrowForSide(u64 run_id,
                                                 u32 episode_id,
                                                 RLCombatEventSide side,
                                                 u32 frame_id,
                                                 u32 max_age_frames);
const RLCombatAttackEvent* RLCombatEvent_FindAttack(u64 event_id);
const RLCombatProjectileEvent* RLCombatEvent_FindProjectile(u64 event_id);
const RLCombatThrowEvent* RLCombatEvent_FindThrow(u64 event_id);
const RLCombatEventStats* RLCombatEvent_GetStats(void);

#endif
