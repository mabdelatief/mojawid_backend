#!/usr/bin/env bash
# Put a Flutter web build where the web front (mojawid_web) serves it (docs/deploy-laptop.md).
#
#   tools/deploy_web.sh <path to the Flutter build/web folder>
#   tools/deploy_web.sh --placeholder      # a one-line page, until there's a build
#
# Everything but index.html is copied first, and index.html last, so a visitor loading the page
# mid-copy never gets a new index.html pointing at files not there yet. nginx needs no restart;
# files are revalidated, so the next page load shows the new build.
set -euo pipefail

DEST="${MOJAWID_WEB_DIR:-$HOME/.local/share/mojawid-web}"
mkdir -p "$DEST"

if [[ "${1:-}" == "--placeholder" ]]; then
    printf '<!doctype html><meta charset="utf-8"><title>Mojawid</title><p>مُجَوِّد: soon.</p>\n' \
        > "$DEST/index.html"
    chmod -R a+rX "$DEST"
    echo "placeholder page in $DEST"
    exit 0
fi

SRC="${1:?usage: tools/deploy_web.sh <flutter build/web folder> | --placeholder}"
if [[ ! -f "$SRC/index.html" ]]; then
    echo "no index.html in $SRC: not a Flutter web build" >&2
    exit 1
fi

rsync -a --delete --exclude /index.html "$SRC/" "$DEST/"
cp "$SRC/index.html" "$DEST/index.html.new"
mv "$DEST/index.html.new" "$DEST/index.html"
chmod -R a+rX "$DEST"
echo "deployed $SRC to $DEST"
