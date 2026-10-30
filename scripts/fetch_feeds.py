import feedparser
import json
import os
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# Crossref is used for publishers (ACS) that block GitHub's servers from their RSS.
CROSSREF_DAYS = 8
CROSSREF_UA = "RSS_Agent/1.0 (https://github.com/elbee99/RSS_Agent)"

# Browser-like user agent, used as a fallback for publishers that reject feedparser's
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

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
    with open(RAW_FEED_CACHE, "r", encoding="utf-8") as f:
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

def fetch_crossref(issn):
    """Return (journal_title, entries) for articles registered in the last few days."""
    since = (datetime.now(timezone.utc) - timedelta(days=CROSSREF_DAYS)).strftime("%Y-%m-%d")
    entries, journal, cursor = [], issn, "*"
    while True:
        params = urllib.parse.urlencode({
            "filter": f"issn:{issn},from-created-date:{since},type:journal-article",
            "rows": 200, "cursor": cursor,
            "select": "DOI,title,abstract,URL,container-title",
        })
        req = urllib.request.Request(f"https://api.crossref.org/works?{params}",
                                     headers={"User-Agent": CROSSREF_UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            msg = json.load(r)["message"]
        for it in msg.get("items", []):
            journal = (it.get("container-title") or [journal])[0]
            entries.append({
                "id": "https://doi.org/" + it["DOI"],
                "title": (it.get("title") or [""])[0],
                "link": "https://doi.org/" + it["DOI"],
                "content": it.get("abstract", ""),
            })
        if len(msg.get("items", [])) < 200:
            break
        cursor = msg.get("next-cursor")
    return journal, entries


def fetch_all_feeds():
    feeds = load_feed_list()
    seen_ids = load_seen_ids()
    existing_entries = load_raw_feed_cache()
    new_entries = []
    # Fetch and process each feed
    for feed_url in feeds:
        print(f"Fetching: {feed_url}")
        if feed_url.startswith("crossref:"):
            try:
                journal_title, items = fetch_crossref(feed_url.split(":", 1)[1].strip())
            except Exception as e:
                print(f"  WARNING: Crossref fetch failed: {e}")
                continue
            print(f"  {len(items)} articles from Crossref")
            for it in items:
                hashed_id = hash_id(it["id"])
                if hashed_id in seen_ids:
                    continue
                new_entries.append({"id": hashed_id, "title": it["title"], "link": it["link"],
                                    "content": it["content"], "journal": journal_title})
                seen_ids.add(hashed_id)
            continue
        # Try feedparser's own user agent first (ACS blocks browser-like agents
        # from GitHub's servers); fall back to a browser agent if that fails.
        parsed = feedparser.parse(feed_url)
        if not parsed.entries:
            parsed = feedparser.parse(feed_url, agent=USER_AGENT)
        if not parsed.entries:
            print(f"  WARNING: 0 entries (status={parsed.get('status')}, bozo={parsed.get('bozo_exception')})")
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
    with open(RAW_FEED_CACHE, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2)

    save_seen_ids(seen_ids)

    print(f"Fetched {len(new_entries)} new unseen articles.")
    return new_entries

if __name__ == "__main__":
    fetch_all_feeds()
