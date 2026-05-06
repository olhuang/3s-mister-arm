#include "rl/rl_combat_event.h"

#include <string.h>

typedef struct RLCombatAttackEventRing {
    RLCombatAttackEvent events[RL_COMBAT_ATTACK_EVENT_RING_CAP];
    u32 cursor;
} RLCombatAttackEventRing;

typedef struct RLCombatProjectileEventRing {
    RLCombatProjectileEvent events[RL_COMBAT_PROJECTILE_EVENT_RING_CAP];
    u32 cursor;
} RLCombatProjectileEventRing;

typedef struct RLCombatThrowEventRing {
    RLCombatThrowEvent events[RL_COMBAT_THROW_EVENT_RING_CAP];
    u32 cursor;
} RLCombatThrowEventRing;

static RLCombatAttackEventRing self_attack_ring;
static RLCombatAttackEventRing opponent_attack_ring;
static RLCombatProjectileEventRing projectile_ring;
static RLCombatThrowEventRing self_throw_ring;
static RLCombatThrowEventRing opponent_throw_ring;
static RLCombatEventStats combat_event_stats;

static bool RLCombatEvent_IsCleanBasicWhiff(const RLCombatAttackEvent* event);
static bool RLCombatEvent_IsCleanFastWhiff(const RLCombatAttackEvent* event);
static u32 RLCombatEvent_FrameAge(u32 frame_id, u32 start_frame);

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

static RLCombatThrowEventRing* RLCombatEvent_ThrowRingForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_throw_ring;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_throw_ring;
    case RL_COMBAT_EVENT_SIDE_NONE:
    default:
        return NULL;
    }
}

static const RLCombatThrowEventRing* RLCombatEvent_ConstThrowRingForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_throw_ring;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_throw_ring;
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

static u32 RLCombatEvent_CountActiveProjectilesForSide(RLCombatEventSide side) {
    u32 count = 0;

    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        const RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_ACTIVE && event->owner_side == side) {
            count++;
        }
    }

    return count;
}

static bool RLCombatEvent_HasAttackCandidateForSide(u64 run_id, u32 episode_id, RLCombatEventSide side) {
    const RLCombatAttackEventRing* ring = RLCombatEvent_ConstRingForSide(side);

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        const RLCombatAttackEvent* event = &ring->events[i];
        if (event->status == RL_COMBAT_ATTACK_EVENT_ACTIVE && event->run_id == run_id &&
            event->episode_id == episode_id && event->side == side && !event->projectile_like &&
            !event->saw_projectile) {
            return true;
        }
    }

    return false;
}

static bool RLCombatEvent_HasProjectileCandidateForSide(u64 run_id,
                                                        u32 episode_id,
                                                        RLCombatEventSide side,
                                                        u32 frame_id) {
    if (run_id == 0 || episode_id == 0 || side == RL_COMBAT_EVENT_SIDE_NONE) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        const RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->run_id != run_id || event->episode_id != episode_id || event->owner_side != side) {
            continue;
        }
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_ACTIVE) {
            return true;
        }
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_FINALIZED && event->end_frame == frame_id) {
            return true;
        }
    }

    return false;
}

static bool RLCombatEvent_HasMutualProjectileExpireEdge(u64 run_id,
                                                        u32 episode_id,
                                                        RLCombatEventSide side,
                                                        u32 frame_id) {
    bool side_expired = false;
    bool opposing_expired = false;

    if (run_id == 0 || episode_id == 0 || side == RL_COMBAT_EVENT_SIDE_NONE) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        const RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->status != RL_COMBAT_PROJECTILE_EVENT_FINALIZED || event->run_id != run_id ||
            event->episode_id != episode_id || event->end_frame != frame_id ||
            event->result != RL_COMBAT_PROJECTILE_RESULT_EXPIRED ||
            event->finalize_reason != RL_COMBAT_PROJECTILE_FINALIZE_DISAPPEARED) {
            continue;
        }
        if (event->owner_side == side) {
            side_expired = true;
        } else if (event->owner_side != RL_COMBAT_EVENT_SIDE_NONE) {
            opposing_expired = true;
        }
    }

    return side_expired && opposing_expired;
}

static bool RLCombatEvent_HasThrowCandidateForSide(u64 run_id,
                                                   u32 episode_id,
                                                   RLCombatEventSide side,
                                                   u32 frame_id) {
    const RLCombatThrowEventRing* ring = RLCombatEvent_ConstThrowRingForSide(side);

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        const RLCombatThrowEvent* event = &ring->events[i];
        if (event->run_id != run_id || event->episode_id != episode_id || event->owner_side != side) {
            continue;
        }
        if (event->status == RL_COMBAT_THROW_EVENT_ACTIVE) {
            return true;
        }
        if (event->status == RL_COMBAT_THROW_EVENT_FINALIZED && event->end_frame == frame_id &&
            event->result != RL_COMBAT_THROW_RESULT_WHIFF) {
            return true;
        }
    }

    return false;
}

static bool RLCombatEvent_TryMarkThrowContactMatchForSide(u64 run_id,
                                                          u32 episode_id,
                                                          RLCombatEventSide side,
                                                          u32 frame_id) {
    RLCombatThrowEventRing* ring = RLCombatEvent_ThrowRingForSide(side);
    RLCombatThrowEvent* best = NULL;

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        RLCombatThrowEvent* event = &ring->events[i];
        if (event->run_id != run_id || event->episode_id != episode_id || event->owner_side != side ||
            event->contact_match_recorded) {
            continue;
        }
        if (event->status == RL_COMBAT_THROW_EVENT_ACTIVE) {
            best = event;
            break;
        }
        if (event->status == RL_COMBAT_THROW_EVENT_FINALIZED && event->end_frame == frame_id &&
            event->result != RL_COMBAT_THROW_RESULT_WHIFF) {
            best = event;
            break;
        }
    }

    if (best == NULL) {
        return false;
    }

    best->contact_match_recorded = 1;
    return true;
}

static u32 RLCombatEvent_CountActiveThrows(const RLCombatThrowEventRing* ring) {
    u32 count = 0;

    if (ring == NULL) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        if (ring->events[i].status == RL_COMBAT_THROW_EVENT_ACTIVE) {
            count++;
        }
    }

    return count;
}

bool RLCombatEvent_HasActiveThrowForSide(u64 run_id, u32 episode_id, RLCombatEventSide side) {
    const RLCombatThrowEventRing* ring = RLCombatEvent_ConstThrowRingForSide(side);

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        const RLCombatThrowEvent* event = &ring->events[i];
        if (event->status == RL_COMBAT_THROW_EVENT_ACTIVE && event->run_id == run_id &&
            event->episode_id == episode_id && event->owner_side == side) {
            return true;
        }
    }

    return false;
}

bool RLCombatEvent_HasRecentNonWhiffThrowForSide(u64 run_id,
                                                 u32 episode_id,
                                                 RLCombatEventSide side,
                                                 u32 frame_id,
                                                 u32 max_age_frames) {
    const RLCombatThrowEventRing* ring = RLCombatEvent_ConstThrowRingForSide(side);

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return false;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        const RLCombatThrowEvent* event = &ring->events[i];
        if (event->status != RL_COMBAT_THROW_EVENT_FINALIZED || event->run_id != run_id ||
            event->episode_id != episode_id || event->owner_side != side ||
            event->result == RL_COMBAT_THROW_RESULT_WHIFF) {
            continue;
        }
        if (RLCombatEvent_FrameAge(frame_id, event->end_frame) <= max_age_frames) {
            return true;
        }
    }

    return false;
}

static void RLCombatEvent_RefreshActiveStats(void) {
    combat_event_stats.attack_active_self_count = RLCombatEvent_CountActive(&self_attack_ring);
    combat_event_stats.attack_active_opponent_count = RLCombatEvent_CountActive(&opponent_attack_ring);
    combat_event_stats.projectile_active_self_count =
        RLCombatEvent_CountActiveProjectilesForSide(RL_COMBAT_EVENT_SIDE_SELF);
    combat_event_stats.projectile_active_opponent_count =
        RLCombatEvent_CountActiveProjectilesForSide(RL_COMBAT_EVENT_SIDE_OPPONENT);
    combat_event_stats.throw_active_self_count = RLCombatEvent_CountActiveThrows(&self_throw_ring);
    combat_event_stats.throw_active_opponent_count = RLCombatEvent_CountActiveThrows(&opponent_throw_ring);
}

static void RLCombatEvent_IncrementSideCounter(RLCombatEventSide side, u32* self_count, u32* opponent_count) {
    if (side == RL_COMBAT_EVENT_SIDE_SELF && self_count != NULL) {
        (*self_count)++;
    } else if (side == RL_COMBAT_EVENT_SIDE_OPPONENT && opponent_count != NULL) {
        (*opponent_count)++;
    }
}

static bool RLCombatEvent_ContactMatchHasTargetEdge(const RLCombatContactMatchUpdate* update,
                                                    bool projectile_candidate,
                                                    bool throw_candidate,
                                                    bool attack_candidate,
                                                    bool projectile_clash_edge) {
    const bool strong_edge =
        update != NULL &&
        (update->target_entered_damage_state || update->target_hp_delta || update->target_stun_delta ||
         update->target_parry_started || update->target_throw_caught);
    const bool contact_edge =
        update != NULL && (update->target_entered_hit_stop || update->target_entered_contact_state);

    if (strong_edge) {
        return true;
    }
    if (projectile_candidate && projectile_clash_edge) {
        return true;
    }
    if (!contact_edge) {
        return false;
    }
    if (projectile_candidate && !throw_candidate && !attack_candidate) {
        return update->target_block_reaction != 0 || update->target_parry_started != 0;
    }
    return projectile_candidate || throw_candidate || attack_candidate;
}

static void RLCombatEvent_IncrementContactMatchCounter(RLCombatEventSide side,
                                                       RLCombatContactMatchSource source) {
    combat_event_stats.contact_match_total_count++;
    switch (source) {
    case RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE:
        RLCombatEvent_IncrementSideCounter(side,
                                           &combat_event_stats.contact_match_projectile_self_count,
                                           &combat_event_stats.contact_match_projectile_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_THROW:
        RLCombatEvent_IncrementSideCounter(side,
                                           &combat_event_stats.contact_match_throw_self_count,
                                           &combat_event_stats.contact_match_throw_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK:
        RLCombatEvent_IncrementSideCounter(side,
                                           &combat_event_stats.contact_match_attack_self_count,
                                           &combat_event_stats.contact_match_attack_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN:
    case RL_COMBAT_CONTACT_MATCH_SOURCE_NONE:
    default:
        RLCombatEvent_IncrementSideCounter(side,
                                           &combat_event_stats.contact_match_unknown_self_count,
                                           &combat_event_stats.contact_match_unknown_opponent_count);
        break;
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
    combat_event_stats.projectile_started_count = 0;
    combat_event_stats.projectile_finalized_count = 0;
    combat_event_stats.projectile_hit_count = 0;
    combat_event_stats.projectile_blocked_count = 0;
    combat_event_stats.projectile_expired_count = 0;
    combat_event_stats.projectile_unknown_count = 0;
    combat_event_stats.projectile_dropped_start_count = 0;
    combat_event_stats.projectile_started_self_count = 0;
    combat_event_stats.projectile_started_opponent_count = 0;
    combat_event_stats.projectile_finalized_self_count = 0;
    combat_event_stats.projectile_finalized_opponent_count = 0;
    combat_event_stats.projectile_hit_self_count = 0;
    combat_event_stats.projectile_hit_opponent_count = 0;
    combat_event_stats.projectile_blocked_self_count = 0;
    combat_event_stats.projectile_blocked_opponent_count = 0;
    combat_event_stats.projectile_expired_self_count = 0;
    combat_event_stats.projectile_expired_opponent_count = 0;
    combat_event_stats.projectile_unknown_self_count = 0;
    combat_event_stats.projectile_unknown_opponent_count = 0;
    combat_event_stats.projectile_dropped_start_self_count = 0;
    combat_event_stats.projectile_dropped_start_opponent_count = 0;
    combat_event_stats.projectile_active_self_count = 0;
    combat_event_stats.projectile_active_opponent_count = 0;
    combat_event_stats.throw_started_count = 0;
    combat_event_stats.throw_finalized_count = 0;
    combat_event_stats.throw_success_count = 0;
    combat_event_stats.throw_whiff_count = 0;
    combat_event_stats.throw_unknown_count = 0;
    combat_event_stats.throw_dropped_start_count = 0;
    combat_event_stats.throw_started_self_count = 0;
    combat_event_stats.throw_started_opponent_count = 0;
    combat_event_stats.throw_finalized_self_count = 0;
    combat_event_stats.throw_finalized_opponent_count = 0;
    combat_event_stats.throw_success_self_count = 0;
    combat_event_stats.throw_success_opponent_count = 0;
    combat_event_stats.throw_whiff_self_count = 0;
    combat_event_stats.throw_whiff_opponent_count = 0;
    combat_event_stats.throw_unknown_self_count = 0;
    combat_event_stats.throw_unknown_opponent_count = 0;
    combat_event_stats.throw_dropped_start_self_count = 0;
    combat_event_stats.throw_dropped_start_opponent_count = 0;
    combat_event_stats.throw_active_self_count = 0;
    combat_event_stats.throw_active_opponent_count = 0;
    combat_event_stats.contact_match_total_count = 0;
    combat_event_stats.contact_match_attack_self_count = 0;
    combat_event_stats.contact_match_attack_opponent_count = 0;
    combat_event_stats.contact_match_projectile_self_count = 0;
    combat_event_stats.contact_match_projectile_opponent_count = 0;
    combat_event_stats.contact_match_throw_self_count = 0;
    combat_event_stats.contact_match_throw_opponent_count = 0;
    combat_event_stats.contact_match_unknown_self_count = 0;
    combat_event_stats.contact_match_unknown_opponent_count = 0;
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

static RLCombatProjectileEvent* RLCombatEvent_FindReusableProjectileSlot(void) {
    for (u32 scanned = 0; scanned < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; scanned++) {
        const u32 index = (projectile_ring.cursor + scanned) % RL_COMBAT_PROJECTILE_EVENT_RING_CAP;
        RLCombatProjectileEvent* event = &projectile_ring.events[index];
        if (event->status != RL_COMBAT_PROJECTILE_EVENT_ACTIVE) {
            projectile_ring.cursor = (index + 1u) % RL_COMBAT_PROJECTILE_EVENT_RING_CAP;
            return event;
        }
    }

    return NULL;
}

static RLCombatProjectileEvent* RLCombatEvent_FindActiveProjectileForSide(RLCombatEventSide side) {
    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_ACTIVE && event->owner_side == side) {
            return event;
        }
    }

    return NULL;
}

static const RLCombatAttackEvent* RLCombatEvent_FindRecentProjectileAttack(RLCombatEventSide side,
                                                                           u64 run_id,
                                                                           u32 episode_id,
                                                                           u32 frame_id) {
    const RLCombatAttackEventRing* ring = RLCombatEvent_ConstRingForSide(side);
    const RLCombatAttackEvent* best = NULL;
    u32 best_age = RL_COMBAT_ATTACK_PROJECTILE_MAX_PENDING_FRAMES + 1u;

    if (ring == NULL) {
        return NULL;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        const RLCombatAttackEvent* event = &ring->events[i];
        u32 age = 0;
        if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || event->run_id != run_id ||
            event->episode_id != episode_id || event->side != side || !event->projectile_like) {
            continue;
        }
        age = RLCombatEvent_FrameAge(frame_id, event->start_frame);
        if (age <= RL_COMBAT_ATTACK_PROJECTILE_MAX_PENDING_FRAMES && age < best_age) {
            best = event;
            best_age = age;
        }
    }

    return best;
}

static RLCombatProjectileResult RLCombatEvent_ProjectileResultFromEvidence(const RLCombatProjectileEvent* event,
                                                                           bool disappeared) {
    if (event == NULL) {
        return RL_COMBAT_PROJECTILE_RESULT_UNKNOWN;
    }

    if (event->saw_target_block_reaction) {
        return RL_COMBAT_PROJECTILE_RESULT_BLOCKED;
    }
    if (event->saw_target_damage_state || event->saw_target_hp_delta || event->saw_target_stun_delta) {
        return RL_COMBAT_PROJECTILE_RESULT_HIT;
    }
    if (event->saw_target_guard && (event->saw_target_contact_or_damage || event->saw_target_hit_stop)) {
        return RL_COMBAT_PROJECTILE_RESULT_BLOCKED;
    }
    if (event->saw_target_contact_or_damage || event->saw_target_hit_stop) {
        return RL_COMBAT_PROJECTILE_RESULT_UNKNOWN;
    }
    return disappeared ? RL_COMBAT_PROJECTILE_RESULT_EXPIRED : RL_COMBAT_PROJECTILE_RESULT_UNKNOWN;
}

static bool RLCombatEvent_FinalizeProjectileSlot(RLCombatProjectileEvent* event,
                                                 RLCombatProjectileResult result,
                                                 RLCombatProjectileFinalizeReason reason,
                                                 u32 frame_id,
                                                 u32 decision_id) {
    if (event == NULL || event->status != RL_COMBAT_PROJECTILE_EVENT_ACTIVE ||
        result == RL_COMBAT_PROJECTILE_RESULT_PENDING) {
        return false;
    }

    event->status = RL_COMBAT_PROJECTILE_EVENT_FINALIZED;
    event->result = result;
    event->finalize_reason = reason;
    event->end_frame = frame_id;
    event->end_decision_id = decision_id;
    combat_event_stats.projectile_finalized_count++;
    combat_event_stats.lifetime_projectile_finalized_count++;
    RLCombatEvent_IncrementSideCounter(event->owner_side,
                                       &combat_event_stats.projectile_finalized_self_count,
                                       &combat_event_stats.projectile_finalized_opponent_count);
    if (result == RL_COMBAT_PROJECTILE_RESULT_HIT) {
        combat_event_stats.projectile_hit_count++;
        combat_event_stats.lifetime_projectile_hit_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.projectile_hit_self_count,
                                           &combat_event_stats.projectile_hit_opponent_count);
    } else if (result == RL_COMBAT_PROJECTILE_RESULT_BLOCKED) {
        combat_event_stats.projectile_blocked_count++;
        combat_event_stats.lifetime_projectile_blocked_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.projectile_blocked_self_count,
                                           &combat_event_stats.projectile_blocked_opponent_count);
    } else if (result == RL_COMBAT_PROJECTILE_RESULT_EXPIRED) {
        combat_event_stats.projectile_expired_count++;
        combat_event_stats.lifetime_projectile_expired_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.projectile_expired_self_count,
                                           &combat_event_stats.projectile_expired_opponent_count);
    } else if (result == RL_COMBAT_PROJECTILE_RESULT_UNKNOWN) {
        combat_event_stats.projectile_unknown_count++;
        combat_event_stats.lifetime_projectile_unknown_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.projectile_unknown_self_count,
                                           &combat_event_stats.projectile_unknown_opponent_count);
    }

    RLCombatEvent_RefreshActiveStats();
    return true;
}

static RLCombatThrowEvent* RLCombatEvent_FindReusableThrowSlot(RLCombatThrowEventRing* ring) {
    if (ring == NULL) {
        return NULL;
    }

    for (u32 scanned = 0; scanned < RL_COMBAT_THROW_EVENT_RING_CAP; scanned++) {
        const u32 index = (ring->cursor + scanned) % RL_COMBAT_THROW_EVENT_RING_CAP;
        RLCombatThrowEvent* event = &ring->events[index];
        if (event->status != RL_COMBAT_THROW_EVENT_ACTIVE) {
            ring->cursor = (index + 1u) % RL_COMBAT_THROW_EVENT_RING_CAP;
            return event;
        }
    }

    return NULL;
}

static bool RLCombatEvent_IsCleanThrowWhiff(const RLCombatThrowEvent* event) {
    return event != NULL && !event->saw_target_caught && !event->saw_target_contact_or_damage &&
           !event->saw_target_hp_delta && !event->saw_target_stun_delta && !event->saw_actor_interrupted &&
           !event->saw_opposing_throw && !event->saw_throw_escape;
}

static bool RLCombatEvent_ThrowHasSuccessDamageEvidence(const RLCombatThrowEvent* event) {
    return event != NULL &&
           (event->saw_target_damage_state || event->saw_target_hp_delta || event->saw_target_stun_delta);
}

static bool RLCombatEvent_ThrowShouldStayUnknownForContest(const RLCombatThrowEvent* event) {
    if (event == NULL) {
        return false;
    }
    if (event->saw_throw_escape) {
        return true;
    }
    return event->saw_opposing_throw && (event->saw_target_caught || event->saw_target_caught_started) &&
           !RLCombatEvent_ThrowHasSuccessDamageEvidence(event);
}

static bool RLCombatEvent_FinalizeThrowSlot(RLCombatThrowEvent* event,
                                            RLCombatThrowResult result,
                                            RLCombatThrowFinalizeReason reason,
                                            u32 frame_id,
                                            u32 decision_id) {
    if (event == NULL || event->status != RL_COMBAT_THROW_EVENT_ACTIVE || result == RL_COMBAT_THROW_RESULT_PENDING) {
        return false;
    }

    event->status = RL_COMBAT_THROW_EVENT_FINALIZED;
    event->result = result;
    event->finalize_reason = reason;
    event->end_frame = frame_id;
    event->end_decision_id = decision_id;
    combat_event_stats.throw_finalized_count++;
    combat_event_stats.lifetime_throw_finalized_count++;
    RLCombatEvent_IncrementSideCounter(event->owner_side,
                                       &combat_event_stats.throw_finalized_self_count,
                                       &combat_event_stats.throw_finalized_opponent_count);
    if (result == RL_COMBAT_THROW_RESULT_SUCCESS) {
        combat_event_stats.throw_success_count++;
        combat_event_stats.lifetime_throw_success_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.throw_success_self_count,
                                           &combat_event_stats.throw_success_opponent_count);
    } else if (result == RL_COMBAT_THROW_RESULT_WHIFF) {
        combat_event_stats.throw_whiff_count++;
        combat_event_stats.lifetime_throw_whiff_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.throw_whiff_self_count,
                                           &combat_event_stats.throw_whiff_opponent_count);
    } else if (result == RL_COMBAT_THROW_RESULT_UNKNOWN) {
        combat_event_stats.throw_unknown_count++;
        combat_event_stats.lifetime_throw_unknown_count++;
        RLCombatEvent_IncrementSideCounter(event->owner_side,
                                           &combat_event_stats.throw_unknown_self_count,
                                           &combat_event_stats.throw_unknown_opponent_count);
    }

    RLCombatEvent_RefreshActiveStats();
    return true;
}

static u32 RLCombatEvent_FinalizeActiveThrowsForSide(u64 run_id,
                                                     u32 episode_id,
                                                     RLCombatEventSide side,
                                                     RLCombatThrowResult result,
                                                     RLCombatThrowFinalizeReason reason,
                                                     u32 frame_id,
                                                     u32 decision_id) {
    RLCombatThrowEventRing* ring = RLCombatEvent_ThrowRingForSide(side);
    u32 finalized = 0;

    if (ring == NULL || run_id == 0 || episode_id == 0 || result == RL_COMBAT_THROW_RESULT_PENDING) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        RLCombatThrowEvent* event = &ring->events[i];
        RLCombatThrowResult event_result = result;
        RLCombatThrowFinalizeReason event_reason = reason;
        if (event->status != RL_COMBAT_THROW_EVENT_ACTIVE || event->run_id != run_id ||
            event->episode_id != episode_id || event->owner_side != side) {
            continue;
        }
        if (reason == RL_COMBAT_THROW_FINALIZE_SUPERSEDED_BY_NEW_START &&
            result == RL_COMBAT_THROW_RESULT_UNKNOWN && RLCombatEvent_IsCleanThrowWhiff(event)) {
            event_result = RL_COMBAT_THROW_RESULT_WHIFF;
            event_reason = RL_COMBAT_THROW_FINALIZE_WHIFF_WINDOW;
        }
        if (RLCombatEvent_FinalizeThrowSlot(event, event_result, event_reason, frame_id, decision_id)) {
            finalized++;
        }
    }

    RLCombatEvent_RefreshActiveStats();
    return finalized;
}

static void RLCombatEvent_ClearRings(void) {
    memset(&self_attack_ring, 0, sizeof(self_attack_ring));
    memset(&opponent_attack_ring, 0, sizeof(opponent_attack_ring));
    memset(&projectile_ring, 0, sizeof(projectile_ring));
    memset(&self_throw_ring, 0, sizeof(self_throw_ring));
    memset(&opponent_throw_ring, 0, sizeof(opponent_throw_ring));
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
    RLCombatThrowEventRing* throw_rings[] = { &self_throw_ring, &opponent_throw_ring };

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
    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->status != RL_COMBAT_PROJECTILE_EVENT_ACTIVE || event->run_id != run_id ||
            event->episode_id != episode_id) {
            continue;
        }
        RLCombatEvent_FinalizeProjectileSlot(event,
                                             RL_COMBAT_PROJECTILE_RESULT_UNKNOWN,
                                             RL_COMBAT_PROJECTILE_FINALIZE_EPISODE_FLUSH,
                                             frame_id,
                                             decision_id);
    }
    for (u32 r = 0; r < 2u; r++) {
        RLCombatThrowEventRing* ring = throw_rings[r];
        for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
            RLCombatThrowEvent* event = &ring->events[i];
            if (event->status != RL_COMBAT_THROW_EVENT_ACTIVE || event->run_id != run_id ||
                event->episode_id != episode_id) {
                continue;
            }
            RLCombatEvent_FinalizeThrowSlot(event,
                                            RL_COMBAT_THROW_RESULT_UNKNOWN,
                                            RL_COMBAT_THROW_FINALIZE_EPISODE_FLUSH,
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
    event->engine_action_id = start->engine_action_id;
    event->engine_sub_action_id = start->engine_sub_action_id;
    event->engine_routine_1 = start->engine_routine_1;
    event->engine_routine_2 = start->engine_routine_2;
    event->engine_current_attack = start->engine_current_attack;
    event->engine_lag_frames = start->engine_lag_frames;
    event->engine_kind_of_waza = start->engine_kind_of_waza;
    event->engine_label_source = start->engine_label_source;
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

static RLCombatProjectileEvent* RLCombatEvent_StartProjectile(const RLCombatProjectileEventUpdate* update) {
    RLCombatProjectileEvent* event = NULL;
    const RLCombatAttackEvent* parent = NULL;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->owner_side == RL_COMBAT_EVENT_SIDE_NONE || !update->projectile_active_for_side) {
        combat_event_stats.projectile_dropped_start_count++;
        combat_event_stats.lifetime_projectile_dropped_start_count++;
        if (update != NULL) {
            RLCombatEvent_IncrementSideCounter(update->owner_side,
                                               &combat_event_stats.projectile_dropped_start_self_count,
                                               &combat_event_stats.projectile_dropped_start_opponent_count);
        }
        return NULL;
    }

    if (combat_event_stats.run_id != update->run_id || combat_event_stats.episode_id != update->episode_id) {
        RLCombatEvent_BeginEpisode(update->run_id, update->episode_id);
    }

    event = RLCombatEvent_FindReusableProjectileSlot();
    if (event == NULL) {
        combat_event_stats.projectile_dropped_start_count++;
        combat_event_stats.lifetime_projectile_dropped_start_count++;
        RLCombatEvent_IncrementSideCounter(update->owner_side,
                                           &combat_event_stats.projectile_dropped_start_self_count,
                                           &combat_event_stats.projectile_dropped_start_opponent_count);
        RLCombatEvent_RefreshActiveStats();
        return NULL;
    }

    parent = RLCombatEvent_FindRecentProjectileAttack(update->owner_side,
                                                     update->run_id,
                                                     update->episode_id,
                                                     update->frame_id);

    memset(event, 0, sizeof(*event));
    event->status = RL_COMBAT_PROJECTILE_EVENT_ACTIVE;
    event->result = RL_COMBAT_PROJECTILE_RESULT_PENDING;
    event->event_id = RLCombatEvent_AllocateEventId();
    event->parent_attack_event_id = parent != NULL ? parent->event_id : RL_COMBAT_EVENT_ID_NONE;
    event->run_id = update->run_id;
    event->episode_id = update->episode_id;
    event->start_decision_id = update->decision_id;
    event->start_frame = update->frame_id;
    event->owner_side = update->owner_side;
    event->spawn_rel_x = update->projectile_rel_x;
    event->spawn_rel_y = update->projectile_rel_y;
    event->spawn_vel_x = update->projectile_vel_x;
    event->spawn_time_to_self = update->projectile_time_to_self;
    event->last_rel_x = update->projectile_rel_x;
    event->last_rel_y = update->projectile_rel_y;
    event->last_vel_x = update->projectile_vel_x;
    event->last_time_to_self = update->projectile_time_to_self;
    if (parent != NULL) {
        event->engine_action_id = parent->engine_action_id;
        event->engine_sub_action_id = parent->engine_sub_action_id;
        event->engine_label_source = parent->engine_label_source;
        RLCombatEvent_FinalizeAttack(parent->event_id,
                                     RL_COMBAT_ATTACK_RESULT_UNKNOWN,
                                     RL_COMBAT_ATTACK_FINALIZE_PROJECTILE_CLAIMED,
                                     update->frame_id,
                                     update->decision_id);
    }

    combat_event_stats.projectile_started_count++;
    combat_event_stats.lifetime_projectile_started_count++;
    RLCombatEvent_IncrementSideCounter(event->owner_side,
                                       &combat_event_stats.projectile_started_self_count,
                                       &combat_event_stats.projectile_started_opponent_count);
    RLCombatEvent_RefreshActiveStats();
    return event;
}

const RLCombatThrowEvent* RLCombatEvent_StartThrow(const RLCombatThrowEventStart* start) {
    RLCombatThrowEventRing* ring = NULL;
    RLCombatThrowEvent* event = NULL;

    if (start == NULL || start->run_id == 0 || start->episode_id == 0 ||
        start->owner_side == RL_COMBAT_EVENT_SIDE_NONE) {
        combat_event_stats.throw_dropped_start_count++;
        combat_event_stats.lifetime_throw_dropped_start_count++;
        if (start != NULL) {
            RLCombatEvent_IncrementSideCounter(start->owner_side,
                                               &combat_event_stats.throw_dropped_start_self_count,
                                               &combat_event_stats.throw_dropped_start_opponent_count);
        }
        return NULL;
    }

    if (combat_event_stats.run_id != start->run_id || combat_event_stats.episode_id != start->episode_id) {
        RLCombatEvent_BeginEpisode(start->run_id, start->episode_id);
    }

    RLCombatEvent_FinalizeActiveThrowsForSide(start->run_id,
                                              start->episode_id,
                                              start->owner_side,
                                              RL_COMBAT_THROW_RESULT_UNKNOWN,
                                              RL_COMBAT_THROW_FINALIZE_SUPERSEDED_BY_NEW_START,
                                              start->frame_id,
                                              start->decision_id);

    ring = RLCombatEvent_ThrowRingForSide(start->owner_side);
    event = RLCombatEvent_FindReusableThrowSlot(ring);
    if (event == NULL) {
        combat_event_stats.throw_dropped_start_count++;
        combat_event_stats.lifetime_throw_dropped_start_count++;
        RLCombatEvent_IncrementSideCounter(start->owner_side,
                                           &combat_event_stats.throw_dropped_start_self_count,
                                           &combat_event_stats.throw_dropped_start_opponent_count);
        RLCombatEvent_RefreshActiveStats();
        return NULL;
    }

    memset(event, 0, sizeof(*event));
    event->status = RL_COMBAT_THROW_EVENT_ACTIVE;
    event->result = RL_COMBAT_THROW_RESULT_PENDING;
    event->event_id = RLCombatEvent_AllocateEventId();
    event->run_id = start->run_id;
    event->episode_id = start->episode_id;
    event->start_decision_id = start->decision_id;
    event->start_frame = start->frame_id;
    event->owner_side = start->owner_side;
    event->character_id = start->character_id;
    event->routine_1 = start->routine_1;
    event->routine_2 = start->routine_2;
    event->current_attack = start->current_attack;
    event->kind_of_waza = start->kind_of_waza;
    event->saw_owner_throw_active = 1;

    combat_event_stats.throw_started_count++;
    combat_event_stats.lifetime_throw_started_count++;
    RLCombatEvent_IncrementSideCounter(event->owner_side,
                                       &combat_event_stats.throw_started_self_count,
                                       &combat_event_stats.throw_started_opponent_count);
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

static void RLCombatEvent_AccumulateProjectileEvidence(RLCombatProjectileEvent* event,
                                                       const RLCombatProjectileEventUpdate* update) {
    const u8 strong_contact =
        (u8)(update != NULL && (update->target_contact_or_damage || update->target_entered_hit_stop ||
                                update->target_entered_damage_state || update->target_hp_delta ||
                                update->target_stun_delta));

    if (event == NULL || update == NULL) {
        return;
    }

    event->saw_target_guard |= (u8)(update->target_guard != 0 && strong_contact);
    event->saw_target_block_reaction |= (u8)(update->target_block_reaction != 0);
    event->saw_target_contact_or_damage |= (u8)(update->target_contact_or_damage != 0);
    event->saw_target_hit_stop |= (u8)(update->target_entered_hit_stop != 0);
    event->saw_target_contact_state |= (u8)(update->target_entered_contact_state != 0);
    event->saw_target_damage_state |= (u8)(update->target_entered_damage_state != 0);
    event->saw_target_hp_delta |= (u8)(update->target_hp_delta != 0);
    event->saw_target_stun_delta |= (u8)(update->target_stun_delta != 0);
}

u32 RLCombatEvent_UpdateProjectiles(const RLCombatProjectileEventUpdate* update) {
    RLCombatProjectileEvent* event = NULL;
    u32 finalized = 0;
    u32 age = 0;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->owner_side == RL_COMBAT_EVENT_SIDE_NONE) {
        return 0;
    }

    event = RLCombatEvent_FindActiveProjectileForSide(update->owner_side);
    if (update->projectile_active_for_side) {
        if (event == NULL) {
            event = RLCombatEvent_StartProjectile(update);
        }
        if (event != NULL) {
            event->last_rel_x = update->projectile_rel_x;
            event->last_rel_y = update->projectile_rel_y;
            event->last_vel_x = update->projectile_vel_x;
            event->last_time_to_self = update->projectile_time_to_self;
            event->missing_frames = 0;
            RLCombatEvent_AccumulateProjectileEvidence(event, update);
        }
    } else if (event != NULL) {
        RLCombatEvent_AccumulateProjectileEvidence(event, update);
        if (!update->any_projectile_active && event->missing_frames < 255u) {
            event->missing_frames++;
        }
        age = RLCombatEvent_FrameAge(update->frame_id, event->start_frame);
        if (event->missing_frames >= RL_COMBAT_PROJECTILE_MISSING_FINALIZE_FRAMES) {
            const RLCombatProjectileResult result = RLCombatEvent_ProjectileResultFromEvidence(event, true);
            const RLCombatProjectileFinalizeReason reason =
                (result == RL_COMBAT_PROJECTILE_RESULT_EXPIRED) ? RL_COMBAT_PROJECTILE_FINALIZE_DISAPPEARED
                                                                : RL_COMBAT_PROJECTILE_FINALIZE_CONTACT;
            if (RLCombatEvent_FinalizeProjectileSlot(event, result, reason, update->frame_id, update->decision_id)) {
                finalized++;
            }
        } else if (age >= RL_COMBAT_PROJECTILE_MAX_PENDING_FRAMES) {
            const RLCombatProjectileResult result = RLCombatEvent_ProjectileResultFromEvidence(event, false);
            if (RLCombatEvent_FinalizeProjectileSlot(event,
                                                     result,
                                                     RL_COMBAT_PROJECTILE_FINALIZE_TIMEOUT,
                                                     update->frame_id,
                                                     update->decision_id)) {
                finalized++;
            }
        }
    }

    RLCombatEvent_RefreshActiveStats();
    return finalized;
}

static bool RLCombatEvent_TryFinalizeThrow(RLCombatThrowEvent* event, const RLCombatThrowEventUpdate* update) {
    const u32 age = RLCombatEvent_FrameAge(update->frame_id, event->start_frame);

    event->saw_owner_throw_active |= (u8)(update->owner_throw_active != 0);
    event->saw_opposing_throw |= (u8)(update->opposing_throw_active || update->opposing_throw_started);
    event->saw_throw_escape |= (u8)(update->throw_escape || update->throw_escape_started);
    event->saw_target_caught |= (u8)(update->target_caught != 0);
    event->saw_target_caught_started |= (u8)(update->target_caught_started != 0);
    event->saw_actor_interrupted |= (u8)(update->actor_interrupted != 0);
    event->saw_target_contact_or_damage |= (u8)(update->target_contact_or_damage != 0);
    event->saw_target_hit_stop |= (u8)(update->target_entered_hit_stop != 0);
    event->saw_target_contact_state |= (u8)(update->target_entered_contact_state != 0);
    event->saw_target_damage_state |= (u8)(update->target_entered_damage_state != 0);
    event->saw_target_hp_delta |= (u8)(update->target_hp_delta != 0);
    event->saw_target_stun_delta |= (u8)(update->target_stun_delta != 0);

    if (RLCombatEvent_ThrowShouldStayUnknownForContest(event)) {
        return RLCombatEvent_FinalizeThrowSlot(event,
                                               RL_COMBAT_THROW_RESULT_UNKNOWN,
                                               RL_COMBAT_THROW_FINALIZE_TECH_ESCAPE,
                                               update->frame_id,
                                               update->decision_id);
    }

    if ((event->saw_target_caught || event->saw_target_caught_started) &&
        (age >= RL_COMBAT_THROW_SUCCESS_CONFIRM_FRAMES || RLCombatEvent_ThrowHasSuccessDamageEvidence(event))) {
        return RLCombatEvent_FinalizeThrowSlot(event,
                                               RL_COMBAT_THROW_RESULT_SUCCESS,
                                               RL_COMBAT_THROW_FINALIZE_TARGET_CAUGHT,
                                               update->frame_id,
                                               update->decision_id);
    }

    if (!update->owner_throw_active && age >= RL_COMBAT_THROW_MIN_WHIFF_FRAMES &&
        RLCombatEvent_IsCleanThrowWhiff(event)) {
        return RLCombatEvent_FinalizeThrowSlot(event,
                                               RL_COMBAT_THROW_RESULT_WHIFF,
                                               RL_COMBAT_THROW_FINALIZE_WHIFF_WINDOW,
                                               update->frame_id,
                                               update->decision_id);
    }

    if (!update->owner_throw_active && age >= RL_COMBAT_THROW_MIN_WHIFF_FRAMES &&
        event->saw_opposing_throw && !RLCombatEvent_ThrowHasSuccessDamageEvidence(event)) {
        return RLCombatEvent_FinalizeThrowSlot(event,
                                               RL_COMBAT_THROW_RESULT_UNKNOWN,
                                               RL_COMBAT_THROW_FINALIZE_TECH_ESCAPE,
                                               update->frame_id,
                                               update->decision_id);
    }

    if (age >= RL_COMBAT_THROW_MAX_PENDING_FRAMES) {
        if (RLCombatEvent_IsCleanThrowWhiff(event)) {
            return RLCombatEvent_FinalizeThrowSlot(event,
                                                   RL_COMBAT_THROW_RESULT_WHIFF,
                                                   RL_COMBAT_THROW_FINALIZE_WHIFF_WINDOW,
                                                   update->frame_id,
                                                   update->decision_id);
        }
        return RLCombatEvent_FinalizeThrowSlot(event,
                                               RL_COMBAT_THROW_RESULT_UNKNOWN,
                                               RL_COMBAT_THROW_FINALIZE_UNKNOWN_TIMEOUT,
                                               update->frame_id,
                                               update->decision_id);
    }

    return false;
}

u32 RLCombatEvent_UpdateThrows(const RLCombatThrowEventUpdate* update) {
    RLCombatThrowEventRing* ring = NULL;
    u32 finalized = 0;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->owner_side == RL_COMBAT_EVENT_SIDE_NONE) {
        return 0;
    }

    ring = RLCombatEvent_ThrowRingForSide(update->owner_side);
    if (ring == NULL) {
        return 0;
    }

    for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
        RLCombatThrowEvent* event = &ring->events[i];
        if (event->status != RL_COMBAT_THROW_EVENT_ACTIVE || event->run_id != update->run_id ||
            event->episode_id != update->episode_id || event->owner_side != update->owner_side) {
            continue;
        }
        if (RLCombatEvent_TryFinalizeThrow(event, update)) {
            finalized++;
        }
    }

    RLCombatEvent_RefreshActiveStats();
    return finalized;
}

bool RLCombatEvent_RecordContactMatch(const RLCombatContactMatchUpdate* update) {
    bool projectile_candidate = false;
    bool projectile_clash_edge = false;
    bool throw_candidate = false;
    bool attack_candidate = false;
    RLCombatContactMatchSource source = RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->source_side == RL_COMBAT_EVENT_SIDE_NONE) {
        return false;
    }

    if (combat_event_stats.run_id != update->run_id || combat_event_stats.episode_id != update->episode_id) {
        RLCombatEvent_BeginEpisode(update->run_id, update->episode_id);
    }

    projectile_candidate =
        (update->projectile_candidate ||
         RLCombatEvent_HasProjectileCandidateForSide(update->run_id,
                                                     update->episode_id,
                                                     update->source_side,
                                                     update->frame_id));
    projectile_clash_edge = RLCombatEvent_HasMutualProjectileExpireEdge(update->run_id,
                                                                        update->episode_id,
                                                                        update->source_side,
                                                                        update->frame_id);
    throw_candidate = (update->throw_candidate ||
                       RLCombatEvent_HasThrowCandidateForSide(update->run_id,
                                                             update->episode_id,
                                                             update->source_side,
                                                             update->frame_id));
    attack_candidate =
        (update->attack_candidate ||
         RLCombatEvent_HasAttackCandidateForSide(update->run_id, update->episode_id, update->source_side));

    if (!RLCombatEvent_ContactMatchHasTargetEdge(update,
                                                 projectile_candidate,
                                                 throw_candidate,
                                                 attack_candidate,
                                                 projectile_clash_edge)) {
        return false;
    }

    if (projectile_candidate) {
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE;
    } else if (throw_candidate) {
        if (!RLCombatEvent_TryMarkThrowContactMatchForSide(update->run_id,
                                                          update->episode_id,
                                                          update->source_side,
                                                          update->frame_id)) {
            return false;
        }
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_THROW;
    } else if (attack_candidate) {
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK;
    }

    RLCombatEvent_IncrementContactMatchCounter(update->source_side, source);
    return true;
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

const RLCombatProjectileEvent* RLCombatEvent_FindProjectile(u64 event_id) {
    if (event_id == RL_COMBAT_EVENT_ID_NONE) {
        return NULL;
    }

    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        const RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->status != RL_COMBAT_PROJECTILE_EVENT_EMPTY && event->event_id == event_id) {
            return event;
        }
    }

    return NULL;
}

const RLCombatThrowEvent* RLCombatEvent_FindThrow(u64 event_id) {
    const RLCombatThrowEventRing* rings[] = {
        RLCombatEvent_ConstThrowRingForSide(RL_COMBAT_EVENT_SIDE_SELF),
        RLCombatEvent_ConstThrowRingForSide(RL_COMBAT_EVENT_SIDE_OPPONENT),
    };

    if (event_id == RL_COMBAT_EVENT_ID_NONE) {
        return NULL;
    }

    for (u32 r = 0; r < 2u; r++) {
        const RLCombatThrowEventRing* ring = rings[r];
        if (ring == NULL) {
            continue;
        }
        for (u32 i = 0; i < RL_COMBAT_THROW_EVENT_RING_CAP; i++) {
            const RLCombatThrowEvent* event = &ring->events[i];
            if (event->status != RL_COMBAT_THROW_EVENT_EMPTY && event->event_id == event_id) {
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
