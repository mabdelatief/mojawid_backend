# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Load the output of tools/import_timings.py into Postgres.

The schema comes from the Alembic migrations (`alembic upgrade head`); this tool only fills it
and refuses to run against a database that hasn't been migrated.

Each recitation is replaced in its own transaction: the row is upserted by slug and its ayah
timings are rewritten, so re-running after a new import is safe.

    DATABASE_URL=postgresql://… uv run tools/load_timings.py TIMINGS_DIR
"""

import json
import os
import pathlib
import sys

import psycopg


def require_schema(conn: psycopg.Connection) -> None:
    """Stop unless the migrations have created the recitation tables."""
    row = conn.execute("SELECT to_regclass('public.recitation_ayah_timing')").fetchone()
    if row is None or row[0] is None:
        raise SystemExit("recitation tables missing: run `alembic upgrade head` first")


def main():
    src = pathlib.Path(sys.argv[1])
    files = sorted(f for f in src.glob("*.json") if f.name != "coverage.json")
    if not files:
        raise SystemExit(f"no timing files in {src}")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        require_schema(conn)
        for f in files:
            data = json.loads(f.read_text())
            r = data["recitation"]
            with conn.transaction():
                rid = conn.execute(
                    """INSERT INTO recitation (slug, name_ar, name_en, style, bucket_prefix,
                                               file_pattern, timing_source)
                       VALUES (%(slug)s, %(name_ar)s, %(name_en)s, %(style)s, %(bucket_prefix)s,
                               %(file_pattern)s, %(timing_source)s)
                       ON CONFLICT (slug) DO UPDATE SET
                           name_ar = EXCLUDED.name_ar, name_en = EXCLUDED.name_en,
                           style = EXCLUDED.style, bucket_prefix = EXCLUDED.bucket_prefix,
                           file_pattern = EXCLUDED.file_pattern,
                           timing_source = EXCLUDED.timing_source
                       RETURNING id""",
                    r,
                ).fetchone()[0]
                conn.execute("DELETE FROM recitation_ayah_timing WHERE recitation_id = %s", (rid,))
                with conn.cursor().copy(
                    "COPY recitation_ayah_timing (recitation_id, surah, ayah, segments) FROM STDIN"
                ) as cp:
                    for key, segs in data["ayat"].items():
                        s, a = map(int, key.split(":"))
                        cp.write_row((rid, s, a, segs))
            n = conn.execute(
                "SELECT count(*) FROM recitation_ayah_timing WHERE recitation_id = %s", (rid,)
            ).fetchone()[0]
            print(f"{r['slug']:20s} id={rid} ayat={n}")


if __name__ == "__main__":
    main()
