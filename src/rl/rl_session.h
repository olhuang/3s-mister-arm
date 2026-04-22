#ifndef RL_SESSION_H
#define RL_SESSION_H

#include "types.h"

#include <stdbool.h>

typedef enum RLMoveIntent {
    RL_MOVE_NEUTRAL = 0,
    RL_MOVE_UP = 1,
    RL_MOVE_DOWN = 2,
    RL_MOVE_BACK = 3,
    RL_MOVE_FORWARD = 4,
    RL_MOVE_UP_BACK = 5,
    RL_MOVE_UP_FORWARD = 6,
    RL_MOVE_DOWN_BACK = 7,
    RL_MOVE_DOWN_FORWARD = 8,
} RLMoveIntent;

typedef struct RLActionContext {
    u8 last_executed_move_intent;
    u16 last_executed_attack_bits;
    u8 next_scheduled_move_intent;
    u16 next_scheduled_attack_bits;
    u8 frames_until_next_action;
} RLActionContext;

bool RLSession_IsActive();
s16 RLSession_AgentPlayerIndex();
s16 RLSession_OpponentPlayerIndex();
bool RLSession_OpponentUsesHumanInput();
const char* RLSession_TestMovementLabel();
const RLActionContext* RLSession_GetActionContext();
void RLSession_ApplyVersusOperatorSetup();
void RLSession_ApplyScriptedMovementToBuffers();
void RLSession_ApplyInputOverrideToBuffers();

#endif
