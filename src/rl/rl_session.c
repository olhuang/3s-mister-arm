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
    return (plw[player].wu.rl_flag == 0) ? SWK_RIGHT : SWK_LEFT;
}

static u16 RLSession_BackDirectionForPlayer(s16 player) {
    return (plw[player].wu.rl_flag == 0) ? SWK_LEFT : SWK_RIGHT;
}

static u16 RLSession_MapTestMovementToSWKey(s16 player) {
    const u16 forward = RLSession_ForwardDirectionForPlayer(player);
    const u16 back = RLSession_BackDirectionForPlayer(player);

    switch (configuration.remote_rl_agent.test_movement) {
    case RL_TEST_MOVEMENT_BACK:
        return back;
    case RL_TEST_MOVEMENT_JUMP_FORWARD:
        return (u16)(SWK_UP | forward);
    case RL_TEST_MOVEMENT_DOWN_BACK:
        return (u16)(SWK_DOWN | back);
    case RL_TEST_MOVEMENT_FORWARD:
    default:
        return forward;
    }
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
    if (!RLSession_IsActive() || !RLSession_OpponentUsesHumanInput() || Mode_Type != MODE_VERSUS) {
        return;
    }

    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 movement = RLSession_MapTestMovementToSWKey(agent);
    u16* target = (agent == 0) ? &p1sw_buff : &p2sw_buff;

    *target = (u16)((*target & ~SWK_DIRECTIONS) | movement);
}
