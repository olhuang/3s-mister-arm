#include "rl/rl_combat_event.h"

#include <string.h>

typedef struct RLCombatAttackEventRing {
    RLCombatAttackEvent events[RL_COMBAT_ATTACK_EVENT_RING_CAP];
    u32 cursor;
} RLCombatAttackEventRing;

static RLCombatAttackEventRing self_attack_ring;
static RLCombatAttackEventRing opponent_attack_ring;
static RLCombatEventStats combat_event_stats;

static bool RLCombatEvent_IsCleanBasicWhiff(const RLCombatAttackEvent* event);
static bool RLCombatEvent_IsCleanFastWhiff(const RLCombatAttackEvent* event);

static RLCombatAttackEventRing* RLCombatEvent_RingForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_attack_ring;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_attack_ring;
    case RL_COMBAT_EVENT_SIDE_NONE:
    default:
        return NULL;
    }
}

static const RLCombatAttackEventRing* RLCombatEvent_ConstRingForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_attack_ring;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_attack_ring;
    case RL_COMBAT_EVENT_SIDE_NONE:
    default:
        return NULL;
    }
}

static u32 RLCombatEvent_CountActive(const RLCombatAttackEventRing* ring) {
    u32 count = 0;

    if (ring == NULL) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        if (ring->events[i].status == RL_COMBAT_ATTACK_EVENT_ACTIVE) {
            count++;
        }
    }

    return count;
}

static void RLCombatEvent_RefreshActiveStats(void) {
    combat_event_stats.attack_active_self_count = RLCombatEvent_CountActive(&self_attack_ring);
    combat_event_stats.attack_active_opponent_count = RLCombatEvent_CountActive(&opponent_attack_ring);
}

static void RLCombatEvent_IncrementSideCounter(RLCombatEventSide side, u32* self_count, u32* opponent_count) {
    if (side == RL_COMBAT_EVENT_SIDE_SELF && self_count != NULL) {
        (*self_count)++;
    } else if (side == RL_COMBAT_EVENT_SIDE_OPPONENT && opponent_count != NULL) {
        (*opponent_count)++;
    }
}

static void RLCombatEvent_RecordTimeoutUnknownCauses(const RLCombatAttackEvent* event) {
    if (event == NULL) {
        return;
    }
    if (event->saw_target_contact_or_damage) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_contact_self_count,
                                           &combat_event_stats.attack_unknown_timeout_contact_opponent_count);
    }
    if (event->saw_target_hit_stop) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_contact_hit_stop_self_count,
                                           &combat_event_stats.attack_unknown_timeout_contact_hit_stop_opponent_count);
    }
    if (event->saw_target_contact_state) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_contact_state_self_count,
                                           &combat_event_stats.attack_unknown_timeout_contact_state_opponent_count);
    }
    if (event->saw_target_damage_state) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_damage_state_self_count,
                                           &combat_event_stats.attack_unknown_timeout_damage_state_opponent_count);
    }
    if (event->saw_target_hp_delta) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_hp_delta_self_count,
                                           &combat_event_stats.attack_unknown_timeout_hp_delta_opponent_count);
    }
    if (event->saw_target_stun_delta) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_stun_delta_self_count,
                                           &combat_event_stats.attack_unknown_timeout_stun_delta_opponent_count);
    }
    if (event->saw_projectile) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_projectile_self_count,
                                           &combat_event_stats.attack_unknown_timeout_projectile_opponent_count);
    }
    if (event->saw_throw) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_throw_self_count,
                                           &combat_event_stats.attack_unknown_timeout_throw_opponent_count);
    }
    if (event->projectile_like) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_projectile_like_self_count,
                                           &combat_event_stats.attack_unknown_timeout_projectile_like_opponent_count);
    }
    if (!event->whiff_eligible) {
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_not_whiff_self_count,
                                           &combat_event_stats.attack_unknown_timeout_not_whiff_opponent_count);
    }
}

static void RLCombatEvent_ResetEpisodeStats(void) {
    combat_event_stats.attack_started_count = 0;
    combat_event_stats.attack_finalized_count = 0;
    combat_event_stats.attack_unknown_flush_count = 0;
    combat_event_stats.attack_unknown_rollover_count = 0;
    combat_event_stats.attack_whiff_count = 0;
    combat_event_stats.attack_interrupted_count = 0;
    combat_event_stats.attack_unknown_timeout_count = 0;
    combat_event_stats.attack_dropped_start_count = 0;
    combat_event_stats.attack_started_self_count = 0;
    combat_event_stats.attack_started_opponent_count = 0;
    combat_event_stats.attack_finalized_self_count = 0;
    combat_event_stats.attack_finalized_opponent_count = 0;
    combat_event_stats.attack_whiff_self_count = 0;
    combat_event_stats.attack_whiff_opponent_count = 0;
    combat_event_stats.attack_interrupted_self_count = 0;
    combat_event_stats.attack_interrupted_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_self_count = 0;
    combat_event_stats.attack_unknown_timeout_opponent_count = 0;
    combat_event_stats.attack_unknown_flush_self_count = 0;
    combat_event_stats.attack_unknown_flush_opponent_count = 0;
    combat_event_stats.attack_unknown_rollover_self_count = 0;
    combat_event_stats.attack_unknown_rollover_opponent_count = 0;
    combat_event_stats.attack_dropped_start_self_count = 0;
    combat_event_stats.attack_dropped_start_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_self_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_hit_stop_self_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_hit_stop_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_state_self_count = 0;
    combat_event_stats.attack_unknown_timeout_contact_state_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_damage_state_self_count = 0;
    combat_event_stats.attack_unknown_timeout_damage_state_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_hp_delta_self_count = 0;
    combat_event_stats.attack_unknown_timeout_hp_delta_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_stun_delta_self_count = 0;
    combat_event_stats.attack_unknown_timeout_stun_delta_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_projectile_self_count = 0;
    combat_event_stats.attack_unknown_timeout_projectile_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_throw_self_count = 0;
    combat_event_stats.attack_unknown_timeout_throw_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_projectile_like_self_count = 0;
    combat_event_stats.attack_unknown_timeout_projectile_like_opponent_count = 0;
    combat_event_stats.attack_unknown_timeout_not_whiff_self_count = 0;
    combat_event_stats.attack_unknown_timeout_not_whiff_opponent_count = 0;
    combat_event_stats.attack_active_self_count = 0;
    combat_event_stats.attack_active_opponent_count = 0;
    combat_event_stats.episode_flush_count = 0;
    combat_event_stats.episode_switch_flush_count = 0;
}

static u64 RLCombatEvent_AllocateEventId(void) {
    u64 event_id = combat_event_stats.next_event_id;

    if (event_id == RL_COMBAT_EVENT_ID_NONE) {
        event_id = 1;
    }

    combat_event_stats.next_event_id = event_id + 1;
    if (combat_event_stats.next_event_id == RL_COMBAT_EVENT_ID_NONE) {
        combat_event_stats.next_event_id = 1;
    }

    return event_id;
}

static RLCombatAttackEvent* RLCombatEvent_FindReusableSlot(RLCombatAttackEventRing* ring) {
    if (ring == NULL) {
        return NULL;
    }

    for (u32 scanned = 0; scanned < RL_COMBAT_ATTACK_EVENT_RING_CAP; scanned++) {
        const u32 index = (ring->cursor + scanned) % RL_COMBAT_ATTACK_EVENT_RING_CAP;
        RLCombatAttackEvent* event = &ring->events[index];
        if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE) {
            ring->cursor = (index + 1u) % RL_COMBAT_ATTACK_EVENT_RING_CAP;
            return event;
        }
    }

    return NULL;
}

static bool RLCombatEvent_FinalizeSlot(RLCombatAttackEvent* event,
                                       RLCombatAttackEventResult result,
                                       RLCombatAttackFinalizeReason reason,
                                       u32 frame_id,
                                       u32 decision_id) {
    if (event == NULL || event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE) {
        return false;
    }

    event->status = RL_COMBAT_ATTACK_EVENT_FINALIZED;
    event->result = result;
    event->finalize_reason = reason;
    event->end_frame = frame_id;
    event->end_decision_id = decision_id;
    combat_event_stats.attack_finalized_count++;
    combat_event_stats.lifetime_attack_finalized_count++;
    RLCombatEvent_IncrementSideCounter(event->side,
                                       &combat_event_stats.attack_finalized_self_count,
                                       &combat_event_stats.attack_finalized_opponent_count);
    if (reason == RL_COMBAT_ATTACK_FINALIZE_EPISODE_FLUSH && result == RL_COMBAT_ATTACK_RESULT_UNKNOWN) {
        combat_event_stats.attack_unknown_flush_count++;
        combat_event_stats.lifetime_attack_unknown_flush_count++;
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_flush_self_count,
                                           &combat_event_stats.attack_unknown_flush_opponent_count);
    }
    if (reason == RL_COMBAT_ATTACK_FINALIZE_SUPERSEDED_BY_NEW_START &&
        result == RL_COMBAT_ATTACK_RESULT_UNKNOWN) {
        combat_event_stats.attack_unknown_rollover_count++;
        combat_event_stats.lifetime_attack_unknown_rollover_count++;
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_rollover_self_count,
                                           &combat_event_stats.attack_unknown_rollover_opponent_count);
    }
    if (reason == RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW && result == RL_COMBAT_ATTACK_RESULT_WHIFF) {
        combat_event_stats.attack_whiff_count++;
        combat_event_stats.lifetime_attack_whiff_count++;
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_whiff_self_count,
                                           &combat_event_stats.attack_whiff_opponent_count);
    }
    if (reason == RL_COMBAT_ATTACK_FINALIZE_BASIC_INTERRUPTED &&
        result == RL_COMBAT_ATTACK_RESULT_INTERRUPTED) {
        combat_event_stats.attack_interrupted_count++;
        combat_event_stats.lifetime_attack_interrupted_count++;
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_interrupted_self_count,
                                           &combat_event_stats.attack_interrupted_opponent_count);
    }
    if (reason == RL_COMBAT_ATTACK_FINALIZE_BASIC_UNKNOWN_TIMEOUT && result == RL_COMBAT_ATTACK_RESULT_UNKNOWN) {
        combat_event_stats.attack_unknown_timeout_count++;
        combat_event_stats.lifetime_attack_unknown_timeout_count++;
        RLCombatEvent_IncrementSideCounter(event->side,
                                           &combat_event_stats.attack_unknown_timeout_self_count,
                                           &combat_event_stats.attack_unknown_timeout_opponent_count);
        RLCombatEvent_RecordTimeoutUnknownCauses(event);
    }
    RLCombatEvent_RefreshActiveStats();
    return true;
}

static void RLCombatEvent_ClearRings(void) {
    memset(&self_attack_ring, 0, sizeof(self_attack_ring));
    memset(&opponent_attack_ring, 0, sizeof(opponent_attack_ring));
    RLCombatEvent_RefreshActiveStats();
}

void RLCombatEvent_ResetRun(u64 run_id) {
    memset(&combat_event_stats, 0, sizeof(combat_event_stats));
    combat_event_stats.run_id = run_id;
    combat_event_stats.next_event_id = 1;
    RLCombatEvent_ClearRings();
}

void RLCombatEvent_BeginEpisode(u64 run_id, u32 episode_id) {
    if (combat_event_stats.run_id != 0 && combat_event_stats.episode_id != 0 &&
        (combat_event_stats.run_id != run_id || combat_event_stats.episode_id != episode_id)) {
        RLCombatEvent_FlushEpisode(combat_event_stats.run_id, combat_event_stats.episode_id, 0, 0);
        combat_event_stats.episode_switch_flush_count++;
        combat_event_stats.lifetime_episode_switch_flush_count++;
    }

    if (combat_event_stats.run_id != run_id) {
        RLCombatEvent_ResetRun(run_id);
    }

    combat_event_stats.run_id = run_id;
    combat_event_stats.episode_id = episode_id;
    RLCombatEvent_ResetEpisodeStats();
    RLCombatEvent_ClearRings();
}

void RLCombatEvent_FlushEpisode(u64 run_id, u32 episode_id, u32 frame_id, u32 decision_id) {
    RLCombatAttackEventRing* rings[] = { &self_attack_ring, &opponent_attack_ring };

    combat_event_stats.episode_flush_count++;
    combat_event_stats.lifetime_episode_flush_count++;
    for (u32 r = 0; r < 2u; r++) {
        RLCombatAttackEventRing* ring = rings[r];
        for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
            RLCombatAttackEvent* event = &ring->events[i];
            if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || event->run_id != run_id ||
                event->episode_id != episode_id) {
                continue;
            }
            RLCombatEvent_FinalizeSlot(event,
                                       RL_COMBAT_ATTACK_RESULT_UNKNOWN,
                                       RL_COMBAT_ATTACK_FINALIZE_EPISODE_FLUSH,
                                       frame_id,
                                       decision_id);
        }
    }
    RLCombatEvent_RefreshActiveStats();
}

const RLCombatAttackEvent* RLCombatEvent_StartAttack(const RLCombatAttackEventStart* start) {
    RLCombatAttackEventRing* ring = NULL;
    RLCombatAttackEvent* event = NULL;

    if (start == NULL || start->run_id == 0 || start->episode_id == 0 ||
        start->side == RL_COMBAT_EVENT_SIDE_NONE) {
        combat_event_stats.attack_dropped_start_count++;
        combat_event_stats.lifetime_attack_dropped_start_count++;
        if (start != NULL) {
            RLCombatEvent_IncrementSideCounter(start->side,
                                               &combat_event_stats.attack_dropped_start_self_count,
                                               &combat_event_stats.attack_dropped_start_opponent_count);
        }
        return NULL;
    }

    if (combat_event_stats.run_id != start->run_id || combat_event_stats.episode_id != start->episode_id) {
        RLCombatEvent_BeginEpisode(start->run_id, start->episode_id);
    }

    ring = RLCombatEvent_RingForSide(start->side);
    event = RLCombatEvent_FindReusableSlot(ring);
    if (event == NULL) {
        combat_event_stats.attack_dropped_start_count++;
        combat_event_stats.lifetime_attack_dropped_start_count++;
        RLCombatEvent_IncrementSideCounter(start->side,
                                           &combat_event_stats.attack_dropped_start_self_count,
                                           &combat_event_stats.attack_dropped_start_opponent_count);
        RLCombatEvent_RefreshActiveStats();
        return NULL;
    }

    memset(event, 0, sizeof(*event));
    event->status = RL_COMBAT_ATTACK_EVENT_ACTIVE;
    event->result = RL_COMBAT_ATTACK_RESULT_PENDING;
    event->event_id = RLCombatEvent_AllocateEventId();
    event->run_id = start->run_id;
    event->episode_id = start->episode_id;
    event->start_decision_id = start->decision_id;
    event->start_frame = start->frame_id;
    event->side = start->side;
    event->character_id = start->character_id;
    event->routine_1 = start->routine_1;
    event->routine_2 = start->routine_2;
    event->current_attack = start->current_attack;
    event->kind_of_waza = start->kind_of_waza;
    event->projectile_like = start->projectile_like;
    event->fast_whiff_fallback = start->fast_whiff_fallback;
    event->whiff_eligible = 1;
    event->policy_action_id = start->policy_action_id;
    event->policy_sub_action_id = start->policy_sub_action_id;
    event->policy_action_step = start->policy_action_step;

    combat_event_stats.attack_started_count++;
    combat_event_stats.lifetime_attack_started_count++;
    RLCombatEvent_IncrementSideCounter(event->side,
                                       &combat_event_stats.attack_started_self_count,
                                       &combat_event_stats.attack_started_opponent_count);
    RLCombatEvent_RefreshActiveStats();
    return event;
}

bool RLCombatEvent_FinalizeAttack(u64 event_id,
                                  RLCombatAttackEventResult result,
                                  RLCombatAttackFinalizeReason reason,
                                  u32 frame_id,
                                  u32 decision_id) {
    RLCombatAttackEventRing* rings[] = { &self_attack_ring, &opponent_attack_ring };

    if (event_id == RL_COMBAT_EVENT_ID_NONE || result == RL_COMBAT_ATTACK_RESULT_PENDING) {
        return false;
    }

    for (u32 r = 0; r < 2u; r++) {
        RLCombatAttackEventRing* ring = rings[r];
        for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
            RLCombatAttackEvent* event = &ring->events[i];
            if (event->status == RL_COMBAT_ATTACK_EVENT_ACTIVE && event->event_id == event_id) {
                return RLCombatEvent_FinalizeSlot(event, result, reason, frame_id, decision_id);
            }
        }
    }

    return false;
}

u32 RLCombatEvent_FinalizeActiveSide(u64 run_id,
                                     u32 episode_id,
                                     RLCombatEventSide side,
                                     RLCombatAttackEventResult result,
                                     RLCombatAttackFinalizeReason reason,
                                     u32 frame_id,
                                     u32 decision_id) {
    RLCombatAttackEventRing* ring = RLCombatEvent_RingForSide(side);
    u32 finalized = 0;

    if (ring == NULL || run_id == 0 || episode_id == 0 || result == RL_COMBAT_ATTACK_RESULT_PENDING) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        RLCombatAttackEvent* event = &ring->events[i];
        RLCombatAttackEventResult event_result = result;
        RLCombatAttackFinalizeReason event_reason = reason;
        if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || event->run_id != run_id ||
            event->episode_id != episode_id || event->side != side) {
            continue;
        }
        if (reason == RL_COMBAT_ATTACK_FINALIZE_SUPERSEDED_BY_NEW_START &&
            result == RL_COMBAT_ATTACK_RESULT_UNKNOWN &&
            (RLCombatEvent_IsCleanBasicWhiff(event) || RLCombatEvent_IsCleanFastWhiff(event))) {
            event_result = RL_COMBAT_ATTACK_RESULT_WHIFF;
            event_reason = RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW;
        }
        if (RLCombatEvent_FinalizeSlot(event, event_result, event_reason, frame_id, decision_id)) {
            finalized++;
        }
    }

    RLCombatEvent_RefreshActiveStats();
    return finalized;
}

static u32 RLCombatEvent_FrameAge(u32 frame_id, u32 start_frame) {
    return (frame_id >= start_frame) ? (frame_id - start_frame) : 0;
}

static u32 RLCombatEvent_MaxPendingFrames(const RLCombatAttackEvent* event) {
    if (event != NULL && (event->projectile_like || event->saw_projectile)) {
        return RL_COMBAT_ATTACK_PROJECTILE_MAX_PENDING_FRAMES;
    }
    return RL_COMBAT_ATTACK_MAX_PENDING_FRAMES;
}

static bool RLCombatEvent_IsCleanBasicWhiff(const RLCombatAttackEvent* event) {
    return event != NULL && event->whiff_eligible && !event->saw_target_contact_or_damage &&
           !event->saw_projectile && !event->saw_throw && !event->projectile_like;
}

static bool RLCombatEvent_IsCleanFastWhiff(const RLCombatAttackEvent* event) {
    return event != NULL && event->fast_whiff_fallback && event->whiff_eligible &&
           !event->saw_target_contact_or_damage && !event->saw_throw && !event->projectile_like;
}

static bool RLCombatEvent_TryBasicFinalize(RLCombatAttackEvent* event, const RLCombatAttackEventUpdate* update) {
    const u32 age = RLCombatEvent_FrameAge(update->frame_id, event->start_frame);

    event->whiff_eligible |= (u8)(update->actor_attack_state_active != 0);
    event->saw_target_contact_or_damage |= (u8)(update->target_contact_or_damage != 0);
    event->saw_target_hit_stop |= (u8)(update->target_entered_hit_stop != 0);
    event->saw_target_contact_state |= (u8)(update->target_entered_contact_state != 0);
    event->saw_target_damage_state |= (u8)(update->target_entered_damage_state != 0);
    event->saw_target_hp_delta |= (u8)(update->target_hp_delta != 0);
    event->saw_target_stun_delta |= (u8)(update->target_stun_delta != 0);
    event->saw_projectile |= (u8)(update->projectile_active_for_side != 0);
    event->saw_throw |= (u8)(update->throw_active_for_side != 0);

    if (update->actor_interrupted && !event->saw_target_contact_or_damage && age > 0) {
        return RLCombatEvent_FinalizeSlot(event,
                                          RL_COMBAT_ATTACK_RESULT_INTERRUPTED,
                                          RL_COMBAT_ATTACK_FINALIZE_BASIC_INTERRUPTED,
                                          update->frame_id,
                                          update->decision_id);
    }

    if (RLCombatEvent_IsCleanFastWhiff(event) && age >= RL_COMBAT_ATTACK_FAST_WHIFF_FALLBACK_FRAMES) {
        return RLCombatEvent_FinalizeSlot(event,
                                          RL_COMBAT_ATTACK_RESULT_WHIFF,
                                          RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW,
                                          update->frame_id,
                                          update->decision_id);
    }

    if (!update->actor_attack_state_active && age >= RL_COMBAT_ATTACK_MIN_WHIFF_FRAMES &&
        RLCombatEvent_IsCleanBasicWhiff(event)) {
        return RLCombatEvent_FinalizeSlot(event,
                                          RL_COMBAT_ATTACK_RESULT_WHIFF,
                                          RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW,
                                          update->frame_id,
                                          update->decision_id);
    }

    if (age >= RLCombatEvent_MaxPendingFrames(event)) {
        if (RLCombatEvent_IsCleanBasicWhiff(event)) {
            return RLCombatEvent_FinalizeSlot(event,
                                              RL_COMBAT_ATTACK_RESULT_WHIFF,
                                              RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW,
                                              update->frame_id,
                                              update->decision_id);
        }
        return RLCombatEvent_FinalizeSlot(event,
                                          RL_COMBAT_ATTACK_RESULT_UNKNOWN,
                                          RL_COMBAT_ATTACK_FINALIZE_BASIC_UNKNOWN_TIMEOUT,
                                          update->frame_id,
                                          update->decision_id);
    }

    return false;
}

u32 RLCombatEvent_UpdateActiveAttacks(const RLCombatAttackEventUpdate* update) {
    RLCombatAttackEventRing* ring = NULL;
    u32 finalized = 0;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->side == RL_COMBAT_EVENT_SIDE_NONE) {
        return 0;
    }

    ring = RLCombatEvent_RingForSide(update->side);
    if (ring == NULL) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        RLCombatAttackEvent* event = &ring->events[i];
        if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || event->run_id != update->run_id ||
            event->episode_id != update->episode_id || event->side != update->side) {
            continue;
        }
        if (RLCombatEvent_TryBasicFinalize(event, update)) {
            finalized++;
        }
    }

    RLCombatEvent_RefreshActiveStats();
    return finalized;
}

const RLCombatAttackEvent* RLCombatEvent_FindAttack(u64 event_id) {
    const RLCombatAttackEventRing* rings[] = {
        RLCombatEvent_ConstRingForSide(RL_COMBAT_EVENT_SIDE_SELF),
        RLCombatEvent_ConstRingForSide(RL_COMBAT_EVENT_SIDE_OPPONENT),
    };

    if (event_id == RL_COMBAT_EVENT_ID_NONE) {
        return NULL;
    }

    for (u32 r = 0; r < 2u; r++) {
        const RLCombatAttackEventRing* ring = rings[r];
        if (ring == NULL) {
            continue;
        }
        for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
            const RLCombatAttackEvent* event = &ring->events[i];
            if (event->status != RL_COMBAT_ATTACK_EVENT_EMPTY && event->event_id == event_id) {
                return event;
            }
        }
    }

    return NULL;
}

const RLCombatEventStats* RLCombatEvent_GetStats(void) {
    RLCombatEvent_RefreshActiveStats();
    return &combat_event_stats;
}
