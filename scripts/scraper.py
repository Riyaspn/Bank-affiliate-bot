import os
import json
import re
import time
from urllib.parse import urljoin, urlparse
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DATA_FILE = os.getenv("DATA_FILE", "data/bank_offers.json")
OUT_FILE = os.getenv("OUT_FILE", "data/bank_offers.enriched.json")
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() == "true"
NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "45000"))
JS_WAIT_MS = int(os.getenv("JS_WAIT_MS", "4000"))

BANK_KEYWORDS = [
"cashback", "reward", "rewards", "points", "miles", "fuel", "octane", "bpcl",
"lounge", "joining fee", "annual fee", "waived", "waiver", "lifetime free",
"welcome bonus", "offer", "discount", "save", "cash back", "%"
]

def best_link(links):
if not links:
return ""
official = [l.get("url") for l in links if l.get("type") == "official" and l.get("url")]
if official:
return official
for l in links:
if l.get("url"):
return l["url"]
return ""

def looks_valid_img(src):
if not src or not src.strip():
return False
return not re.search(r"(sprite|favicon|1x1|pixel|blank|spacer)", src, re.I)

def absolutize(base, src):
if not src:
return ""
if src.startswith("http"):
return src
return urljoin(base, src)

def extract_offer_snippet(soup):
# Try og:title + meta description
ogt = soup.find("meta", property="og:title")
desc = soup.find("meta", attrs={"name": "description"})
if ogt and ogt.get("content"):
t = ogt["content"].strip()
if desc and desc.get("content"):
d = desc["content"].strip()
if d:
return (f"{t} — {d}")[:220]
return t[:220]
# Title tag
if soup.title and soup.title.text:
t = soup.title.text.strip()
if t:
return t[:220]
# First H1/H2
h = soup.find(["h1", "h2"])
if h and h.get_text(strip=True):
return h.get_text(strip=True)[:220]
# Meta description alone
if desc and desc.get("content"):
return desc["content"].strip()[:220]
return ""

def extract_offers_texts(soup):
items = []
# Collect list items and short paragraphs that look like features/offers
for el in soup.select("li, p"):
txt = el.get_text(" ", strip=True)
if not txt:
continue
low = txt.lower()
if any(k in low for k in BANK_KEYWORDS):
if 15 <= len(txt) <= 240:
# reduce whitespace
txt = re.sub(r"\s+", " ", txt)
if txt not in items:
items.append(txt)
if len(items) >= 12:
break
return items[:8]

async def pick_image_from_dom(page, url):
# 1) og:image
og = await page.query_selector('meta[property="og:image"]')
if og:
c = await og.get_attribute("content")
if c:
return absolutize(url, c)
# 2) twitter:image
tw = await page.query_selector('meta[name="twitter:image"]')
if tw:
c = await tw.get_attribute("content")
if c:
return absolutize(url, c)
# 3) header/nav <img> or first few <img>
header_imgs = await page.query_selector_all("header img, nav img")
checked_imgs = header_imgs or await page.query_selector_all("img")
for img in checked_imgs[:12]:
src = await img.get_attribute("src")
if src:
src = absolutize(url, src)
if looks_valid_img(src) and any(src.lower().endswith(e) for e in (".svg",".png",".jpg",".jpeg",".webp")):
return src
# 4) CSS background-image
elems = await page.query_selector_all('[style*="background"]')
for el in elems[:20]:
style = await el.get_attribute("style") or ""
m = re.search(r'background(?:-image)?\s*:\s*url$$['"]?([^)'"]+)', style, re.I)
if m:
src = absolutize(url, m.group(1))
if looks_valid_img(src):
return src
# 5) Largest visible <img>
imgs = await page.query_selector_all("img")
max_area = 0
best = None
for img in imgs[:80]:
src = await img.get_attribute("src")
if not src:
continue
if not looks_valid_img(src):
continue
box = await img.bounding_box()
if not box:
continue
area = (box.get("width") or 0) * (box.get("height") or 0)
if area > max_area and area >= 2500:
max_area = area
best = src
if best:
return absolutize(url, best)
# 6) Fallback: domain avatar
domain = urlparse(url).netloc.replace("www.", "")
return f"https://ui-avatars.com/api/?name={domain}&background=random"

async def scrape_one(context, entry):
# Respect existing image unless FORCE_REFRESH
keep_image = bool(entry.get("image"))
url = best_link(entry.get("links", []))
if not url:
return entry, "skip:no_url"
page = await context.new_page()
page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
try:
await page.goto(url, wait_until="domcontentloaded")
await page.wait_for_timeout(JS_WAIT_MS)
html = await page.content()
final_url = page.url

