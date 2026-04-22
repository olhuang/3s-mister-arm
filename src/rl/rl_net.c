#include "rl/rl_net.h"

#include <string.h>

static RLNetState rl_net_state;

void RLNet_InitDisabled(void) {
    memset(&rl_net_state, 0, sizeof(rl_net_state));
    rl_net_state.config = RLProtocol_DefaultConfig();
}

const RLNetState* RLNet_GetState(void) {
    if (rl_net_state.config.protocol_version == 0) {
        RLNet_InitDisabled();
    }
    return &rl_net_state;
}

bool RLNet_IsHandshakeAccepted(void) {
    return RLNet_GetState()->handshake_accepted;
}
