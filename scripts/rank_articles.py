
from openai import OpenAI
import numpy as np
import json
import re
from collections import Counter

def embed(texts, model="text-embedding-3-small"):
    client = OpenAI()
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]

def cosine(a,b):
    return float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))

def extract_tags(text):
    words = re.findall(r"[a-zA-Z]{5,}", text.lower())
    return Counter(words).most_common(5)

def score_articles(articles, interests_text, tag_history, model="gpt-4o-mini"):
    client = OpenAI()
    interest_emb = embed([interests_text])[0]

    texts = [a["title"] + " " + a["abstract"] for a in articles]
    art_embs = embed(texts)

    scored=[]
    for art, emb in zip(articles, art_embs):
        base = cosine(np.array(emb), np.array(interest_emb))
        tags = extract_tags(art["title"] + " " + art["summary"])
        tag_score = sum(tag_history.get(t[0],0)*0.1 for t in tags)
        total = (base + tag_score + 1)*5
        scored.append({
            "id": art["id"],
            "title": art["title"],
            "link": art["link"],
            "summary": art["summary"],
            "score": round(total,2),
            "tags": [t[0] for t in tags],
            "justification": f"Similarity + tags: {tags}"
        })
    return scored
