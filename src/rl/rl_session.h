#ifndef RL_SESSION_H
#define RL_SESSION_H

#include "types.h"

#include <stdbool.h>

bool RLSession_IsActive();
s16 RLSession_AgentPlayerIndex();
s16 RLSession_OpponentPlayerIndex();
bool RLSession_OpponentUsesHumanInput();
const char* RLSession_TestMovementLabel();
void RLSession_ApplyVersusOperatorSetup();
void RLSession_ApplyScriptedMovementToBuffers();

#endif
