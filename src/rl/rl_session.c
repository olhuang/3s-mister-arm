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

s16 RLSession_CPUPlayerIndex() {
    return RLSession_AgentPlayerIndex() ^ 1;
}

void RLSession_ApplyVersusOperatorSetup() {
    if (!RLSession_IsActive() || Mode_Type != MODE_VERSUS) {
        return;
    }

    const s16 agent = RLSession_AgentPlayerIndex();
    const s16 cpu = RLSession_CPUPlayerIndex();

    plw[agent].wu.operator = 1;
    Operator_Status[agent] = 1;
    plw[cpu].wu.operator = 0;
    Operator_Status[cpu] = 0;
}
