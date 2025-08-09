import os
import json
import time
import random
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
DATA_FILE = os.getenv("DATA_FILE", "data/bank_offers.json")
ENRICHED_FILE = os.getenv("ENRICHED_FILE", "data/bank_offers.enriched.json")
QUEUE_FILE = os.getenv("QUEUE_FILE", "data/today_queue.json")
HISTORY_FILE = os.getenv("HISTORY_FILE", "data/post_history.json")

# Keep below Telegram photo caption cap (1,024 chars); use text messages for longer bodies[1][2][3][5].
MAX_CAPTION = 1000


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def best_link(links):
    if not links:
        return ""
    official = [l for l in links if l.get("type") == "official" and l.get("url")]
    if official:
        item = official[0] if isinstance(official, list) else official
        return item.get("url", "") if isinstance(item, dict) else item
    for l in links:
        if l.get("url"):
            return l["url"]
    return ""


# Axis link overrides as requested
AXIS_REPLACEMENTS = [
    ("axisbank.com", "https://linksredirect.com/?cid=241055&source=linkkit&url=https%3A%2F%2Fleap.axisbank.com%2Fverification"),
    ("axismf.com", "https://linksredirect.com/?cid=241055&source=linkkit&url=https%3A%2F%2Fwww.axismf.com%2Fmicro-investing"),
]


def maybe_override_axis(entry, url):
    tags = set((entry.get("tags") or []))
    lower_url = (url or "").lower()
    name_l = (entry.get("name") or "").lower()
    if "axis" in tags or "axis" in name_l:
        for host, repl in AXIS_REPLACEMENTS:
            if host in lower_url:
                return repl
        # If link is a Cloudflare/Lasso page, prefer verification link for cards
        if "getlasso.co" in lower_url or "cloudflare" in lower_url:
            return AXIS_REPLACEMENTS[0][1]
    return url


# Simple TinyURL shortener (fallback to original URL if API fails)[12][18]
def shorten(url):
    try:
        r = requests.get("https://tinyurl.com/api-create.php", params={"url": url}, timeout=10)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception:
        pass
    return url


def build_caption(entry, url):
    title = entry.get("offer_snippet") or entry.get("name", "")
    offers = entry.get("offers", [])[:3]
    bullets = "\n".join(f"- {o}" for o in offers) if offers else ""
    tags = entry.get("tags", [])
    tag_line = f"\nTags: {', '.join(tags[:5])}" if tags else ""
    caption = (
        f"🏦 The Online Wala: {title}\n"
        f"{bullets}\n\n"
        f"Apply/Know more: {url}{tag_line}\n"
        f"(Disclosure: Affiliate link)"
    ).strip()
    return caption[:MAX_CAPTION]


def post_text(text):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "disable_web_page_preview": False  # allow link preview for images and cards
    }
    r = requests.post(api, json=payload, timeout=30)
    r.raise_for_status()


def post_photo(photo_url, caption):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption}
    r = requests.post(api, data=data, timeout=60)
    # If photo fails (bad URL), fallback to text so the post still goes out
    if r.status_code >= 400:
        post_text(caption)


def dispatch(item, caption, img):
    # If image present and caption is short enough, prefer photo post[1][2][3][5][14][20].
    if img and len(caption) <= MAX_CAPTION:
        post_photo(img, caption)
    else:
        # Use text post for longer bodies or missing image (up to 4,096 chars)[2][5][20].
        post_text(caption)


def pick_next():
    # Try queue first
    queue = load_json(QUEUE_FILE, default=[])
    if queue:
        item = queue.pop(0)
        save_json(QUEUE_FILE, queue)
        return item
    # Fallback to enriched or base data
    data = load_json(ENRICHED_FILE) or load_json(DATA_FILE) or []
    active = [e for e in data if e.get("status", "active") == "active"]
    return random.choice(active) if active else None


def add_history(entry):
    hist = load_json(HISTORY_FILE, default=[])
    hist.append({"name": entry.get("name"), "ts": int(time.time())})
    hist = hist[-1000:]
    save_json(HISTORY_FILE, hist)


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID")
        return

    item = pick_next()
    if not item:
        print("No item to post")
        return

    url = best_link(item.get("links", []))
    if not url:
        print("No link for item; skipping")
        return

    # Apply Axis overrides and shorten URL for cleaner messages
    url = maybe_override_axis(item, url)
    short_url = shorten(url)

    caption = build_caption(item, short_url)
    img = (item.get("image") or "").strip()

    dispatch(item, caption, img)
    add_history(item)
    print(f"Posted: {item.get('name')}")


if __name__ == "__main__":
    # small jitter to avoid exact-time collisions
    time.sleep(random.randint(0, 60))
    main()
