import feedparser
import json
import os
import hashlib

# Configuration
FEED_LIST_FILE = "feeds.txt"
CACHE_DIR = "cache"
RAW_FEED_CACHE = os.path.join(CACHE_DIR, "raw_feeds.json")
SEEN_IDS_FILE = os.path.join(CACHE_DIR, "seen_ids.txt")

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

def load_raw_feed_cache():
    if not os.path.exists(RAW_FEED_CACHE):
        return []
    with open(RAW_FEED_CACHE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []

# Utility functions
def hash_id(s: str) -> str:
    """Stable ID generator for any article."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

# Load seen IDs from file
def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}

# Save seen IDs to file
def save_seen_ids(ids):
    with open(SEEN_IDS_FILE, "w") as f:
        for id_ in sorted(ids):
            f.write(id_ + "\n")

# Load feed list from feeds.txt
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
    existing_entries = load_raw_feed_cache()
    new_entries = []
    # Fetch and process each feed
    for feed_url in feeds:
        print(f"Fetching: {feed_url}")
        parsed = feedparser.parse(feed_url)
        journal_title = parsed.feed.get("title", str(feed_url))
        # Process each entry in the feed
        for entry in parsed.entries:
            entry_id = entry.get("id") or entry.get("link") or entry.get("title")
            if not entry_id:
                continue
            # Generate a stable hash ID for the entry
            hashed_id = hash_id(entry_id)
            # Skip if already seen
            if hashed_id in seen_ids:
                continue
            # Extract relevant fields
            title = entry.get("title", "")
            link = entry.get("link", "")
            content = ""
            # Abstract/description
            if "content" in entry and len(entry.content) > 0:
                content = entry.content[0].value
            elif "summary" in entry:
                content = entry.summary
            # Store the new entry
            new_entries.append({
                "id": hashed_id,
                "title": title,
                "link": link,
                "content": content,
                "journal": journal_title
            })
            # Mark this ID as seen
            seen_ids.add(hashed_id)

    # Save new articles to cache (append to existing cache)
    all_entries = existing_entries + new_entries
    with open(RAW_FEED_CACHE, "w") as f:
        json.dump(all_entries, f, indent=2)

    save_seen_ids(seen_ids)

    print(f"Fetched {len(new_entries)} new unseen articles.")
    return new_entries

if __name__ == "__main__":
    fetch_all_feeds()
