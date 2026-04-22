#ifndef RL_NET_H
#define RL_NET_H

#include "rl/rl_protocol.h"

#include <stdbool.h>

typedef struct RLNetState {
    bool enabled;
    bool handshake_accepted;
    u64 session_nonce;
    RLSessionConfig config;
    RLProbeStats probe_stats;
} RLNetState;

void RLNet_InitDisabled(void);
const RLNetState* RLNet_GetState(void);
bool RLNet_IsHandshakeAccepted(void);

#endif
