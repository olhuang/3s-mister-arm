#ifndef PORT_CONFIG_H
#define PORT_CONFIG_H

#include <stdbool.h>

#define CFG_KEY_FULLSCREEN "fullscreen"
#define CFG_KEY_WINDOW_WIDTH "window-width"
#define CFG_KEY_WINDOW_HEIGHT "window-height"
#define CFG_KEY_SCALEMODE "scale-mode"
#define CFG_KEY_SCANLINES "scanlines"
#define CFG_DRAW_PLAYERS_ABOVE_HUD "draw-players-above-hud"
#define CFG_ARCADE_BALANCE "arcade-balance"
#define CFG_KEY_SOFTWARE_FRAME_MODE "software-frame-mode"
#define CFG_KEY_SUPER_EFFECT_QUALITY "super-effect-quality"
#define CFG_KEY_SHOW_FPS "show-fps"
#define CFG_KEY_VIDEO_DRIVER_ORDER "video-driver-order"
#define CFG_KEY_RENDER_DRIVER_ORDER "render-driver-order"
#define CFG_KEY_GHOST_RESOLUTION "ghost-resolution"
#define CFG_KEY_GHOST_COUNT "ghost-count"
#define CFG_KEY_ARM_CLOCK "arm-clock"
#define CFG_KEY_GAME_MODE "game-mode"
#define CFG_KEY_HOLD_TO_PAUSE "hold-to-pause"
#define CFG_KEY_AI_LUCK_CURRENT_INPUT_CHEAT "ai-luck-current-input-cheat"
#define CFG_KEY_AI_LUCK_PRECISE_GROUND_CHEAT "ai-luck-precise-ground-cheat"
#define CFG_KEY_AI_LUCK_PRECISE_AIR_CHEAT "ai-luck-precise-air-cheat"
#define CFG_KEY_AI_GRIT_BONUS_LOW "ai-grit-bonus-low"
#define CFG_KEY_AI_GRIT_BONUS_MID "ai-grit-bonus-mid"
#define CFG_KEY_AI_GRIT_BONUS_HIGH "ai-grit-bonus-high"
#define CFG_KEY_AI_GUARD_SENSE_LAG_BAL "ai-guard-sense-lag-bal"
#define CFG_KEY_AI_GUARD_SENSE_LAG_RSH "ai-guard-sense-lag-rsh"
#define CFG_KEY_AI_GUARD_SENSE_LAG_TRK "ai-guard-sense-lag-trk"
#define CFG_KEY_AI_GUARD_SENSE_LAG_MET "ai-guard-sense-lag-met"
#define CFG_KEY_AI_PROFILE_BAL "ai-profile-bal"
#define CFG_KEY_AI_PROFILE_RSH "ai-profile-rsh"
#define CFG_KEY_AI_PROFILE_TRK "ai-profile-trk"
#define CFG_KEY_AI_PROFILE_MET "ai-profile-met"
#define CFG_KEY_AI_MOOD_DURATION_RUSHDOWN "ai-mood-duration-rushdown"
#define CFG_KEY_AI_MOOD_DURATION_BAIT "ai-mood-duration-bait"
#define CFG_KEY_AI_MOOD_DURATION_TILT "ai-mood-duration-tilt"
#define CFG_KEY_AI_MOOD_DURATION_PANIC "ai-mood-duration-panic"
#define CFG_KEY_AI_MOOD_DURATION_CONFIDENCE "ai-mood-duration-confidence"
#define CFG_KEY_AI_MOOD_CONFIDENCE_STREAK "ai-mood-confidence-streak"
#define CFG_KEY_AI_MOOD_PANIC_MAX_LV08 "ai-mood-panic-max-lv08"
#define CFG_KEY_AI_ADAPT_THRESHOLD_JUMP "ai-adapt-threshold-jump"
#define CFG_KEY_AI_ADAPT_THRESHOLD_LOW "ai-adapt-threshold-low"
#define CFG_KEY_AI_ADAPT_THRESHOLD_REPEAT "ai-adapt-threshold-repeat"
#define CFG_KEY_AI_ADAPT_THRESHOLD_STRIKE "ai-adapt-threshold-strike"
#define CFG_KEY_AI_ADAPT_THRESHOLD_ART "ai-adapt-threshold-art"
#define CFG_KEY_AI_ADAPT_THRESHOLD_SUPER "ai-adapt-threshold-super"
#define CFG_KEY_AI_ADAPT_BAIT_TRIGGER_JUMP "ai-adapt-bait-trigger-jump"
#define CFG_KEY_AI_ADAPT_BAIT_TRIGGER_LOW "ai-adapt-bait-trigger-low"
#define CFG_KEY_AI_ADAPT_BAIT_TRIGGER_REPEAT "ai-adapt-bait-trigger-repeat"
#define CFG_KEY_NETPLAY_P2P_LOCAL_PLAYER "p2p-local-player"
#define CFG_KEY_NETPLAY_P2P_REMOTE_IP "p2p-remote-ip"
#define CFG_KEY_NETPLAY_MATCHMAKING_IP "matchmaking-ip"
#define CFG_KEY_NETPLAY_MATCHMAKING_PORT "matchmaking-port"

/// Initialize config system
void Config_Init();

/// Destroy resources used by config system
void Config_Destroy();

/// Get the value associated with the given key as a `bool`
/// @return The value associated with `key` if `key` is among entries and the value's type is `bool`, `false` otherwise
bool Config_GetBool(const char* key);

/// Get the value associated with the given key as an `int`
/// @return The value associated with `key` if `key` is among entries and the value's type is `int`, `0` otherwise
int Config_GetInt(const char* key);

/// Get the value associated with the given key as a `string`
/// @return The value associated with `key` if `key` is among entries and the value's type is `string`, `NULL` otherwise
const char* Config_GetString(const char* key);

/// Check whether the config file explicitly provided the given key
bool Config_HasExplicitKey(const char* key);

#endif
