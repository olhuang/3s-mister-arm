#ifndef RL_OBSERVATION_H
#define RL_OBSERVATION_H

#include "types.h"

#include <stdbool.h>
#include <stddef.h>

typedef struct RLObservationV1 {
    bool valid;
    f32 self_hp_ratio;
    f32 opp_hp_ratio;
    u8 self_super_stock;
    u8 self_super_stock_max;
    u8 opp_super_stock;
    u8 opp_super_stock_max;
    f32 self_super_gauge_ratio;
    f32 opp_super_gauge_ratio;
    f32 self_stun_ratio;
    f32 opp_stun_ratio;
    f32 opp_dx_ratio;
    f32 opp_dy_ratio;
    f32 self_left_corner_ratio;
    f32 self_right_corner_ratio;
    f32 opp_left_corner_ratio;
    f32 opp_right_corner_ratio;
    s8 self_facing_sign;
    u8 opp_in_front;
    u8 self_guard_flag;
    u8 opp_guard_flag;
    u16 self_current_attack;
    u16 opp_current_attack;
    u8 self_do_not_move;
    u8 opp_do_not_move;
    u8 self_hit_stop;
    u8 opp_hit_stop;
    u8 self_high_jump_flag;
    u8 opp_high_jump_flag;
    u16 self_routine[3];
    u16 opp_routine[3];
    u8 round_num;
    u8 self_round_wins;
    u8 opp_round_wins;
    u8 last_executed_move_intent;
    u16 last_executed_attack_bits;
    u8 next_scheduled_move_intent;
    u16 next_scheduled_attack_bits;
    u8 frames_until_next_action;
} RLObservationV1;

void RLObservation_OnFrameEnd();
const RLObservationV1* RLObservation_GetLatest();
u16 RLObservation_GetDebugInputSwKey();
u16 RLObservation_GetDebugDisplayMask();
void RLObservation_FormatDebugOverlay(char* out, size_t out_size, const char* session_label);

#endif
