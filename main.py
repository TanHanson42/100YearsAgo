import tweepy
import requests
import schedule
import time
import logging
import yaml
from datetime import datetime

# ============================================================
# Load Config
# ============================================================

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# ============================================================
# Logging Setup
# ============================================================

logging.basicConfig(
    level=getattr(logging, config["logging"]["level"]),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config["logging"]["log_file"]),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# Twitter / X Client
# ============================================================

def get_twitter_client():
    tw = config["twitter"]
    return tweepy.Client(
        bearer_token=tw["bearer_token"],
        consumer_key=tw["consumer_key"],
        consumer_secret=tw["consumer_secret"],
        access_token=tw["access_token"],
        access_token_secret=tw["access_token_secret"]
    )

# ============================================================
# Helpers
# ============================================================

def get_historical_date():
    today = datetime.now()
    years_back = config["bot"]["history_years_back"]
    return today.replace(year=today.year - years_back)

def build_tweet(text: str, year: int) -> str:
    hashtags = " ".join(config["bot"]["hashtags"])
    prefix = f"📰 #OTD in {year}: "
    max_length = config["bot"]["max_tweet_length"]
    # Reserve space for prefix and hashtags
    available = max_length - len(prefix) - len(hashtags) - 2  # 2 for newlines
    truncated = text[:available].rsplit(" ", 1)[0]  # avoid cutting mid-word
    return f"{prefix}{truncated}\n\n{hashtags}"

# ============================================================
# Data Sources
# ============================================================

def fetch_wikipedia_event(date: datetime) -> str | None:
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{date.month}/{date.day}"
    try:
        headers = {"User-Agent": "100YearsAgoBot/1.0 (your@email.com)"}
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        events = response.json().get("events", [])
        log.info("Wikipedia returned %d total events for %s", len(events), date.strftime("%B %d"))
        matching = [e for e in events if e.get("year") == date.year]
        if matching:
            log.info("Found %d matching event(s) for %s — using: %s", len(matching), date.strftime("%Y-%m-%d"), matching[0]["text"][:100])
            return matching[0]["text"]
        else:
            log.warning("Wikipedia had events for %s but none matched the year %d", date.strftime("%B %d"), date.year)
    except Exception as e:
        log.warning("Wikipedia fetch failed: %s", e)
    return None


def fetch_chronicling_america(date: datetime) -> str | None:
    """Fetch a newspaper headline from the Library of Congress Chronicling America archive."""
    date_str = date.strftime("%Y-%m-%d")
    url = (
        f"https://chroniclingamerica.loc.gov/search/pages/results/"
        f"?date1={date_str}&date2={date_str}&format=json&rows=5"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])
        if items:
            item = items[0]
            title = item.get("title", "Unknown Paper")
            snippet = item.get("ocr_eng", "")[:300].strip()
            # Clean up common OCR artifacts
            snippet = " ".join(snippet.split())
            log.info("Found Chronicling America result for %s", date_str)
            return f"{title} — {snippet}"
    except Exception as e:
        log.warning("Chronicling America fetch failed: %s", e)
    return None


def fetch_nyt_archive(date: datetime) -> str | None:
    """Fetch a headline from the NYT Archive API."""
    api_key = config.get("nyt", {}).get("api_key", "")
    if not api_key or api_key == "YOUR_NYT_API_KEY":
        return None
    url = f"https://api.nytimes.com/svc/archive/v1/{date.year}/{date.month}.json?api-key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        # Filter to articles published on this exact day
        day_str = date.strftime("%Y-%m-%d")
        matching = [
            d for d in docs
            if d.get("pub_date", "").startswith(day_str)
        ]
        if matching:
            article = matching[0]
            headline = article.get("headline", {}).get("main", "")
            abstract = article.get("abstract", "")
            log.info("Found NYT article for %s", day_str)
            return f"{headline}. {abstract}".strip()
    except Exception as e:
        log.warning("NYT Archive fetch failed: %s", e)
    return None

# ============================================================
# Core Bot Logic
# ============================================================

def fetch_content(date: datetime) -> tuple[str, int] | tuple[None, None]:
    """Try each data source in order, return (content, year) or (None, None)."""
    sources = [
        fetch_wikipedia_event,
        fetch_nyt_archive,
        fetch_chronicling_america,
    ]
    for source in sources:
        content = source(date)
        if content:
            return content, date.year
    return None, None


def post_tweet(text: str) -> None:
    client = get_twitter_client()
    try:
        response = client.create_tweet(text=text)
        log.info("Tweet posted successfully. Tweet ID: %s", response.data["id"])
    except tweepy.TweepyException as e:
        log.error("Failed to post tweet: %s", e)


def run_bot() -> None:
    date = get_historical_date()
    log.info("Running bot for historical date: %s", date.strftime("%Y-%m-%d"))

    content, year = fetch_content(date)
    if not content:
        log.warning("No content found for %s. Skipping post.", date.strftime("%Y-%m-%d"))
        return

    tweet = build_tweet(content, year)
    log.info("Prepared tweet:\n%s", tweet)
    post_tweet(tweet)

# ============================================================
# Scheduler
# ============================================================

if __name__ == "__main__":
   # post_time = config["bot"]["post_time"]
   # log.info("Bot started. Scheduled to post daily at %s", post_time)

 #   schedule.every().day.at(post_time).do(run_bot)

    # Uncomment the line below to run immediately on startup for testing:
     run_bot()

    #while True:
       # schedule.run_pending()
        #time.sleep(60)