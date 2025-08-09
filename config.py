import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

DATA_FILE = os.getenv("DATA_FILE", "data/bank_offers.json")
ENRICHED_FILE = os.getenv("ENRICHED_FILE", "data/bank_offers.enriched.json")
QUEUE_FILE = os.getenv("QUEUE_FILE", "data/today_queue.json")
STATE_FILE = os.getenv("STATE_FILE", "data/schedule_state.json")
HISTORY_FILE = os.getenv("HISTORY_FILE", "data/post_history.json")
SCHEDULE_FILE = os.getenv("SCHEDULE_FILE", "data/schedule_config.json")

POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "3"))
MAX_CAPTION = 1000 # keep photo captions under 1024
