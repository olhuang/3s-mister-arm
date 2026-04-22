#include "port/config/config.h"
#include "port/config/config_helpers.h"
#include "port/paths.h"

#include <stdbool.h>
#include <stdio.h>

#include <SDL3/SDL.h>

#define CONFIG_ENTRIES_MAX 128

typedef enum ConfigType {
    CFG_BOOL,
    CFG_INT,
    CFG_STRING,
} ConfigType;

typedef union ConfigValue {
    bool b;
    int i;
    char* s;
} ConfigValue;

typedef struct ConfigEntry {
    const char* key;
    ConfigType type;
    ConfigValue value;
} ConfigEntry;

#if defined(PORT_MISTER)
#define DEFAULT_VIDEO_DRIVER_ORDER "dummy"
#define DEFAULT_RENDER_DRIVER_ORDER "software"
#define DEFAULT_WINDOW_WIDTH 320
#define DEFAULT_WINDOW_HEIGHT 240
#define DEFAULT_SCALE_MODE "native"
#define DEFAULT_SOFTWARE_FRAME_MODE "on"
#else
#define DEFAULT_VIDEO_DRIVER_ORDER ""
#define DEFAULT_RENDER_DRIVER_ORDER ""
#define DEFAULT_WINDOW_WIDTH 640
#define DEFAULT_WINDOW_HEIGHT 480
#define DEFAULT_SCALE_MODE "soft-linear"
#define DEFAULT_SOFTWARE_FRAME_MODE "off"
#endif

#define DEFAULT_SUPER_EFFECT_QUALITY "full"
#define DEFAULT_GHOST_RESOLUTION "full"
#define DEFAULT_GHOST_COUNT "4"
#define DEFAULT_ARM_CLOCK "800"
#define DEFAULT_GAME_MODE "console"
#define DEFAULT_HOLD_TO_PAUSE "off"
#define DEFAULT_AI_LUCK_CURRENT_INPUT_CHEAT "4,14,26"
#define DEFAULT_AI_LUCK_PRECISE_GROUND_CHEAT "4,12,24"
#define DEFAULT_AI_LUCK_PRECISE_AIR_CHEAT "4,10,22"
#define DEFAULT_AI_GRIT_BONUS_LOW "0,1,1"
#define DEFAULT_AI_GRIT_BONUS_MID "1,2,3"
#define DEFAULT_AI_GRIT_BONUS_HIGH "2,3,4"
//#define DEFAULT_AI_GUARD_SENSE_LAG_BAL "20,17,14,11,9,9,5,3"
//#define DEFAULT_AI_GUARD_SENSE_LAG_RSH "18,15,12,9,7,5,3,2"
//#define DEFAULT_AI_GUARD_SENSE_LAG_TRK "25,23,22,17,14,11,8,5"
//#define DEFAULT_AI_GUARD_SENSE_LAG_MET "14,11,9,7,5,3,2,1"
#define DEFAULT_AI_GUARD_SENSE_LAG_BAL "0,0,0,0,0,0,0,0"
#define DEFAULT_AI_GUARD_SENSE_LAG_RSH "0,0,0,0,0,0,0,0"
#define DEFAULT_AI_GUARD_SENSE_LAG_TRK "0,0,0,0,0,0,0,0"
#define DEFAULT_AI_GUARD_SENSE_LAG_MET "0,0,0,0,0,0,0,0"
#define DEFAULT_AI_PROFILE_BAL "5,5,5,5,5,5,5,5"
#define DEFAULT_AI_PROFILE_RSH "8,3,4,6,4,2,8,6"
#define DEFAULT_AI_PROFILE_TRK "5,4,5,6,7,4,4,9"
#define DEFAULT_AI_PROFILE_MET "3,8,7,3,4,8,5,2"
#define DEFAULT_AI_MOOD_DURATION_RUSHDOWN 30
#define DEFAULT_AI_MOOD_DURATION_BAIT 0
#define DEFAULT_AI_MOOD_DURATION_TILT 36
#define DEFAULT_AI_MOOD_DURATION_PANIC 48
#define DEFAULT_AI_MOOD_DURATION_CONFIDENCE 45
#define DEFAULT_AI_MOOD_CONFIDENCE_STREAK 2
#define DEFAULT_AI_MOOD_PANIC_MAX_LV08 3
#define DEFAULT_AI_ADAPT_THRESHOLD_JUMP "6,5,4,3"
#define DEFAULT_AI_ADAPT_THRESHOLD_LOW "6,5,4,3"
#define DEFAULT_AI_ADAPT_THRESHOLD_REPEAT "7,6,5,4"
#define DEFAULT_AI_ADAPT_THRESHOLD_STRIKE "6,5,4,3"
#define DEFAULT_AI_ADAPT_THRESHOLD_ART "5,4,3,2"
#define DEFAULT_AI_ADAPT_THRESHOLD_SUPER "3,3,2,2"
#define DEFAULT_AI_ADAPT_BAIT_TRIGGER_JUMP "6"
#define DEFAULT_AI_ADAPT_BAIT_TRIGGER_LOW "6"
#define DEFAULT_AI_ADAPT_BAIT_TRIGGER_REPEAT "6"
#define DEFAULT_RL_AGENT_OBS_PORT 37330
#define DEFAULT_RL_AGENT_ACTION_PORT 37331
#define DEFAULT_RL_AGENT_DELAY_FRAMES 4
#define DEFAULT_RL_AGENT_DECISION_INTERVAL 4
#define DEFAULT_RL_AGENT_ACTION_HOLD 4

static const ConfigEntry default_entries[] = {
    { .key = CFG_KEY_FULLSCREEN, .type = CFG_BOOL, .value.b = true },
    { .key = CFG_KEY_WINDOW_WIDTH, .type = CFG_INT, .value.i = DEFAULT_WINDOW_WIDTH },
    { .key = CFG_KEY_WINDOW_HEIGHT, .type = CFG_INT, .value.i = DEFAULT_WINDOW_HEIGHT },
    { .key = CFG_KEY_SCALEMODE, .type = CFG_STRING, .value.s = DEFAULT_SCALE_MODE },
    { .key = CFG_KEY_SCANLINES, .type = CFG_INT, .value.i = 0 },
    { .key = CFG_DRAW_PLAYERS_ABOVE_HUD, .type = CFG_BOOL, .value.b = false },
    { .key = CFG_ARCADE_BALANCE, .type = CFG_BOOL, .value.b = false },
    { .key = CFG_KEY_SOFTWARE_FRAME_MODE, .type = CFG_STRING, .value.s = DEFAULT_SOFTWARE_FRAME_MODE },
    { .key = CFG_KEY_SUPER_EFFECT_QUALITY, .type = CFG_STRING, .value.s = DEFAULT_SUPER_EFFECT_QUALITY },
    { .key = CFG_KEY_GHOST_RESOLUTION, .type = CFG_STRING, .value.s = DEFAULT_GHOST_RESOLUTION },
    { .key = CFG_KEY_GHOST_COUNT, .type = CFG_STRING, .value.s = DEFAULT_GHOST_COUNT },
    { .key = CFG_KEY_ARM_CLOCK, .type = CFG_STRING, .value.s = DEFAULT_ARM_CLOCK },
    { .key = CFG_KEY_GAME_MODE, .type = CFG_STRING, .value.s = DEFAULT_GAME_MODE },
    { .key = CFG_KEY_HOLD_TO_PAUSE, .type = CFG_STRING, .value.s = DEFAULT_HOLD_TO_PAUSE },
    { .key = CFG_KEY_AI_LUCK_CURRENT_INPUT_CHEAT, .type = CFG_STRING, .value.s = DEFAULT_AI_LUCK_CURRENT_INPUT_CHEAT },
    { .key = CFG_KEY_AI_LUCK_PRECISE_GROUND_CHEAT, .type = CFG_STRING, .value.s = DEFAULT_AI_LUCK_PRECISE_GROUND_CHEAT },
    { .key = CFG_KEY_AI_LUCK_PRECISE_AIR_CHEAT, .type = CFG_STRING, .value.s = DEFAULT_AI_LUCK_PRECISE_AIR_CHEAT },
    { .key = CFG_KEY_AI_GRIT_BONUS_LOW, .type = CFG_STRING, .value.s = DEFAULT_AI_GRIT_BONUS_LOW },
    { .key = CFG_KEY_AI_GRIT_BONUS_MID, .type = CFG_STRING, .value.s = DEFAULT_AI_GRIT_BONUS_MID },
    { .key = CFG_KEY_AI_GRIT_BONUS_HIGH, .type = CFG_STRING, .value.s = DEFAULT_AI_GRIT_BONUS_HIGH },
    { .key = CFG_KEY_AI_GUARD_SENSE_LAG_BAL, .type = CFG_STRING, .value.s = DEFAULT_AI_GUARD_SENSE_LAG_BAL },
    { .key = CFG_KEY_AI_GUARD_SENSE_LAG_RSH, .type = CFG_STRING, .value.s = DEFAULT_AI_GUARD_SENSE_LAG_RSH },
    { .key = CFG_KEY_AI_GUARD_SENSE_LAG_TRK, .type = CFG_STRING, .value.s = DEFAULT_AI_GUARD_SENSE_LAG_TRK },
    { .key = CFG_KEY_AI_GUARD_SENSE_LAG_MET, .type = CFG_STRING, .value.s = DEFAULT_AI_GUARD_SENSE_LAG_MET },
    { .key = CFG_KEY_AI_PROFILE_BAL, .type = CFG_STRING, .value.s = DEFAULT_AI_PROFILE_BAL },
    { .key = CFG_KEY_AI_PROFILE_RSH, .type = CFG_STRING, .value.s = DEFAULT_AI_PROFILE_RSH },
    { .key = CFG_KEY_AI_PROFILE_TRK, .type = CFG_STRING, .value.s = DEFAULT_AI_PROFILE_TRK },
    { .key = CFG_KEY_AI_PROFILE_MET, .type = CFG_STRING, .value.s = DEFAULT_AI_PROFILE_MET },
    { .key = CFG_KEY_AI_MOOD_DURATION_RUSHDOWN, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_DURATION_RUSHDOWN },
    { .key = CFG_KEY_AI_MOOD_DURATION_BAIT, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_DURATION_BAIT },
    { .key = CFG_KEY_AI_MOOD_DURATION_TILT, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_DURATION_TILT },
    { .key = CFG_KEY_AI_MOOD_DURATION_PANIC, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_DURATION_PANIC },
    { .key = CFG_KEY_AI_MOOD_DURATION_CONFIDENCE, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_DURATION_CONFIDENCE },
    { .key = CFG_KEY_AI_MOOD_CONFIDENCE_STREAK, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_CONFIDENCE_STREAK },
    { .key = CFG_KEY_AI_MOOD_PANIC_MAX_LV08, .type = CFG_INT, .value.i = DEFAULT_AI_MOOD_PANIC_MAX_LV08 },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_JUMP, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_JUMP },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_LOW, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_LOW },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_REPEAT, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_REPEAT },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_STRIKE, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_STRIKE },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_ART, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_ART },
    { .key = CFG_KEY_AI_ADAPT_THRESHOLD_SUPER, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_THRESHOLD_SUPER },
    { .key = CFG_KEY_AI_ADAPT_BAIT_TRIGGER_JUMP, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_BAIT_TRIGGER_JUMP },
    { .key = CFG_KEY_AI_ADAPT_BAIT_TRIGGER_LOW, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_BAIT_TRIGGER_LOW },
    { .key = CFG_KEY_AI_ADAPT_BAIT_TRIGGER_REPEAT, .type = CFG_STRING, .value.s = DEFAULT_AI_ADAPT_BAIT_TRIGGER_REPEAT },
    { .key = CFG_KEY_RL_NETWORK, .type = CFG_STRING, .value.s = "off" },
    { .key = CFG_KEY_RL_AGENT_OBS_PORT, .type = CFG_INT, .value.i = DEFAULT_RL_AGENT_OBS_PORT },
    { .key = CFG_KEY_RL_AGENT_ACTION_PORT, .type = CFG_INT, .value.i = DEFAULT_RL_AGENT_ACTION_PORT },
    { .key = CFG_KEY_RL_AGENT_DELAY_FRAMES, .type = CFG_INT, .value.i = DEFAULT_RL_AGENT_DELAY_FRAMES },
    { .key = CFG_KEY_RL_AGENT_DECISION_INTERVAL, .type = CFG_INT, .value.i = DEFAULT_RL_AGENT_DECISION_INTERVAL },
    { .key = CFG_KEY_RL_AGENT_ACTION_HOLD, .type = CFG_INT, .value.i = DEFAULT_RL_AGENT_ACTION_HOLD },
    { .key = CFG_KEY_SHOW_FPS, .type = CFG_STRING, .value.s = "off" },
    { .key = CFG_KEY_VIDEO_DRIVER_ORDER, .type = CFG_STRING, .value.s = DEFAULT_VIDEO_DRIVER_ORDER },
    { .key = CFG_KEY_RENDER_DRIVER_ORDER, .type = CFG_STRING, .value.s = DEFAULT_RENDER_DRIVER_ORDER },
};

static ConfigEntry entries[CONFIG_ENTRIES_MAX] = { 0 };
static int entry_count = 0;

static void clear_entries() {
    for (int i = 0; i < entry_count; i++) {
        ConfigEntry* entry = &entries[i];
        SDL_free(entry->key);

        if (entry->type == CFG_STRING) {
            SDL_free(entry->value.s);
        }
    }

    SDL_zeroa(entries);
    entry_count = 0;
}

static bool is_int(const char* string) {
    for (int i = 0; i < SDL_strlen(string); i++) {
        if (SDL_isdigit(string[i]) || ((i == 0) && (string[i] == '-'))) {
            continue;
        } else {
            return false;
        }
    }

    return true;
}

static ConfigEntry* find_entry_in_array(const char* key, const ConfigEntry* array, size_t size) {
    for (int i = 0; i < size; i++) {
        const ConfigEntry* entry = &array[i];

        if (SDL_strcmp(key, entry->key) == 0) {
            return entry;
        }
    }

    return NULL;
}

static ConfigEntry* find_entry(const char* key) {
    ConfigEntry* default_entry = find_entry_in_array(key, default_entries, SDL_arraysize(default_entries));
    ConfigEntry* read_entry = find_entry_in_array(key, entries, entry_count);

    if (read_entry != NULL) {
        if (default_entry != NULL && read_entry->type != default_entry->type) {
            // If we expect a certain type and the one we read from config is unexpected, let's use the default entry
            // instead
            return default_entry;
        } else {
            return read_entry;
        }
    } else if (default_entry != NULL) {
        return default_entry;
    } else {
        SDL_assert(false);
        return NULL;
    }
}

bool Config_HasExplicitKey(const char* key) {
    return find_entry_in_array(key, entries, entry_count) != NULL;
}

static void print_config_entry_to_io(SDL_IOStream* io, const ConfigEntry* entry) {
    io_printf(io, "%s = ", entry->key);

    switch (entry->type) {
    case CFG_BOOL:
        io_printf(io, entry->value.b ? "true" : "false");
        break;

    case CFG_INT:
        io_printf(io, "%d", entry->value.i);
        break;

    case CFG_STRING:
        io_printf(io, entry->value.s);
        break;
    }
}

static void write_defaults(const char* dst_path) {
    SDL_IOStream* io = SDL_IOFromFile(dst_path, "w");
    io_printf(io,
              "# For the full list of settings see https://github.com/kimchiman52/3s-mister-arm/blob/main/docs/config.md\n\n");

    for (int i = 0; i < SDL_arraysize(default_entries); i++) {
        print_config_entry_to_io(io, &default_entries[i]);
        io_printf(io, "\n");
    }

    SDL_CloseIO(io);
}

static bool dict_iterator(const char* key, const char* value) {
    if (entry_count == CONFIG_ENTRIES_MAX) {
        printf("⚠️ Reached max config entry count (%d), skipping the rest\n", CONFIG_ENTRIES_MAX);
        return false;
    }

    ConfigEntry* entry = &entries[entry_count];
    entry->key = SDL_strdup(key);

    const bool is_true = SDL_strcmp(value, "true") == 0;
    const bool is_false = SDL_strcmp(value, "false") == 0;

    if (is_true || is_false) {
        entry->type = CFG_BOOL;
        entry->value.b = is_true;
    } else if (is_int(value)) {
        entry->type = CFG_INT;
        entry->value.i = SDL_atoi(value);
    } else {
        entry->type = CFG_STRING;
        entry->value.s = SDL_strdup(value);
    }

    entry_count += 1;
    return true;
}

void Config_Init() {
    clear_entries();

    const char* pref_path = Paths_GetPrefPath();
    char* config_path;
    SDL_asprintf(&config_path, "%sconfig", pref_path);

    FILE* f = fopen(config_path, "r");

    if (f == NULL) {
        // Config doesn't exist. Write defaults
        write_defaults(config_path);
        SDL_free(config_path);
        return;
    }

    SDL_free(config_path);
    dict_read(f, dict_iterator);
    fclose(f);
}

void Config_Destroy() {
    clear_entries();
}

bool Config_GetBool(const char* key) {
    const ConfigEntry* entry = find_entry(key);

    if (entry == NULL || entry->type != CFG_BOOL) {
        return false;
    }

    return entry->value.b;
}

int Config_GetInt(const char* key) {
    const ConfigEntry* entry = find_entry(key);

    if (entry == NULL || entry->type != CFG_INT) {
        return 0;
    }

    return entry->value.i;
}

const char* Config_GetString(const char* key) {
    const ConfigEntry* entry = find_entry(key);

    if (entry == NULL || entry->type != CFG_STRING) {
        return NULL;
    }

    return entry->value.s;
}
