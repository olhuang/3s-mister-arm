#!/bin/sh
set -eu

timestamp="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown-time)"
log_path="${1:-/tmp/mvsx-probe-${timestamp}.log}"

mkdir -p "$(dirname "$log_path")"

exec >"$log_path" 2>&1

run_cmd() {
    label="$1"
    shift

    echo
    echo "===== ${label} ====="
    echo "+ $*"
    "$@"
}

run_shell() {
    label="$1"
    shift

    echo
    echo "===== ${label} ====="
    echo "+ $*"
    /bin/sh -c "$*"
}

echo "MVSX probe started"
echo "timestamp: $(date 2>/dev/null || true)"
echo "log_path: $log_path"

run_cmd "uname" uname -a
run_cmd "cpuinfo" cat /proc/cpuinfo
run_cmd "long_bit" getconf LONG_BIT

if command -v ldd >/dev/null 2>&1; then
    run_cmd "ldd_version" ldd --version
else
    echo
    echo "===== ldd_version ====="
    echo "ldd not found"
fi

run_cmd "memory" free -m
run_cmd "mounts" mount
run_shell "device_nodes" "ls -l /dev/fb* /dev/dri /dev/input 2>/dev/null || true"
run_cmd "input_devices" cat /proc/bus/input/devices
run_shell "lib_layout" "ls -l /lib /usr/lib 2>/dev/null | sed -n '1,80p'"
run_shell "write_test" "echo hello; id; pwd; touch /tmp/mvsx_write_test && ls -l /tmp/mvsx_write_test"

echo
echo "MVSX probe finished"
echo "timestamp: $(date 2>/dev/null || true)"
echo "log_path: $log_path"
