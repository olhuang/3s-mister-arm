#!/bin/sh
set -eu

export THIRDSARM_NATIVE_VIDEO=0
export THIRDSARM_SCALE_MODE_STARTUP_OVERRIDE=nearest

exec /media/fat/games/3s-arm/scripts/launch-osd.sh \
    --test-enable \
    --test-scene-preset pressure-exchange \
    --test-preserve-game-transition \
    --test-delay-gameplay-inputs-until-active
