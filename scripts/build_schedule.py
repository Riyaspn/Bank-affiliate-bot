import os
import json
import random
import datetime
import hashlib

DATA_FILE = os.getenv("DATA_FILE", "data/bank_offers.enriched.json")
FALLBACK_DATA_FILE = os.getenv("FALLBACK_DATA_FILE", "data/bank_offers.json")
SCHEDULE_FILE = os.getenv("SCHEDULE_FILE", "data/schedule_config.json")
QUEUE_FILE = os.getenv("QUEUE_FILE", "data/today_queue.json")
STATE_FILE = os.getenv("STATE_FILE", "data/schedule_state.json")

# Manual override (workflow input), one of: mon..sun; blank=auto by IST
DAY_OVERRIDE = os.getenv("DAY_OVERRIDE", "").lower().strip()

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def weekday_key(dt=None):
    if DAY_OVERRIDE in {"mon","tue","wed","thu","fri","sat","sun"}:
        return DAY_OVERRIDE
    dt = dt or datetime.datetime.utcnow()
    dt_ist = dt + datetime.timedelta(hours=5, minutes=30)
    return ["mon","tue","wed","thu","fri","sat","sun"][dt_ist.weekday()]

def entry_id(entry):
    s = (entry.get("name", "") or "") + "|" + (entry.get("product_type", "") or "")
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def matches_rule(entry, rule):
    pt = rule.get("product_type")
    if pt and entry.get("product_type") != pt:
        return False
    tags_any = rule.get("tags_any") or []
    if tags_any:
        etags = set(entry.get("tags") or [])
        if not any(t in etags for t in tags_any):
            return False
    if entry.get("status", "active") != "active":
        return False
    return True

def filter_by_rule(entries, rule):
    return [e for e in entries if matches_rule(e, rule)]

def not_recently_posted(candidates, recent_ids):
    return [e for e in candidates if entry_id(e) not in recent_ids]

def build_today_queue(entries, config, state):
    wk = weekday_key()
    calendar = config.get("calendar") or {}
    day_rules = calendar.get(wk, [])
    posts_per_day = int(config.get("posts_per_day", 3))
    mem_days = int(config.get("rotation_memory_days", 7))

    # Recent rotation window
    recent_ids = set()
    history = (state or {}).get("history", [])
    for h in history[-mem_days * posts_per_day:]:
        hid = h.get("id")
        if hid:
            recent_ids.add(hid)

    chosen = []
    chosen_ids = set()
    rng = random.Random()

    def add_pick(pick):
        pid = entry_id(pick)
        if pid in chosen_ids:
            return False
        chosen.append({
            "id": pid,
            "name": pick.get("name"),
            "product_type": pick.get("product_type"),
            "links": pick.get("links"),
            "tags": pick.get("tags", []),
            "image": pick.get("image", ""),
            "offer_snippet": pick.get("offer_snippet", ""),
            "offers": pick.get("offers", []),
            "status": pick.get("status", "active")
        })
        chosen_ids.add(pid)
        return True

    # 1) Satisfy rules (avoid recent, ensure unique)
    for rule in day_rules:
        pool = filter_by_rule(entries, rule)
        pool_nr = not_recently_posted(pool, recent_ids)
        pool_use = pool_nr if pool_nr else pool
        if not pool_use:
            continue
        rng.shuffle(pool_use)
        for pick in pool_use:
            if add_pick(pick):
                break
        if len(chosen) >= posts_per_day:
            break

    # 2) Top up to posts_per_day with active, prefer not recent, avoid duplicates
    if len(chosen) < posts_per_day:
        active = [e for e in entries if e.get("status", "active") == "active"]
        # First: not recent and not already chosen
        fallback_pool = [e for e in active if entry_id(e) not in chosen_ids and entry_id(e) not in recent_ids]
        rng.shuffle(fallback_pool)
        for e in fallback_pool:
            if add_pick(e) and len(chosen) >= posts_per_day:
                break
        # If still short, allow recent but not chosen
        if len(chosen) < posts_per_day:
            extra = [e for e in active if entry_id(e) not in chosen_ids]
            rng.shuffle(extra)
            for e in extra:
                if add_pick(e) and len(chosen) >= posts_per_day:
                    break

    return chosen

def main():
    data = load_json(DATA_FILE) or load_json(FALLBACK_DATA_FILE) or []
    config = load_json(SCHEDULE_FILE) or {}
    state = load_json(STATE_FILE) or {}

    queue = build_today_queue(data, config, state)
    save_json(QUEUE_FILE, queue)

    hist = state.get("history", [])
    ts = datetime.datetime.utcnow().isoformat()
    for item in queue:
        hist.append({"date": ts, "id": item["id"]})
    state["history"] = hist[-1000:]
    save_json(STATE_FILE, state)

    print(f"Built queue with {len(queue)} items for {weekday_key()}.")

if __name__ == "__main__":
    main()
