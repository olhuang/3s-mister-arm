#include "rl/rl_combat_event.h"

#include <string.h>

typedef struct RLCombatAttackEventRing {
    RLCombatAttackEvent events[RL_COMBAT_ATTACK_EVENT_RING_CAP];
    u32 cursor;
} RLCombatAttackEventRing;

static RLCombatAttackEventRing self_attack_ring;
static RLCombatAttackEventRing opponent_attack_ring;
static RLCombatEventStats combat_event_stats;

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
    if (reason == RL_COMBAT_ATTACK_FINALIZE_EPISODE_FLUSH && result == RL_COMBAT_ATTACK_RESULT_UNKNOWN) {
        combat_event_stats.attack_unknown_flush_count++;
    }
    if (reason == RL_COMBAT_ATTACK_FINALIZE_SUPERSEDED_BY_NEW_START &&
        result == RL_COMBAT_ATTACK_RESULT_UNKNOWN) {
        combat_event_stats.attack_unknown_rollover_count++;
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
    }

    if (combat_event_stats.run_id != run_id) {
        RLCombatEvent_ResetRun(run_id);
    }

    combat_event_stats.run_id = run_id;
    combat_event_stats.episode_id = episode_id;
    RLCombatEvent_ClearRings();
}

void RLCombatEvent_FlushEpisode(u64 run_id, u32 episode_id, u32 frame_id, u32 decision_id) {
    RLCombatAttackEventRing* rings[] = { &self_attack_ring, &opponent_attack_ring };

    combat_event_stats.episode_flush_count++;
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
        return NULL;
    }

    if (combat_event_stats.run_id != start->run_id || combat_event_stats.episode_id != start->episode_id) {
        RLCombatEvent_BeginEpisode(start->run_id, start->episode_id);
    }

    ring = RLCombatEvent_RingForSide(start->side);
    event = RLCombatEvent_FindReusableSlot(ring);
    if (event == NULL) {
        combat_event_stats.attack_dropped_start_count++;
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
    event->policy_action_id = start->policy_action_id;
    event->policy_sub_action_id = start->policy_sub_action_id;
    event->policy_action_step = start->policy_action_step;

    combat_event_stats.attack_started_count++;
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
        if (event->status != RL_COMBAT_ATTACK_EVENT_ACTIVE || event->run_id != run_id ||
            event->episode_id != episode_id || event->side != side) {
            continue;
        }
        if (RLCombatEvent_FinalizeSlot(event, result, reason, frame_id, decision_id)) {
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
