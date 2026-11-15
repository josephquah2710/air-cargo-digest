import os, re, time, calendar, html
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
import feedparser, anthropic, requests

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

# --- 1. Collect ---
def collect():
    cutoff = time.time() - 24 * 60 * 60
    articles, seen = [], set()
    for name, url in SOURCES.items():
        try:
            feed = feedparser.parse(url, agent=BROWSER)
        except Exception as e:
            print(f"Skipped {name}: {e}")
            continue
        for a in feed.entries:
            date = a.get("published_parsed") or a.get("updated_parsed")
            if not date or calendar.timegm(date) < cutoff or a.title in seen:
                continue
            seen.add(a.title)
            summary = re.sub("<[^>]+>", "", a.get("summary", ""))[:300]
            articles.append({"source": name, "title": a.title,
                             "summary": summary, "link": a.link})
    return articles

# --- 2. Summarise with Claude ---
RULES = f"""Today is {TODAY}. You write a morning air cargo industry briefing for Joseph.
From the articles below:
1. Drop anything that isn't a real air cargo or airline news article
   (author pages, event pages, stock quote pages). Merge duplicates.
2. Start with a title line, then "What matters today": 2-3 sentences.
3. "Top stories": up to 10, mixing topics, in this priority:
   (1) industry trends and analysis, (2) IATA updates,
   (3) airline and cargo company news.
4. "Cargo systems watch": a separate section for airlines adopting or
   switching cargo management systems (iCargo, CargoWise etc.).
   Only include it if there is such news.
5. Put 🚩 before, and rank higher, any story about IBS Software,
   anything affecting Singapore Airlines Cargo, airspace closures,
   or tech initiatives in airline cargo.
FORMAT: Telegram HTML. Only use <b>, <i> and <a href="...">.
Section titles in <b>. Each story is one line:
<a href="ARTICLE_n">Headline</a> - one-line summary
(use the article's ARTICLE_ label exactly, e.g. ARTICLE_7)
with a blank line between stories. Write & as "and". Never use < or >
except in those tags. No markdown. If nothing relevant, say it was a quiet day."""

def summarise(articles):
    listing = "\n\n".join(
        f"ARTICLE_{i} [{a['source']}] {a['title']}\n{a['summary']}"
        for i, a in enumerate(articles))
    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-5-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": RULES + "\n\nARTICLES:\n\n" + listing}],
    ) as stream:
        text = "".join(stream.text_stream)

    # swap each ARTICLE_n label for the real link
    def real_link(match):
        i = int(match.group(1))
        return html.escape(articles[i]["link"]) if i < len(articles) else "#"
    return re.sub(r"ARTICLE_(\d+)", real_link, text)

# --- 3. Send to Telegram ---
def send(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram allows 4096 characters per message, so split long digests
    parts, current = [], ""
    for block in text.split("\n\n"):
        if len(current) + len(block) > 3800:
            parts.append(current)
            current = ""
        current += block + "\n\n"
    parts.append(current)
    for part in parts:
        r = requests.post(url, data={"chat_id": chat_id, "message_thread_id": 4, "text": part,
                                     "parse_mode": "HTML", "disable_web_page_preview": True})
        if not r.ok:  # if the formatting is rejected, send it as plain text instead
            plain = re.sub("<[^>]+>", "", part)
            requests.post(url, data={"chat_id": chat_id, "message_thread_id": 4, "text": plain})

# --- Run everything ---
articles = collect()
print(f"Collected {len(articles)} articles. Asking Claude...")
digest = summarise(articles)
print("Sending to Telegram...")
send(digest)
print("Done ✅")