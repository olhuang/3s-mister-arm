#include "rl/rl_combat_event.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
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

typedef struct RLCombatAttributionEventRing {
    RLCombatAttributionEvent events[RL_COMBAT_ATTRIBUTION_EVENT_RING_CAP];
    u32 cursor;
} RLCombatAttributionEventRing;

typedef struct RLCombatPunishEventRing {
    RLCombatPunishEvent events[RL_COMBAT_PUNISH_EVENT_RING_CAP];
    u32 cursor;
} RLCombatPunishEventRing;

typedef enum RLCombatJournalEventKind {
    RL_COMBAT_JOURNAL_EVENT_NONE = 0,
    RL_COMBAT_JOURNAL_EVENT_ATTACK = 1,
    RL_COMBAT_JOURNAL_EVENT_PROJECTILE = 2,
    RL_COMBAT_JOURNAL_EVENT_THROW = 3,
    RL_COMBAT_JOURNAL_EVENT_ATTRIBUTION = 4,
    RL_COMBAT_JOURNAL_EVENT_PUNISH = 5,
} RLCombatJournalEventKind;

typedef struct RLCombatJournalEntry {
    RLCombatJournalEventKind kind;
    u64 event_id;
    u64 run_id;
    u32 episode_id;
    union {
        RLCombatAttackEvent attack;
        RLCombatProjectileEvent projectile;
        RLCombatThrowEvent throw_event;
        RLCombatAttributionEvent attribution;
        RLCombatPunishEvent punish;
    } event;
} RLCombatJournalEntry;

typedef struct RLCombatPunishableAttackCandidate {
    bool valid;
    u64 event_id;
    u64 run_id;
    u32 episode_id;
    u32 end_frame;
    u32 end_decision_id;
    RLCombatEventSide side;
    RLCombatPunishReason reason;
} RLCombatPunishableAttackCandidate;

#define RL_COMBAT_PUNISH_CANDIDATE_WINDOW_FRAMES 12u
#define RL_COMBAT_EVENT_JOURNAL_ENTRY_CAP 2048u

static RLCombatAttackEventRing self_attack_ring;
static RLCombatAttackEventRing opponent_attack_ring;
static RLCombatProjectileEventRing projectile_ring;
static RLCombatThrowEventRing self_throw_ring;
static RLCombatThrowEventRing opponent_throw_ring;
static RLCombatAttributionEventRing attribution_ring;
static RLCombatPunishEventRing punish_ring;
static RLCombatJournalEntry journal_entries[RL_COMBAT_EVENT_JOURNAL_ENTRY_CAP];
static u32 journal_entry_count;
static RLCombatPunishableAttackCandidate self_punishable_attack;
static RLCombatPunishableAttackCandidate opponent_punishable_attack;
static u64 self_last_punished_attack_event_id;
static u64 opponent_last_punished_attack_event_id;
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

static RLCombatPunishableAttackCandidate* RLCombatEvent_PunishableAttackForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_punishable_attack;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_punishable_attack;
    case RL_COMBAT_EVENT_SIDE_NONE:
    default:
        return NULL;
    }
}

static u64* RLCombatEvent_LastPunishedAttackIdForSide(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return &self_last_punished_attack_event_id;
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return &opponent_last_punished_attack_event_id;
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

static RLCombatEventSide RLCombatEvent_OppositeSide(RLCombatEventSide side) {
    if (side == RL_COMBAT_EVENT_SIDE_SELF) {
        return RL_COMBAT_EVENT_SIDE_OPPONENT;
    }
    if (side == RL_COMBAT_EVENT_SIDE_OPPONENT) {
        return RL_COMBAT_EVENT_SIDE_SELF;
    }
    return RL_COMBAT_EVENT_SIDE_NONE;
}

static const RLCombatAttackEvent* RLCombatEvent_FindAttackCandidateForSide(u64 run_id,
                                                                           u32 episode_id,
                                                                           RLCombatEventSide side) {
    const RLCombatAttackEventRing* ring = RLCombatEvent_ConstRingForSide(side);

    if (ring == NULL || run_id == 0 || episode_id == 0) {
        return NULL;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        const RLCombatAttackEvent* event = &ring->events[i];
        if (event->status == RL_COMBAT_ATTACK_EVENT_ACTIVE && event->run_id == run_id &&
            event->episode_id == episode_id && event->side == side && !event->projectile_like &&
            !event->saw_projectile) {
            return event;
        }
    }

    return NULL;
}

static const RLCombatProjectileEvent* RLCombatEvent_FindProjectileCandidateForSide(u64 run_id,
                                                                                   u32 episode_id,
                                                                                   RLCombatEventSide side,
                                                                                   u32 frame_id) {
    if (run_id == 0 || episode_id == 0 || side == RL_COMBAT_EVENT_SIDE_NONE) {
        return NULL;
    }

    for (u32 i = 0; i < RL_COMBAT_PROJECTILE_EVENT_RING_CAP; i++) {
        const RLCombatProjectileEvent* event = &projectile_ring.events[i];
        if (event->run_id != run_id || event->episode_id != episode_id || event->owner_side != side) {
            continue;
        }
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_ACTIVE) {
            return event;
        }
        if (event->status == RL_COMBAT_PROJECTILE_EVENT_FINALIZED && event->end_frame == frame_id) {
            return event;
        }
    }

    return NULL;
}

static bool RLCombatEvent_HasProjectileClashEdgeForSide(u64 run_id,
                                                        u32 episode_id,
                                                        RLCombatEventSide side,
                                                        u32 frame_id) {
    bool side_expired = false;
    bool side_saw_opposing_projectile = false;
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
            side_saw_opposing_projectile |= (event->saw_opposing_projectile != 0);
        } else if (event->owner_side != RL_COMBAT_EVENT_SIDE_NONE) {
            opposing_expired = true;
        }
    }

    return side_expired && (side_saw_opposing_projectile || opposing_expired);
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
                                                          u32 frame_id,
                                                          u64* event_id_out) {
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
    if (event_id_out != NULL) {
        *event_id_out = best->event_id;
    }
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

static bool RLCombatEvent_IsWeakContactOnlyEdge(RLCombatAttributionEdgeType edge_type) {
    return edge_type == RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE ||
           edge_type == RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP;
}

static bool RLCombatEvent_HasStrongDefenseOutcomeEdge(const RLCombatContactMatchUpdate* update,
                                                      bool projectile_clash_edge) {
    if (update == NULL) {
        return false;
    }

    return projectile_clash_edge || update->target_entered_damage_state || update->target_hp_delta ||
           update->target_stun_delta || update->target_block_reaction || update->target_parry_started ||
           update->target_throw_caught;
}

static bool RLCombatEvent_ShouldSuppressWeakAttackAttribution(const RLCombatContactMatchUpdate* update,
                                                              RLCombatContactMatchSource source,
                                                              RLCombatAttributionEdgeType edge_type,
                                                              bool projectile_clash_edge) {
    return update != NULL && source == RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK &&
           RLCombatEvent_IsWeakContactOnlyEdge(edge_type) &&
           !RLCombatEvent_HasStrongDefenseOutcomeEdge(update, projectile_clash_edge);
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
    combat_event_stats.attribution_recorded_count = 0;
    combat_event_stats.attribution_failure_count = 0;
    combat_event_stats.attribution_ring_overwrite_count = 0;
    combat_event_stats.event_journal_entry_count = 0;
    combat_event_stats.event_journal_overflow_count = 0;
    combat_event_stats.attribution_edge_hit_stop_count = 0;
    combat_event_stats.attribution_edge_contact_state_count = 0;
    combat_event_stats.attribution_edge_damage_state_count = 0;
    combat_event_stats.attribution_edge_hp_delta_count = 0;
    combat_event_stats.attribution_edge_stun_delta_count = 0;
    combat_event_stats.attribution_edge_block_reaction_count = 0;
    combat_event_stats.attribution_edge_parry_count = 0;
    combat_event_stats.attribution_edge_throw_caught_count = 0;
    combat_event_stats.attribution_edge_projectile_clash_count = 0;
    combat_event_stats.defense_hit_self_count = 0;
    combat_event_stats.defense_hit_opponent_count = 0;
    combat_event_stats.defense_blocked_self_count = 0;
    combat_event_stats.defense_blocked_opponent_count = 0;
    combat_event_stats.defense_blocked_chip_self_count = 0;
    combat_event_stats.defense_blocked_chip_opponent_count = 0;
    combat_event_stats.defense_parry_self_count = 0;
    combat_event_stats.defense_parry_opponent_count = 0;
    combat_event_stats.defense_thrown_self_count = 0;
    combat_event_stats.defense_thrown_opponent_count = 0;
    combat_event_stats.defense_evaded_self_count = 0;
    combat_event_stats.defense_evaded_opponent_count = 0;
    combat_event_stats.defense_unknown_self_count = 0;
    combat_event_stats.defense_unknown_opponent_count = 0;
    combat_event_stats.defense_context_guard_self_count = 0;
    combat_event_stats.defense_context_guard_opponent_count = 0;
    combat_event_stats.defense_context_block_reaction_self_count = 0;
    combat_event_stats.defense_context_block_reaction_opponent_count = 0;
    combat_event_stats.defense_context_parry_self_count = 0;
    combat_event_stats.defense_context_parry_opponent_count = 0;
    combat_event_stats.defense_context_throw_caught_self_count = 0;
    combat_event_stats.defense_context_throw_caught_opponent_count = 0;
    combat_event_stats.punish_candidate_self_count = 0;
    combat_event_stats.punish_candidate_opponent_count = 0;
    combat_event_stats.punish_whiff_self_count = 0;
    combat_event_stats.punish_whiff_opponent_count = 0;
    combat_event_stats.punish_interrupted_self_count = 0;
    combat_event_stats.punish_interrupted_opponent_count = 0;
    combat_event_stats.punish_source_attack_self_count = 0;
    combat_event_stats.punish_source_attack_opponent_count = 0;
    combat_event_stats.punish_source_projectile_self_count = 0;
    combat_event_stats.punish_source_projectile_opponent_count = 0;
    combat_event_stats.punish_source_throw_self_count = 0;
    combat_event_stats.punish_source_throw_opponent_count = 0;
    combat_event_stats.punish_finalized_candidate_self_count = 0;
    combat_event_stats.punish_finalized_candidate_opponent_count = 0;
    combat_event_stats.punish_active_candidate_self_count = 0;
    combat_event_stats.punish_active_candidate_opponent_count = 0;
    combat_event_stats.punish_finalized_whiff_self_count = 0;
    combat_event_stats.punish_finalized_whiff_opponent_count = 0;
    combat_event_stats.punish_finalized_interrupted_self_count = 0;
    combat_event_stats.punish_finalized_interrupted_opponent_count = 0;
    combat_event_stats.punish_active_whiff_self_count = 0;
    combat_event_stats.punish_active_whiff_opponent_count = 0;
    combat_event_stats.punish_active_interrupted_self_count = 0;
    combat_event_stats.punish_active_interrupted_opponent_count = 0;
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

static void RLCombatEvent_ClearJournal(void) {
    memset(journal_entries, 0, sizeof(journal_entries));
    journal_entry_count = 0;
    combat_event_stats.event_journal_entry_count = 0;
}

static RLCombatJournalEntry* RLCombatEvent_AppendJournalEntry(RLCombatJournalEventKind kind,
                                                              u64 event_id,
                                                              u64 run_id,
                                                              u32 episode_id) {
    RLCombatJournalEntry* entry = NULL;

    if (kind == RL_COMBAT_JOURNAL_EVENT_NONE || event_id == RL_COMBAT_EVENT_ID_NONE ||
        run_id == 0 || episode_id == 0) {
        return NULL;
    }
    if (journal_entry_count >= RL_COMBAT_EVENT_JOURNAL_ENTRY_CAP) {
        combat_event_stats.event_journal_overflow_count++;
        return NULL;
    }

    entry = &journal_entries[journal_entry_count++];
    memset(entry, 0, sizeof(*entry));
    entry->kind = kind;
    entry->event_id = event_id;
    entry->run_id = run_id;
    entry->episode_id = episode_id;
    combat_event_stats.event_journal_entry_count = journal_entry_count;
    return entry;
}

static void RLCombatEvent_JournalAttack(const RLCombatAttackEvent* event) {
    RLCombatJournalEntry* entry = NULL;

    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE ||
        event->status == RL_COMBAT_ATTACK_EVENT_EMPTY) {
        return;
    }
    entry = RLCombatEvent_AppendJournalEntry(RL_COMBAT_JOURNAL_EVENT_ATTACK,
                                             event->event_id,
                                             event->run_id,
                                             event->episode_id);
    if (entry != NULL) {
        entry->event.attack = *event;
    }
}

static void RLCombatEvent_JournalProjectile(const RLCombatProjectileEvent* event) {
    RLCombatJournalEntry* entry = NULL;

    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE ||
        event->status == RL_COMBAT_PROJECTILE_EVENT_EMPTY) {
        return;
    }
    entry = RLCombatEvent_AppendJournalEntry(RL_COMBAT_JOURNAL_EVENT_PROJECTILE,
                                             event->event_id,
                                             event->run_id,
                                             event->episode_id);
    if (entry != NULL) {
        entry->event.projectile = *event;
    }
}

static void RLCombatEvent_JournalThrow(const RLCombatThrowEvent* event) {
    RLCombatJournalEntry* entry = NULL;

    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE ||
        event->status == RL_COMBAT_THROW_EVENT_EMPTY) {
        return;
    }
    entry = RLCombatEvent_AppendJournalEntry(RL_COMBAT_JOURNAL_EVENT_THROW,
                                             event->event_id,
                                             event->run_id,
                                             event->episode_id);
    if (entry != NULL) {
        entry->event.throw_event = *event;
    }
}

static void RLCombatEvent_JournalAttribution(const RLCombatAttributionEvent* event) {
    RLCombatJournalEntry* entry = NULL;

    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE) {
        return;
    }
    entry = RLCombatEvent_AppendJournalEntry(RL_COMBAT_JOURNAL_EVENT_ATTRIBUTION,
                                             event->event_id,
                                             event->run_id,
                                             event->episode_id);
    if (entry != NULL) {
        entry->event.attribution = *event;
    }
}

static void RLCombatEvent_JournalPunish(const RLCombatPunishEvent* event) {
    RLCombatJournalEntry* entry = NULL;

    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE) {
        return;
    }
    entry = RLCombatEvent_AppendJournalEntry(RL_COMBAT_JOURNAL_EVENT_PUNISH,
                                             event->event_id,
                                             event->run_id,
                                             event->episode_id);
    if (entry != NULL) {
        entry->event.punish = *event;
    }
}

static RLCombatAttributionEdgeType
RLCombatEvent_DeriveAttributionEdgeType(const RLCombatContactMatchUpdate* update, bool projectile_clash_edge) {
    if (projectile_clash_edge) {
        return RL_COMBAT_ATTRIBUTION_EDGE_PROJECTILE_CLASH;
    }
    if (update == NULL) {
        return RL_COMBAT_ATTRIBUTION_EDGE_NONE;
    }
    if (update->target_throw_caught) {
        return RL_COMBAT_ATTRIBUTION_EDGE_THROW_CAUGHT;
    }
    if (update->target_parry_started) {
        return RL_COMBAT_ATTRIBUTION_EDGE_PARRY;
    }
    if (update->target_hp_delta) {
        return RL_COMBAT_ATTRIBUTION_EDGE_HP_DELTA;
    }
    if (update->target_stun_delta) {
        return RL_COMBAT_ATTRIBUTION_EDGE_STUN_DELTA;
    }
    if (update->target_entered_damage_state) {
        return RL_COMBAT_ATTRIBUTION_EDGE_DAMAGE_STATE;
    }
    if (update->target_block_reaction) {
        return RL_COMBAT_ATTRIBUTION_EDGE_BLOCK_REACTION;
    }
    if (update->target_entered_contact_state) {
        return RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE;
    }
    if (update->target_entered_hit_stop) {
        return RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP;
    }
    return RL_COMBAT_ATTRIBUTION_EDGE_NONE;
}

static RLCombatAttributionConfidence
RLCombatEvent_DeriveAttributionConfidence(RLCombatContactMatchSource source,
                                          RLCombatAttributionEdgeType edge_type,
                                          RLCombatAttributionFailureReason failure_reason) {
    if (failure_reason != RL_COMBAT_ATTRIBUTION_FAILURE_NONE ||
        source == RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN ||
        source == RL_COMBAT_CONTACT_MATCH_SOURCE_NONE) {
        return RL_COMBAT_ATTRIBUTION_CONFIDENCE_LOW;
    }
    switch (edge_type) {
    case RL_COMBAT_ATTRIBUTION_EDGE_HP_DELTA:
    case RL_COMBAT_ATTRIBUTION_EDGE_STUN_DELTA:
    case RL_COMBAT_ATTRIBUTION_EDGE_DAMAGE_STATE:
    case RL_COMBAT_ATTRIBUTION_EDGE_PARRY:
    case RL_COMBAT_ATTRIBUTION_EDGE_THROW_CAUGHT:
    case RL_COMBAT_ATTRIBUTION_EDGE_PROJECTILE_CLASH:
        return RL_COMBAT_ATTRIBUTION_CONFIDENCE_HIGH;
    case RL_COMBAT_ATTRIBUTION_EDGE_BLOCK_REACTION:
    case RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE:
    case RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP:
        return RL_COMBAT_ATTRIBUTION_CONFIDENCE_MEDIUM;
    case RL_COMBAT_ATTRIBUTION_EDGE_NONE:
    default:
        return RL_COMBAT_ATTRIBUTION_CONFIDENCE_NONE;
    }
}

static void RLCombatEvent_IncrementAttributionEdgeCounter(RLCombatAttributionEdgeType edge_type) {
    switch (edge_type) {
    case RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP:
        combat_event_stats.attribution_edge_hit_stop_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE:
        combat_event_stats.attribution_edge_contact_state_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_DAMAGE_STATE:
        combat_event_stats.attribution_edge_damage_state_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_HP_DELTA:
        combat_event_stats.attribution_edge_hp_delta_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_STUN_DELTA:
        combat_event_stats.attribution_edge_stun_delta_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_BLOCK_REACTION:
        combat_event_stats.attribution_edge_block_reaction_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_PARRY:
        combat_event_stats.attribution_edge_parry_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_THROW_CAUGHT:
        combat_event_stats.attribution_edge_throw_caught_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_PROJECTILE_CLASH:
        combat_event_stats.attribution_edge_projectile_clash_count++;
        break;
    case RL_COMBAT_ATTRIBUTION_EDGE_NONE:
    default:
        break;
    }
}

static bool RLCombatEvent_ProjectileEvidenceIsBlocked(const RLCombatProjectileEvent* projectile_event) {
    return projectile_event != NULL &&
           (projectile_event->result == RL_COMBAT_PROJECTILE_RESULT_BLOCKED ||
            projectile_event->saw_target_block_reaction);
}

static RLCombatDefenseResult
RLCombatEvent_DeriveDefenseResult(const RLCombatContactMatchUpdate* update,
                                  RLCombatContactMatchSource source,
                                  RLCombatAttributionEdgeType edge_type,
                                  RLCombatAttributionFailureReason failure_reason,
                                  const RLCombatProjectileEvent* projectile_event) {
    const bool explicit_block_context =
        update != NULL &&
        (update->target_block_reaction || RLCombatEvent_ProjectileEvidenceIsBlocked(projectile_event));
    const bool guarded_projectile_chip_context =
        update != NULL && source == RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE && update->target_guard &&
        update->target_hp_delta && !update->target_stun_delta && !update->target_entered_damage_state &&
        projectile_event != NULL && projectile_event->saw_target_guard;
    const bool blocked_chip_context = explicit_block_context || guarded_projectile_chip_context;

    if (failure_reason != RL_COMBAT_ATTRIBUTION_FAILURE_NONE ||
        source == RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN ||
        source == RL_COMBAT_CONTACT_MATCH_SOURCE_NONE) {
        return RL_COMBAT_DEFENSE_RESULT_UNKNOWN;
    }
    if (edge_type == RL_COMBAT_ATTRIBUTION_EDGE_PROJECTILE_CLASH) {
        return RL_COMBAT_DEFENSE_RESULT_EVADED;
    }
    if (edge_type == RL_COMBAT_ATTRIBUTION_EDGE_PARRY) {
        return RL_COMBAT_DEFENSE_RESULT_PARRY;
    }
    if (source == RL_COMBAT_CONTACT_MATCH_SOURCE_THROW ||
        edge_type == RL_COMBAT_ATTRIBUTION_EDGE_THROW_CAUGHT) {
        return RL_COMBAT_DEFENSE_RESULT_THROWN;
    }
    if (update != NULL && (update->target_hp_delta || update->target_stun_delta ||
                           update->target_entered_damage_state)) {
        return blocked_chip_context ? RL_COMBAT_DEFENSE_RESULT_BLOCKED_CHIP
                                    : RL_COMBAT_DEFENSE_RESULT_HIT;
    }
    if (edge_type == RL_COMBAT_ATTRIBUTION_EDGE_BLOCK_REACTION ||
        (explicit_block_context && (edge_type == RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE ||
                                    edge_type == RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP))) {
        return RL_COMBAT_DEFENSE_RESULT_BLOCKED;
    }
    return RL_COMBAT_DEFENSE_RESULT_UNKNOWN;
}

static void RLCombatEvent_IncrementDefenseResultCounter(RLCombatEventSide target_side,
                                                        RLCombatDefenseResult result) {
    switch (result) {
    case RL_COMBAT_DEFENSE_RESULT_HIT:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_hit_self_count,
                                           &combat_event_stats.defense_hit_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_BLOCKED:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_blocked_self_count,
                                           &combat_event_stats.defense_blocked_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_BLOCKED_CHIP:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_blocked_chip_self_count,
                                           &combat_event_stats.defense_blocked_chip_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_PARRY:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_parry_self_count,
                                           &combat_event_stats.defense_parry_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_THROWN:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_thrown_self_count,
                                           &combat_event_stats.defense_thrown_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_EVADED:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_evaded_self_count,
                                           &combat_event_stats.defense_evaded_opponent_count);
        break;
    case RL_COMBAT_DEFENSE_RESULT_UNKNOWN:
    case RL_COMBAT_DEFENSE_RESULT_NONE:
    default:
        RLCombatEvent_IncrementSideCounter(target_side,
                                           &combat_event_stats.defense_unknown_self_count,
                                           &combat_event_stats.defense_unknown_opponent_count);
        break;
    }
}

static RLCombatDefenseTargetState RLCombatEvent_DeriveDefenseTargetState(const RLCombatContactMatchUpdate* update) {
    if (update == NULL) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_UNKNOWN;
    }
    if (update->target_throw_caught) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_THROW_CAUGHT;
    }
    if (update->target_block_reaction) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_BLOCKSTUN;
    }
    if (update->target_entered_damage_state || update->target_hp_delta || update->target_stun_delta) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_HITSTUN;
    }
    if (update->target_airborne) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_AIR;
    }
    if (update->target_attack_state_active) {
        return RL_COMBAT_DEFENSE_TARGET_STATE_ATTACKING;
    }
    return RL_COMBAT_DEFENSE_TARGET_STATE_NEUTRAL;
}

static void RLCombatEvent_IncrementDefenseContextCounters(const RLCombatAttributionEvent* event) {
    if (event == NULL) {
        return;
    }
    if (event->target_guard) {
        RLCombatEvent_IncrementSideCounter(event->target_side,
                                           &combat_event_stats.defense_context_guard_self_count,
                                           &combat_event_stats.defense_context_guard_opponent_count);
    }
    if (event->target_block_reaction) {
        RLCombatEvent_IncrementSideCounter(event->target_side,
                                           &combat_event_stats.defense_context_block_reaction_self_count,
                                           &combat_event_stats.defense_context_block_reaction_opponent_count);
    }
    if (event->target_parry_started) {
        RLCombatEvent_IncrementSideCounter(event->target_side,
                                           &combat_event_stats.defense_context_parry_self_count,
                                           &combat_event_stats.defense_context_parry_opponent_count);
    }
    if (event->target_throw_caught) {
        RLCombatEvent_IncrementSideCounter(event->target_side,
                                           &combat_event_stats.defense_context_throw_caught_self_count,
                                           &combat_event_stats.defense_context_throw_caught_opponent_count);
    }
}

static RLCombatPunishReason RLCombatEvent_PunishReasonForAttackResult(RLCombatAttackEventResult result) {
    switch (result) {
    case RL_COMBAT_ATTACK_RESULT_WHIFF:
        return RL_COMBAT_PUNISH_REASON_WHIFF;
    case RL_COMBAT_ATTACK_RESULT_INTERRUPTED:
        return RL_COMBAT_PUNISH_REASON_INTERRUPTED;
    case RL_COMBAT_ATTACK_RESULT_PENDING:
    case RL_COMBAT_ATTACK_RESULT_UNKNOWN:
    default:
        return RL_COMBAT_PUNISH_REASON_NONE;
    }
}

static void RLCombatEvent_RememberPunishableAttack(const RLCombatAttackEvent* attack) {
    RLCombatPunishableAttackCandidate* candidate = NULL;
    RLCombatPunishReason reason = RL_COMBAT_PUNISH_REASON_NONE;

    if (attack == NULL || attack->status != RL_COMBAT_ATTACK_EVENT_FINALIZED) {
        return;
    }
    reason = RLCombatEvent_PunishReasonForAttackResult(attack->result);
    if (reason == RL_COMBAT_PUNISH_REASON_NONE) {
        return;
    }
    candidate = RLCombatEvent_PunishableAttackForSide(attack->side);
    if (candidate == NULL) {
        return;
    }

    memset(candidate, 0, sizeof(*candidate));
    candidate->valid = true;
    candidate->event_id = attack->event_id;
    candidate->run_id = attack->run_id;
    candidate->episode_id = attack->episode_id;
    candidate->end_frame = attack->end_frame;
    candidate->end_decision_id = attack->end_decision_id;
    candidate->side = attack->side;
    candidate->reason = reason;
}

static bool RLCombatEvent_AttributionCanPunish(const RLCombatAttributionEvent* event) {
    if (event == NULL || event->failure_reason != RL_COMBAT_ATTRIBUTION_FAILURE_NONE ||
        event->confidence != RL_COMBAT_ATTRIBUTION_CONFIDENCE_HIGH || event->source_event_id == RL_COMBAT_EVENT_ID_NONE) {
        return false;
    }
    return event->defense_result == RL_COMBAT_DEFENSE_RESULT_HIT ||
           event->defense_result == RL_COMBAT_DEFENSE_RESULT_THROWN;
}

static void RLCombatEvent_IncrementPunishSourceCounter(RLCombatEventSide punisher_side,
                                                       RLCombatContactMatchSource source_family) {
    switch (source_family) {
    case RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK:
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_source_attack_self_count,
                                           &combat_event_stats.punish_source_attack_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE:
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_source_projectile_self_count,
                                           &combat_event_stats.punish_source_projectile_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_THROW:
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_source_throw_self_count,
                                           &combat_event_stats.punish_source_throw_opponent_count);
        break;
    case RL_COMBAT_CONTACT_MATCH_SOURCE_NONE:
    case RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN:
    default:
        break;
    }
}

static void RLCombatEvent_RecordPunishEvent(const RLCombatAttributionEvent* attribution,
                                            u64 punished_attack_event_id,
                                            RLCombatEventSide punished_side,
                                            RLCombatPunishReason reason,
                                            RLCombatPunishPath path) {
    RLCombatPunishEvent* event = NULL;

    if (attribution == NULL || attribution->run_id == 0 || attribution->episode_id == 0 ||
        punished_attack_event_id == RL_COMBAT_EVENT_ID_NONE || reason == RL_COMBAT_PUNISH_REASON_NONE ||
        path == RL_COMBAT_PUNISH_PATH_NONE) {
        return;
    }

    event = &punish_ring.events[punish_ring.cursor];
    memset(event, 0, sizeof(*event));
    event->event_id = RLCombatEvent_AllocateEventId();
    event->source_event_id = attribution->source_event_id;
    event->punished_attack_event_id = punished_attack_event_id;
    event->run_id = attribution->run_id;
    event->episode_id = attribution->episode_id;
    event->decision_id = attribution->decision_id;
    event->frame_id = attribution->frame_id;
    event->punisher_side = attribution->source_side;
    event->punished_side = punished_side;
    event->source_family = attribution->source_family;
    event->reason = reason;
    event->path = path;

    RLCombatEvent_JournalPunish(event);
    punish_ring.cursor = (punish_ring.cursor + 1u) % RL_COMBAT_PUNISH_EVENT_RING_CAP;
}

static void RLCombatEvent_IncrementPunishCounters(RLCombatEventSide punisher_side,
                                                  RLCombatPunishReason reason,
                                                  RLCombatContactMatchSource source_family,
                                                  bool active_fallback) {
    RLCombatEvent_IncrementSideCounter(punisher_side,
                                       &combat_event_stats.punish_candidate_self_count,
                                       &combat_event_stats.punish_candidate_opponent_count);
    if (active_fallback) {
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_active_candidate_self_count,
                                           &combat_event_stats.punish_active_candidate_opponent_count);
    } else {
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_finalized_candidate_self_count,
                                           &combat_event_stats.punish_finalized_candidate_opponent_count);
    }
    if (reason == RL_COMBAT_PUNISH_REASON_WHIFF) {
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_whiff_self_count,
                                           &combat_event_stats.punish_whiff_opponent_count);
        if (active_fallback) {
            RLCombatEvent_IncrementSideCounter(punisher_side,
                                               &combat_event_stats.punish_active_whiff_self_count,
                                               &combat_event_stats.punish_active_whiff_opponent_count);
        } else {
            RLCombatEvent_IncrementSideCounter(punisher_side,
                                               &combat_event_stats.punish_finalized_whiff_self_count,
                                               &combat_event_stats.punish_finalized_whiff_opponent_count);
        }
    } else if (reason == RL_COMBAT_PUNISH_REASON_INTERRUPTED) {
        RLCombatEvent_IncrementSideCounter(punisher_side,
                                           &combat_event_stats.punish_interrupted_self_count,
                                           &combat_event_stats.punish_interrupted_opponent_count);
        if (active_fallback) {
            RLCombatEvent_IncrementSideCounter(punisher_side,
                                               &combat_event_stats.punish_active_interrupted_self_count,
                                               &combat_event_stats.punish_active_interrupted_opponent_count);
        } else {
            RLCombatEvent_IncrementSideCounter(punisher_side,
                                               &combat_event_stats.punish_finalized_interrupted_self_count,
                                               &combat_event_stats.punish_finalized_interrupted_opponent_count);
        }
    }
    RLCombatEvent_IncrementPunishSourceCounter(punisher_side, source_family);
}

static bool RLCombatEvent_AttackHasStrongTargetDamageEvidence(const RLCombatAttackEvent* attack) {
    return attack != NULL &&
           (attack->saw_target_damage_state || attack->saw_target_hp_delta || attack->saw_target_stun_delta);
}

static const RLCombatAttackEvent* RLCombatEvent_FindActivePunishableAttackForSide(u64 run_id,
                                                                                  u32 episode_id,
                                                                                  RLCombatEventSide side,
                                                                                  u32 frame_id) {
    const RLCombatAttackEventRing* ring = RLCombatEvent_ConstRingForSide(side);
    const RLCombatAttackEvent* best = NULL;
    u32 best_age = ~0u;

    if (ring == NULL) {
        return NULL;
    }

    for (u32 i = 0; i < RL_COMBAT_ATTACK_EVENT_RING_CAP; i++) {
        const RLCombatAttackEvent* attack = &ring->events[i];
        u32 age = 0;
        if (attack->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || attack->run_id != run_id ||
            attack->episode_id != episode_id || attack->side != side || attack->projectile_like ||
            attack->saw_projectile || RLCombatEvent_AttackHasStrongTargetDamageEvidence(attack)) {
            continue;
        }
        age = RLCombatEvent_FrameAge(frame_id, attack->start_frame);
        if (age <= RL_COMBAT_ATTACK_MAX_PENDING_FRAMES && age < best_age) {
            best = attack;
            best_age = age;
        }
    }

    return best;
}

static RLCombatPunishReason RLCombatEvent_ActivePunishReason(const RLCombatAttackEvent* attack,
                                                             const RLCombatAttributionEvent* event) {
    const u32 age =
        (attack != NULL && event != NULL) ? RLCombatEvent_FrameAge(event->frame_id, attack->start_frame) : 0;

    if (attack != NULL && attack->whiff_eligible && age >= RL_COMBAT_ATTACK_MIN_WHIFF_FRAMES) {
        return RL_COMBAT_PUNISH_REASON_WHIFF;
    }
    return RL_COMBAT_PUNISH_REASON_INTERRUPTED;
}

static bool RLCombatEvent_TryRecordActivePunishCandidate(const RLCombatAttributionEvent* event) {
    const RLCombatAttackEvent* attack = NULL;
    u64* last_punished_id = NULL;
    RLCombatPunishReason reason = RL_COMBAT_PUNISH_REASON_NONE;

    if (event == NULL) {
        return false;
    }

    attack = RLCombatEvent_FindActivePunishableAttackForSide(event->run_id,
                                                            event->episode_id,
                                                            event->target_side,
                                                            event->frame_id);
    if (attack == NULL || event->source_side != RLCombatEvent_OppositeSide(attack->side)) {
        return false;
    }

    last_punished_id = RLCombatEvent_LastPunishedAttackIdForSide(attack->side);
    if (last_punished_id != NULL && *last_punished_id == attack->event_id) {
        return false;
    }

    reason = RLCombatEvent_ActivePunishReason(attack, event);
    RLCombatEvent_RecordPunishEvent(event,
                                    attack->event_id,
                                    attack->side,
                                    reason,
                                    RL_COMBAT_PUNISH_PATH_ACTIVE_ATTACK_FALLBACK);
    RLCombatEvent_IncrementPunishCounters(event->source_side, reason, event->source_family, true);
    if (last_punished_id != NULL) {
        *last_punished_id = attack->event_id;
    }
    return true;
}

static void RLCombatEvent_TryRecordPunishCandidate(const RLCombatAttributionEvent* event) {
    RLCombatPunishableAttackCandidate* candidate = NULL;
    u64* last_punished_id = NULL;
    u32 age = 0;

    if (!RLCombatEvent_AttributionCanPunish(event)) {
        return;
    }

    candidate = RLCombatEvent_PunishableAttackForSide(event->target_side);
    if (candidate == NULL || !candidate->valid || candidate->run_id != event->run_id ||
        candidate->episode_id != event->episode_id || candidate->side != event->target_side ||
        event->source_side != RLCombatEvent_OppositeSide(candidate->side) ||
        event->frame_id < candidate->end_frame) {
        RLCombatEvent_TryRecordActivePunishCandidate(event);
        return;
    }

    age = RLCombatEvent_FrameAge(event->frame_id, candidate->end_frame);
    if (candidate->reason == RL_COMBAT_PUNISH_REASON_WHIFF ||
        age > RL_COMBAT_PUNISH_CANDIDATE_WINDOW_FRAMES) {
        candidate->valid = false;
        RLCombatEvent_TryRecordActivePunishCandidate(event);
        return;
    }

    last_punished_id = RLCombatEvent_LastPunishedAttackIdForSide(candidate->side);
    if (last_punished_id != NULL && *last_punished_id == candidate->event_id) {
        candidate->valid = false;
        return;
    }
    RLCombatEvent_RecordPunishEvent(event,
                                    candidate->event_id,
                                    candidate->side,
                                    candidate->reason,
                                    RL_COMBAT_PUNISH_PATH_FINALIZED_WINDOW);
    RLCombatEvent_IncrementPunishCounters(event->source_side, candidate->reason, event->source_family, false);
    if (last_punished_id != NULL) {
        *last_punished_id = candidate->event_id;
    }
    candidate->valid = false;
}

static void RLCombatEvent_RecordAttributionEvent(const RLCombatContactMatchUpdate* update,
                                                 RLCombatContactMatchSource source,
                                                 u64 source_event_id,
                                                 RLCombatAttributionEdgeType edge_type,
                                                 RLCombatAttributionFailureReason failure_reason,
                                                 const RLCombatProjectileEvent* projectile_event) {
    RLCombatAttributionEvent* event = NULL;
    RLCombatDefenseResult defense_result = RL_COMBAT_DEFENSE_RESULT_NONE;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->source_side == RL_COMBAT_EVENT_SIDE_NONE) {
        return;
    }

    event = &attribution_ring.events[attribution_ring.cursor];
    if (event->event_id != RL_COMBAT_EVENT_ID_NONE) {
        combat_event_stats.attribution_ring_overwrite_count++;
    }

    memset(event, 0, sizeof(*event));
    event->event_id = RLCombatEvent_AllocateEventId();
    event->source_event_id = source_event_id;
    event->run_id = update->run_id;
    event->episode_id = update->episode_id;
    event->decision_id = update->decision_id;
    event->frame_id = update->frame_id;
    event->source_side = update->source_side;
    event->target_side = RLCombatEvent_OppositeSide(update->source_side);
    event->source_family = source;
    event->edge_type = edge_type;
    event->failure_reason = failure_reason;
    event->confidence = RLCombatEvent_DeriveAttributionConfidence(source, edge_type, failure_reason);
    defense_result =
        RLCombatEvent_DeriveDefenseResult(update, source, edge_type, failure_reason, projectile_event);
    event->defense_result = defense_result;
    event->actual_guard_state_at_contact = update->target_guard_state;
    event->target_state = RLCombatEvent_DeriveDefenseTargetState(update);
    event->target_policy_action_id = update->target_policy_action_id;
    event->target_policy_sub_action_id = update->target_policy_sub_action_id;
    event->target_policy_action_step = update->target_policy_action_step;
    event->target_routine_1 = update->target_routine_1;
    event->target_routine_2 = update->target_routine_2;
    event->target_guard = update->target_guard;
    event->target_block_reaction = update->target_block_reaction;
    event->target_parry_started = update->target_parry_started;
    event->target_throw_caught = update->target_throw_caught;
    event->target_airborne = update->target_airborne;
    event->target_attack_state_active = update->target_attack_state_active;
    event->target_contact_reaction_state = update->target_contact_reaction_state;
    event->target_entered_hit_stop = update->target_entered_hit_stop;
    event->target_entered_contact_state = update->target_entered_contact_state;
    event->target_entered_damage_state = update->target_entered_damage_state;
    event->target_hp_delta = update->target_hp_delta;
    event->target_stun_delta = update->target_stun_delta;

    attribution_ring.cursor = (attribution_ring.cursor + 1u) % RL_COMBAT_ATTRIBUTION_EVENT_RING_CAP;
    combat_event_stats.attribution_recorded_count++;
    RLCombatEvent_IncrementAttributionEdgeCounter(edge_type);
    RLCombatEvent_IncrementDefenseResultCounter(event->target_side, defense_result);
    RLCombatEvent_IncrementDefenseContextCounters(event);
    RLCombatEvent_TryRecordPunishCandidate(event);
    if (failure_reason != RL_COMBAT_ATTRIBUTION_FAILURE_NONE) {
        combat_event_stats.attribution_failure_count++;
    }
    RLCombatEvent_JournalAttribution(event);
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
    RLCombatEvent_RememberPunishableAttack(event);
    RLCombatEvent_JournalAttack(event);
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
    RLCombatEvent_JournalProjectile(event);
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
    RLCombatEvent_JournalThrow(event);
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
    memset(&attribution_ring, 0, sizeof(attribution_ring));
    memset(&punish_ring, 0, sizeof(punish_ring));
    RLCombatEvent_ClearJournal();
    memset(&self_punishable_attack, 0, sizeof(self_punishable_attack));
    memset(&opponent_punishable_attack, 0, sizeof(opponent_punishable_attack));
    self_last_punished_attack_event_id = RL_COMBAT_EVENT_ID_NONE;
    opponent_last_punished_attack_event_id = RL_COMBAT_EVENT_ID_NONE;
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
    event->saw_opposing_projectile |= (u8)(update->opposing_projectile_active != 0);
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
    const RLCombatAttackEvent* attack_event = NULL;
    const RLCombatProjectileEvent* projectile_event = NULL;
    bool projectile_candidate = false;
    bool projectile_clash_edge = false;
    bool throw_candidate = false;
    bool attack_candidate = false;
    RLCombatContactMatchSource source = RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN;
    RLCombatAttributionFailureReason failure_reason = RL_COMBAT_ATTRIBUTION_FAILURE_NONE;
    RLCombatAttributionEdgeType edge_type = RL_COMBAT_ATTRIBUTION_EDGE_NONE;
    u64 source_event_id = RL_COMBAT_EVENT_ID_NONE;

    if (update == NULL || update->run_id == 0 || update->episode_id == 0 ||
        update->source_side == RL_COMBAT_EVENT_SIDE_NONE) {
        return false;
    }

    if (combat_event_stats.run_id != update->run_id || combat_event_stats.episode_id != update->episode_id) {
        RLCombatEvent_BeginEpisode(update->run_id, update->episode_id);
    }

    projectile_event = RLCombatEvent_FindProjectileCandidateForSide(update->run_id,
                                                                    update->episode_id,
                                                                    update->source_side,
                                                                    update->frame_id);
    projectile_candidate =
        (update->projectile_candidate || projectile_event != NULL);
    projectile_clash_edge = RLCombatEvent_HasProjectileClashEdgeForSide(update->run_id,
                                                                        update->episode_id,
                                                                        update->source_side,
                                                                        update->frame_id);
    throw_candidate = (update->throw_candidate ||
                       RLCombatEvent_HasThrowCandidateForSide(update->run_id,
                                                             update->episode_id,
                                                             update->source_side,
                                                             update->frame_id));
    attack_event =
        RLCombatEvent_FindAttackCandidateForSide(update->run_id, update->episode_id, update->source_side);
    attack_candidate =
        (update->attack_candidate || attack_event != NULL);

    if (!RLCombatEvent_ContactMatchHasTargetEdge(update,
                                                 projectile_candidate,
                                                 throw_candidate,
                                                 attack_candidate,
                                                 projectile_clash_edge)) {
        return false;
    }
    edge_type = RLCombatEvent_DeriveAttributionEdgeType(update, projectile_clash_edge);

    if (projectile_candidate) {
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE;
        source_event_id = projectile_event != NULL ? projectile_event->event_id : RL_COMBAT_EVENT_ID_NONE;
    } else if (throw_candidate) {
        if (!RLCombatEvent_TryMarkThrowContactMatchForSide(update->run_id,
                                                          update->episode_id,
                                                          update->source_side,
                                                          update->frame_id,
                                                          &source_event_id)) {
            return false;
        }
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_THROW;
    } else if (attack_candidate) {
        source = RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK;
        source_event_id = attack_event != NULL ? attack_event->event_id : RL_COMBAT_EVENT_ID_NONE;
    } else {
        failure_reason = RL_COMBAT_ATTRIBUTION_FAILURE_NO_SOURCE_CANDIDATE;
    }

    if (RLCombatEvent_ShouldSuppressWeakAttackAttribution(update, source, edge_type, projectile_clash_edge)) {
        return false;
    }

    RLCombatEvent_IncrementContactMatchCounter(update->source_side, source);
    RLCombatEvent_RecordAttributionEvent(update, source, source_event_id, edge_type, failure_reason, projectile_event);
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

static const char* RLCombatEvent_SideText(RLCombatEventSide side) {
    switch (side) {
    case RL_COMBAT_EVENT_SIDE_SELF:
        return "self";
    case RL_COMBAT_EVENT_SIDE_OPPONENT:
        return "opponent";
    case RL_COMBAT_EVENT_SIDE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_AttackStatusText(RLCombatAttackEventStatus status) {
    switch (status) {
    case RL_COMBAT_ATTACK_EVENT_ACTIVE:
        return "active";
    case RL_COMBAT_ATTACK_EVENT_FINALIZED:
        return "finalized";
    case RL_COMBAT_ATTACK_EVENT_EMPTY:
    default:
        return "empty";
    }
}

static const char* RLCombatEvent_AttackResultText(RLCombatAttackEventResult result) {
    switch (result) {
    case RL_COMBAT_ATTACK_RESULT_WHIFF:
        return "whiff";
    case RL_COMBAT_ATTACK_RESULT_INTERRUPTED:
        return "interrupted";
    case RL_COMBAT_ATTACK_RESULT_UNKNOWN:
        return "unknown";
    case RL_COMBAT_ATTACK_RESULT_PENDING:
    default:
        return "pending";
    }
}

static const char* RLCombatEvent_AttackFinalizeReasonText(RLCombatAttackFinalizeReason reason) {
    switch (reason) {
    case RL_COMBAT_ATTACK_FINALIZE_EXPLICIT:
        return "explicit";
    case RL_COMBAT_ATTACK_FINALIZE_EPISODE_FLUSH:
        return "episode_flush";
    case RL_COMBAT_ATTACK_FINALIZE_SUPERSEDED_BY_NEW_START:
        return "superseded_by_new_start";
    case RL_COMBAT_ATTACK_FINALIZE_BASIC_WHIFF_WINDOW:
        return "basic_whiff_window";
    case RL_COMBAT_ATTACK_FINALIZE_BASIC_INTERRUPTED:
        return "basic_interrupted";
    case RL_COMBAT_ATTACK_FINALIZE_BASIC_UNKNOWN_TIMEOUT:
        return "basic_unknown_timeout";
    case RL_COMBAT_ATTACK_FINALIZE_PROJECTILE_CLAIMED:
        return "projectile_claimed";
    case RL_COMBAT_ATTACK_FINALIZE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_ProjectileStatusText(RLCombatProjectileEventStatus status) {
    switch (status) {
    case RL_COMBAT_PROJECTILE_EVENT_ACTIVE:
        return "active";
    case RL_COMBAT_PROJECTILE_EVENT_FINALIZED:
        return "finalized";
    case RL_COMBAT_PROJECTILE_EVENT_EMPTY:
    default:
        return "empty";
    }
}

static const char* RLCombatEvent_ProjectileResultText(RLCombatProjectileResult result) {
    switch (result) {
    case RL_COMBAT_PROJECTILE_RESULT_HIT:
        return "hit";
    case RL_COMBAT_PROJECTILE_RESULT_BLOCKED:
        return "blocked";
    case RL_COMBAT_PROJECTILE_RESULT_EXPIRED:
        return "expired";
    case RL_COMBAT_PROJECTILE_RESULT_UNKNOWN:
        return "unknown";
    case RL_COMBAT_PROJECTILE_RESULT_PENDING:
    default:
        return "pending";
    }
}

static const char* RLCombatEvent_ProjectileFinalizeReasonText(RLCombatProjectileFinalizeReason reason) {
    switch (reason) {
    case RL_COMBAT_PROJECTILE_FINALIZE_EPISODE_FLUSH:
        return "episode_flush";
    case RL_COMBAT_PROJECTILE_FINALIZE_DISAPPEARED:
        return "disappeared";
    case RL_COMBAT_PROJECTILE_FINALIZE_CONTACT:
        return "contact";
    case RL_COMBAT_PROJECTILE_FINALIZE_TIMEOUT:
        return "timeout";
    case RL_COMBAT_PROJECTILE_FINALIZE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_ThrowStatusText(RLCombatThrowEventStatus status) {
    switch (status) {
    case RL_COMBAT_THROW_EVENT_ACTIVE:
        return "active";
    case RL_COMBAT_THROW_EVENT_FINALIZED:
        return "finalized";
    case RL_COMBAT_THROW_EVENT_EMPTY:
    default:
        return "empty";
    }
}

static const char* RLCombatEvent_ThrowResultText(RLCombatThrowResult result) {
    switch (result) {
    case RL_COMBAT_THROW_RESULT_SUCCESS:
        return "success";
    case RL_COMBAT_THROW_RESULT_WHIFF:
        return "whiff";
    case RL_COMBAT_THROW_RESULT_UNKNOWN:
        return "unknown";
    case RL_COMBAT_THROW_RESULT_PENDING:
    default:
        return "pending";
    }
}

static const char* RLCombatEvent_ThrowFinalizeReasonText(RLCombatThrowFinalizeReason reason) {
    switch (reason) {
    case RL_COMBAT_THROW_FINALIZE_EPISODE_FLUSH:
        return "episode_flush";
    case RL_COMBAT_THROW_FINALIZE_SUPERSEDED_BY_NEW_START:
        return "superseded_by_new_start";
    case RL_COMBAT_THROW_FINALIZE_TARGET_CAUGHT:
        return "target_caught";
    case RL_COMBAT_THROW_FINALIZE_WHIFF_WINDOW:
        return "whiff_window";
    case RL_COMBAT_THROW_FINALIZE_UNKNOWN_TIMEOUT:
        return "unknown_timeout";
    case RL_COMBAT_THROW_FINALIZE_TECH_ESCAPE:
        return "tech_escape";
    case RL_COMBAT_THROW_FINALIZE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_SourceFamilyText(RLCombatContactMatchSource source) {
    switch (source) {
    case RL_COMBAT_CONTACT_MATCH_SOURCE_ATTACK:
        return "attack";
    case RL_COMBAT_CONTACT_MATCH_SOURCE_PROJECTILE:
        return "projectile";
    case RL_COMBAT_CONTACT_MATCH_SOURCE_THROW:
        return "throw";
    case RL_COMBAT_CONTACT_MATCH_SOURCE_UNKNOWN:
        return "unknown";
    case RL_COMBAT_CONTACT_MATCH_SOURCE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_AttributionEdgeText(RLCombatAttributionEdgeType edge_type) {
    switch (edge_type) {
    case RL_COMBAT_ATTRIBUTION_EDGE_HIT_STOP:
        return "hit_stop";
    case RL_COMBAT_ATTRIBUTION_EDGE_CONTACT_STATE:
        return "contact_state";
    case RL_COMBAT_ATTRIBUTION_EDGE_DAMAGE_STATE:
        return "damage_state";
    case RL_COMBAT_ATTRIBUTION_EDGE_HP_DELTA:
        return "hp_delta";
    case RL_COMBAT_ATTRIBUTION_EDGE_STUN_DELTA:
        return "stun_delta";
    case RL_COMBAT_ATTRIBUTION_EDGE_BLOCK_REACTION:
        return "block_reaction";
    case RL_COMBAT_ATTRIBUTION_EDGE_PARRY:
        return "parry";
    case RL_COMBAT_ATTRIBUTION_EDGE_THROW_CAUGHT:
        return "throw_caught";
    case RL_COMBAT_ATTRIBUTION_EDGE_PROJECTILE_CLASH:
        return "projectile_clash";
    case RL_COMBAT_ATTRIBUTION_EDGE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_ConfidenceText(RLCombatAttributionConfidence confidence) {
    switch (confidence) {
    case RL_COMBAT_ATTRIBUTION_CONFIDENCE_LOW:
        return "low";
    case RL_COMBAT_ATTRIBUTION_CONFIDENCE_MEDIUM:
        return "medium";
    case RL_COMBAT_ATTRIBUTION_CONFIDENCE_HIGH:
        return "high";
    case RL_COMBAT_ATTRIBUTION_CONFIDENCE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_AttributionFailureText(RLCombatAttributionFailureReason reason) {
    switch (reason) {
    case RL_COMBAT_ATTRIBUTION_FAILURE_NO_SOURCE_CANDIDATE:
        return "no_source_candidate";
    case RL_COMBAT_ATTRIBUTION_FAILURE_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_DefenseResultText(RLCombatDefenseResult result) {
    switch (result) {
    case RL_COMBAT_DEFENSE_RESULT_HIT:
        return "hit";
    case RL_COMBAT_DEFENSE_RESULT_BLOCKED:
        return "blocked";
    case RL_COMBAT_DEFENSE_RESULT_BLOCKED_CHIP:
        return "blocked_chip";
    case RL_COMBAT_DEFENSE_RESULT_PARRY:
        return "parry";
    case RL_COMBAT_DEFENSE_RESULT_THROWN:
        return "thrown";
    case RL_COMBAT_DEFENSE_RESULT_EVADED:
        return "evaded";
    case RL_COMBAT_DEFENSE_RESULT_UNKNOWN:
        return "unknown";
    case RL_COMBAT_DEFENSE_RESULT_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_GuardStateText(RLCombatDefenseGuardState guard_state) {
    switch (guard_state) {
    case RL_COMBAT_DEFENSE_GUARD_STATE_NONE:
        return "none";
    case RL_COMBAT_DEFENSE_GUARD_STATE_STAND:
        return "stand";
    case RL_COMBAT_DEFENSE_GUARD_STATE_CROUCH:
        return "crouch";
    case RL_COMBAT_DEFENSE_GUARD_STATE_AIR:
        return "air";
    case RL_COMBAT_DEFENSE_GUARD_STATE_UNKNOWN:
    default:
        return "unknown";
    }
}

static const char* RLCombatEvent_TargetStateText(RLCombatDefenseTargetState target_state) {
    switch (target_state) {
    case RL_COMBAT_DEFENSE_TARGET_STATE_NEUTRAL:
        return "neutral";
    case RL_COMBAT_DEFENSE_TARGET_STATE_BLOCKSTUN:
        return "blockstun";
    case RL_COMBAT_DEFENSE_TARGET_STATE_HITSTUN:
        return "hitstun";
    case RL_COMBAT_DEFENSE_TARGET_STATE_AIR:
        return "air";
    case RL_COMBAT_DEFENSE_TARGET_STATE_ATTACKING:
        return "attacking";
    case RL_COMBAT_DEFENSE_TARGET_STATE_THROW_CAUGHT:
        return "throw_caught";
    case RL_COMBAT_DEFENSE_TARGET_STATE_UNKNOWN:
    default:
        return "unknown";
    }
}

static const char* RLCombatEvent_PunishReasonText(RLCombatPunishReason reason) {
    switch (reason) {
    case RL_COMBAT_PUNISH_REASON_WHIFF:
        return "whiff";
    case RL_COMBAT_PUNISH_REASON_INTERRUPTED:
        return "interrupted";
    case RL_COMBAT_PUNISH_REASON_NONE:
    default:
        return "none";
    }
}

static const char* RLCombatEvent_PunishPathText(RLCombatPunishPath path) {
    switch (path) {
    case RL_COMBAT_PUNISH_PATH_FINALIZED_WINDOW:
        return "finalized_window";
    case RL_COMBAT_PUNISH_PATH_ACTIVE_ATTACK_FALLBACK:
        return "active_attack_fallback";
    case RL_COMBAT_PUNISH_PATH_NONE:
    default:
        return "none";
    }
}

static bool RLCombatEvent_WriteJournalLine(char* line_buf,
                                           size_t line_buf_size,
                                           RLCombatEventJournalLineWriter writer,
                                           void* userdata,
                                           u32* emitted,
                                           u32* errors,
                                           const char* fmt,
                                           ...) {
    va_list args;
    int written = 0;
    size_t line_len = 0;

    if (line_buf == NULL || line_buf_size == 0 || writer == NULL || fmt == NULL) {
        if (errors != NULL) {
            (*errors)++;
        }
        return false;
    }

    va_start(args, fmt);
    written = vsnprintf(line_buf, line_buf_size, fmt, args);
    va_end(args);
    if (written < 0 || (size_t)written >= line_buf_size) {
        line_buf[0] = '\0';
        if (errors != NULL) {
            (*errors)++;
        }
        return true;
    }

    line_len = (size_t)written;
    if (!writer(line_buf, line_len, userdata)) {
        if (errors != NULL) {
            (*errors)++;
        }
        return false;
    }
    if (emitted != NULL) {
        (*emitted)++;
    }
    return true;
}

static bool RLCombatEvent_EmitAttackJournalLine(const RLCombatAttackEvent* event,
                                                char* line_buf,
                                                size_t line_buf_size,
                                                RLCombatEventJournalLineWriter writer,
                                                void* userdata,
                                                u32* emitted,
                                                u32* errors) {
    if (event == NULL || event->status == RL_COMBAT_ATTACK_EVENT_EMPTY) {
        return true;
    }
    return RLCombatEvent_WriteJournalLine(
        line_buf,
        line_buf_size,
        writer,
        userdata,
        emitted,
        errors,
        "{\"combat_event_schema_version\":%u,\"event_kind\":\"attack\",\"event_id\":%" PRIu64
        ",\"run_id\":%" PRIu64 ",\"episode_id\":%u,\"side\":\"%s\","
        "\"status\":\"%s\",\"status_code\":%u,\"result\":\"%s\",\"result_code\":%u,"
        "\"finalize_reason\":\"%s\",\"finalize_reason_code\":%u,"
        "\"start_decision_id\":%u,\"start_frame\":%u,\"end_decision_id\":%u,\"end_frame\":%u,"
        "\"projectile_like\":%u,\"whiff_eligible\":%u,"
        "\"engine_action_id\":%u,\"engine_sub_action_id\":%u,\"engine_current_attack\":%u,"
        "\"engine_label_source\":%u,\"policy_action_id\":%u,\"policy_sub_action_id\":%u,"
        "\"policy_action_step\":%u}\n",
        RL_COMBAT_EVENT_JOURNAL_SCHEMA_VERSION,
        (uint64_t)event->event_id,
        (uint64_t)event->run_id,
        event->episode_id,
        RLCombatEvent_SideText(event->side),
        RLCombatEvent_AttackStatusText(event->status),
        (unsigned int)event->status,
        RLCombatEvent_AttackResultText(event->result),
        (unsigned int)event->result,
        RLCombatEvent_AttackFinalizeReasonText(event->finalize_reason),
        (unsigned int)event->finalize_reason,
        event->start_decision_id,
        event->start_frame,
        event->end_decision_id,
        event->end_frame,
        event->projectile_like,
        event->whiff_eligible,
        event->engine_action_id,
        event->engine_sub_action_id,
        event->engine_current_attack,
        event->engine_label_source,
        event->policy_action_id,
        event->policy_sub_action_id,
        event->policy_action_step);
}

static bool RLCombatEvent_EmitProjectileJournalLine(const RLCombatProjectileEvent* event,
                                                    char* line_buf,
                                                    size_t line_buf_size,
                                                    RLCombatEventJournalLineWriter writer,
                                                    void* userdata,
                                                    u32* emitted,
                                                    u32* errors) {
    if (event == NULL || event->status == RL_COMBAT_PROJECTILE_EVENT_EMPTY) {
        return true;
    }
    return RLCombatEvent_WriteJournalLine(
        line_buf,
        line_buf_size,
        writer,
        userdata,
        emitted,
        errors,
        "{\"combat_event_schema_version\":%u,\"event_kind\":\"projectile\",\"event_id\":%" PRIu64
        ",\"parent_attack_event_id\":%" PRIu64 ",\"run_id\":%" PRIu64
        ",\"episode_id\":%u,\"owner_side\":\"%s\","
        "\"status\":\"%s\",\"status_code\":%u,\"result\":\"%s\",\"result_code\":%u,"
        "\"finalize_reason\":\"%s\",\"finalize_reason_code\":%u,"
        "\"start_decision_id\":%u,\"start_frame\":%u,\"end_decision_id\":%u,\"end_frame\":%u,"
        "\"spawn_rel_x\":%d,\"spawn_rel_y\":%d,\"spawn_vel_x\":%d,\"spawn_time_to_self\":%d,"
        "\"last_rel_x\":%d,\"last_rel_y\":%d,\"last_vel_x\":%d,\"last_time_to_self\":%d,"
        "\"engine_action_id\":%u,\"engine_sub_action_id\":%u,\"engine_label_source\":%u,"
        "\"saw_opposing_projectile\":%u}\n",
        RL_COMBAT_EVENT_JOURNAL_SCHEMA_VERSION,
        (uint64_t)event->event_id,
        (uint64_t)event->parent_attack_event_id,
        (uint64_t)event->run_id,
        event->episode_id,
        RLCombatEvent_SideText(event->owner_side),
        RLCombatEvent_ProjectileStatusText(event->status),
        (unsigned int)event->status,
        RLCombatEvent_ProjectileResultText(event->result),
        (unsigned int)event->result,
        RLCombatEvent_ProjectileFinalizeReasonText(event->finalize_reason),
        (unsigned int)event->finalize_reason,
        event->start_decision_id,
        event->start_frame,
        event->end_decision_id,
        event->end_frame,
        event->spawn_rel_x,
        event->spawn_rel_y,
        event->spawn_vel_x,
        event->spawn_time_to_self,
        event->last_rel_x,
        event->last_rel_y,
        event->last_vel_x,
        event->last_time_to_self,
        event->engine_action_id,
        event->engine_sub_action_id,
        event->engine_label_source,
        event->saw_opposing_projectile);
}

static bool RLCombatEvent_EmitThrowJournalLine(const RLCombatThrowEvent* event,
                                               char* line_buf,
                                               size_t line_buf_size,
                                               RLCombatEventJournalLineWriter writer,
                                               void* userdata,
                                               u32* emitted,
                                               u32* errors) {
    if (event == NULL || event->status == RL_COMBAT_THROW_EVENT_EMPTY) {
        return true;
    }
    return RLCombatEvent_WriteJournalLine(
        line_buf,
        line_buf_size,
        writer,
        userdata,
        emitted,
        errors,
        "{\"combat_event_schema_version\":%u,\"event_kind\":\"throw\",\"event_id\":%" PRIu64
        ",\"run_id\":%" PRIu64 ",\"episode_id\":%u,\"owner_side\":\"%s\","
        "\"status\":\"%s\",\"status_code\":%u,\"result\":\"%s\",\"result_code\":%u,"
        "\"finalize_reason\":\"%s\",\"finalize_reason_code\":%u,"
        "\"start_decision_id\":%u,\"start_frame\":%u,\"end_decision_id\":%u,\"end_frame\":%u,"
        "\"current_attack\":%u,\"kind_of_waza\":%u,"
        "\"saw_opposing_throw\":%u,\"saw_throw_escape\":%u,\"saw_target_caught\":%u}\n",
        RL_COMBAT_EVENT_JOURNAL_SCHEMA_VERSION,
        (uint64_t)event->event_id,
        (uint64_t)event->run_id,
        event->episode_id,
        RLCombatEvent_SideText(event->owner_side),
        RLCombatEvent_ThrowStatusText(event->status),
        (unsigned int)event->status,
        RLCombatEvent_ThrowResultText(event->result),
        (unsigned int)event->result,
        RLCombatEvent_ThrowFinalizeReasonText(event->finalize_reason),
        (unsigned int)event->finalize_reason,
        event->start_decision_id,
        event->start_frame,
        event->end_decision_id,
        event->end_frame,
        event->current_attack,
        event->kind_of_waza,
        event->saw_opposing_throw,
        event->saw_throw_escape,
        event->saw_target_caught);
}

static bool RLCombatEvent_EmitAttributionJournalLine(const RLCombatAttributionEvent* event,
                                                     char* line_buf,
                                                     size_t line_buf_size,
                                                     RLCombatEventJournalLineWriter writer,
                                                     void* userdata,
                                                     u32* emitted,
                                                     u32* errors) {
    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE) {
        return true;
    }
    return RLCombatEvent_WriteJournalLine(
        line_buf,
        line_buf_size,
        writer,
        userdata,
        emitted,
        errors,
        "{\"combat_event_schema_version\":%u,\"event_kind\":\"attribution\",\"event_id\":%" PRIu64
        ",\"source_event_id\":%" PRIu64 ",\"run_id\":%" PRIu64
        ",\"episode_id\":%u,\"decision_id\":%u,\"frame_id\":%u,"
        "\"source_side\":\"%s\",\"target_side\":\"%s\","
        "\"source_family\":\"%s\",\"source_family_code\":%u,"
        "\"edge_type\":\"%s\",\"edge_type_code\":%u,"
        "\"confidence\":\"%s\",\"confidence_code\":%u,"
        "\"failure_reason\":\"%s\",\"failure_reason_code\":%u,"
        "\"defense_result\":\"%s\",\"defense_result_code\":%u,"
        "\"actual_guard_state\":\"%s\",\"actual_guard_state_code\":%u,"
        "\"target_state\":\"%s\",\"target_state_code\":%u,"
        "\"target_policy_action_id\":%u,\"target_policy_sub_action_id\":%u,"
        "\"target_policy_action_step\":%u,\"target_routine_1\":%u,\"target_routine_2\":%u,"
        "\"target_guard\":%u,\"target_block_reaction\":%u,\"target_parry_started\":%u,"
        "\"target_throw_caught\":%u,\"target_airborne\":%u,\"target_attack_state_active\":%u,"
        "\"target_hp_delta\":%u,\"target_stun_delta\":%u}\n",
        RL_COMBAT_EVENT_JOURNAL_SCHEMA_VERSION,
        (uint64_t)event->event_id,
        (uint64_t)event->source_event_id,
        (uint64_t)event->run_id,
        event->episode_id,
        event->decision_id,
        event->frame_id,
        RLCombatEvent_SideText(event->source_side),
        RLCombatEvent_SideText(event->target_side),
        RLCombatEvent_SourceFamilyText(event->source_family),
        (unsigned int)event->source_family,
        RLCombatEvent_AttributionEdgeText(event->edge_type),
        (unsigned int)event->edge_type,
        RLCombatEvent_ConfidenceText(event->confidence),
        (unsigned int)event->confidence,
        RLCombatEvent_AttributionFailureText(event->failure_reason),
        (unsigned int)event->failure_reason,
        RLCombatEvent_DefenseResultText(event->defense_result),
        (unsigned int)event->defense_result,
        RLCombatEvent_GuardStateText(event->actual_guard_state_at_contact),
        (unsigned int)event->actual_guard_state_at_contact,
        RLCombatEvent_TargetStateText(event->target_state),
        (unsigned int)event->target_state,
        event->target_policy_action_id,
        event->target_policy_sub_action_id,
        event->target_policy_action_step,
        event->target_routine_1,
        event->target_routine_2,
        event->target_guard,
        event->target_block_reaction,
        event->target_parry_started,
        event->target_throw_caught,
        event->target_airborne,
        event->target_attack_state_active,
        event->target_hp_delta,
        event->target_stun_delta);
}

static bool RLCombatEvent_EmitPunishJournalLine(const RLCombatPunishEvent* event,
                                                char* line_buf,
                                                size_t line_buf_size,
                                                RLCombatEventJournalLineWriter writer,
                                                void* userdata,
                                                u32* emitted,
                                                u32* errors) {
    if (event == NULL || event->event_id == RL_COMBAT_EVENT_ID_NONE) {
        return true;
    }
    return RLCombatEvent_WriteJournalLine(
        line_buf,
        line_buf_size,
        writer,
        userdata,
        emitted,
        errors,
        "{\"combat_event_schema_version\":%u,\"event_kind\":\"punish\",\"event_id\":%" PRIu64
        ",\"source_event_id\":%" PRIu64 ",\"punished_attack_event_id\":%" PRIu64
        ",\"run_id\":%" PRIu64 ",\"episode_id\":%u,\"decision_id\":%u,\"frame_id\":%u,"
        "\"punisher_side\":\"%s\",\"punished_side\":\"%s\","
        "\"source_family\":\"%s\",\"source_family_code\":%u,"
        "\"reason\":\"%s\",\"reason_code\":%u,\"path\":\"%s\",\"path_code\":%u}\n",
        RL_COMBAT_EVENT_JOURNAL_SCHEMA_VERSION,
        (uint64_t)event->event_id,
        (uint64_t)event->source_event_id,
        (uint64_t)event->punished_attack_event_id,
        (uint64_t)event->run_id,
        event->episode_id,
        event->decision_id,
        event->frame_id,
        RLCombatEvent_SideText(event->punisher_side),
        RLCombatEvent_SideText(event->punished_side),
        RLCombatEvent_SourceFamilyText(event->source_family),
        (unsigned int)event->source_family,
        RLCombatEvent_PunishReasonText(event->reason),
        (unsigned int)event->reason,
        RLCombatEvent_PunishPathText(event->path),
        (unsigned int)event->path);
}

u32 RLCombatEvent_EmitJournal(u64 run_id,
                              u32 episode_id,
                              char* line_buf,
                              size_t line_buf_size,
                              RLCombatEventJournalLineWriter writer,
                              void* userdata,
                              u32* out_error_count) {
    u64 last_event_id = 0;
    u32 matching = 0;
    u32 processed = 0;
    u32 emitted = 0;
    u32 errors = 0;

    if (out_error_count != NULL) {
        *out_error_count = 0;
    }
    if (run_id == 0 || episode_id == 0 || line_buf == NULL || line_buf_size == 0 || writer == NULL) {
        if (out_error_count != NULL) {
            *out_error_count = 1;
        }
        return 0;
    }

    for (u32 i = 0; i < journal_entry_count; i++) {
        const RLCombatJournalEntry* entry = &journal_entries[i];
        if (entry->run_id == run_id && entry->episode_id == episode_id &&
            entry->kind != RL_COMBAT_JOURNAL_EVENT_NONE) {
            matching++;
        }
    }

    while (processed < matching) {
        const RLCombatJournalEntry* best = NULL;

        for (u32 i = 0; i < journal_entry_count; i++) {
            const RLCombatJournalEntry* entry = &journal_entries[i];
            if (entry->run_id != run_id || entry->episode_id != episode_id ||
                entry->kind == RL_COMBAT_JOURNAL_EVENT_NONE || entry->event_id <= last_event_id) {
                continue;
            }
            if (best == NULL || entry->event_id < best->event_id) {
                best = entry;
            }
        }

        if (best == NULL) {
            break;
        }

        switch (best->kind) {
        case RL_COMBAT_JOURNAL_EVENT_ATTACK:
            if (!RLCombatEvent_EmitAttackJournalLine(&best->event.attack,
                                                     line_buf,
                                                     line_buf_size,
                                                     writer,
                                                     userdata,
                                                     &emitted,
                                                     &errors)) {
                goto done;
            }
            break;
        case RL_COMBAT_JOURNAL_EVENT_PROJECTILE:
            if (!RLCombatEvent_EmitProjectileJournalLine(&best->event.projectile,
                                                         line_buf,
                                                         line_buf_size,
                                                         writer,
                                                         userdata,
                                                         &emitted,
                                                         &errors)) {
                goto done;
            }
            break;
        case RL_COMBAT_JOURNAL_EVENT_THROW:
            if (!RLCombatEvent_EmitThrowJournalLine(&best->event.throw_event,
                                                    line_buf,
                                                    line_buf_size,
                                                    writer,
                                                    userdata,
                                                    &emitted,
                                                    &errors)) {
                goto done;
            }
            break;
        case RL_COMBAT_JOURNAL_EVENT_ATTRIBUTION:
            if (!RLCombatEvent_EmitAttributionJournalLine(&best->event.attribution,
                                                          line_buf,
                                                          line_buf_size,
                                                          writer,
                                                          userdata,
                                                          &emitted,
                                                          &errors)) {
                goto done;
            }
            break;
        case RL_COMBAT_JOURNAL_EVENT_PUNISH:
            if (!RLCombatEvent_EmitPunishJournalLine(&best->event.punish,
                                                     line_buf,
                                                     line_buf_size,
                                                     writer,
                                                     userdata,
                                                     &emitted,
                                                     &errors)) {
                goto done;
            }
            break;
        case RL_COMBAT_JOURNAL_EVENT_NONE:
        default:
            break;
        }

        last_event_id = best->event_id;
        processed++;
    }

done:
    if (out_error_count != NULL) {
        *out_error_count = errors;
    }
    return emitted;
}

const RLCombatEventStats* RLCombatEvent_GetStats(void) {
    RLCombatEvent_RefreshActiveStats();
    return &combat_event_stats;
}
