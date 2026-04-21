#include "rl/rl_session.h"

#include "main.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/workuser.h"

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
