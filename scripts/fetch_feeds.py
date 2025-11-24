
import feedparser
import datetime

def fetch_all(feed_list):
    articles = []
    for url in feed_list:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            articles.append({
                "id": entry.get("id"),
                "link": entry.get("link", ""),
                "title": entry.get("title", ""),
                "abstract": entry.get("content", ""),
                "published": entry.get("published", str(datetime.datetime.now(datetime.timezone.utc)))
            })
    return articles
