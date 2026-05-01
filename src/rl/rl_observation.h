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
    f32 self_hp_ratio;
    f32 opp_hp_ratio;
    s16 delta_self_hp;
    s16 delta_opp_hp;
    s16 delta_self_x;
    s16 delta_self_y;
    s16 delta_opp_x;
    s16 delta_opp_y;
    u8 self_super_stock;
    u8 self_super_stock_max;
    u8 opp_super_stock;
    u8 opp_super_stock_max;
    f32 self_super_gauge_ratio;
    f32 opp_super_gauge_ratio;
    f32 self_stun_ratio;
    f32 opp_stun_ratio;
    s16 delta_self_stun;
    s16 delta_opp_stun;
    f32 opp_dx_ratio;
    f32 opp_dy_ratio;
    f32 self_left_corner_ratio;
    f32 self_right_corner_ratio;
    f32 opp_left_corner_ratio;
    f32 opp_right_corner_ratio;
    s8 self_facing_sign;
    s8 opp_facing_sign;
    u8 opp_in_front;
    u8 self_guard_flag;
    u8 opp_guard_flag;
    u16 self_current_attack;
    u16 opp_current_attack;
    u8 self_kind_of_waza;
    u8 opp_kind_of_waza;
    u8 self_do_not_move;
    u8 opp_do_not_move;
    u8 self_hit_stop;
    u8 opp_hit_stop;
    u8 self_high_jump_flag;
    u8 opp_high_jump_flag;
    u8 self_airborne;
    u8 opp_airborne;
    u8 self_jump_phase;
    u8 self_ground_action_start_allowed;
    u8 self_jump_start_allowed;
    u8 self_air_attack_allowed;
    u8 self_airborne_started;
    u8 opp_airborne_started;
    u8 self_attack_started;
    u8 opp_attack_started;
    u8 self_attack_code_changed;
    u8 opp_attack_code_changed;
    u8 self_attack_counter_started;
    u8 opp_attack_counter_started;
    u8 self_attack_routine_started;
    u8 opp_attack_routine_started;
    u8 self_routine_attack_state;
    u8 opp_routine_attack_state;
    u8 self_contact_reaction_state;
    u8 opp_contact_reaction_state;
    u8 self_caution_started;
    u8 opp_caution_started;
    u8 self_entered_hit_stop;
    u8 opp_entered_hit_stop;
    u8 self_entered_contact_state;
    u8 opp_entered_contact_state;
    u8 self_entered_damage_state;
    u8 opp_entered_damage_state;
    u8 self_throw_active;
    u8 opp_throw_caught;
    u8 self_throw_started;
    u8 opp_throw_caught_started;
    u16 self_routine[3];
    u16 opp_routine[3];
    u8 round_num;
    u8 self_match_round_wins;
    u8 opp_match_round_wins;
    u8 self_round_wins;
    u8 opp_round_wins;
    u8 last_executed_move_intent;
    u16 last_executed_attack_bits;
    u8 next_scheduled_move_intent;
    u16 next_scheduled_attack_bits;
    u8 frames_until_next_action;
} RLObservationV1;

typedef enum RLDebugOverlayView {
    RL_DEBUG_OVERLAY_VIEW_OFF = 0,
    RL_DEBUG_OVERLAY_VIEW_ALL = 1,
    RL_DEBUG_OVERLAY_VIEW_NET = 2,
    RL_DEBUG_OVERLAY_VIEW_INPUT = 3,
    RL_DEBUG_OVERLAY_VIEW_FIGHT = 4,
    RL_DEBUG_OVERLAY_VIEW_OUTCOME = 5,
} RLDebugOverlayView;

void RLObservation_OnFrameEnd();
const RLObservationV1* RLObservation_GetLatest();
u16 RLObservation_GetDebugInputSwKey();
u16 RLObservation_GetDebugDisplayMask();
void RLObservation_FormatDebugOverlay(char* out, size_t out_size, const char* session_label, RLDebugOverlayView view);

#endif
