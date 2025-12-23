import json
import os
from openai import OpenAI
import numpy as np

RAW_FEED_CACHE = "cache/raw_feeds.json"
RANKED_CACHE = "cache/ranked_articles.json"

def rank_articles(threshold=0.80, keep_top_n=50):
    with open(RAW_FEED_CACHE, "r") as f:
        articles = json.load(f)
    print(type(articles))
    print(articles[0])

# rank_articles()


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
# def hash_id(s: str) -> str:
#     """Stable ID generator for any article."""
#     return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

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

import feedparser

def fetch_all_feeds():
    feeds = load_feed_list()
    seen_ids = load_seen_ids()
    existing_entries = load_raw_feed_cache()
    new_entries = []
    # Fetch and process each feed
    i = 0
    for feed_url in feeds:
        # i += 1
        # if i < 2:
            # print(f"Fetching: {feed_url}")
            parsed = feedparser.parse(feed_url)
            # print(parsed.feed.keys())
            title = parsed.feed.get('title', 'No title')
            if title == "No title":
                print(feed_url)
            # print(parsed['title'])
        # Process each entry in the feed
        # if len(parsed.entries) > 0:
        #     print(parsed.entries[0])

fetch_all_feeds()