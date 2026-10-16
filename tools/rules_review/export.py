"""Write docs/rules-review/answers.md: every item with each teacher's answer and correction. It is
how the rulings come back into app/engine/text/rules.py, and a copy of the answers in git.

    .venv/bin/python -m tools.rules_review.export
"""

from __future__ import annotations

import json
from typing import Any

from tools.rules_review import store
from tools.rules_review.server import CONTENT, display_name

OUT = CONTENT.parent / "answers.md"
VERDICT = {"approve": "موافق", "correct": "يحتاج تصحيحًا", "note": "ملاحظة"}


def _item_lines(it: dict[str, Any], answers: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"### {it['title']}", "", f"`{it['id']}` · {it['source']}", ""]
    if not answers:
        return [*lines, "- لا إجابة بعد", ""]
    for email, a in sorted(answers.items()):
        stale = " (أُجيب عن نص أقدم)" if a["item_hash"] != it["hash"] else ""
        lines.append(
            f"- **{display_name(email)}**: {VERDICT[a['verdict']]}{stale} — {a['updated_at']}"
        )
        if a["correction"]:
            lines += [f"  > {line}" for line in a["correction"].splitlines()]
    return [*lines, ""]


def render(content: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    by_item: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by_item.setdefault(r["item_id"], {})[r["reviewer"]] = r
    total = sum(1 for sec in content["sections"] for _ in sec["items"])
    answered = sum(1 for sec in content["sections"] for it in sec["items"] if it["id"] in by_item)
    corrections = sum(1 for r in rows if r["verdict"] == "correct")
    out = [
        f"# {content['title']} — الإجابات",
        "",
        f"بنود أُجيب عنها: {answered} من {total}. طلبات تصحيح: {corrections}.",
        "",
    ]
    for sec in content["sections"]:
        out += [f"## {sec['title']}", ""]
        for it in sec["items"]:
            out += _item_lines(it, by_item.get(it["id"], {}))
    return "\n".join(out)


def main() -> None:
    content = json.loads(CONTENT.read_text())
    OUT.write_text(render(content, store.all_answers()))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
