import feedparser
from urllib.parse import quote

def google_news(search):
    q = quote(search + " when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-SG&gl=SG&ceid=SG:en"

TESTS = {
    "Air Cargo News": google_news("site:aircargonews.net"),
    "Air Cargo Week": google_news("site:aircargoweek.com"),
    "STAT Times": google_news("site:stattimes.com"),
    "IATA cargo": google_news("site:iata.org cargo"),
    "IBS Software": google_news('"IBS Software" cargo'),
    "SIA Cargo": google_news('"Singapore Airlines" cargo'),
}

for name, url in TESTS.items():
    feed = feedparser.parse(url)
    print(f"--- {name}: {len(feed.entries)} articles ---")
    for a in feed.entries[:3]:
        print(" ", a.title)
    print()