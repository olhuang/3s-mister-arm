#include "rl/rl_session.h"

#include "rl/rl_net.h"
#include "rl/rl_observation.h"
#include "port/paths.h"
#include "sf33rd/AcrSDK/common/pad.h"
#include "main.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/stun.h"
#include "sf33rd/Source/Game/engine/workuser.h"
#include "sf33rd/Source/Game/system/work_sys.h"

#include <SDL3/SDL.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef enum RLTestMovement {
    RL_TEST_MOVEMENT_FORWARD = 0,
    RL_TEST_MOVEMENT_BACK = 1,
    RL_TEST_MOVEMENT_JUMP_FORWARD = 2,
    RL_TEST_MOVEMENT_DOWN_BACK = 3,
} RLTestMovement;

typedef struct RLLocalFakeAction {
    RLMoveIntent move;
    u16 attacks;
    u16 hold_frames;
} RLLocalFakeAction;

typedef struct RLQueuedRemoteAction {
    bool valid;
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
    u16 action_wire;
    u32 model_version;
} RLQueuedRemoteAction;

typedef struct RLExpectedRemoteDecision {
    bool valid;
    bool fulfilled;
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
} RLExpectedRemoteDecision;

typedef struct RLSeenRemoteDecision {
    bool valid;
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
} RLSeenRemoteDecision;

typedef struct RLRemoteActiveAction {
    bool valid;
    u8 move_intent;
    u16 attack_bits;
    u8 movement_remaining_frames;
    u8 attack_remaining_frames;
} RLRemoteActiveAction;

typedef struct RLDecisionLedgerEntry {
    bool valid;
    bool active;
    bool exported;
    bool done;
    bool was_executed;
    u64 run_id;
    u32 episode_id;
    u32 decision_id;
    u8 round_num;
    s16 start_self_hp;
    s16 start_opp_hp;
    s16 final_self_hp;
    s16 final_opp_hp;
    u8 agent_character_id;
    u8 opponent_character_id;
    u32 obs_frame;
    u32 target_frame;
    u32 execution_frame_actual;
    u32 model_version_expected;
    u32 model_version_requested;
    u32 model_version_executed;
    u16 requested_action_wire;
    u16 executed_action_wire;
    s16 delta_self_hp;
    s16 delta_opp_hp;
    s16 delta_self_stun;
    s16 delta_opp_stun;
    s16 delta_self_x;
    s16 delta_self_y;
    s16 delta_opp_x;
    s16 delta_opp_y;
    s16 delta_self_forward;
    s16 delta_opp_forward;
    s16 obs_abs_dx;
    s16 obs_abs_dy;
    s16 obs_self_front_edge_dist;
    s16 obs_self_back_edge_dist;
    s16 obs_opp_front_edge_dist;
    s16 obs_opp_back_edge_dist;
    u8 obs_opp_in_front;
    u8 obs_self_routine_attack_state;
    u8 obs_opp_routine_attack_state;
    u8 obs_self_contact_reaction_state;
    u8 obs_opp_contact_reaction_state;
    u8 executed_move_intent;
    u16 executed_attack_bits;
    u8 execution_source;
    u8 terminal_reason;
    u8 self_attack_state_seen;
    u8 self_attack_started;
    u8 self_attack_code_changed;
    u8 self_attack_counter_started;
    u8 self_attack_routine_started;
    u8 opp_attack_started;
    u8 opp_attack_code_changed;
    u8 opp_attack_counter_started;
    u8 opp_attack_routine_started;
    u8 self_airborne_seen;
    u8 opp_airborne_seen;
    u8 self_airborne_started;
    u8 opp_airborne_started;
    u8 self_entered_hit_stop;
    u8 opp_entered_hit_stop;
    u8 self_entered_contact_state;
    u8 opp_entered_contact_state;
    u8 self_entered_damage_state;
    u8 opp_entered_damage_state;
    u8 self_throw_started;
    u8 opp_throw_caught_started;
    u8 self_throw_seen;
    u8 opp_throw_caught_seen;
    u8 requested_movement_succeeded;
    u8 requested_attack_entered_state;
    u8 requested_attack_made_contact;
    u8 requested_attack_likely_whiffed;
    u8 requested_attack_input_started;
    u8 requested_attack_became_active;
    u8 observed_attack_state_started;
    u8 observed_attack_code_changed;
    u8 observed_attack_counter_started;
    u8 overlay_attack_event_finalized;
    u8 overlay_attack_contact;
    u8 overlay_attack_whiff;
    u32 overlay_attack_active_count;
    u32 overlay_attack_contact_count;
    u32 overlay_attack_whiff_count;
    u8 requested_jump_started;

    float reward_accum;
} RLDecisionLedgerEntry;

static const RLLocalFakeAction kLocalFakeAgentSequence[] = {
    { RL_MOVE_FORWARD, 0, 30 },
    { RL_MOVE_NEUTRAL, SWK_WEST, 8 },
    { RL_MOVE_DOWN_BACK, 0, 24 },
    { RL_MOVE_NEUTRAL, 0, 8 },
    { RL_MOVE_UP_FORWARD, SWK_NORTH, 10 },
    { RL_MOVE_BACK, 0, 18 },
    { RL_MOVE_NEUTRAL, 0, 8 },
};

#define RL_REMOTE_QUEUE_CAP 16u
#define RL_REMOTE_EXPECTED_CAP 16u
#define RL_REMOTE_SEEN_CAP 32u
#define RL_DECISION_LEDGER_CAP 128u


static u16 local_fake_action_index;
static u16 local_fake_action_frame;
static u8 active_round_num;
static bool remote_runtime_initialized;
static u32 next_episode_id = 1;
static RLRemoteDebugState remote_debug;
static RLQueuedRemoteAction remote_queue[RL_REMOTE_QUEUE_CAP];
static RLExpectedRemoteDecision expected_decisions[RL_REMOTE_EXPECTED_CAP];
static RLSeenRemoteDecision seen_decisions[RL_REMOTE_SEEN_CAP];
static RLDecisionLedgerEntry decision_ledger[RL_DECISION_LEDGER_CAP];
static RLRemoteActiveAction active_remote_action;
static RLDecisionLedgerEntry* active_ledger_entry;
static bool overlay_attack_event_pending;
static bool overlay_attack_event_contact_seen;
static u32 overlay_attack_event_seq;
static u32 overlay_attack_event_logged_seq;
static u16 last_executed_action_wire;
static u32 last_executed_model_version;
static u32 transition_batch_episode_id = UINT32_MAX;
static char* transition_batch_payload;
static size_t transition_batch_payload_len;
static size_t transition_batch_payload_cap;
static u32 transition_batch_row_count;
static bool hp_damage_baseline_valid;
static s16 last_self_damage_total;
static s16 last_opp_damage_total;
static void RLSession_ResetTransitionBatch();
static RLActionContext action_context = {
    .last_executed_move_intent = RL_MOVE_NEUTRAL,
    .last_executed_attack_bits = 0,
    .next_scheduled_move_intent = RL_MOVE_NEUTRAL,
    .next_scheduled_attack_bits = 0,
    .frames_until_next_action = 255,
};

static void RLSession_ClearActionContext() {
    action_context.last_executed_move_intent = RL_MOVE_NEUTRAL;
    action_context.last_executed_attack_bits = 0;
    action_context.next_scheduled_move_intent = RL_MOVE_NEUTRAL;
    action_context.next_scheduled_attack_bits = 0;
    action_context.frames_until_next_action = 255;
}

static void RLSession_ClearScheduledActionContext() {
    action_context.next_scheduled_move_intent = RL_MOVE_NEUTRAL;
    action_context.next_scheduled_attack_bits = 0;
    action_context.frames_until_next_action = 255;
}

static u64 RLSession_FallbackRunId() {
    const u64 now = (u64)time(NULL);
    const u64 ticks = (u64)SDL_GetTicksNS();
    return (now << 32) ^ ticks;
}

static u64 RLSession_LoadNextRunId() {
    char* logs_dir = NULL;
    char* state_path = NULL;
    const char* pref_path = Paths_GetPrefPath();
    SDL_IOStream* io = NULL;
    char buf[64];
    u64 previous = 0;
    u64 next = 0;
    bool persisted = false;

    if (pref_path == NULL) {
        return RLSession_FallbackRunId();
    }

    SDL_asprintf(&logs_dir, "%slogs", pref_path);
    if (logs_dir == NULL) {
        return RLSession_FallbackRunId();
    }
    SDL_CreateDirectory(logs_dir);
    SDL_asprintf(&state_path, "%s/rl-run-state.txt", logs_dir);
    if (state_path == NULL) {
        SDL_free(logs_dir);
        return RLSession_FallbackRunId();
    }

    io = SDL_IOFromFile(state_path, "r");
    if (io != NULL) {
        const size_t read = SDL_ReadIO(io, buf, sizeof(buf) - 1);
        buf[read] = '\0';
        previous = (u64)strtoull(buf, NULL, 10);
        SDL_CloseIO(io);
    }

    next = previous + 1;
    if (next == 0) {
        next = RLSession_FallbackRunId();
    }

    io = SDL_IOFromFile(state_path, "w");
    if (io != NULL) {
        const int written = SDL_snprintf(buf, sizeof(buf), "%" PRIu64 "\n", next);
        if (written > 0) {
            SDL_WriteIO(io, buf, (size_t)written);
            persisted = true;
        }
        SDL_CloseIO(io);
    }

    SDL_free(state_path);
    SDL_free(logs_dir);
    return persisted ? next : RLSession_FallbackRunId();
}

static void RLSession_StartNewEpisode() {
    remote_debug.episode_id = next_episode_id++;
    if (next_episode_id == 0) {
        next_episode_id = 1;
    }
    remote_debug.next_decision_id = 0;
    active_round_num = Round_num;
    hp_damage_baseline_valid = false;
    last_self_damage_total = 0;
    last_opp_damage_total = 0;
}

static bool RLSession_RoundEpisodeChanged() {
    return active_round_num != Round_num;
}

static u8 RLSession_DecisionIntervalFrames() {
    const int frames = configuration.remote_rl_agent.decision_interval_frames;
    return (u8)((frames > 0) ? frames : 4);
}

static u8 RLSession_ActionHoldFrames() {
    const int frames = configuration.remote_rl_agent.action_hold_frames;
    return (u8)((frames > 0) ? frames : 4);
}

static u8 RLSession_DelayFrames() {
    const int frames = configuration.remote_rl_agent.delay_frames;
    return (u8)((frames > 0) ? frames : 4);
}

static bool RLSession_IsRoundBattleActive() {
    return Allow_a_battle_f != 0 && Demo_Time_Stop == 0;
}

static bool RLSession_CanOverrideGameplayInput() {
    return RLSession_IsActive() && Mode_Type == MODE_VERSUS && mpp_w.inGame && Play_Mode == 1 && Game_pause == 0 &&
           RLSession_IsRoundBattleActive();
}

static bool RLSession_RemoteControlEnabled() {
    const RLNetState* net = RLNet_GetState();
    return RLSession_IsActive() && net->enabled;
}

static void RLSession_ClearRemoteQueue() {
    memset(remote_queue, 0, sizeof(remote_queue));
    memset(expected_decisions, 0, sizeof(expected_decisions));
    memset(seen_decisions, 0, sizeof(seen_decisions));
    memset(decision_ledger, 0, sizeof(decision_ledger));
    memset(&active_remote_action, 0, sizeof(active_remote_action));
    active_ledger_entry = NULL;
    last_executed_action_wire = 0;
    last_executed_model_version = 0;
    remote_debug.queue_depth = 0;
}

static void RLSession_ResetOverlayAttackCounters() {
    remote_debug.episode_attack_active_count = 0;
    remote_debug.episode_attack_contact_count = 0;
    remote_debug.episode_attack_whiff_count = 0;
    remote_debug.last_overlay_attack_contact = 0;
    remote_debug.last_overlay_attack_whiff = 0;
    overlay_attack_event_pending = false;
    overlay_attack_event_contact_seen = false;
    overlay_attack_event_seq = 0;
    overlay_attack_event_logged_seq = 0;
}

static void RLSession_FinalizeOverlayAttackEvent() {
    if (!overlay_attack_event_pending) {
        return;
    }
    remote_debug.episode_attack_active_count++;
    if (overlay_attack_event_contact_seen) {
        remote_debug.episode_attack_contact_count++;
        remote_debug.last_overlay_attack_contact = 1;
        remote_debug.last_overlay_attack_whiff = 0;
    } else {
        remote_debug.episode_attack_whiff_count++;
        remote_debug.last_overlay_attack_contact = 0;
        remote_debug.last_overlay_attack_whiff = 1;
    }
    overlay_attack_event_seq++;
    overlay_attack_event_pending = false;
    overlay_attack_event_contact_seen = false;
}

static void RLSession_ResetRemoteRuntime(bool reset_counters) {
    RLSession_ClearRemoteQueue();
    RLSession_ClearActionContext();
    RLSession_ResetTransitionBatch();
    active_round_num = Round_num;
    remote_runtime_initialized = false;
    if (reset_counters) {
        memset(&remote_debug, 0, sizeof(remote_debug));
    }
    RLSession_ResetOverlayAttackCounters();
}

bool RLSession_IsActive() {
    return configuration.remote_rl_agent.enabled;
}

s16 RLSession_AgentPlayerIndex() {
    const int player = configuration.remote_rl_agent.player;
    return (player == 2) ? 1 : 0;
}

s16 RLSession_OpponentPlayerIndex() {
    return RLSession_AgentPlayerIndex() ^ 1;
}

bool RLSession_OpponentUsesHumanInput() {
    return configuration.remote_rl_agent.human_opponent;
}

const char* RLSession_TestMovementLabel() {
    switch (configuration.remote_rl_agent.test_movement) {
    case RL_TEST_MOVEMENT_BACK:
        return "B";
    case RL_TEST_MOVEMENT_JUMP_FORWARD:
        return "JF";
    case RL_TEST_MOVEMENT_DOWN_BACK:
        return "DB";
    case RL_TEST_MOVEMENT_FORWARD:
    default:
        return "F";
    }
}

const RLActionContext* RLSession_GetActionContext() {
    return &action_context;
}

const RLRemoteDebugState* RLSession_GetRemoteDebugState() {
    return &remote_debug;
}

u32 RLSession_GetCurrentFrameId() {
    return remote_debug.frame_id;
}

static u16 RLSession_ForwardDirectionForPlayer(s16 player) {
    const s16 opponent = player ^ 1;

    if (plw[player].wu.position_x < plw[opponent].wu.position_x) {
        return SWK_RIGHT;
    }
    if (plw[player].wu.position_x > plw[opponent].wu.position_x) {
        return SWK_LEFT;
    }

    return (plw[player].wu.rl_flag == 0) ? SWK_LEFT : SWK_RIGHT;
}

static u16 RLSession_BackDirectionForPlayer(s16 player) {
    return (plw[player].wu.rl_flag == 0) ? SWK_RIGHT : SWK_LEFT;
}

static u16 RLSession_MapMoveIntentToSWKey(s16 player, RLMoveIntent move) {
    const u16 forward = RLSession_ForwardDirectionForPlayer(player);
    const u16 back = RLSession_BackDirectionForPlayer(player);

    switch (move) {
    case RL_MOVE_UP:
        return SWK_UP;
    case RL_MOVE_DOWN:
        return SWK_DOWN;
    case RL_MOVE_BACK:
        return back;
    case RL_MOVE_FORWARD:
        return forward;
    case RL_MOVE_UP_BACK:
        return (u16)(SWK_UP | back);
    case RL_MOVE_UP_FORWARD:
        return (u16)(SWK_UP | forward);
    case RL_MOVE_DOWN_BACK:
        return (u16)(SWK_DOWN | back);
    case RL_MOVE_DOWN_FORWARD:
        return (u16)(SWK_DOWN | forward);
    case RL_MOVE_NEUTRAL:
    default:
        return 0;
    }
}

static u16 RLSession_MapTestMovementToSWKey(s16 player) {
    switch (configuration.remote_rl_agent.test_movement) {
    case RL_TEST_MOVEMENT_BACK:
        return RLSession_MapMoveIntentToSWKey(player, RL_MOVE_BACK);
    case RL_TEST_MOVEMENT_JUMP_FORWARD:
        return RLSession_MapMoveIntentToSWKey(player, RL_MOVE_UP_FORWARD);
    case RL_TEST_MOVEMENT_DOWN_BACK:
        return RLSession_MapMoveIntentToSWKey(player, RL_MOVE_DOWN_BACK);
    case RL_TEST_MOVEMENT_FORWARD:
    default:
        return RLSession_MapMoveIntentToSWKey(player, RL_MOVE_FORWARD);
    }
}

static u8 RLSession_DecodeMoveIntent(u16 action_wire) {
    const u8 move = (u8)(action_wire & 0x000Fu);
    return (move <= RL_MOVE_DOWN_FORWARD) ? move : RL_MOVE_NEUTRAL;
}

static u16 RLSession_DecodeAttackBits(u16 action_wire) {
    return (u16)(action_wire & (u16)SWK_ATTACKS & 0xFFF0u);
}

static u16 RLSession_EncodeActionWire(u8 move_intent, u16 attack_bits) {
    return (u16)((move_intent & 0x000Fu) | (attack_bits & 0xFFF0u));
}


static const char* RLSession_TerminalReasonLabel(u8 terminal_reason) {
    switch (terminal_reason) {
    case 1:
        return "decision_replaced";
    case 2:
        return "episode_end";
    case 3:
        return "not_terminal";
    default:
        return "unknown";
    }
}

static bool RLSession_MoveIntentRequestsMovement(u8 move_intent) {
    return move_intent != RL_MOVE_NEUTRAL;
}

static void RLSession_UpdateDerivedOutcomeFields(RLDecisionLedgerEntry* entry) {
    const u8 requested_move = RLSession_DecodeMoveIntent(entry->requested_action_wire);
    const u16 requested_attacks = RLSession_DecodeAttackBits(entry->requested_action_wire);

    entry->requested_movement_succeeded = 0;
    entry->requested_attack_entered_state = 0;
    entry->requested_attack_made_contact = 0;
    entry->requested_attack_likely_whiffed = 0;
    entry->requested_attack_input_started = 0;
    entry->requested_attack_became_active = 0;
    entry->observed_attack_state_started = 0;
    entry->observed_attack_code_changed = 0;
    entry->observed_attack_counter_started = 0;
    entry->overlay_attack_event_finalized = 0;
    entry->overlay_attack_contact = 0;
    entry->overlay_attack_whiff = 0;
    entry->overlay_attack_active_count = remote_debug.episode_attack_active_count;
    entry->overlay_attack_contact_count = remote_debug.episode_attack_contact_count;
    entry->overlay_attack_whiff_count = remote_debug.episode_attack_whiff_count;
    entry->requested_jump_started = 0;

    if (entry->was_executed && RLSession_MoveIntentRequestsMovement(requested_move)) {
        switch (requested_move) {
        case RL_MOVE_FORWARD:
            entry->requested_movement_succeeded = (u8)(entry->delta_self_forward > 0);
            break;
        case RL_MOVE_BACK:
            entry->requested_movement_succeeded = (u8)(entry->delta_self_forward < 0);
            break;
        case RL_MOVE_UP:
            entry->requested_movement_succeeded = (u8)(entry->self_airborne_seen || entry->delta_self_y != 0);
            break;
        case RL_MOVE_UP_FORWARD:
            entry->requested_movement_succeeded =
                (u8)((entry->self_airborne_seen || entry->delta_self_y != 0) && entry->delta_self_forward > 0);
            break;
        case RL_MOVE_UP_BACK:
            entry->requested_movement_succeeded =
                (u8)((entry->self_airborne_seen || entry->delta_self_y != 0) && entry->delta_self_forward < 0);
            break;
        case RL_MOVE_DOWN:
        case RL_MOVE_DOWN_FORWARD:
        case RL_MOVE_DOWN_BACK:
            entry->requested_movement_succeeded = 0;
            break;
        case RL_MOVE_NEUTRAL:
        default:
            entry->requested_movement_succeeded = 0;
            break;
        }
        if (requested_move == RL_MOVE_UP || requested_move == RL_MOVE_UP_FORWARD || requested_move == RL_MOVE_UP_BACK) {
            entry->requested_jump_started = entry->self_airborne_started;
        }
    }

    if (entry->was_executed && requested_attacks != 0) {
        entry->requested_attack_input_started = (u8)(entry->executed_attack_bits != 0);
        entry->requested_attack_became_active = entry->self_attack_counter_started;
        entry->observed_attack_state_started = entry->self_attack_started;
        entry->observed_attack_code_changed = entry->self_attack_code_changed;
        entry->observed_attack_counter_started = entry->self_attack_counter_started;
        entry->requested_attack_entered_state = entry->self_attack_state_seen;
        entry->requested_attack_made_contact =
            (u8)(entry->self_entered_hit_stop || entry->opp_entered_hit_stop ||
                 entry->opp_entered_contact_state || entry->opp_entered_damage_state ||
                 entry->delta_opp_hp > 0 || entry->delta_opp_stun > 0);
        entry->requested_attack_likely_whiffed =
            (u8)(entry->requested_attack_became_active && !entry->requested_attack_made_contact);
    }

    if (overlay_attack_event_seq != overlay_attack_event_logged_seq) {
        entry->overlay_attack_event_finalized = 1;
        entry->overlay_attack_contact = remote_debug.last_overlay_attack_contact;
        entry->overlay_attack_whiff = remote_debug.last_overlay_attack_whiff;
        overlay_attack_event_logged_seq = overlay_attack_event_seq;
    }
}

static s16 RLSession_ClampDeltaS16(s32 value) {
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return (s16)value;
}

static s16 RLSession_ClampDamageTotal(s32 start_hp, s32 current_hp) {
    const s32 damage = start_hp - current_hp;
    if (damage <= 0) {
        return 0;
    }
    if (damage > 32767) {
        return 32767;
    }
    return (s16)damage;
}

static bool RLSession_IsRoundEndHpSync(const RLObservationV1* obs, s16 self_hp_delta, s16 opp_hp_delta) {
    if (obs == NULL) {
        return false;
    }
    return (opp_hp_delta > 64 && obs->opp_hp <= 3 && obs->delta_opp_stun > 0 && !obs->opp_throw_caught_started) ||
           (self_hp_delta > 64 && obs->self_hp <= 3 && obs->delta_self_stun > 0 && !obs->self_throw_started);
}

static s16 RLSession_ClampDistanceS16(s32 value) {
    if (value < 0) {
        value = -value;
    }
    if (value > 32767) {
        return 32767;
    }
    return (s16)value;
}

static s16 RLSession_ClampNonnegativeDistanceS16(s32 value) {
    if (value <= 0) {
        return 0;
    }
    if (value > 32767) {
        return 32767;
    }
    return (s16)value;
}

static s16 RLSession_FrontEdgeDistance(s8 facing_sign, s32 x) {
    return facing_sign < 0 ? RLSession_ClampNonnegativeDistanceS16(x - scrl)
                           : RLSession_ClampNonnegativeDistanceS16(scrr - x);
}

static s16 RLSession_BackEdgeDistance(s8 facing_sign, s32 x) {
    return facing_sign < 0 ? RLSession_ClampNonnegativeDistanceS16(scrr - x)
                           : RLSession_ClampNonnegativeDistanceS16(x - scrl);
}

static void RLSession_FillObsSpacingPayload(RLObsSpacingPayloadV1* payload, const RLObservationV1* obs) {
    s16 self;
    s16 opp;
    s32 self_x;
    s32 self_y;
    s32 opp_x;
    s32 opp_y;

    if (payload == NULL || obs == NULL) {
        return;
    }
    self = RLSession_AgentPlayerIndex();
    opp = RLSession_OpponentPlayerIndex();
    self_x = plw[self].wu.position_x;
    self_y = plw[self].wu.position_y;
    opp_x = plw[opp].wu.position_x;
    opp_y = plw[opp].wu.position_y;
    memset(payload, 0, sizeof(*payload));
    payload->payload_version = RL_OBSERVATION_SCHEMA_VERSION;
    payload->obs_abs_dx = RLSession_ClampDistanceS16(opp_x - self_x);
    payload->obs_abs_dy = RLSession_ClampDistanceS16(opp_y - self_y);
    payload->obs_self_front_edge_dist = RLSession_FrontEdgeDistance(obs->self_facing_sign, self_x);
    payload->obs_self_back_edge_dist = RLSession_BackEdgeDistance(obs->self_facing_sign, self_x);
    payload->obs_opp_front_edge_dist = RLSession_FrontEdgeDistance(obs->opp_facing_sign, opp_x);
    payload->obs_opp_back_edge_dist = RLSession_BackEdgeDistance(obs->opp_facing_sign, opp_x);
    payload->obs_opp_in_front = obs->opp_in_front ? 1u : 0u;
    payload->obs_self_routine_attack_state = obs->self_routine_attack_state ? 1u : 0u;
    payload->obs_opp_routine_attack_state = obs->opp_routine_attack_state ? 1u : 0u;
    payload->obs_self_contact_reaction_state = obs->self_contact_reaction_state ? 1u : 0u;
    payload->obs_opp_contact_reaction_state = obs->opp_contact_reaction_state ? 1u : 0u;
}

static void RLSession_CaptureObservationSpacing(RLDecisionLedgerEntry* entry, const RLObservationV1* obs) {
    RLObsSpacingPayloadV1 payload;

    if (entry == NULL || obs == NULL) {
        return;
    }
    RLSession_FillObsSpacingPayload(&payload, obs);
    entry->obs_abs_dx = payload.obs_abs_dx;
    entry->obs_abs_dy = payload.obs_abs_dy;
    entry->obs_self_front_edge_dist = payload.obs_self_front_edge_dist;
    entry->obs_self_back_edge_dist = payload.obs_self_back_edge_dist;
    entry->obs_opp_front_edge_dist = payload.obs_opp_front_edge_dist;
    entry->obs_opp_back_edge_dist = payload.obs_opp_back_edge_dist;
    entry->obs_opp_in_front = payload.obs_opp_in_front;
    entry->obs_self_routine_attack_state = payload.obs_self_routine_attack_state;
    entry->obs_opp_routine_attack_state = payload.obs_opp_routine_attack_state;
    entry->obs_self_contact_reaction_state = payload.obs_self_contact_reaction_state;
    entry->obs_opp_contact_reaction_state = payload.obs_opp_contact_reaction_state;
}

static void RLSession_AccumulateDeltaS16(s16* accum, s32 delta) {
    if (accum == NULL) {
        return;
    }
    *accum = RLSession_ClampDeltaS16((s32)(*accum) + delta);
}

static RLDecisionLedgerEntry* RLSession_FindLedgerEntry(u64 run_id, u32 episode_id, u32 decision_id) {
    for (u32 i = 0; i < RL_DECISION_LEDGER_CAP; i++) {
        if (decision_ledger[i].valid && decision_ledger[i].run_id == run_id &&
            decision_ledger[i].episode_id == episode_id &&
            decision_ledger[i].decision_id == decision_id) {
            return &decision_ledger[i];
        }
    }
    return NULL;
}

static RLDecisionLedgerEntry* RLSession_AllocLedgerEntry() {
    for (u32 i = 0; i < RL_DECISION_LEDGER_CAP; i++) {
        if (!decision_ledger[i].valid) {
            return &decision_ledger[i];
        }
    }
    for (u32 i = 0; i < RL_DECISION_LEDGER_CAP; i++) {
        if (!decision_ledger[i].active && decision_ledger[i].exported) {
            memset(&decision_ledger[i], 0, sizeof(decision_ledger[i]));
            return &decision_ledger[i];
        }
    }
    return NULL;
}

static void RLSession_ResetTransitionBatch() {
    SDL_free(transition_batch_payload);
    transition_batch_payload = NULL;
    transition_batch_payload_len = 0;
    transition_batch_payload_cap = 0;
    transition_batch_row_count = 0;
    transition_batch_episode_id = UINT32_MAX;
}

static bool RLSession_EnsureTransitionBatchCapacity(size_t extra_len) {
    const size_t needed = transition_batch_payload_len + extra_len;
    char* grown = NULL;
    size_t new_cap = transition_batch_payload_cap;

    if (needed <= transition_batch_payload_cap) {
        return true;
    }
    if (new_cap == 0) {
        new_cap = 4096;
    }
    while (new_cap < needed) {
        new_cap *= 2;
    }
    grown = (char*)SDL_realloc(transition_batch_payload, new_cap);
    if (grown == NULL) {
        return false;
    }
    transition_batch_payload = grown;
    transition_batch_payload_cap = new_cap;
    return true;
}

static int RLSession_FormatTransitionLogLine(const RLDecisionLedgerEntry* entry, char* line, size_t line_size) {
    if (entry == NULL || line == NULL || line_size == 0) {
        return -1;
    }
    return SDL_snprintf(line,
                        line_size,
                        "{\"run_id\":%" PRIu64 ",\"episode_id\":%u,\"decision_id\":%u,"
                        "\"round_num\":%u,\"obs_frame\":%u,"
                        "\"agent_character_id\":%u,\"opponent_character_id\":%u,"
                        "\"executed_action_wire\":%u,"
                        "\"delta_self_hp\":%d,\"delta_opp_hp\":%d,"
                        "\"delta_self_stun\":%d,\"delta_opp_stun\":%d,"
                        "\"delta_self_y\":%d,\"delta_opp_y\":%d,"
                        "\"delta_self_forward\":%d,\"delta_opp_forward\":%d,"
                        "\"obs_abs_dx\":%d,\"obs_abs_dy\":%d,"
                        "\"obs_self_front_edge_dist\":%d,\"obs_self_back_edge_dist\":%d,"
                        "\"obs_opp_front_edge_dist\":%d,\"obs_opp_back_edge_dist\":%d,"
                        "\"obs_opp_in_front\":%u,"
                        "\"obs_self_routine_attack_state\":%u,\"obs_opp_routine_attack_state\":%u,"
                        "\"obs_self_contact_reaction_state\":%u,\"obs_opp_contact_reaction_state\":%u,"
                        "\"final_self_hp\":%d,\"final_opp_hp\":%d,"
                        "\"model_version_executed\":%u,"
                        "\"reward_accum\":%.3f,\"done\":%s,"
                        "\"terminal_reason\":\"%s\"}\n",
                        entry->run_id,
                        entry->episode_id,
                        entry->decision_id,
                        entry->round_num,
                        entry->obs_frame,
                        entry->agent_character_id,
                        entry->opponent_character_id,
                        entry->executed_action_wire,
                        entry->delta_self_hp,
                        entry->delta_opp_hp,
                        entry->delta_self_stun,
                        entry->delta_opp_stun,
                        entry->delta_self_y,
                        entry->delta_opp_y,
                        entry->delta_self_forward,
                        entry->delta_opp_forward,
                        entry->obs_abs_dx,
                        entry->obs_abs_dy,
                        entry->obs_self_front_edge_dist,
                        entry->obs_self_back_edge_dist,
                        entry->obs_opp_front_edge_dist,
                        entry->obs_opp_back_edge_dist,
                        entry->obs_opp_in_front,
                        entry->obs_self_routine_attack_state,
                        entry->obs_opp_routine_attack_state,
                        entry->obs_self_contact_reaction_state,
                        entry->obs_opp_contact_reaction_state,
                        entry->final_self_hp,
                        entry->final_opp_hp,
                        entry->model_version_executed,
                        (double)entry->reward_accum,
                        entry->done ? "true" : "false",
                        RLSession_TerminalReasonLabel(entry->terminal_reason));
}

static void RLSession_AppendTransitionBatchLine(const RLDecisionLedgerEntry* entry, const char* line, size_t line_len) {
    if (entry == NULL || line == NULL || line_len == 0) {
        return;
    }
    if (transition_batch_episode_id == UINT32_MAX) {
        transition_batch_episode_id = entry->episode_id;
    }
    if (transition_batch_episode_id != entry->episode_id) {
        return;
    }
    if (!RLSession_EnsureTransitionBatchCapacity(line_len)) {
        return;
    }
    SDL_memcpy(transition_batch_payload + transition_batch_payload_len, line, line_len);
    transition_batch_payload_len += line_len;
    transition_batch_row_count++;
}

static void RLSession_AppendTransitionLogLine(const char* line, size_t line_len) {
    char* logs_dir = NULL;
    char* log_path = NULL;
    SDL_IOStream* io = NULL;
    const char* pref_path = NULL;

    if (line == NULL || line_len == 0) {
        return;
    }

    pref_path = Paths_GetPrefPath();
    if (pref_path == NULL) {
        return;
    }
    SDL_asprintf(&logs_dir, "%slogs", pref_path);
    SDL_CreateDirectory(logs_dir);
    SDL_asprintf(&log_path, "%s/rl-transitions.ndjson", logs_dir);
    io = SDL_IOFromFile(log_path, "a");
    if (io != NULL) {
        SDL_WriteIO(io, line, line_len);
        SDL_CloseIO(io);
    }
    SDL_free(log_path);
    SDL_free(logs_dir);
}

static void RLSession_FinalizeLedgerEntry(RLDecisionLedgerEntry* entry, bool done, u8 terminal_reason) {
    char line[2048];
    int written = 0;

    if (entry == NULL || !entry->valid || entry->exported) {
        return;
    }
    entry->active = false;
    entry->done = done;
    entry->terminal_reason = terminal_reason;

    RLSession_UpdateDerivedOutcomeFields(entry);
    written = RLSession_FormatTransitionLogLine(entry, line, sizeof(line));
    if (written > 0) {
        RLSession_AppendTransitionLogLine(line, (size_t)written);
        RLSession_AppendTransitionBatchLine(entry, line, (size_t)written);
    }
    entry->exported = true;
    remote_debug.transition_export_count++;
    remote_debug.last_delta_self_forward = entry->delta_self_forward;
    remote_debug.last_delta_opp_forward = entry->delta_opp_forward;
    remote_debug.last_requested_movement_succeeded = entry->requested_movement_succeeded;
    remote_debug.last_requested_attack_entered_state = entry->requested_attack_entered_state;
    remote_debug.last_requested_attack_made_contact = entry->requested_attack_made_contact;
    remote_debug.last_requested_attack_likely_whiffed = entry->requested_attack_likely_whiffed;
    remote_debug.last_requested_attack_input_started = entry->requested_attack_input_started;
    remote_debug.last_requested_attack_became_active = entry->requested_attack_became_active;
    remote_debug.last_observed_attack_state_started = entry->observed_attack_state_started;
    remote_debug.last_observed_attack_code_changed = entry->observed_attack_code_changed;
    remote_debug.last_observed_attack_counter_started = entry->observed_attack_counter_started;
    remote_debug.last_requested_jump_started = entry->requested_jump_started;
}

static void RLSession_DiscardLedgerEntry(RLDecisionLedgerEntry* entry) {
    if (entry == NULL) {
        return;
    }
    if (active_ledger_entry == entry) {
        active_ledger_entry = NULL;
    }
    memset(entry, 0, sizeof(*entry));
}

static void RLSession_SetActiveLedgerEntry(RLDecisionLedgerEntry* entry) {
    if (active_ledger_entry != NULL && active_ledger_entry != entry) {
        RLSession_FinalizeLedgerEntry(active_ledger_entry, false, 1);
    }
    active_ledger_entry = entry;
    if (entry != NULL) {
        entry->active = true;
    }
}

static void RLSession_FinalizeEpisodeLedger(u32 episode_id) {
    RLSession_FinalizeOverlayAttackEvent();
    if (active_ledger_entry != NULL && active_ledger_entry->valid &&
        active_ledger_entry->run_id == remote_debug.run_id && active_ledger_entry->episode_id == episode_id) {
        const s16 self = RLSession_AgentPlayerIndex();
        const s16 opp = RLSession_OpponentPlayerIndex();
        const s16 self_hp = SDL_max(0, plw[self].wu.vital_new);
        const s16 opp_hp = SDL_max(0, plw[opp].wu.vital_new);
        if (opp_hp <= 0 && self_hp > 0) {
            active_ledger_entry->reward_accum += 100.0f;
        } else if (self_hp <= 0 && opp_hp > 0) {
            active_ledger_entry->reward_accum -= 100.0f;
        }
    }
    for (u32 i = 0; i < RL_DECISION_LEDGER_CAP; i++) {
        if (!decision_ledger[i].valid || decision_ledger[i].run_id != remote_debug.run_id ||
            decision_ledger[i].episode_id != episode_id || decision_ledger[i].exported) {
            continue;
        }
        if (!decision_ledger[i].was_executed) {
            RLSession_DiscardLedgerEntry(&decision_ledger[i]);
            continue;
        }
        RLSession_FinalizeLedgerEntry(&decision_ledger[i], true, 2);
    }
    if (transition_batch_episode_id == episode_id && transition_batch_payload != NULL && transition_batch_payload_len > 0) {
        RLNet_QueueTransitionBatch(remote_debug.run_id,
                                   episode_id,
                                   transition_batch_payload,
                                   (u32)transition_batch_payload_len,
                                   transition_batch_row_count);
    }
    RLSession_ResetTransitionBatch();
    active_ledger_entry = NULL;
}

static void RLSession_FinalizeRuntimeBeforeReset() {
    if (!remote_runtime_initialized || remote_debug.run_id == 0 || remote_debug.episode_id == 0) {
        return;
    }
    if (RLSession_IsRoundBattleActive() && Mode_Type == MODE_VERSUS && mpp_w.inGame && Play_Mode == 1) {
        return;
    }
    RLSession_FinalizeEpisodeLedger(remote_debug.episode_id);
}

static bool RLSession_IsTerminalObservation(const RLObservationV1* obs) {
    return obs != NULL && obs->valid && !RLSession_IsRoundBattleActive();
}

static void RLSession_UpdateLedgerHpBounds(RLDecisionLedgerEntry* entry, const RLObservationV1* obs) {
    if (entry == NULL || obs == NULL) {
        return;
    }
    if (entry->start_self_hp == 0 && entry->start_opp_hp == 0) {
        entry->start_self_hp = obs->self_hp;
        entry->start_opp_hp = obs->opp_hp;
    }
    entry->final_self_hp = obs->self_hp;
    entry->final_opp_hp = obs->opp_hp;
}

static void RLSession_AccumulateMovementSpan(RLDecisionLedgerEntry* entry, const RLObservationV1* obs) {
    if (entry == NULL || obs == NULL) {
        return;
    }
    RLSession_AccumulateDeltaS16(&entry->delta_self_x, obs->delta_self_x);
    RLSession_AccumulateDeltaS16(&entry->delta_opp_x, obs->delta_opp_x);
    RLSession_AccumulateDeltaS16(&entry->delta_self_y, obs->delta_self_y);
    RLSession_AccumulateDeltaS16(&entry->delta_opp_y, obs->delta_opp_y);
    RLSession_AccumulateDeltaS16(&entry->delta_self_forward, (s32)obs->delta_self_x * (s32)obs->self_facing_sign);
    RLSession_AccumulateDeltaS16(&entry->delta_opp_forward, (s32)obs->delta_opp_x * (s32)obs->opp_facing_sign);
    entry->self_airborne_seen |= obs->self_airborne;
    entry->opp_airborne_seen |= obs->opp_airborne;
    entry->self_airborne_started |= obs->self_airborne_started;
    entry->opp_airborne_started |= obs->opp_airborne_started;
}

static void RLSession_AccumulateAttackSignals(RLDecisionLedgerEntry* entry, const RLObservationV1* obs) {
    if (entry == NULL || obs == NULL) {
        return;
    }
    entry->self_attack_state_seen |= (u8)(obs->self_current_attack != 0);
    entry->self_attack_started |= obs->self_attack_started;
    entry->self_attack_code_changed |= obs->self_attack_code_changed;
    entry->self_attack_counter_started |= obs->self_attack_counter_started;
    entry->self_attack_routine_started |= obs->self_attack_routine_started;
    entry->opp_attack_started |= obs->opp_attack_started;
    entry->opp_attack_code_changed |= obs->opp_attack_code_changed;
    entry->opp_attack_counter_started |= obs->opp_attack_counter_started;
    entry->opp_attack_routine_started |= obs->opp_attack_routine_started;
}

static void RLSession_AccumulateCombatSpan(RLDecisionLedgerEntry* entry,
                                           const RLObservationV1* obs,
                                           s16 self_hp_delta,
                                           s16 opp_hp_delta) {
    if (entry == NULL || obs == NULL) {
        return;
    }
    entry->reward_accum += (float)(opp_hp_delta - self_hp_delta);
    RLSession_AccumulateDeltaS16(&entry->delta_self_hp, self_hp_delta);
    RLSession_AccumulateDeltaS16(&entry->delta_opp_hp, opp_hp_delta);
    RLSession_AccumulateDeltaS16(&entry->delta_self_stun, obs->delta_self_stun);
    RLSession_AccumulateDeltaS16(&entry->delta_opp_stun, obs->delta_opp_stun);
    entry->self_entered_hit_stop |= obs->self_entered_hit_stop;
    entry->opp_entered_hit_stop |= obs->opp_entered_hit_stop;
    entry->self_entered_contact_state |= obs->self_entered_contact_state;
    entry->opp_entered_contact_state |= obs->opp_entered_contact_state;
    entry->self_entered_damage_state |= (u8)(obs->self_entered_damage_state || self_hp_delta > 0);
    entry->opp_entered_damage_state |= (u8)(obs->opp_entered_damage_state || opp_hp_delta > 0);
    entry->self_throw_started |= obs->self_throw_started;
    entry->opp_throw_caught_started |= obs->opp_throw_caught_started;
    entry->self_throw_seen |= obs->self_throw_active;
    entry->opp_throw_caught_seen |= obs->opp_throw_caught;
}

void RLSession_OnObservationFrameEnd(const RLObservationV1* obs) {
    s16 self_damage_total = 0;
    s16 opp_damage_total = 0;
    s16 self_hp_delta = 0;
    s16 opp_hp_delta = 0;
    bool terminal = false;
    RLDecisionLedgerEntry* active_entry = NULL;

    if (obs == NULL || !obs->valid) {
        return;
    }

    terminal = RLSession_IsTerminalObservation(obs);

    self_damage_total = RLSession_ClampDamageTotal(obs->self_hp_start, obs->self_hp);
    opp_damage_total = RLSession_ClampDamageTotal(obs->opp_hp_start, obs->opp_hp);
    if (!hp_damage_baseline_valid) {
        last_self_damage_total = self_damage_total;
        last_opp_damage_total = opp_damage_total;
        hp_damage_baseline_valid = true;
    }
    self_hp_delta = RLSession_ClampDeltaS16((s32)self_damage_total - (s32)last_self_damage_total);
    opp_hp_delta = RLSession_ClampDeltaS16((s32)opp_damage_total - (s32)last_opp_damage_total);
    last_self_damage_total = self_damage_total;
    last_opp_damage_total = opp_damage_total;
    if (RLSession_IsRoundEndHpSync(obs, self_hp_delta, opp_hp_delta)) {
        self_hp_delta = 0;
        opp_hp_delta = 0;
    }

    if (obs->self_caution_started) {
        RLSession_FinalizeOverlayAttackEvent();
        overlay_attack_event_pending = true;
        overlay_attack_event_contact_seen = false;
    }
    if (overlay_attack_event_pending &&
        (obs->self_entered_hit_stop || obs->opp_entered_hit_stop || obs->opp_entered_contact_state ||
         obs->opp_entered_damage_state || opp_hp_delta > 0 || obs->delta_opp_stun > 0)) {
        overlay_attack_event_contact_seen = true;
    }

    active_entry = (active_ledger_entry != NULL && active_ledger_entry->valid && active_ledger_entry->active)
                       ? active_ledger_entry
                       : NULL;

    if (active_entry != NULL) {
        RLSession_UpdateLedgerHpBounds(active_entry, obs);
        RLSession_AccumulateMovementSpan(active_entry, obs);
        RLSession_AccumulateAttackSignals(active_entry, obs);
        RLSession_AccumulateCombatSpan(active_entry, obs, self_hp_delta, opp_hp_delta);
    }

    if (terminal) {
        RLSession_FinalizeEpisodeLedger(remote_debug.episode_id);
        RLSession_ClearRemoteQueue();
        return;
    }
}

static RLExpectedRemoteDecision* RLSession_FindExpectedDecision(u64 run_id, u32 episode_id, u32 decision_id) {
    for (u32 i = 0; i < RL_REMOTE_EXPECTED_CAP; i++) {
        if (expected_decisions[i].valid && expected_decisions[i].run_id == run_id &&
            expected_decisions[i].episode_id == episode_id &&
            expected_decisions[i].decision_id == decision_id) {
            return &expected_decisions[i];
        }
    }
    return NULL;
}

static RLQueuedRemoteAction* RLSession_FindQueuedAction(u64 run_id, u32 episode_id, u32 decision_id, u32 target_frame) {
    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (remote_queue[i].valid && remote_queue[i].run_id == run_id && remote_queue[i].episode_id == episode_id &&
            remote_queue[i].decision_id == decision_id && remote_queue[i].target_frame == target_frame) {
            return &remote_queue[i];
        }
    }
    return NULL;
}

static RLExpectedRemoteDecision* RLSession_AllocExpectedDecision() {
    for (u32 i = 0; i < RL_REMOTE_EXPECTED_CAP; i++) {
        if (!expected_decisions[i].valid) {
            return &expected_decisions[i];
        }
    }
    return NULL;
}

static RLQueuedRemoteAction* RLSession_AllocQueuedAction() {
    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (!remote_queue[i].valid) {
            return &remote_queue[i];
        }
    }
    return NULL;
}

static RLSeenRemoteDecision* RLSession_FindSeenDecision(u64 run_id, u32 episode_id, u32 decision_id) {
    for (u32 i = 0; i < RL_REMOTE_SEEN_CAP; i++) {
        if (seen_decisions[i].valid && seen_decisions[i].run_id == run_id &&
            seen_decisions[i].episode_id == episode_id &&
            seen_decisions[i].decision_id == decision_id) {
            return &seen_decisions[i];
        }
    }
    return NULL;
}

static RLSeenRemoteDecision* RLSession_AllocSeenDecision() {
    for (u32 i = 0; i < RL_REMOTE_SEEN_CAP; i++) {
        if (!seen_decisions[i].valid) {
            return &seen_decisions[i];
        }
    }
    return &seen_decisions[0];
}

static void RLSession_RemoveExpectedDecision(RLExpectedRemoteDecision* entry) {
    if (entry != NULL) {
        memset(entry, 0, sizeof(*entry));
    }
}

static void RLSession_UpdateNextScheduledContext() {
    u32 best_target = UINT32_MAX;
    const RLQueuedRemoteAction* best = NULL;

    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (!remote_queue[i].valid || remote_queue[i].run_id != remote_debug.run_id ||
            remote_queue[i].episode_id != remote_debug.episode_id) {
            continue;
        }
        if (remote_queue[i].target_frame < best_target) {
            best_target = remote_queue[i].target_frame;
            best = &remote_queue[i];
        }
    }

    if (best == NULL || best->target_frame <= remote_debug.frame_id) {
        action_context.next_scheduled_move_intent = RL_MOVE_NEUTRAL;
        action_context.next_scheduled_attack_bits = 0;
        action_context.frames_until_next_action = 255;
        return;
    }

    action_context.next_scheduled_move_intent = RLSession_DecodeMoveIntent(best->action_wire);
    action_context.next_scheduled_attack_bits = RLSession_DecodeAttackBits(best->action_wire);
    action_context.frames_until_next_action = (u8)SDL_min(best->target_frame - remote_debug.frame_id, 255u);
}

static void RLSession_MaybeInitRemoteRuntime() {
    if (!remote_runtime_initialized) {
        if (remote_debug.run_id == 0) {
            remote_debug.run_id = RLSession_LoadNextRunId();
            next_episode_id = 1;
        }
        RLSession_StartNewEpisode();
        RLSession_ResetOverlayAttackCounters();
        remote_runtime_initialized = true;
    }
    if (RLSession_RoundEpisodeChanged()) {
        RLSession_FinalizeOverlayAttackEvent();
        RLSession_FinalizeEpisodeLedger(remote_debug.episode_id);
        RLSession_StartNewEpisode();
        RLSession_ResetOverlayAttackCounters();
        RLSession_ClearRemoteQueue();
    }
}

static void RLSession_ResetLocalFakeAgent() {
    local_fake_action_index = 0;
    local_fake_action_frame = 0;
    RLSession_ClearActionContext();
}

void RLSession_ApplyVersusOperatorSetup() {
    if (!RLSession_IsActive() || Mode_Type != MODE_VERSUS) {
        return;
    }

    const s16 agent = RLSession_AgentPlayerIndex();
    const s16 opponent = RLSession_OpponentPlayerIndex();
    const s16 opponent_operator = RLSession_OpponentUsesHumanInput() ? 1 : 0;

    plw[agent].wu.operator = 1;
    Operator_Status[agent] = 1;
    plw[opponent].wu.operator = opponent_operator;
    Operator_Status[opponent] = opponent_operator;
}

void RLSession_ApplyScriptedMovementToBuffers() {
    if (!RLSession_OpponentUsesHumanInput() || RLSession_RemoteControlEnabled()) {
        return;
    }

    if (!RLSession_CanOverrideGameplayInput()) {
        RLSession_ClearActionContext();
        return;
    }

    RLSession_ResetLocalFakeAgent();

    const s16 agent = RLSession_AgentPlayerIndex();
    u8 move_intent = RL_MOVE_FORWARD;
    const u16 movement = RLSession_MapTestMovementToSWKey(agent);
    u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;

    switch (configuration.remote_rl_agent.test_movement) {
    case RL_TEST_MOVEMENT_BACK:
        move_intent = RL_MOVE_BACK;
        break;
    case RL_TEST_MOVEMENT_JUMP_FORWARD:
        move_intent = RL_MOVE_UP_FORWARD;
        break;
    case RL_TEST_MOVEMENT_DOWN_BACK:
        move_intent = RL_MOVE_DOWN_BACK;
        break;
    case RL_TEST_MOVEMENT_FORWARD:
    default:
        move_intent = RL_MOVE_FORWARD;
        break;
    }

    *target = (u16)((*target & ~SWK_DIRECTIONS) | movement);
    action_context.last_executed_move_intent = move_intent;
    action_context.last_executed_attack_bits = 0;
    action_context.next_scheduled_move_intent = RL_MOVE_NEUTRAL;
    action_context.next_scheduled_attack_bits = 0;
    action_context.frames_until_next_action = 255;
}

static void RLSession_ApplyLocalFakeAgentToBuffers() {
    if (RLSession_OpponentUsesHumanInput() || RLSession_RemoteControlEnabled() || !RLSession_CanOverrideGameplayInput()) {
        RLSession_ResetLocalFakeAgent();
        return;
    }

    const u16 action_count = (u16)(sizeof(kLocalFakeAgentSequence) / sizeof(kLocalFakeAgentSequence[0]));
    const RLLocalFakeAction* action = &kLocalFakeAgentSequence[local_fake_action_index];
    const RLLocalFakeAction* next_action = &kLocalFakeAgentSequence[(local_fake_action_index + 1) % action_count];
    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 movement = RLSession_MapMoveIntentToSWKey(agent, action->move);
    u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;

    *target = (u16)((*target & ~(SWK_DIRECTIONS | SWK_ATTACKS)) | movement | action->attacks);
    action_context.last_executed_move_intent = (u8)action->move;
    action_context.last_executed_attack_bits = action->attacks;
    action_context.next_scheduled_move_intent = (u8)next_action->move;
    action_context.next_scheduled_attack_bits = next_action->attacks;
    action_context.frames_until_next_action = (u8)action->hold_frames;

    local_fake_action_frame++;
    if (local_fake_action_frame >= action->hold_frames) {
        local_fake_action_frame = 0;
        local_fake_action_index = (u16)((local_fake_action_index + 1) % action_count);
    } else {
        action_context.frames_until_next_action = (u8)(action->hold_frames - local_fake_action_frame);
    }
}

static void RLSession_StartActiveRemoteAction(u32 episode_id,
                                              u32 decision_id,
                                              u8 move_intent,
                                              u16 attack_bits,
                                              u32 model_version,
                                              RLExecutionSource source) {
    RLDecisionLedgerEntry* ledger = RLSession_FindLedgerEntry(remote_debug.run_id, episode_id, decision_id);
    const u16 executed_action_wire = RLSession_EncodeActionWire(move_intent, attack_bits);

    active_remote_action.valid = true;
    active_remote_action.move_intent = move_intent;
    active_remote_action.attack_bits = attack_bits;
    active_remote_action.movement_remaining_frames = RLSession_ActionHoldFrames();
    active_remote_action.attack_remaining_frames = (attack_bits != 0) ? 1 : 0;
    action_context.last_executed_move_intent = move_intent;
    action_context.last_executed_attack_bits = attack_bits;
    last_executed_action_wire = executed_action_wire;
    last_executed_model_version = model_version;
    remote_debug.model_version_current = model_version;
    if (ledger != NULL) {
        ledger->was_executed = true;
        ledger->executed_action_wire = executed_action_wire;
        ledger->execution_frame_actual = remote_debug.frame_id;
        ledger->execution_source = (u8)source;
        ledger->executed_move_intent = move_intent;
        ledger->executed_attack_bits = attack_bits;
        ledger->model_version_executed = model_version;

        RLSession_SetActiveLedgerEntry(ledger);
    }
    if (source == RL_EXECUTION_SOURCE_REMOTE) {
        remote_debug.executed_count++;
    } else {
        remote_debug.fallback_count++;
    }
}

static bool RLSession_ExecuteDueQueuedAction() {
    RLQueuedRemoteAction* best = NULL;

    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (!remote_queue[i].valid || remote_queue[i].run_id != remote_debug.run_id ||
            remote_queue[i].episode_id != remote_debug.episode_id ||
            remote_queue[i].target_frame != remote_debug.frame_id) {
            continue;
        }
        best = &remote_queue[i];
        break;
    }

    if (best == NULL) {
        return false;
    }

    RLSession_StartActiveRemoteAction(best->episode_id,
                                      best->decision_id,
                                      RLSession_DecodeMoveIntent(best->action_wire),
                                      RLSession_DecodeAttackBits(best->action_wire),
                                      best->model_version,
                                      RL_EXECUTION_SOURCE_REMOTE);
    RLSession_RemoveExpectedDecision(RLSession_FindExpectedDecision(best->run_id, best->episode_id, best->decision_id));
    memset(best, 0, sizeof(*best));
    if (remote_debug.queue_depth > 0) {
        remote_debug.queue_depth--;
    }
    return true;
}

static void RLSession_ApplyExpectedFallbackIfDue() {
    for (u32 i = 0; i < RL_REMOTE_EXPECTED_CAP; i++) {
        RLExpectedRemoteDecision* entry = &expected_decisions[i];
        u8 move_intent = RL_MOVE_NEUTRAL;
        u16 attack_bits = 0;
        RLExecutionSource source = RL_EXECUTION_SOURCE_NEUTRAL_FALLBACK;
        if (!entry->valid || entry->run_id != remote_debug.run_id || entry->episode_id != remote_debug.episode_id ||
            entry->target_frame > remote_debug.frame_id) {
            continue;
        }
        if (!entry->fulfilled &&
            RLSession_FindQueuedAction(entry->run_id, entry->episode_id, entry->decision_id, entry->target_frame) == NULL) {
            if (last_executed_action_wire != 0) {
                move_intent = RLSession_DecodeMoveIntent(last_executed_action_wire);
                attack_bits = RLSession_DecodeAttackBits(last_executed_action_wire);
                last_executed_model_version = remote_debug.model_version_current;
                source = RL_EXECUTION_SOURCE_REPEATED_LAST_ACTION;
            }
            RLSession_StartActiveRemoteAction(entry->episode_id,
                                              entry->decision_id,
                                              move_intent,
                                              attack_bits,
                                              last_executed_model_version,
                                              source);
        }
        RLSession_RemoveExpectedDecision(entry);
        return;
    }
}

static void RLSession_ApplyRemoteActionToBuffers() {
    if (!RLSession_CanOverrideGameplayInput()) {
        RLSession_FinalizeRuntimeBeforeReset();
        RLSession_ResetRemoteRuntime(false);
        return;
    }

    RLSession_MaybeInitRemoteRuntime();
    RLSession_ClearScheduledActionContext();

    if (!RLNet_IsHandshakeAccepted()) {
        return;
    }

    if (!RLSession_ExecuteDueQueuedAction()) {
        RLSession_ApplyExpectedFallbackIfDue();
    }

    if (active_remote_action.valid &&
        (active_remote_action.movement_remaining_frames > 0 || active_remote_action.attack_remaining_frames > 0)) {
        const s16 agent = RLSession_AgentPlayerIndex();
        const u16 movement = RLSession_MapMoveIntentToSWKey(agent, active_remote_action.move_intent);
        const u16 attacks = (active_remote_action.attack_remaining_frames > 0) ? active_remote_action.attack_bits : 0;
        u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;
        *target = (u16)((*target & ~(SWK_DIRECTIONS | SWK_ATTACKS)) | movement | attacks);
        action_context.last_executed_move_intent = active_remote_action.move_intent;
        action_context.last_executed_attack_bits = attacks;
        if (active_remote_action.movement_remaining_frames > 0) {
            active_remote_action.movement_remaining_frames--;
        }
        if (active_remote_action.attack_remaining_frames > 0) {
            active_remote_action.attack_remaining_frames--;
        }
        if (active_remote_action.movement_remaining_frames == 0 && active_remote_action.attack_remaining_frames == 0) {
            active_remote_action.valid = false;
        }
    }

    RLSession_UpdateNextScheduledContext();
    RLSession_SendRemoteObservationIfDue();
    remote_debug.frame_id++;
}

RLRemoteActionSubmitResult RLSession_SubmitRemoteAction(const RLActionPacket* packet) {
    RLExpectedRemoteDecision* expected = NULL;
    RLQueuedRemoteAction* queued = NULL;
    RLSeenRemoteDecision* seen = NULL;

    if (packet == NULL || !RLSession_RemoteControlEnabled()) {
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }
    if (!RLSession_IsRoundBattleActive()) {
        remote_debug.target_mismatch_count++;
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }

    RLSession_MaybeInitRemoteRuntime();

    if (packet->target_frame < remote_debug.frame_id) {
        remote_debug.late_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_LATE;
    }

    if (packet->run_id != remote_debug.run_id) {
        remote_debug.target_mismatch_count++;
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }

    seen = RLSession_FindSeenDecision(packet->run_id, packet->episode_id, packet->decision_id);
    if (seen != NULL) {
        if (seen->target_frame != packet->target_frame) {
            remote_debug.target_mismatch_count++;
            return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
        }
        remote_debug.duplicate_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_DUPLICATE;
    }

    expected = RLSession_FindExpectedDecision(packet->run_id, packet->episode_id, packet->decision_id);
    if (expected == NULL || expected->target_frame != packet->target_frame) {
        remote_debug.target_mismatch_count++;
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }

    if (RLSession_FindQueuedAction(packet->run_id, packet->episode_id, packet->decision_id, packet->target_frame) != NULL) {
        remote_debug.duplicate_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_DUPLICATE;
    }

    queued = RLSession_AllocQueuedAction();
    if (queued == NULL) {
        remote_debug.duplicate_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_DUPLICATE;
    }

    queued->valid = true;
    queued->run_id = packet->run_id;
    queued->episode_id = packet->episode_id;
    queued->decision_id = packet->decision_id;
    queued->target_frame = packet->target_frame;
    queued->action_wire = packet->action_wire;
    queued->model_version = packet->model_version;
    seen = RLSession_AllocSeenDecision();
    seen->valid = true;
    seen->run_id = packet->run_id;
    seen->episode_id = packet->episode_id;
    seen->decision_id = packet->decision_id;
    seen->target_frame = packet->target_frame;
    {
        RLDecisionLedgerEntry* ledger = RLSession_FindLedgerEntry(packet->run_id, packet->episode_id, packet->decision_id);
        if (ledger != NULL) {
            ledger->requested_action_wire = packet->action_wire;
            ledger->model_version_requested = packet->model_version;
        }
    }
    expected->fulfilled = true;
    remote_debug.queued_count++;
    remote_debug.queue_depth++;
    RLSession_UpdateNextScheduledContext();
    return RL_REMOTE_ACTION_SUBMIT_ACCEPTED;
}

bool RLSession_SendRemoteObservationIfDue() {
    RLObsPacketHeader header;
    RLObsSpacingPayloadV1 payload;
    RLExpectedRemoteDecision* expected = NULL;
    RLDecisionLedgerEntry* ledger = NULL;
    const RLObservationV1* obs = RLObservation_GetLatest();

    if (!RLSession_RemoteControlEnabled() || !RLSession_CanOverrideGameplayInput() || !RLNet_IsHandshakeAccepted()) {
        return false;
    }
    if (obs == NULL || !obs->valid) {
        return false;
    }
    if (RLSession_IsTerminalObservation(obs)) {
        return false;
    }
    if ((remote_debug.frame_id % RLSession_DecisionIntervalFrames()) != 0) {
        return false;
    }

    expected = RLSession_AllocExpectedDecision();
    ledger = RLSession_AllocLedgerEntry();
    if (expected == NULL || ledger == NULL) {
        return false;
    }
    RLSession_FillObsSpacingPayload(&payload, obs);

    memset(&header, 0, sizeof(header));
    header.magic = RL_PROTOCOL_MAGIC;
    header.version = RL_PROTOCOL_VERSION;
    header.packet_type = RL_OBS_PACKET_TYPE_V1;
    header.session_nonce = RLNet_GetState()->session_nonce;
    header.run_id = remote_debug.run_id;
    header.episode_id = remote_debug.episode_id;
    header.decision_id = remote_debug.next_decision_id++;
    header.obs_frame = remote_debug.frame_id;
    header.target_frame = remote_debug.frame_id + RLSession_DelayFrames();
    header.obs_len = sizeof(payload);
    header.action_hold_frames = RLSession_ActionHoldFrames();
    header.model_version_expected = remote_debug.model_version_current;

    if (!RLNet_SendObservation(&header, &payload, sizeof(payload))) {
        return false;
    }

    expected->valid = true;
    expected->fulfilled = false;
    expected->run_id = header.run_id;
    expected->episode_id = header.episode_id;
    expected->decision_id = header.decision_id;
    expected->target_frame = header.target_frame;
    memset(ledger, 0, sizeof(*ledger));
    ledger->valid = true;
    ledger->run_id = header.run_id;
    ledger->episode_id = header.episode_id;
    ledger->decision_id = header.decision_id;
    ledger->round_num = Round_num;
    ledger->start_self_hp = obs->self_hp;
    ledger->start_opp_hp = obs->opp_hp;
    ledger->final_self_hp = obs->self_hp;
    ledger->final_opp_hp = obs->opp_hp;
    ledger->agent_character_id = My_char[RLSession_AgentPlayerIndex()];
    ledger->opponent_character_id = My_char[RLSession_OpponentPlayerIndex()];
    ledger->obs_frame = header.obs_frame;
    ledger->target_frame = header.target_frame;
    ledger->model_version_expected = header.model_version_expected;
    ledger->terminal_reason = 3;
    RLSession_CaptureObservationSpacing(ledger, obs);
    remote_debug.obs_sent_count++;
    return true;
}

void RLSession_ApplyInputOverrideToBuffers() {
    RLSession_ApplyScriptedMovementToBuffers();
    if (RLSession_RemoteControlEnabled()) {
        RLSession_ApplyRemoteActionToBuffers();
    } else {
        RLSession_ApplyLocalFakeAgentToBuffers();
    }
}
