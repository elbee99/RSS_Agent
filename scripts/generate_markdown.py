import json
import os
import re
from datetime import datetime

CURATED_CACHE = "cache/curated.json"
RANKED_CACHE = "cache/ranked_articles.json"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "curated_latest.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def md_escape(text: str) -> str:
    """Escape characters that pandoc would treat as markdown/LaTeX syntax."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return re.sub(r"([\\`*_{}\[\]#$<>|~^])", r"\\\1", text)


def clean_title(title: str) -> str:
    return re.sub(r"^\[ASAP\]\s*", "", title or "").strip()


def clean_journal(j: str) -> str:
    j = re.sub(r"^(Wiley: |ScienceDirect Publication: )", "", j or "")
    j = re.sub(r"(: Table of Contents|: Latest Articles \(ACS Publications\))$", "", j)
    return j.strip()


def generate_markdown():
    with open(CURATED_CACHE, "r", encoding="utf-8") as f:
        curated = json.load(f)
    n_scanned = 0
    if os.path.exists(RANKED_CACHE):
        with open(RANKED_CACHE, "r", encoding="utf-8") as f:
            n_scanned = len(json.load(f))

    week = datetime.now().strftime("%d %B %Y")
    lines = [
        "---",
        f'title: "Battery literature digest — week of {week}"',
        "---",
        "",
        f"*{len(curated)} papers selected from {n_scanned} scanned. "
        "Scores out of 10; click a title to open the paper.*",
        "",
    ]

    if not curated:
        lines.append("Nothing cleared the bar this week.")

    for i, a in enumerate(curated, 1):
        title = md_escape(clean_title(a["title"]))
        url = (a.get("link") or "").replace(" ", "%20").replace(")", "%29")
        score = int(round(a["score"]))
        journal = md_escape(clean_journal(a.get("journal", "")))
        technique = md_escape(a.get("technique", ""))
        summary = md_escape(a.get("summary", ""))

        lines.append(f"## {i}. [{title}]({url})")
        lines.append("")
        meta = f"**{score}/10** · *{journal}*"
        if technique and technique.lower() not in ("none notable", "none"):
            meta += f" · {technique}"
        lines.append(meta)
        lines.append("")
        if summary:
            lines.append(summary)
            lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown written to {OUTPUT_FILE} ({len(curated)} papers)")


if __name__ == "__main__":
    generate_markdown()
