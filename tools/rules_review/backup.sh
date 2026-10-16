#!/usr/bin/env bash
# Copy the teachers' answers to the home lab, done the way tajweed_ai/tools/backup.sh does it.
#
#   tools/rules_review/backup.sh [host:path]    default: homelab:/srv/backup/mojawid-review
#
# Each run writes <path>/answers-<UTC time>.sqlite3, a consistent copy taken with SQLite's own
# backup (safe while the service is writing). Copies are small, so all are kept.
# Daily at 02:40 (a run missed while the laptop slept happens on wake):
#   cp tools/systemd/mojawid-review-backup.* ~/.config/systemd/user/
#   systemctl --user daemon-reload && systemctl --user enable --now mojawid-review-backup.timer
# Away from home the home lab doesn't answer: it fails fast and the next run catches up.
set -euo pipefail
cd "$(dirname "$0")/../.."

DEST="${1:-homelab:/srv/backup/mojawid-review}"
HOST="${DEST%%:*}"
DIR="${DEST#*:}"
DB="${MOJAWID_REVIEW_DB:-$HOME/.local/share/mojawid-review/answers.sqlite3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)

if [ ! -f "$DB" ]; then
  echo "No answers yet ($DB)." >&2
  exit 0
fi
if ! "${SSH[@]}" "$HOST" "test -d '$DIR' && test -w '$DIR'"; then
  echo "Backup folder $DEST is missing or not writable." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
.venv/bin/python -c "import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))" \
  "$DB" "$TMP/answers.sqlite3"
rsync -a -e "${SSH[*]}" "$TMP/answers.sqlite3" "$HOST:$DIR/answers-$STAMP.sqlite3.partial"
"${SSH[@]}" "$HOST" "mv '$DIR/answers-$STAMP.sqlite3.partial' '$DIR/answers-$STAMP.sqlite3'"
echo "backup: $DEST/answers-$STAMP.sqlite3"
