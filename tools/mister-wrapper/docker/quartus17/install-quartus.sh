#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: install-quartus.sh <quartus-install-dir>" >&2
    exit 2
fi

INSTALL_DIR="$1"
INSTALLER_DIR="/tmp/quartus-installer"
LOG_FILE="/tmp/quartus-installer.log"
BITROCK_LOG="/tmp/bitrock_installer.log"

kill_descendants() {
    local parent_pid="$1"
    local child
    for child in $(ps -o pid= --ppid "${parent_pid}" 2>/dev/null); do
        kill_descendants "${child}"
        kill -TERM "${child}" 2>/dev/null || true
    done
}

QUARTUS_RUN="$(find "${INSTALLER_DIR}" -maxdepth 1 -type f -name 'QuartusLiteSetup-17.0*.run' | sort | head -n 1)"
if [ -z "${QUARTUS_RUN}" ]; then
    QUARTUS_RUN="$(find "${INSTALLER_DIR}" -maxdepth 1 -type f -name 'QuartusSetup-17.0*.run' | sort | head -n 1)"
fi
CYCLONE_QDZ="$(find "${INSTALLER_DIR}" -maxdepth 1 -type f -name 'cyclone-17.0*.qdz' | sort | head -n 1)"
CYCLONEV_QDZ="$(find "${INSTALLER_DIR}" -maxdepth 1 -type f -name 'cyclonev-17.0*.qdz' | sort | head -n 1)"

[ -n "${QUARTUS_RUN}" ] || { echo "missing Quartus Lite or Standard setup .run in ${INSTALLER_DIR}" >&2; exit 1; }
[ -n "${CYCLONE_QDZ}" ] || { echo "missing Cyclone .qdz in ${INSTALLER_DIR}" >&2; exit 1; }
[ -n "${CYCLONEV_QDZ}" ] || { echo "missing Cyclone V .qdz in ${INSTALLER_DIR}" >&2; exit 1; }

chmod +x "${QUARTUS_RUN}"
mkdir -p "${INSTALL_DIR}"

cd "${INSTALLER_DIR}"
echo "quartus_run=${QUARTUS_RUN}"
echo "install_dir=${INSTALL_DIR}"
echo "log_file=${LOG_FILE}"
echo "bitrock_log=${BITROCK_LOG}"
echo "starting Quartus installer..."

set +e
rm -f "${LOG_FILE}" "${BITROCK_LOG}"
"${QUARTUS_RUN}" --mode unattended --unattendedmodeui none --installdir "${INSTALL_DIR}" >> "${LOG_FILE}" 2>&1 &
installer_pid=$!

status=0
completed_via_log=0
while kill -0 "${installer_pid}" 2>/dev/null; do
    if [ -f "${BITROCK_LOG}" ] && grep -q "Installation completed" "${BITROCK_LOG}"; then
        completed_via_log=1
        break
    fi
    sleep 5
done

if [ "${completed_via_log}" -eq 1 ]; then
    echo "bitrock log indicates installation completed; stopping lingering installer wrapper"
    kill_descendants "${installer_pid}"
    kill "${installer_pid}" 2>/dev/null || true
    sleep 2
    kill_descendants "${installer_pid}"
    kill -KILL "${installer_pid}" 2>/dev/null || true
    status=0
else
    wait "${installer_pid}"
    status=$?
fi
set -e

echo "installer_exit_code=${status}"
echo "installer_log_tail:"
tail -n 200 "${LOG_FILE}" || true
echo "bitrock_log_tail:"
tail -n 200 "${BITROCK_LOG}" || true

exit "${status}"
