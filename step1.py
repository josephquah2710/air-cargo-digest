import feedparser

feed = feedparser.parse("https://www.stattimes.com/feed")

print("Found", len(feed.entries), "articles\n")

for article in feed.entries[:10]:
    print(article.title)
    print(article.link)
    print()