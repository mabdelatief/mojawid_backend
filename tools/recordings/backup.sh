#!/usr/bin/env bash
# Copy the kept recordings and their results to the home lab (closed testing; see
# docs/deploy-laptop.md), the way tools/rules_review/backup.sh copies the review answers.
#
#   tools/recordings/backup.sh [host:path]    default: homelab:/srv/backup/mojawid-recordings
#
# <path>/audio/ mirrors the recordings folder (a recording deleted on the admin page goes from
# the copy on the next run), and <path>/recordings.json holds every row of the recording table,
# results included, replaced on each run.
# Daily at 03:10 (a run missed while the laptop slept happens on wake):
#   cp tools/systemd/mojawid-recordings-backup.* ~/.config/systemd/user/
#   systemctl --user daemon-reload && systemctl --user enable --now mojawid-recordings-backup.timer
# Away from home the home lab doesn't answer: it fails fast and the next run catches up.
set -euo pipefail
cd "$(dirname "$0")/../.."

DEST="${1:-homelab:/srv/backup/mojawid-recordings}"
HOST="${DEST%%:*}"
DIR="${DEST#*:}"
SRC="${MOJAWID_RECORDINGS_DIR:-$HOME/.local/share/mojawid-recordings}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)

if ! "${SSH[@]}" "$HOST" "test -d '$DIR/audio' && test -w '$DIR'"; then
  echo "Backup folder $DEST is missing or not writable." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# a plain query, not COPY: COPY's text format escapes backslashes and would break the JSON
docker exec mojawid_postgres psql -U mojawid -d mojawid -At -v ON_ERROR_STOP=1 \
  -c "SELECT coalesce(json_agg(r ORDER BY r.created_at), '[]') FROM recording r" \
  > "$TMP/recordings.json"
python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$TMP/recordings.json"

rsync -a --delete --exclude '.*' -e "${SSH[*]}" "$SRC/" "$HOST:$DIR/audio/"
rsync -a -e "${SSH[*]}" "$TMP/recordings.json" "$HOST:$DIR/recordings.json.partial"
"${SSH[@]}" "$HOST" "mv '$DIR/recordings.json.partial' '$DIR/recordings.json'"
echo "backup: $(ls "$SRC" | wc -l) files and the results -> $DEST"
