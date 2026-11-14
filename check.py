import feedparser

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

SOURCES = {
    "Air Cargo News": "https://www.aircargonews.net/feed",
    "Air Cargo Week": "https://aircargoweek.com/feed",
    "STAT Times": "https://www.stattimes.com/feed",
    "Cargo Facts": "https://cargofacts.com/feed",
    "Payload Asia": "https://payloadasia.com/feed",
}

for name, url in SOURCES.items():
    feed = feedparser.parse(url, agent=BROWSER)
    print(f"--- {name} ---")
    print("Status:", feed.get("status"), "| Articles:", len(feed.entries))
    if feed.entries:
        a = feed.entries[0]
        print("Newest:", a.title)
        print("Date text:", a.get("published") or a.get("updated"))
    elif feed.get("bozo"):
        print("Problem:", feed.bozo_exception)
    print()