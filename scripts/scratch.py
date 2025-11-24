import feedparser
import datetime
import dateparser

# A scratch file for testing feed fetching
url = "https://rss.sciencedirect.com/publication/science/00796611" # works
url = "https://nar.oxfordjournals.org/rss/current.xml" # doesn't work
url = "https://www.int-res.com/rss/meps_rss.xml"
url = "http://onlinelibrary.wiley.com/rss/journal/10.1111/(ISSN)1461-0248"
url = "http://advances.sciencemag.org/rss/current.xml#"
feed = feedparser.parse(url)
entry = feed.entries[0]
# print keys
print(entry.keys())