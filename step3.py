import os, re, time, calendar
import feedparser, anthropic
from urllib.parse import quote

from datetime import datetime
from zoneinfo import ZoneInfo
TODAY = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%A, %d %B %Y")

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"

def google_news(search):
    q = quote(search + " when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-SG&gl=SG&ceid=SG:en"

SOURCES = {
    "The Loadstar": "https://theloadstar.com/feed",
    "Payload Asia": "https://payloadasia.com/feed",
    "Air Cargo News": google_news("site:aircargonews.net"),
    "Air Cargo Week": google_news("site:aircargoweek.com"),
    "STAT Times": google_news("site:stattimes.com"),
    "IATA": google_news("site:iata.org cargo"),
    "IBS Software": google_news('"IBS Software" OR iCargo'),
    "SIA Cargo": google_news('"Singapore Airlines" cargo'),
    "Airspace": google_news("airspace closure cargo flights"),
    "Cargo tech": google_news('air cargo digitalisation OR "cargo management system"'),
}

# --- 1. Collect articles from the last 24 hours ---
cutoff = time.time() - 24 * 60 * 60
articles, seen = [], set()

for name, url in SOURCES.items():
    feed = feedparser.parse(url, agent=BROWSER)
    for a in feed.entries:
        date = a.get("published_parsed") or a.get("updated_parsed")
        if not date or calendar.timegm(date) < cutoff:
            continue
        if a.title in seen:
            continue
        seen.add(a.title)
        summary = re.sub("<[^>]+>", "", a.get("summary", ""))[:300]
        articles.append(f"[{name}] {a.title}\n{summary}\nLink: {a.link}")

print(f"Collected {len(articles)} articles. Asking Claude...\n")

# --- 2. Ask Claude to rank and summarise ---
RULES = f"""Today is {TODAY}. You write a morning air cargo industry briefing for Joseph.
From the articles below:
1. Drop anything that isn't a real air cargo or airline news article
   (author pages, event pages, stock quote pages). Merge duplicates.
2. Start with "What matters today": 2-3 sentences.
3. "Top stories": up to 10, mixing topics, in this priority:
   (1) industry trends and analysis, (2) IATA updates,
   (3) airline and cargo company news.
4. "Cargo systems watch": a separate section for airlines adopting or
   switching cargo management systems (iCargo, CargoWise etc.).
   Only include it if there is such news.
5. Put 🚩 before, and rank higher, any story about IBS Software,
   anything affecting Singapore Airlines Cargo, airspace closures,
   or tech initiatives in airline cargo.
Format each story as: headline - one-line summary, then the link
on the next line. Plain text only. If nothing relevant, say it was
a quiet day."""

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY automatically
with client.messages.stream(
    model="claude-sonnet-5-5",
    max_tokens=4000,
    messages=[{"role": "user", "content": RULES + "\n\nARTICLES:\n\n" + "\n\n".join(articles)}],
) as stream:
    for chunk in stream.text_stream:
        print(chunk, end="", flush=True)

print("\n\n--- Done ---")