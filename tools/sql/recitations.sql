-- Reciters and their word timings. Filled by tools/load_timings.py from the output of
-- tools/import_timings.py. Read at runtime instead of any third-party API.

CREATE TABLE IF NOT EXISTS recitation (
    id            smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug          text NOT NULL UNIQUE,
    name_ar       text NOT NULL,
    name_en       text NOT NULL,
    style         text NOT NULL CHECK (style IN ('murattal', 'mujawwad', 'muallim')),
    -- the ayah file is bucket_prefix || format(file_pattern) in the verseaudiofiles bucket
    bucket_prefix text NOT NULL,
    file_pattern  text NOT NULL,
    timing_source text NOT NULL,
    offered       boolean NOT NULL DEFAULT true
);

-- One row per ayah. Each segment is {first_word, last_word, start_ms, end_ms}: word indexes
-- 0-based and inclusive into the ayah's words (Tanzil Uthmani split on spaces, as the analysis
-- uses), times into that ayah's mp3. A segment covering more than one word is a merged span:
-- a tap on any of its words plays the span. A word in no segment has no timing and isn't
-- tappable for this reciter.
CREATE TABLE IF NOT EXISTS recitation_ayah_timing (
    recitation_id smallint NOT NULL REFERENCES recitation (id) ON DELETE CASCADE,
    surah         smallint NOT NULL CHECK (surah BETWEEN 1 AND 114),
    ayah          smallint NOT NULL CHECK (ayah >= 1),
    segments      integer[] NOT NULL CHECK (array_ndims(segments) = 2 OR segments = '{}'),
    PRIMARY KEY (recitation_id, surah, ayah)
);
