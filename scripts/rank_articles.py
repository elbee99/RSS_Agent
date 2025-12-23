import json
import os
from openai import OpenAI
import numpy as np

RAW_FEED_CACHE = "cache/raw_feeds.json"
RANKED_CACHE = "cache/ranked_articles.json"

client = OpenAI()

# DOMAIN-SPECIFIC PROMPT
RANKING_PROMPT = """
You are a domain expert in battery chemistry, advanced battery characterisations,
and structure-function relationships in batteries. Score the relevance of this article to the following interests:

- Battery chemistry
- Advanced characterisation (operando, spatially resolved, novel techniques etc.)
- Structure-function relationships in batteries

Score from 0 to 1. A score of 1 means “highly relevant" and implies overlap with multiple interests.

Return ONLY a JSON object: {"score": float}
"""

def embed_text(text):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def get_relevance_score(title, content):
    text = f"Title: {title}\nAbstract: {content}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": RANKING_PROMPT},
            {"role": "user", "content": text}
        ]
    )
    try:
        return float(json.loads(response.choices[0].message.content)["score"])
    except Exception:
        return 0.0

def rank_articles(threshold=0.50, keep_top_n=100):
    with open(RAW_FEED_CACHE, "r") as f:
        articles = json.load(f)

    ranked = []

    for a in articles:
        score = get_relevance_score(a["title"], a["content"])
        embedding = embed_text(a["title"] + "\n" + a["content"])
        ranked.append({
            "id": a["id"],
            "title": a["title"],
            "link": a["link"],
            "content": a["content"],
            "score": score,
            "embedding": embedding
        })

    # Sort by score
    ranked_sorted = sorted(ranked, key=lambda x: x["score"], reverse=True)

    # Filter: keep only top N OR those above threshold
    filtered = [a for a in ranked_sorted if a["score"] >= threshold]
    if len(filtered) < keep_top_n:
        filtered = ranked_sorted[:keep_top_n]

    # Save all ranked results for later analysis
    with open(RANKED_CACHE, "w") as f:
        json.dump(ranked_sorted, f, indent=2)

    print(f"Ranked {len(ranked)} articles. Kept {len(filtered)}.")
    return filtered

if __name__ == "__main__":
    rank_articles()
