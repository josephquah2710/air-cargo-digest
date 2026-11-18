import os, re, sys, json, time, calendar, html
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
import feedparser, anthropic, requests
from googlenewsdecoder import gnewsdecoder

# ---------------- Settings ----------------
NOW = datetime.now(ZoneInfo("Asia/Singapore"))
TODAY = NOW.strftime("%A, %d %B %Y")
DAY_ID = NOW.strftime("%Y%m%d")
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"

KEYWORDS_FILE = "keywords.json"   # your search keywords (changed with /add, /remove)
RATINGS_FILE = "ratings.json"     # every story you have rated
STORIES_FILE = "stories.json"     # stories sent recently, so ratings can be matched

# Used only the very first time, before keywords.json exists
DEFAULT_KEYWORDS = [
    '"IBS Software" OR iCargo',
    '"Singapore Airlines" cargo',
    "airspace closure cargo flights",
    'air cargo digitalisation OR "cargo management system"',
]


def google_news(search):
    q = quote(search + " when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-SG&gl=SG&ceid=SG:en"


# Sources that never change
FIXED_SOURCES = {
    "The Loadstar": "https://theloadstar.com/feed",
    "Payload Asia": "https://payloadasia.com/feed",
    "Air Cargo News": google_news("site:aircargonews.net"),
    "Air Cargo Week": google_news("site:aircargoweek.com"),
    "STAT Times": google_news("site:stattimes.com"),
    "IATA": google_news("site:iata.org cargo"),
}


# ---------------- Helpers ----------------
def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def tg(method, **params):
    r = requests.post(f"{API}/{method}", json=params, timeout=30)
    result = r.json()
    if not result.get("ok"):
        print(f"Telegram refused {method}: {result.get('description')}")
    return result


def esc(text):
    return html.escape(str(text), quote=True)


def real_url(link):
    """Turn a Google News redirect link into the publisher's own link."""
    if "news.google.com" not in link:
        return link
    try:
        result = gnewsdecoder(link, interval=1)
        if result.get("success"):
            return result["decoded_url"]
    except Exception as e:
        print(f"Could not decode link: {e}")
    return link  # fall back to the Google link


# ---------------- 0. Read yesterday's ratings and commands ----------------
def process_updates(keywords, ratings, stories):
    updates = tg("getUpdates", timeout=0).get("result", [])
    replies, rated = [], 0

    for u in updates:
        # A star button was tapped
        if "callback_query" in u:
            cq = u["callback_query"]
            if str(cq["message"]["chat"]["id"]) != CHAT_ID:
                continue
            parts = cq.get("data", "").split(":")
            if len(parts) == 3 and parts[0] == "r" and parts[1] in stories:
                ratings[parts[1]] = {**stories[parts[1]], "stars": int(parts[2])}
                rated += 1

        # A text message was sent
        elif "message" in u:
            msg = u["message"]
            if str(msg["chat"]["id"]) != CHAT_ID:
                continue
            text = msg.get("text", "").strip()

            if text.lower().startswith("/add "):
                kw = text[5:].strip()
                if kw and kw.lower() not in [k.lower() for k in keywords]:
                    keywords.append(kw)
                    replies.append(f"✅ Added keyword: {kw}")

            elif text.lower().startswith("/remove "):
                kw = text[8:].strip()
                match = next((k for k in keywords if k.lower() == kw.lower()), None)
                if match:
                    keywords.remove(match)
                    replies.append(f"🗑 Removed keyword: {match}")
                else:
                    replies.append(f"❓ Not in your list: {kw} (send /list to check)")

            elif text.lower().startswith("/list"):
                replies.append("🔎 Your keywords:\n" + "\n".join(f"• {k}" for k in keywords))

    # Tell Telegram we've read these, so they aren't processed twice
    if updates:
        tg("getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)

    if rated:
        replies.insert(0, f"⭐ Saved {rated} rating(s) from yesterday. Thanks!")
    return replies


# ---------------- 1. Collect articles ----------------
def collect(keywords):
    sources = dict(FIXED_SOURCES)
    for kw in keywords:
        sources[kw] = google_news(kw)

    cutoff = time.time() - 24 * 60 * 60
    articles, seen = [], set()
    for name, url in sources.items():
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


# ---------------- 2. Ask Claude to pick and summarise ----------------
RULES = f"""Today is {TODAY}. You write a morning air cargo industry briefing for Joseph.
From the numbered articles below:
1. Drop anything that isn't a real air cargo or airline news article
   (author pages, event pages, stock quote pages). Merge duplicates.
2. "overview": 2-3 sentences on what matters today.
3. "top": up to 10 stories, mixing topics, in this priority:
   (1) industry trends and analysis, (2) IATA updates,
   (3) airline and cargo company news.
4. "systems": stories about airlines adopting or switching cargo
   management systems (iCargo, CargoWise etc.). Empty list if none.
5. Set "flag": true, and rank higher, for any story about IBS Software,
   anything affecting Singapore Airlines Cargo, airspace closures,
   or tech initiatives in airline cargo.

Return ONLY valid JSON in exactly this shape, nothing else:
{{"overview": "...",
  "top": [{{"article": 7, "headline": "...", "summary": "one line", "flag": false}}],
  "systems": [{{"article": 12, "headline": "...", "summary": "one line", "flag": true}}]}}
"article" is the article's number from the list."""


def preference_notes(ratings):
    recent = list(ratings.values())[-60:]
    if not recent:
        return "Joseph has not rated any stories yet."
    lines = [f"{r['stars']}★ [{r['source']}] {r['title']}" for r in recent]
    return ("Joseph's recent ratings (5★ = very useful, 1★ = not useful):\n"
            + "\n".join(lines)
            + "\nFavour stories similar in topic and type to his 4-5★ ratings, and "
              "rank down stories like his 1-2★ ones. Still follow all the rules above.")


def summarise(articles, ratings):
    listing = "\n\n".join(
        f"#{i} [{a['source']}] {a['title']}\n{a['summary']}"
        for i, a in enumerate(articles))
    prompt = (RULES + "\n\nPREFERENCES:\n" + preference_notes(ratings)
              + "\n\nARTICLES:\n\n" + listing)

    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-5-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        text = "".join(stream.text_stream)

    found = re.search(r"\{.*\}", text, re.S)
    return json.loads(found.group(0))


# ---------------- 3. Send to Telegram ----------------
def send_story(number, item, articles, stories):
    i = item.get("article")
    if not isinstance(i, int) or i >= len(articles):
        return
    art = articles[i]
    story_id = f"{DAY_ID}-{number}"
    stories[story_id] = {"title": item["headline"], "source": art["source"], "date": DAY_ID}

    flag = "🚩 " if item.get("flag") else ""
    text = (f"{number}. {flag}<a href=\"{esc(real_url(art['link']))}\">{esc(item['headline'])}</a>\n"
            f"{esc(item.get('summary', ''))}")
    stars = [{"text": f"{s}★", "callback_data": f"r:{story_id}:{s}"} for s in range(1, 6)]
    tg("sendMessage", chat_id=CHAT_ID, text=text, parse_mode="HTML",
       disable_notification=True,
       link_preview_options={"is_disabled": True},
       reply_markup={"inline_keyboard": [stars]})


def send_digest(data, articles, stories):
    header = (f"<b>✈️ Air Cargo Briefing – {esc(TODAY)}</b>\n\n"
              f"<b>What matters today</b>\n{esc(data.get('overview', ''))}")
    if data.get("top"):
        header += "\n\n<i>Rate each story 1–5★. Ratings are collected at the next morning's run.</i>"
    if not tg("sendMessage", chat_id=CHAT_ID, text=header, parse_mode="HTML").get("ok"):
        return False   # the digest didn't reach you; no point sending the stories

    number = 1
    for item in data.get("top", [])[:10]:
        send_story(number, item, articles, stories)
        number += 1

    if data.get("systems"):
        tg("sendMessage", chat_id=CHAT_ID, text="<b>🖥 Cargo systems watch</b>",
           parse_mode="HTML", disable_notification=True)
        for item in data["systems"]:
            send_story(number, item, articles, stories)
            number += 1
    return True


# ---------------- Run everything ----------------
keywords = load(KEYWORDS_FILE, DEFAULT_KEYWORDS)
ratings = load(RATINGS_FILE, {})
stories = load(STORIES_FILE, {})

replies = process_updates(keywords, ratings, stories)
save(KEYWORDS_FILE, keywords)
save(RATINGS_FILE, ratings)
if replies:
    tg("sendMessage", chat_id=CHAT_ID, text="\n\n".join(replies))

articles = collect(keywords)
print(f"Collected {len(articles)} articles using {len(keywords)} keywords. Asking Claude...")
data = summarise(articles, ratings)
print("Sending to Telegram...")
delivered = send_digest(data, articles, stories)

stories = dict(list(stories.items())[-300:])  # keep the file small
save(STORIES_FILE, stories)

# Fail loudly: mark the run as failed (red X) so the Bot Watcher notices.
if not delivered:
    sys.exit("❌ The digest was NOT delivered to Telegram (see the 'Telegram refused' line above).")
print("Done ✅")