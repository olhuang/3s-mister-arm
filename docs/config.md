# Config

3S-ARM supports a config file which allows you to change several useful options.

Config location:
- **Windows**: `C:\Users\<username>\AppData\Roaming\CrowdedStreet\3S-ARM\config`
- **Linux**: `~/.local/share/CrowdedStreet/3S-ARM/config`
- **macOS**: `~/Library/Application Support/CrowdedStreet/3S-ARM/config`

## Options

### `fullscreen`

Whether the game should start in fullscreen mode.

### `window-width` / `window-height`

Window dimensions to use when `fullscreen` is set to `false`.

### `scale-mode`

The way the internal 384x224 buffer is scaled.

Possible values:
- `native`: No scaling. Keeps the internal `384x224` image size and centers it. On MiSTer's 384-native analog TV path, this preserves the game's native width in the framebuffer.
- `nearest`
- `linear`
- `soft-linear`: Produces an image with a balance of sharpness and sizing consistency
- `integer`: Produces a pixel-perfect image, but requires a 4K display (⚠️ WARNING: the image is gonna be cropped if your display resolution is smaller than 2688x2016)
- `square-pixels`: Integer (whole-number) scaling with square pixels. Use this if you play on a CRT

### `scanlines`

Defines the strength of the scanline filter (from `0` to `100`). `0` means the filter is disabled.

### `draw-players-above-hud`

Allow characters to render in front of the top HUD similar to Street Fighter IV. May introduce visual abnormalities on certain stages.

### `arcade-balance` (experimental)

Enables arcade balance instead of PS2 balance (work in progress). Requires `sfiii3nr1.zip` to be present in `resources` directory.

### `software-frame-mode`

Controls whether gameplay uses the 3S-ARM-owned software frame path or the legacy SDL-owned gameplay frame path.

Defaults:
- MiSTer builds: `on`
- Non-MiSTer builds: `off`

Possible values:
- `off`: Keep the existing SDL-owned gameplay frame path
- `on`: Keep the `384x224` gameplay frame in 3S-ARM-owned software memory. On MiSTer, eligible frames present directly through fbdev to avoid SDL readback; when composition or screenshots still need SDL, the frame uploads back to `cps3_canvas`.

### `super-effect-quality`

Controls MiSTer-only rendering optimization during super art activation.

Defaults:
- MiSTer builds: `cached-bg`
- Non-MiSTer builds: `full`

Possible values:
- `full`: No reduction — render every frame fully
- `cached-bg`: Cache the rendered background surface on the first super art activation frame, then restore it via fast blit on subsequent frames while rendering characters/effects/HUD fresh at 60fps

Notes:
- This setting is only active on MiSTer builds. On non-MiSTer builds the config key is parsed but behaves like `full`.
- Detection uses `sa_stop_check()` (cinematic freeze signal) which fires for all characters and all super arts. A grace period of ~15 frames after the signal drops covers the zoom-out transition.

### `ghost-resolution`

Controls whether ghost/after-image sprites render at half resolution.

Defaults:
- `full`

Possible values:
- `full`: Ghost sprites render at normal resolution (no change from vanilla)
- `half`: Ghost sprites render at 2x step in X and Y, duplicating pixels (~75% less pixel work)

Notes:
- Ghost sprites are the blue-tinted semi-transparent after-images that appear during super art activations.
- The half-resolution mode is nearly imperceptible because the sprites are already translucent blurs.
- On MiSTer, this can be toggled at runtime via the OSD menu.

### `ghost-count`

Controls the maximum number of ghost copies per activation.

Defaults:
- `4`

Possible values:
- `1`: Maximum 1 ghost copy per activation
- `2`: Maximum 2 ghost copies per activation
- `3`: Maximum 3 ghost copies per activation
- `4`: No cap (vanilla behavior)

Notes:
- Lower values reduce sprite rendering cost during super art activations.
- The cap applies to the `dmcal_d` value in the after-image effect system. Original values range 1-4 depending on the move.
- On MiSTer, this can be toggled at runtime via the OSD menu.

### `show-fps`

Whether to draw a small FPS readout while the game is running.

Defaults:
- `false`

Notes:
- On MiSTer fbdev output, the overlay is drawn at the bottom-center of the active picture area so it stays away from overscan-prone corners.
- The overlay is opt-in and uses a lightweight cached label update path instead of perf capture telemetry.
- On MiSTer, valid values are `off`, `fps`, `debug`, and `rl-debug`.
- `rl-debug` is a lightweight RL-specific overlay mode intended for remote-agent bring-up. In v1 it shows the effective RL agent slot state as `P0`, `P1`, or `P2`.

### `rl-agent-player`

Controls the MiSTer wrapper's remote RL agent launch mode.

Possible values:
- `off`
- `1`
- `2`

Notes:
- This key is primarily written by the MiSTer OSD menu entry `RL Agent (Restart)`.
- `1` means the wrapper relaunches the game with `--rl-agent --rl-player 1`.
- `2` means the wrapper relaunches the game with `--rl-agent --rl-player 2`.
- Changes take effect on the next wrapper `Restart`; they do not hot-switch the currently running match.

### `video-driver-order`

Comma-separated SDL video backend preference list passed via `SDL_HINT_VIDEO_DRIVER` before SDL init.

Example:
- `kmsdrm,offscreen,dummy`

### `render-driver-order`

Comma-separated SDL renderer backend preference list passed via `SDL_HINT_RENDER_DRIVER` before renderer creation.

Example:
- `software`

### `ai-luck-current-input-cheat`

Comma-separated `LOW,MID,HIGH` cheat rates for throw-tech / throw-response logic reading the player's current-frame input.

Default:
- `2,8,16`

Notes:
- Values are compared against `random_32_com()`, so they are effectively out of `32`.
- Higher values make `MID` / `HIGH` luck rounds more likely to use the original same-frame input-read behavior.

### `ai-luck-precise-ground-cheat`

Comma-separated `LOW,MID,HIGH` cheat rates for ground guard using exact engine threat data instead of delayed/coarse/fallible sensing.

Default:
- `2,7,14`

### `ai-luck-precise-air-cheat`

Comma-separated `LOW,MID,HIGH` cheat rates for air guard using exact engine threat data instead of delayed/coarse/fallible sensing.

Default:
- `3,9,18`

Notes:
- These two keys control how often luck restores the old "all-knowing" defense path.
- Air guard is typically set a bit higher than ground guard.

### `ai-grit-bonus-low`

Comma-separated grit bonuses for `LOW` grit at health thresholds:
- `50%~75%`
- `25%~50%`
- `<=25%`

Default:
- `0,0,1`

### `ai-grit-bonus-mid`

Comma-separated grit bonuses for `MID` grit at health thresholds:
- `50%~75%`
- `25%~50%`
- `<=25%`

Default:
- `0,1,2`

### `ai-grit-bonus-high`

Comma-separated grit bonuses for `HIGH` grit at health thresholds:
- `50%~75%`
- `25%~50%`
- `<=25%`

Default:
- `2,4,6`

Notes:
- These bonuses are added to internal AI level calculations (`Lv08`, `Lv10`, `Lv18`) when the CPU is low on life.
- Higher values make comeback behavior much stronger, especially on `HIGH` grit rounds.

### `ai-guard-sense-lag-bal`

Comma-separated guard-sense lag values for the `BAL` personality at difficulty levels `0~7`.

Default:
- `22,19,16,13,11,9,7,5`

### `ai-guard-sense-lag-rsh`

Comma-separated guard-sense lag values for the `RSH` personality at difficulty levels `0~7`.

Default:
- `20,17,14,11,9,7,5,3`

### `ai-guard-sense-lag-trk`

Comma-separated guard-sense lag values for the `TRK` personality at difficulty levels `0~7`.

Default:
- `30,27,24,21,18,15,12,9`

### `ai-guard-sense-lag-met`

Comma-separated guard-sense lag values for the `MET` personality at difficulty levels `0~7`.

Default:
- `16,13,11,9,7,5,3,2`

Notes:
- These values control how many frames back the CPU looks when sensing threats for guard / air-guard decisions.
- Lower values mean more responsive defense.
- Personality-specific base-style modifiers still apply on top of these tables in code.
