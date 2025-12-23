import json
import os
from datetime import datetime

RANKED_CACHE = "cache/ranked_articles.json"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "curated_latest.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_markdown():
    with open(RANKED_CACHE, "r", encoding="utf-8") as f:
        ranked = json.load(f)

    lines = []
    lines.append(f"# Curated Research Articles\n")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    for a in ranked[:50]:  # Already filtered previously
        title = a["title"].replace("\n", " ").strip()
        url = a["link"]
        score = f"{a['score']:.3f}"
        summary = a["summary"]
        print(summary)
        lines.append(f"- **[{title}]({url})** — score: {score}\n{summary}\nJournal: *{a.get('journal')}*\n")

    md = "\n".join(lines)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Markdown written to {OUTPUT_FILE}")
    

if __name__ == "__main__":
    generate_markdown()
