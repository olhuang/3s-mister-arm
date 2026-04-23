#include "rl/rl_observation.h"

#include "rl/rl_net.h"
#include "rl/rl_session.h"
#include "sf33rd/AcrSDK/common/pad.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/stun.h"
#include "sf33rd/Source/Game/system/sys_sub.h"
#include "sf33rd/Source/Game/engine/workuser.h"
#include "sf33rd/Source/Game/system/work_sys.h"

#include <SDL3/SDL.h>
#include <stdarg.h>
#include <stdio.h>

static RLObservationV1 latest_obs;
static s16 round_start_hp[2];
static u8 captured_round_num;
static bool round_start_hp_valid;
static u16 debug_input_swkey;
static s16 prev_frame_hp[2];
static s16 prev_frame_stun[2];
static s16 prev_frame_pos_x[2];
static s16 prev_frame_pos_y[2];
static u16 prev_frame_current_attack[2];
static s16 prev_frame_attack_counter[2];
static u16 prev_frame_routine1[2];
static u8 prev_frame_caution[2];
static u8 prev_frame_airborne[2];
static u8 prev_frame_hit_stop[2];
static u8 prev_frame_contact_state[2];
static bool prev_frame_valid;
static Uint64 obs_build_total_ns;
static Uint64 obs_build_max_ns;
static u32 obs_build_count;

typedef struct RLObservationDebugState {
    s16 self_hp;
    s16 opp_hp;
    s16 self_hp_start;
    s16 opp_hp_start;
    s16 self_super_stock;
    s16 self_super_stock_max;
    s16 opp_super_stock;
    s16 opp_super_stock_max;
    s16 self_super_gauge;
    s16 self_super_gauge_max;
    s16 opp_super_gauge;
    s16 opp_super_gauge_max;
    s16 self_stun;
    s16 self_stun_max;
    s16 opp_stun;
    s16 opp_stun_max;
    s16 self_left_corner;
    s16 self_right_corner;
    s16 opp_left_corner;
    s16 opp_right_corner;
    s16 opp_dx;
    s16 opp_dy;
    Uint32 obs_build_avg_us;
    Uint32 obs_build_max_us;
} RLObservationDebugState;

static RLObservationDebugState latest_debug;

enum {
    RL_DEBUG_BTN_LP = 0x0010,
    RL_DEBUG_BTN_MP = 0x0020,
    RL_DEBUG_BTN_HP = 0x0040,
    RL_DEBUG_BTN_LK = 0x0100,
    RL_DEBUG_BTN_MK = 0x0200,
    RL_DEBUG_BTN_HK = 0x0400,
};

static s16 clamp_s16_nonnegative(s16 value) {
    return (value < 0) ? 0 : value;
}

static s16 clamp_s16_delta(s32 value) {
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return (s16)value;
}

static f32 clamp_ratio(s32 numerator, s32 denominator) {
    if (denominator <= 0) {
        return 0.0f;
    }
    if (numerator <= 0) {
        return 0.0f;
    }
    if (numerator >= denominator) {
        return 1.0f;
    }
    return (f32)numerator / (f32)denominator;
}

static s16 safe_stun_max(s16 player) {
    if (plw[player].py == NULL || plw[player].py->genkai <= 0) {
        return 1;
    }
    return plw[player].py->genkai;
}

static s16 safe_super_max(s16 player) {
    if (plw[player].sa == NULL || plw[player].sa->store_max <= 0) {
        return 1;
    }
    return plw[player].sa->store_max;
}

static s16 safe_super_store(s16 player) {
    if (plw[player].sa == NULL) {
        return 0;
    }
    return plw[player].sa->store;
}

static s16 safe_super_gauge_value(s16 player) {
    if (plw[player].sa == NULL) {
        return 0;
    }
    return plw[player].sa->gauge.s.h;
}

static s16 safe_super_gauge_max(s16 player) {
    if (plw[player].sa == NULL || plw[player].sa->gauge_len <= 0) {
        return 1;
    }
    return plw[player].sa->gauge_len;
}

static u16 agent_input_swkey(s16 agent) {
    return (agent == 0) ? p1sw_0 : p2sw_0;
}

static s16 safe_stage_width(void) {
    const s16 width = scrr - scrl;
    return (width > 0) ? width : 1;
}

static void maybe_capture_round_start_hp() {
    if (!round_start_hp_valid || captured_round_num != Round_num ||
        plw[0].wu.vital_new > round_start_hp[0] || plw[1].wu.vital_new > round_start_hp[1]) {
        round_start_hp[0] = clamp_s16_nonnegative(plw[0].wu.vital_new);
        round_start_hp[1] = clamp_s16_nonnegative(plw[1].wu.vital_new);
        if (round_start_hp[0] <= 0) {
            round_start_hp[0] = 1;
        }
        if (round_start_hp[1] <= 0) {
            round_start_hp[1] = 1;
        }
        captured_round_num = Round_num;
        round_start_hp_valid = true;
    }
}

void RLObservation_OnFrameEnd() {
    const Uint64 build_start_ns = SDL_GetTicksNS();

    if (!RLSession_IsActive()) {
        latest_obs.valid = false;
        round_start_hp_valid = false;
        debug_input_swkey = 0;
        prev_frame_valid = false;
        return;
    }

    maybe_capture_round_start_hp();

    const s16 self = RLSession_AgentPlayerIndex();
    const s16 opp = RLSession_OpponentPlayerIndex();
    const s16 stage_width = safe_stage_width();
    const RLActionContext* action_context = RLSession_GetActionContext();
    RLObservationV1 obs = { 0 };
    RLObservationDebugState debug = { 0 };

    obs.valid = true;
    debug.self_hp = clamp_s16_nonnegative(plw[self].wu.vital_new);
    debug.opp_hp = clamp_s16_nonnegative(plw[opp].wu.vital_new);
    debug.self_hp_start = round_start_hp[self];
    debug.opp_hp_start = round_start_hp[opp];
    debug.self_super_stock = safe_super_store(self);
    debug.self_super_stock_max = safe_super_max(self);
    debug.opp_super_stock = safe_super_store(opp);
    debug.opp_super_stock_max = safe_super_max(opp);
    debug.self_super_gauge = safe_super_gauge_value(self);
    debug.self_super_gauge_max = safe_super_gauge_max(self);
    debug.opp_super_gauge = safe_super_gauge_value(opp);
    debug.opp_super_gauge_max = safe_super_gauge_max(opp);
    debug.self_stun = sdat[self].cstn;
    debug.self_stun_max = safe_stun_max(self);
    debug.opp_stun = sdat[opp].cstn;
    debug.opp_stun_max = safe_stun_max(opp);
    debug.opp_dx = plw[opp].wu.position_x - plw[self].wu.position_x;
    debug.opp_dy = plw[opp].wu.position_y - plw[self].wu.position_y;
    debug.self_left_corner = clamp_s16_nonnegative(plw[self].wu.position_x - scrl);
    debug.self_right_corner = clamp_s16_nonnegative(scrr - plw[self].wu.position_x);
    debug.opp_left_corner = clamp_s16_nonnegative(plw[opp].wu.position_x - scrl);
    debug.opp_right_corner = clamp_s16_nonnegative(scrr - plw[opp].wu.position_x);
    obs.self_hp_ratio = clamp_ratio(debug.self_hp, debug.self_hp_start);
    obs.opp_hp_ratio = clamp_ratio(debug.opp_hp, debug.opp_hp_start);
    obs.self_airborne = (u8)(plw[self].wu.position_y != 0);
    obs.opp_airborne = (u8)(plw[opp].wu.position_y != 0);
    obs.self_super_stock = (u8)debug.self_super_stock;
    obs.self_super_stock_max = (u8)debug.self_super_stock_max;
    obs.opp_super_stock = (u8)debug.opp_super_stock;
    obs.opp_super_stock_max = (u8)debug.opp_super_stock_max;
    obs.self_super_gauge_ratio = clamp_ratio(debug.self_super_gauge, debug.self_super_gauge_max);
    obs.opp_super_gauge_ratio = clamp_ratio(debug.opp_super_gauge, debug.opp_super_gauge_max);
    obs.self_stun_ratio = clamp_ratio(debug.self_stun, debug.self_stun_max);
    obs.opp_stun_ratio = clamp_ratio(debug.opp_stun, debug.opp_stun_max);
    obs.opp_dx_ratio = (f32)debug.opp_dx / (f32)stage_width;
    obs.opp_dy_ratio = (f32)debug.opp_dy / (f32)stage_width;
    obs.self_left_corner_ratio = clamp_ratio(debug.self_left_corner, stage_width);
    obs.self_right_corner_ratio = clamp_ratio(debug.self_right_corner, stage_width);
    obs.opp_left_corner_ratio = clamp_ratio(debug.opp_left_corner, stage_width);
    obs.opp_right_corner_ratio = clamp_ratio(debug.opp_right_corner, stage_width);
    obs.self_facing_sign = (plw[self].wu.rl_flag == 0) ? -1 : 1;
    obs.opp_facing_sign = (plw[opp].wu.rl_flag == 0) ? -1 : 1;
    obs.opp_in_front = (u8)((obs.self_facing_sign < 0) ? (plw[opp].wu.position_x < plw[self].wu.position_x)
                                                       : (plw[opp].wu.position_x > plw[self].wu.position_x));
    obs.self_guard_flag = plw[self].guard_flag;
    obs.opp_guard_flag = plw[opp].guard_flag;
    obs.self_current_attack = (u16)plw[self].current_attack;
    obs.opp_current_attack = (u16)plw[opp].current_attack;
    obs.self_do_not_move = plw[self].do_not_move;
    obs.opp_do_not_move = plw[opp].do_not_move;
    obs.self_hit_stop = plw[self].wu.hit_stop != 0;
    obs.opp_hit_stop = plw[opp].wu.hit_stop != 0;
    obs.self_high_jump_flag = plw[self].high_jump_flag;
    obs.opp_high_jump_flag = plw[opp].high_jump_flag;
    obs.self_routine[0] = (u16)plw[self].wu.routine_no[0];
    obs.self_routine[1] = (u16)plw[self].wu.routine_no[1];
    obs.self_routine[2] = (u16)plw[self].wu.routine_no[2];
    obs.opp_routine[0] = (u16)plw[opp].wu.routine_no[0];
    obs.opp_routine[1] = (u16)plw[opp].wu.routine_no[1];
    obs.opp_routine[2] = (u16)plw[opp].wu.routine_no[2];
    if (prev_frame_valid) {
        const s16 self_hp_delta = clamp_s16_delta((s32)prev_frame_hp[self] - (s32)debug.self_hp);
        const s16 opp_hp_delta = clamp_s16_delta((s32)prev_frame_hp[opp] - (s32)debug.opp_hp);
        const s16 self_x_delta = clamp_s16_delta((s32)plw[self].wu.position_x - (s32)prev_frame_pos_x[self]);
        const s16 opp_x_delta = clamp_s16_delta((s32)plw[opp].wu.position_x - (s32)prev_frame_pos_x[opp]);
        const s16 self_y_delta = clamp_s16_delta((s32)plw[self].wu.position_y - (s32)prev_frame_pos_y[self]);
        const s16 opp_y_delta = clamp_s16_delta((s32)plw[opp].wu.position_y - (s32)prev_frame_pos_y[opp]);
        const s16 self_stun_delta = clamp_s16_delta((s32)debug.self_stun - (s32)prev_frame_stun[self]);
        const s16 opp_stun_delta = clamp_s16_delta((s32)debug.opp_stun - (s32)prev_frame_stun[opp]);
        const u8 self_contact_state = (u8)((obs.self_guard_flag != 0) || obs.self_hit_stop);
        const u8 opp_contact_state = (u8)((obs.opp_guard_flag != 0) || obs.opp_hit_stop);

        obs.delta_self_hp = self_hp_delta;
        obs.delta_opp_hp = opp_hp_delta;
        obs.delta_self_x = self_x_delta;
        obs.delta_self_y = self_y_delta;
        obs.delta_opp_x = opp_x_delta;
        obs.delta_opp_y = opp_y_delta;
        obs.delta_self_stun = self_stun_delta;
        obs.delta_opp_stun = opp_stun_delta;
        obs.self_entered_hit_stop = (u8)(!prev_frame_hit_stop[self] && obs.self_hit_stop);
        obs.opp_entered_hit_stop = (u8)(!prev_frame_hit_stop[opp] && obs.opp_hit_stop);
        obs.self_airborne_started = (u8)(!prev_frame_airborne[self] && obs.self_airborne);
        obs.opp_airborne_started = (u8)(!prev_frame_airborne[opp] && obs.opp_airborne);
        obs.self_attack_started = (u8)(prev_frame_current_attack[self] == 0 && obs.self_current_attack != 0);
        obs.opp_attack_started = (u8)(prev_frame_current_attack[opp] == 0 && obs.opp_current_attack != 0);
        obs.self_attack_code_changed =
            (u8)(prev_frame_current_attack[self] != obs.self_current_attack && obs.self_current_attack != 0);
        obs.opp_attack_code_changed =
            (u8)(prev_frame_current_attack[opp] != obs.opp_current_attack && obs.opp_current_attack != 0);
        obs.self_attack_counter_started = (u8)(Attack_Counter[opp] != prev_frame_attack_counter[opp]);
        obs.opp_attack_counter_started = (u8)(Attack_Counter[self] != prev_frame_attack_counter[self]);
        obs.self_attack_routine_started = (u8)(prev_frame_routine1[self] != 4 && obs.self_routine[1] == 4);
        obs.opp_attack_routine_started = (u8)(prev_frame_routine1[opp] != 4 && obs.opp_routine[1] == 4);
        obs.self_caution_started = (u8)(!prev_frame_caution[self] && plw[self].caution_flag);
        obs.opp_caution_started = (u8)(!prev_frame_caution[opp] && plw[opp].caution_flag);
        obs.self_entered_contact_state = (u8)(!prev_frame_contact_state[self] && self_contact_state);
        obs.opp_entered_contact_state = (u8)(!prev_frame_contact_state[opp] && opp_contact_state);
        obs.self_entered_damage_state = (u8)(self_hp_delta > 0 || self_stun_delta > 0);
        obs.opp_entered_damage_state = (u8)(opp_hp_delta > 0 || opp_stun_delta > 0);
        prev_frame_contact_state[self] = self_contact_state;
        prev_frame_contact_state[opp] = opp_contact_state;
    } else {
        prev_frame_contact_state[self] = (u8)((obs.self_guard_flag != 0) || obs.self_hit_stop);
        prev_frame_contact_state[opp] = (u8)((obs.opp_guard_flag != 0) || obs.opp_hit_stop);
    }
    obs.round_num = Round_num;
    obs.self_match_round_wins = PL_Wins[self];
    obs.opp_match_round_wins = PL_Wins[opp];
    obs.self_round_wins = (u8)VS_Win_Record[self];
    obs.opp_round_wins = (u8)VS_Win_Record[opp];
    obs.last_executed_move_intent = action_context->last_executed_move_intent;
    obs.last_executed_attack_bits = action_context->last_executed_attack_bits;
    obs.next_scheduled_move_intent = action_context->next_scheduled_move_intent;
    obs.next_scheduled_attack_bits = action_context->next_scheduled_attack_bits;
    obs.frames_until_next_action = action_context->frames_until_next_action;

    latest_obs = obs;
    latest_debug = debug;
    debug_input_swkey = agent_input_swkey(self);
    prev_frame_hp[self] = debug.self_hp;
    prev_frame_hp[opp] = debug.opp_hp;
    prev_frame_pos_x[self] = plw[self].wu.position_x;
    prev_frame_pos_x[opp] = plw[opp].wu.position_x;
    prev_frame_pos_y[self] = plw[self].wu.position_y;
    prev_frame_pos_y[opp] = plw[opp].wu.position_y;
    prev_frame_current_attack[self] = obs.self_current_attack;
    prev_frame_current_attack[opp] = obs.opp_current_attack;
    prev_frame_attack_counter[self] = Attack_Counter[self];
    prev_frame_attack_counter[opp] = Attack_Counter[opp];
    prev_frame_routine1[self] = obs.self_routine[1];
    prev_frame_routine1[opp] = obs.opp_routine[1];
    prev_frame_caution[self] = (u8)(plw[self].caution_flag != 0);
    prev_frame_caution[opp] = (u8)(plw[opp].caution_flag != 0);
    prev_frame_airborne[self] = obs.self_airborne;
    prev_frame_airborne[opp] = obs.opp_airborne;
    prev_frame_stun[self] = debug.self_stun;
    prev_frame_stun[opp] = debug.opp_stun;
    prev_frame_hit_stop[self] = obs.self_hit_stop;
    prev_frame_hit_stop[opp] = obs.opp_hit_stop;
    prev_frame_valid = true;
    RLSession_OnObservationFrameEnd(&latest_obs);

    {
        const Uint64 build_ns = SDL_GetTicksNS() - build_start_ns;
        obs_build_total_ns += build_ns;
        obs_build_count++;
        if (build_ns > obs_build_max_ns) {
            obs_build_max_ns = build_ns;
        }
        latest_debug.obs_build_avg_us = (Uint32)((obs_build_total_ns / SDL_max(1u, obs_build_count)) / 1000u);
        latest_debug.obs_build_max_us = (Uint32)(obs_build_max_ns / 1000u);
    }
}

const RLObservationV1* RLObservation_GetLatest() {
    return &latest_obs;
}

u16 RLObservation_GetDebugInputSwKey() {
    return latest_obs.valid ? debug_input_swkey : 0;
}

u16 RLObservation_GetDebugDisplayMask() {
    if (!latest_obs.valid) {
        return 0;
    }

    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 logical = Convert_User_Setting(agent) &
                        (RL_DEBUG_BTN_LP | RL_DEBUG_BTN_MP | RL_DEBUG_BTN_HP |
                         RL_DEBUG_BTN_LK | RL_DEBUG_BTN_MK | RL_DEBUG_BTN_HK);
    const u16 directions = debug_input_swkey & (SWK_UP | SWK_DOWN | SWK_LEFT | SWK_RIGHT);
    return (u16)(directions | logical);
}

static void append_overlay_line(char* out, size_t out_size, size_t* used, const char* fmt, ...) {
    if (out_size == 0 || used == NULL || *used >= out_size) {
        return;
    }
    if (*used > 0) {
        const int newline_written = snprintf(out + *used, out_size - *used, "\n");
        if (newline_written <= 0) {
            return;
        }
        *used += (size_t)newline_written;
        if (*used >= out_size) {
            return;
        }
    }

    va_list args;
    va_start(args, fmt);
    const int written = vsnprintf(out + *used, out_size - *used, fmt, args);
    va_end(args);
    if (written > 0) {
        *used += (size_t)written;
        if (*used >= out_size) {
            *used = out_size - 1;
        }
    }
}

void RLObservation_FormatDebugOverlay(char* out, size_t out_size, const char* session_label, RLDebugOverlayView view) {
    if (out_size == 0) {
        return;
    }
    out[0] = '\0';

    if (view == RL_DEBUG_OVERLAY_VIEW_OFF) {
        return;
    }

    if (!latest_obs.valid) {
        snprintf(out, out_size, "%s\nOBS WAIT", session_label != NULL ? session_label : "P0");
        return;
    }

    const char dx_side = latest_debug.opp_dx < 0 ? 'L' : 'R';
    const int dx_abs = latest_debug.opp_dx < 0 ? -latest_debug.opp_dx : latest_debug.opp_dx;
    const RLNetState* net = RLNet_GetState();
    const RLRemoteDebugState* remote = RLSession_GetRemoteDebugState();
    const char* net_state = "OFF";
    if (net->enabled) {
        net_state = net->handshake_accepted ? "OK" : (net->socket_open ? "HELLO" : "ERR");
    }

    size_t used = 0;
    const bool show_all = view == RL_DEBUG_OVERLAY_VIEW_ALL;

    append_overlay_line(out,
                        out_size,
                        &used,
                        "%s HP%d/%d OP%d/%d R%d RW%d-%d M%d-%d",
                        session_label != NULL ? session_label : "P0",
                        latest_debug.self_hp,
                        latest_debug.self_hp_start,
                        latest_debug.opp_hp,
                        latest_debug.opp_hp_start,
                        latest_obs.round_num,
                        latest_obs.self_match_round_wins,
                        latest_obs.opp_match_round_wins,
                        latest_obs.self_round_wins,
                        latest_obs.opp_round_wins);

    if (show_all || view == RL_DEBUG_OVERLAY_VIEW_FIGHT) {
        append_overlay_line(out,
                            out_size,
                            &used,
                            "SA%d/%d SG%d/%d ST%d/%d",
                            latest_debug.self_super_stock,
                            latest_debug.self_super_stock_max,
                            latest_debug.self_super_gauge,
                            latest_debug.self_super_gauge_max,
                            latest_debug.self_stun,
                            latest_debug.self_stun_max);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "DX%c%d DY%d F%d",
                            dx_side,
                            dx_abs,
                            latest_debug.opp_dy,
                            latest_obs.self_facing_sign);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "CL%d CR%d OL%d OR%d",
                            latest_debug.self_left_corner,
                            latest_debug.self_right_corner,
                            latest_debug.opp_left_corner,
                            latest_debug.opp_right_corner);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "CF%d/%d AK%03X/%03X",
                            latest_obs.self_guard_flag,
                            latest_obs.opp_guard_flag,
                            latest_obs.self_current_attack,
                            latest_obs.opp_current_attack);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "NM%d/%d HS%d/%d HJ%d/%d",
                            latest_obs.self_do_not_move,
                            latest_obs.opp_do_not_move,
                            latest_obs.self_hit_stop,
                            latest_obs.opp_hit_stop,
                            latest_obs.self_high_jump_flag,
                            latest_obs.opp_high_jump_flag);
        if (show_all) {
            append_overlay_line(out,
                                out_size,
                                &used,
                                "SR%d,%d,%d OR%d,%d,%d",
                                latest_obs.self_routine[0],
                                latest_obs.self_routine[1],
                                latest_obs.self_routine[2],
                                latest_obs.opp_routine[0],
                                latest_obs.opp_routine[1],
                                latest_obs.opp_routine[2]);
        }
    }

    if (show_all || view == RL_DEBUG_OVERLAY_VIEW_OUTCOME) {
        append_overlay_line(out,
                            out_size,
                            &used,
                            "DH%d/%d DS%d/%d AB%d/%d",
                            latest_obs.delta_self_hp,
                            latest_obs.delta_opp_hp,
                            latest_obs.delta_self_stun,
                            latest_obs.delta_opp_stun,
                            latest_obs.self_airborne,
                            latest_obs.opp_airborne);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "EH%d/%d EC%d/%d ED%d/%d",
                            latest_obs.self_entered_hit_stop,
                            latest_obs.opp_entered_hit_stop,
                            latest_obs.self_entered_contact_state,
                            latest_obs.opp_entered_contact_state,
                            latest_obs.self_entered_damage_state,
                            latest_obs.opp_entered_damage_state);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "RF%d/%d MS%d AI%d AR%d OS%d/%d/%d AC%d AW%d J%d",
                            remote->last_delta_self_forward,
                            remote->last_delta_opp_forward,
                            remote->last_requested_movement_succeeded,
                            remote->last_requested_attack_input_started,
                            remote->last_requested_attack_became_active,
                            remote->last_observed_attack_state_started,
                            remote->last_observed_attack_code_changed,
                            remote->last_observed_attack_counter_started,
                            remote->last_requested_attack_made_contact,
                            remote->last_requested_attack_likely_whiffed,
                            remote->last_requested_jump_started);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "AH%lu ACC%lu AWC%lu",
                            (unsigned long)remote->episode_attack_active_count,
                            (unsigned long)remote->episode_attack_contact_count,
                            (unsigned long)remote->episode_attack_whiff_count);
    }

    if (show_all || view == RL_DEBUG_OVERLAY_VIEW_INPUT) {
        append_overlay_line(out,
                            out_size,
                            &used,
                            "X%d/%03X N%d/%03X T%d O%lu/%luus",
                            latest_obs.last_executed_move_intent,
                            latest_obs.last_executed_attack_bits,
                            latest_obs.next_scheduled_move_intent,
                            latest_obs.next_scheduled_attack_bits,
                            latest_obs.frames_until_next_action,
                            (unsigned long)latest_debug.obs_build_avg_us,
                            (unsigned long)latest_debug.obs_build_max_us);
    }

    if (show_all || view == RL_DEBUG_OVERLAY_VIEW_NET) {
        append_overlay_line(out,
                            out_size,
                            &used,
                            "NET%s S%u P%u/%u/%u MAX%uus E%u",
                            net_state,
                            (unsigned int)net->probe_stats.sample_count,
                            (unsigned int)net->probe_stats.p50_us,
                            (unsigned int)net->probe_stats.p95_us,
                            (unsigned int)net->probe_stats.p99_us,
                            (unsigned int)net->probe_stats.max_us,
                            (unsigned int)net->last_error_count);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "ACT%u OK%u UA%u SN%u BV%u BM%u",
                            (unsigned int)net->action_received_count,
                            (unsigned int)net->action_accepted_count,
                            (unsigned int)net->action_rejected_unacked_count,
                            (unsigned int)net->action_rejected_nonce_count,
                            (unsigned int)net->action_rejected_version_count,
                            (unsigned int)net->action_rejected_malformed_count);
        append_overlay_line(out,
                            out_size,
                            &used,
                            "OBS%u Q%u/%u EX%u LT%u DU%u TM%u FB%u",
                            (unsigned int)remote->obs_sent_count,
                            (unsigned int)remote->queue_depth,
                            (unsigned int)remote->queued_count,
                            (unsigned int)remote->executed_count,
                            (unsigned int)remote->late_drop_count,
                            (unsigned int)remote->duplicate_drop_count,
                            (unsigned int)remote->target_mismatch_count,
                            (unsigned int)remote->fallback_count);
    }
}
