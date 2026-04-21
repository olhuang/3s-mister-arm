#include "rl/rl_observation.h"

#include "rl/rl_session.h"
#include "sf33rd/AcrSDK/common/pad.h"
#include "sf33rd/Source/Game/engine/plcnt.h"
#include "sf33rd/Source/Game/engine/stun.h"
#include "sf33rd/Source/Game/system/sys_sub.h"
#include "sf33rd/Source/Game/engine/workuser.h"
#include "sf33rd/Source/Game/system/work_sys.h"

#include <stdio.h>

static RLObservationV1 latest_obs;
static s16 round_start_hp[2];
static u8 captured_round_num;
static bool round_start_hp_valid;

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

static u16 agent_input_swkey(s16 agent) {
    return (agent == 0) ? p1sw_0 : p2sw_0;
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
    if (!RLSession_IsActive()) {
        latest_obs.valid = false;
        round_start_hp_valid = false;
        return;
    }

    maybe_capture_round_start_hp();

    const s16 self = RLSession_AgentPlayerIndex();
    const s16 opp = RLSession_OpponentPlayerIndex();
    RLObservationV1 obs = { 0 };

    obs.valid = true;
    obs.self_hp = clamp_s16_nonnegative(plw[self].wu.vital_new);
    obs.opp_hp = clamp_s16_nonnegative(plw[opp].wu.vital_new);
    obs.self_hp_start = round_start_hp[self];
    obs.opp_hp_start = round_start_hp[opp];
    obs.self_super = safe_super_store(self);
    obs.self_super_max = safe_super_max(self);
    obs.opp_super = safe_super_store(opp);
    obs.opp_super_max = safe_super_max(opp);
    obs.self_stun = sdat[self].cstn;
    obs.self_stun_max = safe_stun_max(self);
    obs.opp_stun = sdat[opp].cstn;
    obs.opp_stun_max = safe_stun_max(opp);
    obs.opp_dx = plw[opp].wu.position_x - plw[self].wu.position_x;
    obs.opp_dy = plw[opp].wu.position_y - plw[self].wu.position_y;
    obs.self_facing_sign = (plw[self].wu.rl_flag == 0) ? -1 : 1;
    obs.opp_in_front = (obs.self_facing_sign < 0) ? (plw[opp].wu.position_x < plw[self].wu.position_x)
                                                  : (plw[opp].wu.position_x > plw[self].wu.position_x);
    obs.self_guard_flag = plw[self].guard_flag;
    obs.opp_guard_flag = plw[opp].guard_flag;
    obs.self_current_attack = plw[self].current_attack;
    obs.opp_current_attack = plw[opp].current_attack;
    obs.self_do_not_move = plw[self].do_not_move;
    obs.opp_do_not_move = plw[opp].do_not_move;
    obs.self_hit_stop = plw[self].wu.hit_stop != 0;
    obs.opp_hit_stop = plw[opp].wu.hit_stop != 0;
    obs.self_high_jump_flag = plw[self].high_jump_flag;
    obs.opp_high_jump_flag = plw[opp].high_jump_flag;
    obs.self_routine[0] = plw[self].wu.routine_no[0];
    obs.self_routine[1] = plw[self].wu.routine_no[1];
    obs.self_routine[2] = plw[self].wu.routine_no[2];
    obs.opp_routine[0] = plw[opp].wu.routine_no[0];
    obs.opp_routine[1] = plw[opp].wu.routine_no[1];
    obs.opp_routine[2] = plw[opp].wu.routine_no[2];
    obs.round_num = Round_num;
    obs.self_round_wins = (u8)Win_Record[self];
    obs.opp_round_wins = (u8)Win_Record[opp];
    obs.input_swkey = agent_input_swkey(self);

    latest_obs = obs;
}

const RLObservationV1* RLObservation_GetLatest() {
    return &latest_obs;
}

u16 RLObservation_GetDebugInputSwKey() {
    return latest_obs.valid ? latest_obs.input_swkey : 0;
}

u16 RLObservation_GetDebugDisplayMask() {
    if (!latest_obs.valid) {
        return 0;
    }

    const s16 agent = RLSession_AgentPlayerIndex();
    const u16 logical = Convert_User_Setting(agent) &
                        (RL_DEBUG_BTN_LP | RL_DEBUG_BTN_MP | RL_DEBUG_BTN_HP |
                         RL_DEBUG_BTN_LK | RL_DEBUG_BTN_MK | RL_DEBUG_BTN_HK);
    const u16 directions = latest_obs.input_swkey & (SWK_UP | SWK_DOWN | SWK_LEFT | SWK_RIGHT);
    return (u16)(directions | logical);
}

void RLObservation_FormatDebugOverlay(char* out, size_t out_size, const char* session_label) {
    if (out_size == 0) {
        return;
    }

    if (!latest_obs.valid) {
        snprintf(out, out_size, "%s\nOBS WAIT", session_label != NULL ? session_label : "P0");
        return;
    }

    const char dx_side = latest_obs.opp_dx < 0 ? 'L' : 'R';
    const int dx_abs = latest_obs.opp_dx < 0 ? -latest_obs.opp_dx : latest_obs.opp_dx;

    snprintf(out,
             out_size,
             "%s HP%d/%d OP%d/%d\nSA%d/%d ST%d/%d DX%c%d F%d R%d",
             session_label != NULL ? session_label : "P0",
             latest_obs.self_hp,
             latest_obs.self_hp_start,
             latest_obs.opp_hp,
             latest_obs.opp_hp_start,
             latest_obs.self_super,
             latest_obs.self_super_max,
             latest_obs.self_stun,
             latest_obs.self_stun_max,
             dx_side,
             dx_abs,
             latest_obs.self_facing_sign,
             latest_obs.round_num);
}
