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

MAX_CAPTION = 1000  # keep below photo caption limit (1024)


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
    # prefer official
    official = [l for l in links if l.get("type") == "official" and l.get("url")]
    if official:
        # list -> first item url
        if isinstance(official, list):
            return official[0].get("url", "")
        # dict
        return official.get("url", "")
    # else first link with url
    for l in links:
        if l.get("url"):
            return l["url"]
    return ""


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
        "disable_web_page_preview": False
    }
    r = requests.post(api, json=payload, timeout=30)
    r.raise_for_status()


def post_photo(photo_url, caption):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption}
    r = requests.post(api, data=data, timeout=60)
    if r.status_code >= 400:
        # fallback to text if photo fails
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

    caption = build_caption(item, url)
    img = (item.get("image") or "").strip()

    if img:
        post_photo(img, caption)
    else:
        post_text(caption)

    add_history(item)
    print(f"Posted: {item.get('name')}")


if __name__ == "__main__":
    time.sleep(random.randint(0, 60))  # small jitter
    main()
