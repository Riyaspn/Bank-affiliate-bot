import os
import json
import time
import random
import requests
from urllib.parse import urlparse

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
DATA_FILE = os.getenv("DATA_FILE", "data/bank_offers.json")
ENRICHED_FILE = os.getenv("ENRICHED_FILE", "data/bank_offers.enriched.json")
QUEUE_FILE = os.getenv("QUEUE_FILE", "data/today_queue.json")
HISTORY_FILE = os.getenv("HISTORY_FILE", "data/post_history.json")

# Telegram photo caption has a hard cap around 1,024 chars; messages allow ~4,096 chars.
MAX_CAPTION = 1000
HTTP_TIMEOUT = 15

# Known-good link overrides (extend as needed)
LINK_OVERRIDES = {
    "axisbank_verification": "https://linksredirect.com/?cid=241055&source=linkkit&url=https%3A%2F%2Fleap.axisbank.com%2Fverification",
    "axis_mf_micro": "https://linksredirect.com/?cid=241055&source=linkkit&url=https%3A%2F%2Fwww.axismf.com%2Fmicro-investing",
}

# Treat some hosts as risky if campaigns are frequently paused
PAUSED_HOSTS = {
    "www.cuelinks.com",
    "cuelinks.com",
}

# Optional per-merchant image overrides (use CDN high-quality images)
IMAGE_OVERRIDES = {
    # "play.google.com": "https://yourcdn.com/brands/google-play-card.jpg",
    # "leap.axisbank.com": "https://yourcdn.com/brands/axis-hero.jpg",
}

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

def hostname(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def shorten(url):
    try:
        r = requests.get("https://tinyurl.com/api-create.php", params={"url": url}, timeout=HTTP_TIMEOUT)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception:
        pass
    return url

def url_ok(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
        if 200 <= r.status_code < 400:
            return True
        r = requests.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
        return (200 <= r.status_code < 400)
    except Exception:
        return False

def apply_link_policy(entry, url):
    name_l = (entry.get("name") or "").lower()
    tags = set((entry.get("tags") or []))
    host = hostname(url)

    # Axis overrides
    if "axis" in tags or "axis" in name_l:
        if "getlasso.co" in url or "cloudflare" in url or "cloudflare" in name_l:
            url = LINK_OVERRIDES["axisbank_verification"]
        if "axisbank.com" in url and not url_ok(url):
            url = LINK_OVERRIDES["axisbank_verification"]

    # Skip paused/broken Cuelinks if unhealthy
    if host in PAUSED_HOSTS and not url_ok(url):
        return ""

    return url

def build_caption_photo(entry, short_url):
    # For photo captions (no clickable anchor), keep it concise with visible short URL
    title = entry.get("offer_snippet") or entry.get("name") or "Offer"
    offers = entry.get("offers", [])[:3]
    bullets = "\n".join(f"-  {o}" for o in offers) if offers else ""
    tags = entry.get("tags", [])
    tag_line = f"\nTags: {', '.join(tags[:5])}" if tags else ""
    caption = (
        f"🏦 {title}\n"
        f"{bullets}\n\n"
        f"Apply/Know more: {short_url}{tag_line}\n"
        f"(Disclosure: Affiliate link)"
    ).strip()
    return caption[:MAX_CAPTION]

def build_message_html(entry, short_url):
    # For text messages: richer formatting and clickable CTA
    title = entry.get("offer_snippet") or entry.get("name") or "Offer"
    offers = entry.get("offers", [])[:3]
    bullets = "\n".join(f"-  {o}" for o in offers) if offers else ""
    tags = entry.get("tags", [])
    tag_line = f"\nTags: {', '.join(tags[:5])}" if tags else ""
    body = (
        f"🏦 <b>{title}</b>\n"
        f"{bullets}\n\n"
        f'<a href="{short_url}">Click here to apply</a>{tag_line}\n'
        f"(Disclosure: Affiliate link)"
    ).strip()
    return body

def post_text_html(text):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(api, json=payload, timeout=HTTP_TIMEOUT)
    r.raise_for_status()

def post_photo(photo_url, caption):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption}
    r = requests.post(api, data=data, timeout=HTTP_TIMEOUT)
    if r.status_code >= 400:
        post_text_html(caption)  # fallback without HTML formatting

def pick_next_from_queue():
    q = load_json(QUEUE_FILE, default=[])
    if not q:
        return None, []
    item = q.pop(0)
    save_json(QUEUE_FILE, q)
    return item, q

def add_history(entry):
    hist = load_json(HISTORY_FILE, default=[])
    hist.append({"name": entry.get("name"), "ts": int(time.time())})
    hist = hist[-1000:]
    save_json(HISTORY_FILE, hist)

def choose_image(entry):
    img = (entry.get("image") or "").strip()
    if img and img.lower().endswith(".svg"):
        img = ""
    if not img:
        host = hostname(best_link(entry.get("links", [])))
        override = IMAGE_OVERRIDES.get(host)
        if override:
            img = override
    return img

def dispatch(item, short_url, img):
    caption_photo = build_caption_photo(item, short_url)
    message_html = build_message_html(item, short_url)
    if img and len(caption_photo) <= MAX_CAPTION:
        post_photo(img, caption_photo)
    else:
        post_text_html(message_html)

def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID")
        return

    item, remaining = pick_next_from_queue()
    if not item:
        data = load_json(ENRICHED_FILE) or load_json(DATA_FILE) or []
        active = [e for e in data if e.get("status", "active") == "active"]
        item = random.choice(active) if active else None
        if not item:
            print("No item to post")
            return

    url = best_link(item.get("links", []))
    if not url:
        print("No link for item; skipping")
        return

    url = apply_link_policy(item, url)
    if not url:
        print("Skipping item due to paused/bad campaign link")
        return

    short_url = shorten(url)
    img = choose_image(item)
    dispatch(item, short_url, img)

    add_history(item)
    print(f"Posted: {item.get('name')} | Remaining today: {len(remaining)}")

if __name__ == "__main__":
    time.sleep(random.randint(0, 60))
    main()
