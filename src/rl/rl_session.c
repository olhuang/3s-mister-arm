#include "rl/rl_session.h"

#include "rl/rl_net.h"
#include "rl/rl_observation.h"
#include "sf33rd/AcrSDK/common/pad.h"
#include "main.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/workuser.h"
#include "sf33rd/Source/Game/system/work_sys.h"

#include <SDL3/SDL_stdinc.h>
#include <string.h>

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
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
    u16 action_wire;
} RLQueuedRemoteAction;

typedef struct RLExpectedRemoteDecision {
    bool valid;
    bool fulfilled;
    u32 episode_id;
    u32 decision_id;
    u32 target_frame;
} RLExpectedRemoteDecision;

typedef struct RLRemoteActiveAction {
    bool valid;
    u8 move_intent;
    u16 attack_bits;
    u8 movement_remaining_frames;
    u8 attack_remaining_frames;
} RLRemoteActiveAction;

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

static u16 local_fake_action_index;
static u16 local_fake_action_frame;
static u8 active_round_num;
static bool remote_runtime_initialized;
static RLRemoteDebugState remote_debug;
static RLQueuedRemoteAction remote_queue[RL_REMOTE_QUEUE_CAP];
static RLExpectedRemoteDecision expected_decisions[RL_REMOTE_EXPECTED_CAP];
static RLRemoteActiveAction active_remote_action;
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

static bool RLSession_CanOverrideGameplayInput() {
    return RLSession_IsActive() && Mode_Type == MODE_VERSUS && mpp_w.inGame && Play_Mode == 1 && Game_pause == 0;
}

static bool RLSession_RemoteControlEnabled() {
    const RLNetState* net = RLNet_GetState();
    return RLSession_IsActive() && !RLSession_OpponentUsesHumanInput() && net->enabled;
}

static void RLSession_ClearRemoteQueue() {
    memset(remote_queue, 0, sizeof(remote_queue));
    memset(expected_decisions, 0, sizeof(expected_decisions));
    memset(&active_remote_action, 0, sizeof(active_remote_action));
    remote_debug.queue_depth = 0;
}

static void RLSession_ResetRemoteRuntime(bool reset_counters) {
    RLSession_ClearRemoteQueue();
    RLSession_ClearActionContext();
    active_round_num = Round_num;
    remote_runtime_initialized = false;
    if (reset_counters) {
        memset(&remote_debug, 0, sizeof(remote_debug));
    }
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

static RLExpectedRemoteDecision* RLSession_FindExpectedDecision(u32 episode_id, u32 decision_id) {
    for (u32 i = 0; i < RL_REMOTE_EXPECTED_CAP; i++) {
        if (expected_decisions[i].valid && expected_decisions[i].episode_id == episode_id &&
            expected_decisions[i].decision_id == decision_id) {
            return &expected_decisions[i];
        }
    }
    return NULL;
}

static RLQueuedRemoteAction* RLSession_FindQueuedAction(u32 episode_id, u32 decision_id, u32 target_frame) {
    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (remote_queue[i].valid && remote_queue[i].episode_id == episode_id &&
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

static void RLSession_RemoveExpectedDecision(RLExpectedRemoteDecision* entry) {
    if (entry != NULL) {
        memset(entry, 0, sizeof(*entry));
    }
}

static void RLSession_UpdateNextScheduledContext() {
    u32 best_target = UINT32_MAX;
    const RLQueuedRemoteAction* best = NULL;

    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (!remote_queue[i].valid || remote_queue[i].episode_id != remote_debug.episode_id) {
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
        active_round_num = Round_num;
        remote_debug.episode_id = Round_num;
        remote_runtime_initialized = true;
    }
    if (active_round_num != Round_num) {
        active_round_num = Round_num;
        remote_debug.episode_id = Round_num;
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
    if (!RLSession_OpponentUsesHumanInput()) {
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
    if (RLSession_OpponentUsesHumanInput() || !RLSession_CanOverrideGameplayInput()) {
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

static void RLSession_StartActiveRemoteAction(u8 move_intent, u16 attack_bits, bool fallback_used) {
    active_remote_action.valid = true;
    active_remote_action.move_intent = move_intent;
    active_remote_action.attack_bits = attack_bits;
    active_remote_action.movement_remaining_frames = RLSession_ActionHoldFrames();
    active_remote_action.attack_remaining_frames = (attack_bits != 0) ? 1 : 0;
    action_context.last_executed_move_intent = move_intent;
    action_context.last_executed_attack_bits = attack_bits;
    if (fallback_used) {
        remote_debug.fallback_count++;
    } else {
        remote_debug.executed_count++;
    }
}

static bool RLSession_ExecuteDueQueuedAction() {
    RLQueuedRemoteAction* best = NULL;

    for (u32 i = 0; i < RL_REMOTE_QUEUE_CAP; i++) {
        if (!remote_queue[i].valid || remote_queue[i].episode_id != remote_debug.episode_id ||
            remote_queue[i].target_frame != remote_debug.frame_id) {
            continue;
        }
        best = &remote_queue[i];
        break;
    }

    if (best == NULL) {
        return false;
    }

    RLSession_StartActiveRemoteAction(RLSession_DecodeMoveIntent(best->action_wire),
                                      RLSession_DecodeAttackBits(best->action_wire),
                                      false);
    RLSession_RemoveExpectedDecision(RLSession_FindExpectedDecision(best->episode_id, best->decision_id));
    memset(best, 0, sizeof(*best));
    if (remote_debug.queue_depth > 0) {
        remote_debug.queue_depth--;
    }
    return true;
}

static void RLSession_ApplyExpectedFallbackIfDue() {
    for (u32 i = 0; i < RL_REMOTE_EXPECTED_CAP; i++) {
        RLExpectedRemoteDecision* entry = &expected_decisions[i];
        if (!entry->valid || entry->episode_id != remote_debug.episode_id || entry->target_frame > remote_debug.frame_id) {
            continue;
        }
        if (!entry->fulfilled && RLSession_FindQueuedAction(entry->episode_id, entry->decision_id, entry->target_frame) == NULL) {
            RLSession_StartActiveRemoteAction(action_context.last_executed_move_intent,
                                              action_context.last_executed_attack_bits,
                                              true);
        }
        RLSession_RemoveExpectedDecision(entry);
        return;
    }
}

static void RLSession_ApplyRemoteActionToBuffers() {
    if (!RLSession_CanOverrideGameplayInput()) {
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

    if (packet == NULL || !RLSession_RemoteControlEnabled()) {
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }

    RLSession_MaybeInitRemoteRuntime();

    if (packet->target_frame < remote_debug.frame_id) {
        remote_debug.late_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_LATE;
    }

    expected = RLSession_FindExpectedDecision(packet->episode_id, packet->decision_id);
    if (expected == NULL || expected->target_frame != packet->target_frame) {
        remote_debug.target_mismatch_count++;
        return RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH;
    }

    if (RLSession_FindQueuedAction(packet->episode_id, packet->decision_id, packet->target_frame) != NULL) {
        remote_debug.duplicate_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_DUPLICATE;
    }

    queued = RLSession_AllocQueuedAction();
    if (queued == NULL) {
        remote_debug.duplicate_drop_count++;
        return RL_REMOTE_ACTION_SUBMIT_DUPLICATE;
    }

    queued->valid = true;
    queued->episode_id = packet->episode_id;
    queued->decision_id = packet->decision_id;
    queued->target_frame = packet->target_frame;
    queued->action_wire = packet->action_wire;
    expected->fulfilled = true;
    remote_debug.queued_count++;
    remote_debug.queue_depth++;
    RLSession_UpdateNextScheduledContext();
    return RL_REMOTE_ACTION_SUBMIT_ACCEPTED;
}

bool RLSession_SendRemoteObservationIfDue() {
    RLObsPacketHeader header;
    RLExpectedRemoteDecision* expected = NULL;
    const RLObservationV1* obs = RLObservation_GetLatest();

    if (!RLSession_RemoteControlEnabled() || !RLSession_CanOverrideGameplayInput() || !RLNet_IsHandshakeAccepted()) {
        return false;
    }
    if (obs == NULL || !obs->valid) {
        return false;
    }
    if ((remote_debug.frame_id % RLSession_DecisionIntervalFrames()) != 0) {
        return false;
    }

    expected = RLSession_AllocExpectedDecision();
    if (expected == NULL) {
        return false;
    }

    memset(&header, 0, sizeof(header));
    header.magic = RL_PROTOCOL_MAGIC;
    header.version = RL_PROTOCOL_VERSION;
    header.packet_type = RL_OBS_PACKET_TYPE_V1;
    header.session_nonce = RLNet_GetState()->session_nonce;
    header.episode_id = remote_debug.episode_id;
    header.decision_id = remote_debug.next_decision_id++;
    header.obs_frame = remote_debug.frame_id;
    header.target_frame = remote_debug.frame_id + RLSession_DelayFrames();
    header.obs_len = 0;
    header.action_hold_frames = RLSession_ActionHoldFrames();

    if (!RLNet_SendObservationHeader(&header)) {
        return false;
    }

    expected->valid = true;
    expected->fulfilled = false;
    expected->episode_id = header.episode_id;
    expected->decision_id = header.decision_id;
    expected->target_frame = header.target_frame;
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
