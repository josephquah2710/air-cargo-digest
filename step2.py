import feedparser
import calendar
import time

SOURCES = {
    "Air Cargo News": "https://www.aircargonews.net/feed",
    "Air Cargo Week": "https://aircargoweek.com/feed",
    "STAT Times": "https://www.stattimes.com/feed",
    "The Loadstar": "https://theloadstar.com/feed",
    "Cargo Facts": "https://cargofacts.com/feed",
    "Payload Asia": "https://payloadasia.com/feed",
}

cutoff = time.time() - 24 * 60 * 60
recent = []

for name, url in SOURCES.items():
    feed = feedparser.parse(url)
    count = 0
    for a in feed.entries:
        date = a.get("published_parsed") or a.get("updated_parsed")
        if date and calendar.timegm(date) >= cutoff:
            recent.append((name, a.title, a.link))
            count += 1
    print(f"{name}: {len(feed.entries)} in feed, {count} from last 24h")

print(f"\nTotal recent articles: {len(recent)}\n")
for name, title, link in recent:
    print(f"[{name}] {title}\n{link}\n")