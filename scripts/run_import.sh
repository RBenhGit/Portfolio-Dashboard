#!/usr/bin/env bash
# ---------------------------------------------------------------------
# Weekly IBI transaction import: fetch the latest report PDF from Gmail
# and ingest it. Called from cron — see scripts/install_cron.sh.
#
# Usage:
#   ./run_import.sh
# ---------------------------------------------------------------------
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/import_$(date +%F).log"

mkdir -p "$LOG_DIR"

export PYTHONIOENCODING=utf-8
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

if [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
    PY="$PROJECT_ROOT/venv/bin/python"
else
    PY="$(command -v python3)"
fi

log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

cd "$PROJECT_ROOT" || exit 1

# Snapshot the DB before the run. builder.build() truncates
# daily_portfolio_state and realized_trades in their own committed
# transactions and only then rebuilds (~minutes, with network I/O), so a
# crash in that window leaves both tables empty with no rollback. data/ is
# gitignored, so portfolio.db is otherwise a single copy.
BACKUP_DIR="$PROJECT_ROOT/data/backups"
DB="$PROJECT_ROOT/data/portfolio.db"
KEEP=10

if [[ -f "$DB" ]]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP="$BACKUP_DIR/portfolio.db.$(date +%Y%m%d-%H%M%S)"
    # VACUUM INTO takes a consistent snapshot even with WAL active; fall
    # back to cp if this sqlite3 is too old to support it.
    if "$PY" -c "import sqlite3,sys; sqlite3.connect(sys.argv[1]).execute('VACUUM INTO ?', (sys.argv[2],))" \
            "$DB" "$BACKUP" 2>/dev/null; then
        log "BACKUP: $BACKUP (vacuum)"
    elif cp "$DB" "$BACKUP" 2>/dev/null; then
        log "BACKUP: $BACKUP (copy)"
    else
        log "WARNING: backup failed; continuing"
    fi
    # Retain the most recent $KEEP snapshots.
    ls -1t "$BACKUP_DIR"/portfolio.db.* 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
        rm -f "$old" && log "PRUNED: $old"
    done
fi

log "START: run_import.py"
"$PY" scripts/run_import.py >> "$LOG_FILE" 2>&1
rc=$?
log "DONE: run_import.py (exit $rc)"

exit $rc
