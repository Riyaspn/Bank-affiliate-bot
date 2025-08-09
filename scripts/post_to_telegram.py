import os, json, time, random, requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, QUEUE_FILE, HISTORY_FILE, ENRICHED_FILE, DATA_FILE, MAX_CAPTION

def load_json(path, default=None):
try:
with open(path, "r", encoding="utf-8") as f:
return json.load(f)
except:
return default

def save_json(path, obj):
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
json.dump(obj, f, ensure_ascii=False, indent=2)

def best_link(links):
if not links:
return ""
official = [l for l in links if l.get("type")=="official" and l.get("url")]
if official:
return official["url"]
for l in links:
if l.get("url"):
return l["url"]
return ""

def build_caption(entry, url):
title = entry.get("offer_snippet") or entry.get("name","")
offers = entry.get("offers", [])[:3]
bullets = ""
if offers:
bullets = "\n".join(f"- {o}" for o in offers)
tags = entry.get("tags", [])
tag_line = f"\nTags: {', '.join(tags[:5])}" if tags else ""
cap = f"🏦 The Online Wala: {title}\n{bullets}\n\nApply/Know more: {url}{tag_line}\n(Disclosure: Affiliate link)"
return cap[:MAX_CAPTION]

def post_text(text):
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
r = requests.post(url, json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "disable_web_page_preview": False}, timeout=30)
r.raise_for_status()

def post_photo(photo_url, caption):
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
r = requests.post(url, data={"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo_url, "caption": caption}, timeout=60)
if r.status_code >= 400:
post_text(caption)

def pick_next():
queue = load_json(QUEUE_FILE, default=[])
if queue:
item = queue.pop(0)
save_json(QUEUE_FILE, queue)
return item
# fallback: pick a random active
data = load_json(ENRICHED_FILE) or load_json(DATA_FILE) or []
active = [e for e in data if e.get("status","active")=="active"]
return random.choice(active) if active else None

def add_history(entry):
hist = load_json(HISTORY_FILE, default=[])
hist.append({"name": entry.get("name"), "ts": int(time.time())})
hist = hist[-1000:]
save_json(HISTORY_FILE, hist)

def main():
item = pick_next()
if not item:
return
url = best_link(item.get("links", []))
if not url:
return
caption = build_caption(item, url)
img = item.get("image","").strip()
if img:
post_photo(img, caption)
else:
post_text(caption)
add_history(item)

if name == "main":
time.sleep(random.randint(0, 60))
main()
