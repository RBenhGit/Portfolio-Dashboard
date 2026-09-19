#!/usr/bin/env bash
# ---------------------------------------------------------------------
# Installs the monthly IBI transaction-import cron job.
#
# Idempotent — safe to re-run; the existing block is replaced.
# No sudo needed (installs to the current user's crontab).
#
#   ./install_cron.sh            # install / update
#   ./install_cron.sh --remove   # remove
# ---------------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$PROJECT_ROOT/scripts/run_import.sh"

BEGIN_MARK="# >>> PortfolioDashboard import (managed) >>>"
END_MARK="# <<< PortfolioDashboard import (managed) <<<"

current_without_block() {
    crontab -l 2>/dev/null | sed "\|^${BEGIN_MARK}\$|,\|^${END_MARK}\$|d" || true
}

if [[ "${1:-}" == "--remove" ]]; then
    current_without_block | crontab -
    echo "PortfolioDashboard import cron entry removed."
    crontab -l 2>/dev/null || echo "(crontab is now empty)"
    exit 0
fi

if [[ ! -x "$RUNNER" ]]; then
    echo "ERROR: $RUNNER is not executable. Run: chmod +x '$RUNNER'" >&2
    exit 1
fi

{
    current_without_block
    cat <<EOF
$BEGIN_MARK
# Managed by scripts/install_cron.sh — do not edit between the markers.
#
# Monthly: fetch the latest IBI report PDF over IMAP and ingest new
# transactions. IBI issues one report per month, so a weekly schedule just
# re-downloaded and re-ingested the same PDF three times out of four.
# Observed arrival for the PRIOR month's report: 19 Aug (07/2026) and
# 15 Sep (08/2026) -- i.e. mid-month, not month-start. The 20th at 08:00
# sits after both, with days of slack left in the month to notice a failed
# run and retry by hand.
#
# Auth is an IMAP app password in .env (IMAP_USER / IMAP_APP_PASSWORD);
# the run emails a summary on every outcome — see src/input/notifier.py.
0 8 20 * * "$RUNNER"
$END_MARK
EOF
} | crontab -

echo "Installed PortfolioDashboard import cron entry:"
crontab -l | sed -n "\|^${BEGIN_MARK}\$|,\|^${END_MARK}\$|p"
