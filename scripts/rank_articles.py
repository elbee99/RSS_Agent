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
- Novel insights into the chemistry of common battery materials (i.e. how and why they work, not just that they do)
- Advanced characterisation (operando, spatially resolved, novel techniques etc.)
- Spatial analysis of heterogeneity in batteries
- Tomographic imaging of batteries

Score from 0 to 1. A score of 1 means “highly relevant" and implies overlap with multiple interests. In particular,
a score of 1 should be given to articles that discuss novel insights into battery chemistry using advanced characterisation
techniques, such as novel operando methods, synchrotron techniques, and/or spatially resolved analyses that reveal new insights into
the structure-function relationships in batteries. 

A paper which simply uses a new material and shows better performance with
little insight would score low (0-0.2). Papers which do not discuss batteries should always score low (0)

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

def get_summary(title, content):
    text = f"Title: {title}\nAbstract: {content}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Provide a concise 2-3 line summary of the following article abstract, giving more detail than just rewording the title."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

def rank_articles(threshold=0.50, keep_top_n=50):
    with open(RAW_FEED_CACHE, "r") as f:
        articles = json.load(f)

    ranked = []

    for a in articles:
        score = get_relevance_score(a["title"], a["content"])
        summary = get_summary(a["title"], a["content"])
        embedding = embed_text(a["title"] + "\n" + a["content"])
        ranked.append({
            "id": a["id"],
            "title": a["title"],
            "link": a["link"],
            "content": a["content"],
            "journal":a["journal"],
            "score": score,
            "summary": summary,
            "embedding": embedding
        })

    # Sort by score
    ranked_sorted = sorted(ranked, key=lambda x: x["score"], reverse=True)

    # Filter: keep only top N OR those above threshold
    filtered = [
        a for a in ranked_sorted
        if a["score"] >= threshold
    ][:keep_top_n]

    # Save all ranked results for later analysis
    with open(RANKED_CACHE, "w") as f:
        json.dump(ranked_sorted, f, indent=2)

    print(f"Ranked {len(ranked)} articles. Kept {len(filtered)}.")
    return filtered

if __name__ == "__main__":
    rank_articles()
