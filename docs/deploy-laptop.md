# Running Mojawid from this laptop (tajweed.codavvy.com)

The user's decision (2026-10-17): until further notice, everything runs on this laptop, and the
web app is served at **https://tajweed.codavvy.com** through the Cloudflare tunnel that used to
serve the lab. It stands in for phase 9 (Linode) in `docs/architecture.md` for now.

**Status:** live since 2026-10-17. The first Flutter web build is deployed, and the tunnel's
catch-all points at the web front (:8400) instead of the retired lab (:8000).

## What runs where

| Part | Where | Reached from |
|---|---|---|
| `mojawid_web` (nginx) | 127.0.0.1:8400 (172.30.0.10 on the compose network) | the tunnel |
| `mojawid_api` | 192.168.1.17:8100 and 127.0.0.1:8100 | `mojawid_web`, and the home Wi-Fi |
| `mojawid_worker` (GPU) | 127.0.0.1:8200 | the API |
| `mojawid_postgres` | 127.0.0.1:5452 | the API |
| `mojawid-review` (systemd, teachers' page) | 127.0.0.1:8300 | the tunnel |

**The tunnel** `tajweed-laptop` (`cloudflared-tajweed.service`, a user unit; the token is in
`~/.config/cloudflared/tajweed-laptop.token`) has two rules for host `tajweed.codavvy.com`:
1. path `^/mojawid(/.*)?$` → `http://localhost:8300` (the review page);
2. everything else → `http://localhost:8400` (the web front; it was the lab's :8000 until
   2026-10-17).

It's managed remotely: rules change through the Cloudflare API, with `CF_API_TOKEN` from
`/srv/homelab/.env` on the home box (`docs/rules-review/README.md` did it the same way).

**The login:** Cloudflare Access covers the whole host with an email allowlist (the user's
choice: Mojawid stays invite-only while it runs on a laptop GPU). Add or remove people under Zero
Trust → Access → Applications. The app's `/v1` calls are same-origin, so the Access cookie goes
with them.

## The web front (`docker/web.nginx.conf`, `docker/web.proxy.conf`)

- **`/`**: the Flutter web build, from `~/.local/share/mojawid-web/` (mounted read-only).
  - A path without a file extension is an app route and gets `index.html` (path URL strategy).
  - A missing file is a 404.
  - Everything is sent `Cache-Control: no-cache`, with an ETag. Flutter keeps `main.dart.js` and
    most other names across builds, so long caching would serve old code after an update.
  - **The app's code gets a new address with each build.** `tools/deploy_web.sh` tags
    `flutter_bootstrap.js` in `index.html`, and `main.dart.js` in the bootstrap, with
    `?v=<build hash>`. This is needed because Cloudflare's edge kept serving the first build's
    `.js` files after a deploy without asking the server (2026-10-17). We can't purge that cache:
    the API token has no zone permissions. `index.html` always reaches the server, so the new
    addresses do too.
- **`/v1/`, `/healthz`**: proxied to the API.
  - The recording streams to the API (`proxy_request_buffering off`), and results stay in
    memory (`proxy_max_temp_file_size 0`). Nothing a user sends touches the disk.
  - The body limit is 3 MiB, so the API's own `audio_too_large` (2 MiB) is what the app sees.
- **`/admin`**: 404. The admin page stays on the Wi-Fi only, at
  `http://192.168.1.17:8100/admin` (the user's choice).
- **The log** has the method, path, status, size and time. It has no query strings and no
  addresses.

**The visitor's address for the rate limits.** Cloudflare sends it in `CF-Connecting-IP`; nginx
passes it through and drops any `X-Forwarded-For`. The API believes it only from 172.30.0.10
(`MOJAWID_TRUSTED_PROXY_NETWORKS`), the front's fixed address on the pinned compose network. A
forged header sent straight to :8100 is ignored, and the per-IP limit then falls on the
connection's own address.

## Settings and keys (`.env.deploy`)

The API and worker load `.env.deploy` after `.env`. It is git-ignored, mode 600, and compose
refuses to start without it. It sets:
- `MOJAWID_ENVIRONMENT=production` and `MOJAWID_WORKER_ENVIRONMENT=production`. The API then
  refuses to start with any dev key or secret, and /docs is off.
- `MOJAWID_API_KEYS`, with two keys:
  - `web`: compiled into the web build with `--dart-define=MOJAWID_API_KEY=…`;
  - `dev`: for phone builds over the Wi-Fi.

  `mojawid-dev-key`, which is in git, no longer works.
- `MOJAWID_IDENTITY_SECRET` (the HMAC behind install and IP hashes) and `MOJAWID_WORKER_TOKEN`.
- `MOJAWID_TRUSTED_PROXY_NETWORKS`.

Keys reach the Flutter session by message, never through git or the tracker. A key in a web
build is readable by anyone, so it only identifies the client; the limits are the protection.
To rotate a key, edit the file and run `docker compose up -d`. To read one:
`grep API_KEYS .env.deploy`.

**A copy is in Infisical** (https://secrets.lab.egglink.com), in the project *Mojawid*: `.env`
under `dev/mojawid_backend`, and `.env.deploy` under `prod/mojawid_backend`. It is a verified
copy only; the stack reads the files on this laptop. After changing either file, update the copy
as well.

## Updating

| What | How |
|---|---|
| A new web build | `tools/deploy_web.sh <mojawid_flutter build/web>`. It copies `index.html` last, and needs no restart. |
| Backend code | `docker compose up -d --build` |
| nginx config | `docker compose restart mojawid_web` |
| The placeholder page again | `tools/deploy_web.sh --placeholder` |

`docker compose ps` shows all four containers. All are `restart: unless-stopped`, so they come
back after a reboot.

## Going live (done 2026-10-17; kept for a rebuild of the tunnel)

1. `tools/deploy_web.sh <build/web>`, then try it on `http://127.0.0.1:8400`, including a
   recording.
2. Read the tunnel's ingress through the API and change only the catch-all's service, from
   `http://localhost:8000` to `http://localhost:8400`. The `/mojawid` rule and the Access app
   stay as they are.
3. On the real hostname, check:
   - the app loads, and a deep link reloads;
   - a recording is analysed;
   - `/admin` gives 404;
   - `/mojawid/` still shows the review page.

## Known limits

- **The laptop must be on, awake and online.** Otherwise visitors get a Cloudflare error page.
- **Cloudflare cuts a proxied request after 100 s.** An analysis on the warm local GPU takes
  under a second for a short clip, and about 1.6 s for 53 s. Only a hung worker hits this.
- **GPU tests (`pytest -m gpu`) need the worker container stopped** (`docker compose stop
  mojawid_worker`): both won't fit in 8 GB. The site can't analyse while they run, so start the
  worker again afterwards.
- **Calling the worker by hand** now needs the token from `.env.deploy`, not the dev token.
- **The lab is retired from the root.** `muaalem-app` stays installed and disabled. Its data and
  backups aren't touched.

## Taking it down

1. Point the tunnel's catch-all away from :8400, or turn the Access policy to deny all.
2. `docker compose stop mojawid_web`. The API keeps serving the Wi-Fi.
