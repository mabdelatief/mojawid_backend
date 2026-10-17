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

# The app's code is fetched under addresses that change with every build. Flutter keeps the
# names flutter_bootstrap.js and main.dart.js, and Cloudflare's edge kept serving the first
# build's .js after a deploy without asking the server (2026-10-17). index.html itself always
# reaches the server, so it carries the new addresses.
VERSION="$(cat "$SRC/main.dart.js" "$SRC/flutter_bootstrap.js" | sha256sum | cut -c1-12)"
BOOT_FROM='"mainJsPath":"main.dart.js"'
INDEX_FROM='src="flutter_bootstrap.js"'
grep -qF "$BOOT_FROM" "$SRC/flutter_bootstrap.js" || { echo "no $BOOT_FROM in flutter_bootstrap.js" >&2; exit 1; }
grep -qF "$INDEX_FROM" "$SRC/index.html" || { echo "no $INDEX_FROM in index.html" >&2; exit 1; }

rsync -a --delete --exclude /index.html "$SRC/" "$DEST/"
sed "s|$BOOT_FROM|\"mainJsPath\":\"main.dart.js?v=$VERSION\"|" "$SRC/flutter_bootstrap.js" \
    > "$DEST/flutter_bootstrap.js"
sed "s|$INDEX_FROM|src=\"flutter_bootstrap.js?v=$VERSION\"|" "$SRC/index.html" \
    > "$DEST/index.html.new"
mv "$DEST/index.html.new" "$DEST/index.html"
chmod -R a+rX "$DEST"
echo "deployed $SRC to $DEST (build $VERSION)"
