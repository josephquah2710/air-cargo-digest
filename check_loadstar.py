import feedparser

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"
feed = feedparser.parse("https://theloadstar.com/feed", agent=BROWSER)

print("Fields available:", list(feed.entries[0].keys()), "\n")

for a in feed.entries:
    print(a.title)
    print("  tags:", [t.term for t in a.get("tags", [])])
    print("  link:", a.link)
    print()