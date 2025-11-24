
import json, os
from fetch_feeds import fetch_all
from rank_articles import score_articles
from generate_markdown import make_markdown

CACHE_FILE = "cache/seen.json"
TAGS_FILE = "cache/tags.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        return json.load(open(CACHE_FILE))
    return []

def save_cache(ids):
    os.makedirs("cache", exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(ids, f)

def load_tags():
    if os.path.exists(TAGS_FILE):
        return json.load(open(TAGS_FILE))
    return {}

def save_tags(t):
    os.makedirs("cache", exist_ok=True)
    with open(TAGS_FILE,"w") as f:
        json.dump(t,f)

def main():
    # clear last week's cache
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    feeds = open("feeds.txt").read().strip().splitlines()
    interests = open("interests.md").read()

    seen = load_cache()
    tags = load_tags()

    articles = fetch_all(feeds)
    new_articles = [a for a in articles if a["id"] not in seen]

    scored = score_articles(new_articles, interests, tags)

    # update tag history
    for item in scored:
        for t in item["tags"]:
            tags[t] = tags.get(t,0)+1

    save_tags(tags)
    save_cache([a["id"] for a in new_articles])

    md = make_markdown(scored)
    with open("output/curated-latest.md", "w") as f:
        f.write(md)

if __name__ == "__main__":
    main()
