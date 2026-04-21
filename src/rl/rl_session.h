#ifndef RL_SESSION_H
#define RL_SESSION_H

#include "types.h"

#include <stdbool.h>

bool RLSession_IsActive();
s16 RLSession_AgentPlayerIndex();
s16 RLSession_CPUPlayerIndex();
void RLSession_ApplyVersusOperatorSetup();

#endif
