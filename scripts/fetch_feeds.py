import feedparser
import json
import os
import hashlib

FEED_LIST_FILE = "feeds.txt"
CACHE_DIR = "cache"
RAW_FEED_CACHE = os.path.join(CACHE_DIR, "raw_feeds.json")
SEEN_IDS_FILE = os.path.join(CACHE_DIR, "seen_ids.txt")

os.makedirs(CACHE_DIR, exist_ok=True)

def hash_id(s: str) -> str:
    """Stable ID generator for any article."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}

def save_seen_ids(ids):
    with open(SEEN_IDS_FILE, "w") as f:
        for id_ in sorted(ids):
            f.write(id_ + "\n")

def load_feed_list():
    """Load feeds.txt (one URL per line, ignore empty lines and comments)."""
    if not os.path.exists(FEED_LIST_FILE):
        raise FileNotFoundError("feeds.txt not found in project root.")
    feeds = []
    with open(FEED_LIST_FILE, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                feeds.append(stripped)
    return feeds

def fetch_all_feeds():
    feeds = load_feed_list()
    seen_ids = load_seen_ids()
    new_entries = []

    for feed_url in feeds:
        print(f"Fetching: {feed_url}")
        parsed = feedparser.parse(feed_url)

        for entry in parsed.entries:
            entry_id = entry.get("id") or entry.get("link") or entry.get("title")
            if not entry_id:
                continue

            hashed_id = hash_id(entry_id)

            if hashed_id in seen_ids:
                continue

            title = entry.get("title", "")
            link = entry.get("link", "")
            content = ""

            # Abstract/description
            if "summary" in entry:
                content = entry.summary
            elif "content" in entry and len(entry.content) > 0:
                content = entry.content[0].value

            new_entries.append({
                "id": hashed_id,
                "title": title,
                "link": link,
                "content": content
            })

            seen_ids.add(hashed_id)

    # Save new articles to cache
    with open(RAW_FEED_CACHE, "w") as f:
        json.dump(new_entries, f, indent=2)

    save_seen_ids(seen_ids)

    print(f"Fetched {len(new_entries)} new unseen articles.")
    return new_entries

if __name__ == "__main__":
    fetch_all_feeds()
