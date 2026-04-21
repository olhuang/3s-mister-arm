#ifndef RL_OBSERVATION_H
#define RL_OBSERVATION_H

#include "types.h"

#include <stdbool.h>
#include <stddef.h>

typedef struct RLObservationV1 {
    bool valid;
    s16 self_hp;
    s16 opp_hp;
    s16 self_hp_start;
    s16 opp_hp_start;
    s16 self_super;
    s16 self_super_max;
    s16 opp_super;
    s16 opp_super_max;
    s16 self_stun;
    s16 self_stun_max;
    s16 opp_stun;
    s16 opp_stun_max;
    s16 opp_dx;
    s16 opp_dy;
    s8 self_facing_sign;
    u8 opp_in_front;
    u8 self_guard_flag;
    u8 opp_guard_flag;
    s16 self_current_attack;
    s16 opp_current_attack;
    u8 self_do_not_move;
    u8 opp_do_not_move;
    u8 self_hit_stop;
    u8 opp_hit_stop;
    u8 self_high_jump_flag;
    u8 opp_high_jump_flag;
    s16 self_routine[3];
    s16 opp_routine[3];
    u8 round_num;
    u8 self_round_wins;
    u8 opp_round_wins;
    u16 input_swkey;
} RLObservationV1;

void RLObservation_OnFrameEnd();
const RLObservationV1* RLObservation_GetLatest();
u16 RLObservation_GetDebugInputSwKey();
void RLObservation_FormatDebugOverlay(char* out, size_t out_size, const char* session_label);

#endif
