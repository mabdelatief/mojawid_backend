# mojawid_backend

The backend for **Mojawid (مُجَوِّد)**, a free Quran recitation practice app with no accounts.
It's planned as FastAPI, PostgreSQL and docker compose, with the speech model on Modal and the
Python service on Linode. **The architecture is not decided yet:** propose it and discuss it,
don't assume it. Nothing is built yet.

## Read first

1. `docs/model-and-analysis.md`: the model, how a recording becomes a result, the result data,
   known limits, and what this backend must provide.
2. `../mojawid_flutter/docs/product.md`: the product. It holds the user's decisions, every
   screen, the corrections to the design export, and the open questions.
3. `docs/recitations.md`: the reciters offered, the audio bucket, where the word timings come
   from, and how they're stored.

## Rules

- **The analysis was worked out in `../tajweed_ai`** (`muaalem_lab/`, and its
  `docs/project-log.md` §11).
  - tajweed_ai is finished, and it is the reference. Rebuild the analysis here properly, for
    production.
  - Keep its behaviour. Its fixes came from real recordings and the teachers' rulings, and
    each one has a reason recorded there.
  - Never add Mojawid features to tajweed_ai; they're built in this repo.
- **Use tajweed_ai's patched quran-transcript** (`vendor/quran-transcript`,
  `0.6.4+muaalem.1`), never the PyPI release. It changes the expected reading at specific
  places, listed in `MUAALEM_PATCHES.md`.
- **The models stay pinned:**
  - `obadx/muaalem-model-v3_2` at `01a1ef9fbe40d144ef845101e89ff924aed3fef5`;
  - `obadx/recitation-segmenter-v2` at `5ee90364e7090ea6eb9dffe80353bed06996a196`.
  A new revision changes what the model hears, so it is only taken on purpose.
- **Never store a user's recording.** The audio is analysed, then discarded. The one exception
  is a "bad result" report the user explicitly agreed to send. It is kept only to investigate,
  and deleted after review. Logs must not hold audio either.
- **No accounts, no login, no payments.** API keys and rate limits protect the service. They
  must not get in a normal user's way. Details are to be agreed with the user.
- **What is correct tajweed is the teachers' call, not ours.** The user's sisters are licensed
  teachers (Hafs via al-Shatibiyya).
  - Their rulings override published sources, and live in one rules table (tajweed_ai
    `muaalem_lab/rules.py`).
  - When a case isn't covered, ask the user; never guess.
- **A place the model wasn't sure about is never counted as a mistake.** Neither is an
  allowed variant.
- **Nothing third-party at runtime.** Reciter audio comes from our own bucket and word timings
  from our own Postgres; never call quran.com, QUL or the like from the running service. Only
  recitations with word-by-word timing are offered. Pulls from outside sources are one-time
  copies, one request at a time with sleeps (`docs/recitations.md`).

## Project tracking (Vikunja)

- **Project:** [Mojawid](https://plan.lab.egglink.com/projects/23) (id `23`) — one
  project for the whole product. Every repo in it is a **label**, not a sub-project.
- **Label:** `MJW-BE` (id `35`) — this repo's work inside that project.
- **Use `vk`** (`home-lab/bin/vk`, on PATH) rather than raw MCP calls — it applies the
  label, picks the right bucket and resolves card numbers:
  - `vk queue` — this repo's open work, plus product-wide items that carry no label
  - `vk board` — this repo's blackboard notes
  - `vk note "<title>"` — write a note; it lands in the blackboard bucket, tagged
  - `vk ask <LABEL> "<title>"` — file against another repo; the label is never omitted
  - `vk done <#N> <sha>` — comment the result and hand the card back to whoever asked
  - `vk close <#N>` — finish a card that was handed back to you
  - `vk show <#N>` — resolve a card number, and print its comment thread
- **Sibling labels** in this product:
  - `MJW-APP` (id `36`) — mojawid_flutter
- **A request and its answer are ONE card.** `vk done` posts the result as a comment and moves
  the label to whoever asked. A request crossing to a *different product* needs its own card in
  that product.
- **Buckets on kanban view `97`:** `To-Do` **96** · `Doing` **97** · `Done` **98** ·
  `blackboard` **99**.
- **Blackboard:** bucket `99` holds notes that outlive the session that wrote them — gotchas,
  decisions and their reasons. Knowledge only; a claim on work is a message to the live session
  or a card in `Doing`, never a note.
- **The `#N` on a card is a per-project index, not the task id** — `vk show N` resolves it.
- **Contracts live in git** (`docs/contracts/`), referenced from a card by commit — never pasted
  into the tracker.
