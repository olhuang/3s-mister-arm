#ifndef RL_NET_H
#define RL_NET_H

#include "configuration.h"
#include "rl/rl_protocol.h"

#include <stdbool.h>

typedef struct RLNetState {
    bool enabled;
    bool handshake_accepted;
    bool socket_open;
    bool probe_ready;
    u64 session_nonce;
    u32 probe_sequence;
    u32 last_error_count;
    u32 sent_count;
    u32 received_count;
    RLSessionConfig config;
    RLProbeStats probe_stats;
} RLNetState;

void RLNet_InitDisabled(void);
void RLNet_Init(const RemoteRLAgentConfiguration* config);
void RLNet_Tick(void);
void RLNet_Shutdown(void);
const RLNetState* RLNet_GetState(void);
bool RLNet_IsHandshakeAccepted(void);

#endif
