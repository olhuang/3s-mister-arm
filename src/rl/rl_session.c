#include "rl/rl_session.h"

#include "sf33rd/AcrSDK/common/pad.h"
#include "main.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/workuser.h"
#include "sf33rd/Source/Game/system/work_sys.h"

typedef enum RLTestMovement {
    RL_TEST_MOVEMENT_FORWARD = 0,
    RL_TEST_MOVEMENT_BACK = 1,
    RL_TEST_MOVEMENT_JUMP_FORWARD = 2,
    RL_TEST_MOVEMENT_DOWN_BACK = 3,
} RLTestMovement;

typedef enum RLLocalMove {
    RL_LOCAL_MOVE_NEUTRAL,
    RL_LOCAL_MOVE_FORWARD,
    RL_LOCAL_MOVE_BACK,
    RL_LOCAL_MOVE_JUMP_FORWARD,
    RL_LOCAL_MOVE_DOWN_BACK,
} RLLocalMove;

typedef struct RLLocalFakeAction {
    RLLocalMove move;
    u16 attacks;
    u16 hold_frames;
} RLLocalFakeAction;

static const RLLocalFakeAction kLocalFakeAgentSequence[] = {
    { RL_LOCAL_MOVE_FORWARD, 0, 30 },
    { RL_LOCAL_MOVE_NEUTRAL, SWK_WEST, 8 },
    { RL_LOCAL_MOVE_DOWN_BACK, 0, 24 },
    { RL_LOCAL_MOVE_NEUTRAL, 0, 8 },
    { RL_LOCAL_MOVE_JUMP_FORWARD, SWK_NORTH, 10 },
    { RL_LOCAL_MOVE_BACK, 0, 18 },
    { RL_LOCAL_MOVE_NEUTRAL, 0, 8 },
};

static u16 local_fake_action_index;
static u16 local_fake_action_frame;

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

static u16 RLSession_MapLocalMoveToSWKey(s16 player, RLLocalMove move) {
    const u16 forward = RLSession_ForwardDirectionForPlayer(player);
    const u16 back = RLSession_BackDirectionForPlayer(player);

    switch (move) {
    case RL_LOCAL_MOVE_BACK:
        return back;
    case RL_LOCAL_MOVE_JUMP_FORWARD:
        return (u16)(SWK_UP | forward);
    case RL_LOCAL_MOVE_DOWN_BACK:
        return (u16)(SWK_DOWN | back);
    case RL_LOCAL_MOVE_FORWARD:
        return forward;
    case RL_LOCAL_MOVE_NEUTRAL:
    default:
        return 0;
    }
}

static u16 RLSession_MapTestMovementToSWKey(s16 player) {
    switch (configuration.remote_rl_agent.test_movement) {
    case RL_TEST_MOVEMENT_BACK:
        return RLSession_MapLocalMoveToSWKey(player, RL_LOCAL_MOVE_BACK);
    case RL_TEST_MOVEMENT_JUMP_FORWARD:
        return RLSession_MapLocalMoveToSWKey(player, RL_LOCAL_MOVE_JUMP_FORWARD);
    case RL_TEST_MOVEMENT_DOWN_BACK:
        return RLSession_MapLocalMoveToSWKey(player, RL_LOCAL_MOVE_DOWN_BACK);
    case RL_TEST_MOVEMENT_FORWARD:
    default:
        return RLSession_MapLocalMoveToSWKey(player, RL_LOCAL_MOVE_FORWARD);
    }
}

static bool RLSession_CanOverrideGameplayInput() {
    return RLSession_IsActive() && Mode_Type == MODE_VERSUS && mpp_w.inGame && Play_Mode == 1 && Game_pause == 0;
}

static void RLSession_ResetLocalFakeAgent() {
    local_fake_action_index = 0;
    local_fake_action_frame = 0;
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
    if (!RLSession_OpponentUsesHumanInput() || !RLSession_CanOverrideGameplayInput()) {
        return;
    }

    RLSession_ResetLocalFakeAgent();

    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 movement = RLSession_MapTestMovementToSWKey(agent);
    u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;

    *target = (u16)((*target & ~SWK_DIRECTIONS) | movement);
}

static void RLSession_ApplyLocalFakeAgentToBuffers() {
    if (RLSession_OpponentUsesHumanInput() || !RLSession_CanOverrideGameplayInput()) {
        RLSession_ResetLocalFakeAgent();
        return;
    }

    const u16 action_count = (u16)(sizeof(kLocalFakeAgentSequence) / sizeof(kLocalFakeAgentSequence[0]));
    const RLLocalFakeAction* action = &kLocalFakeAgentSequence[local_fake_action_index];
    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 movement = RLSession_MapLocalMoveToSWKey(agent, action->move);
    u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;

    *target = (u16)((*target & ~(SWK_DIRECTIONS | SWK_ATTACKS)) | movement | action->attacks);

    local_fake_action_frame++;
    if (local_fake_action_frame >= action->hold_frames) {
        local_fake_action_frame = 0;
        local_fake_action_index = (u16)((local_fake_action_index + 1) % action_count);
    }
}

void RLSession_ApplyInputOverrideToBuffers() {
    RLSession_ApplyScriptedMovementToBuffers();
    RLSession_ApplyLocalFakeAgentToBuffers();
}
