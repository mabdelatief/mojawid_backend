# The teachers' rules review

A page where the teachers go through every tajweed rule Mojawid applies, in فصحى, and approve
or correct each line. It's at **https://tajweed.codavvy.com/mojawid/**, behind the same
Cloudflare email login as the lab.

## What's in it

`content.json` (generated, committed) holds 111 lines in 9 sections, tajweed rules only:
- the reading settings and their places in the Quran;
- madd lengths and the munfasil/muttasil pairs;
- the places where both ways are correct;
- raum;
- how a result is judged;
- the 7 tajweed colours;
- the rules the phonetizer applies, with counts and examples;
- the words it treats specially;
- a free-text box for general notes.

Each line comes from one entry of `app/engine/text/rules.py`, one behaviour in
`docs/model-and-analysis.md`, or one kind found by the scan in `tools/rules_review/scan.py`.
Three of the app's reading settings are left off: recitation speed, takbeer, and the sakin
before a hamza. quran-transcript declares them but its phonetizer never reads them, so they
aren't tajweed rules and change nothing (`NOT_TAJWEED` in `sections.py`). The Arabic wording is
in `tools/rules_review/wording.py`. Ayat and examples always come from
the Quran text, phonetized at the default settings. A ruling about a stop is shown read with
that stop.

Rebuild after changing the rules or the wording (about 30 s):

    .venv/bin/python -m tools.rules_review.build

Line ids are stable, so answers survive a rebuild. If a line's text changes after a teacher
answered it, the page tells her to look at it again.

## Getting the answers back

    .venv/bin/python -m tools.rules_review.export     # writes docs/rules-review/answers.md

That file lists every line, each teacher's answer, and her correction. Rulings go from there
into `rules.py` (and the lab's table), the same way the earlier rulings did.

- **Where the answers are stored:** SQLite at `~/.local/share/mojawid-review/answers.sqlite3`.
  Every change is also appended to `answers_log`, so nothing typed is lost to an overwrite.
- **Names:** answers are kept by login email. To show a name in place of the part before `@`,
  put `{"email": "name"}` in `~/.local/share/mojawid-review/names.json`.

## How it runs

- **The service.** User unit `mojawid-review.service` (`tools/systemd/`) runs
  `uvicorn tools.rules_review.server:app` on 127.0.0.1:8300 from this repo's `.venv`. Linger is
  on, so it starts at boot.
  - After a code change: `systemctl --user restart mojawid-review`. A rebuilt `content.json` is
    picked up without a restart.
  - Logs: `journalctl --user -u mojawid-review`.
- **The tunnel.** The lab's tunnel `tajweed-laptop` (`cloudflared-tajweed.service`) has one rule
  ahead of the lab's. The rule sends host `tajweed.codavvy.com`, path `^/mojawid(/.*)?$`, to
  `http://localhost:8300`. Everything else goes to the lab on :8000 (stopped since 2026-10-16),
  and moves to the Mojawid web app on :8400 when it goes live (`docs/deploy-laptop.md`). The
  tunnel is managed remotely, so the rule was added through the Cloudflare API with
  `CF_API_TOKEN` from `/srv/homelab/.env` on the home box. The lab's code and service weren't
  touched.
- **The login.** The Access app for `tajweed.codavvy.com` covers every path, so the same
  allowlist applies. Add or remove a teacher under Zero Trust → Access → Applications. The
  service trusts `cf-access-authenticated-user-email` because only cloudflared can reach
  127.0.0.1:8300.
- **Backup.** `mojawid-review-backup.timer` runs daily at 02:40 and writes a consistent copy to
  `homelab:/srv/backup/mojawid-review/answers-<UTC time>.sqlite3` (`tools/rules_review/backup.sh`).
- **Local testing** without Cloudflare: set `MOJAWID_REVIEW_DEV_EMAIL=you@example.com` and
  `MOJAWID_REVIEW_DB` to a scratch file, then run uvicorn on another port.

## Taking it down

1. Remove the `/mojawid` rule from the tunnel's ingress (API, or Zero Trust → Networks →
   Tunnels → tajweed-laptop → Public hostnames).
2. Run `systemctl --user disable --now mojawid-review mojawid-review-backup.timer`.
3. Export the answers first.
