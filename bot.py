"""
Telegram Link Organiser Bot
Powered by Claude API

Setup:
  pip install python-telegram-bot anthropic requests beautifulsoup4

Set these environment variables:
  TELEGRAM_TOKEN  - from @BotFather
  ANTHROPIC_KEY   - from console.anthropic.com
"""

import os
import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

from storage import save_link, get_links, delete_link, clear_links

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY",  "")

MODEL = "claude-sonnet-4-6"

# Social media platforms that need content-aware classification
SOCIAL_PLATFORMS = ["tiktok.com", "instagram.com", "youtube.com", "youtu.be"]

# Place-related topics — bot will try to extract name + address for these
PLACE_TOPICS = {
    "Restaurant", "Pet Friendly Restaurant", "Cafe",
    "Bar & Nightlife", "Street Food", "Hotel & Accommodation", "Things To Do",
}

# Content topic tags for social media videos
SOCIAL_TOPICS = [
    "Restaurant",
    "Pet Friendly Restaurant",
    "Cafe",
    "Bar & Nightlife",
    "Street Food",
    "Food Recipe",
    "Shopping",
    "Fashion & Outfit",
    "Beauty & Skincare",
    "Travel & Places",
    "Hotel & Accommodation",
    "Things To Do",
    "Fitness & Workout",
    "Pet & Animals",
    "Tech & Gadgets",
    "Entertainment & Funny",
    "Education & Tips",
    "News & Current Affairs",
    "Health & Wellness",
    "Other",
]

# Standard categories for non-social-media links
CATEGORIES = [
    "News", "Shopping", "Tech", "Entertainment",
    "Finance", "Food & Recipes", "Travel", "Education", "Health", "Sports", "Other",
]

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── URL helpers ───────────────────────────────────────────────────────────────
URL_RE = re.compile(r'https?://[^\s]+', re.IGNORECASE)

def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")

def is_social_media(url: str) -> bool:
    return any(p in url.lower() for p in SOCIAL_PLATFORMS)

def make_maps_url(name: str, address: str) -> str:
    """Build a Google Maps search URL from name + address."""
    query = f"{name} {address}".strip()
    return "https://maps.google.com/?q=" + urllib.parse.quote(query)

# ── Page metadata fetcher ─────────────────────────────────────────────────────
def fetch_page_meta(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        og_title = soup.find("meta", property="og:title")
        og_desc  = soup.find("meta", property="og:description")
        og_site  = soup.find("meta", property="og:site_name")

        title       = og_title["content"] if og_title else (soup.title.string if soup.title else "")
        description = og_desc["content"]  if og_desc  else ""
        site        = og_site["content"]  if og_site  else ""

        return {
            "title":       (title or "").strip(),
            "description": (description or "").strip(),
            "site":        (site or "").strip(),
        }
    except Exception as e:
        print(f"[META] Could not fetch page meta for {url}: {e}")
        return {"title": "", "description": "", "site": ""}

# ── Claude classification ─────────────────────────────────────────────────────
def classify_social_link(url: str, meta: dict) -> dict:
    """
    For TikTok / Instagram / YouTube links:
    - Classify the topic
    - Extract name + address if it's a place-related video
    """
    topics_str = ", ".join(SOCIAL_TOPICS)
    place_topics_str = ", ".join(PLACE_TOPICS)

    title       = meta.get("title", "")
    description = meta.get("description", "")
    site        = meta.get("site", "")

    content_hint = ""
    if title:       content_hint += f"Video title: {title}\n"
    if description: content_hint += f"Description: {description[:400]}\n"
    if site:        content_hint += f"Platform: {site}\n"
    if not content_hint:
        content_hint = "(No metadata retrieved — use the URL to make a best guess.)"

    prompt = f"""You are a content classifier for a link-saving app. A user shared this social media video link:

URL: {url}

{content_hint}

Your job:
1. Pick the single best topic tag from this list:
   {topics_str}

2. Write a specific 1-sentence summary (e.g. "A TikTok review of a pet-friendly cafe in Tiong Bahru, Singapore").

3. Extract a short content label (2-5 words), e.g. "Chili Crab Recipe", "Cafe in Tiong Bahru".

4. If the topic is one of these place-related tags: {place_topics_str}
   — try to extract:
     a. place_name: the name of the specific restaurant, cafe, bar, hotel or attraction mentioned.
        If multiple places are mentioned, pick the main one. If none is clearly mentioned, return "".
     b. place_address: the address or area/neighbourhood (e.g. "56 Eng Hoon St, Singapore" or "Tiong Bahru, Singapore").
        If not mentioned, return "".
   — For non-place topics, return "" for both.

Reply ONLY with valid JSON, no markdown fences:
{{
  "topic": "...",
  "summary": "...",
  "label": "...",
  "place_name": "...",
  "place_address": "..."
}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*|```$', '', raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def classify_link(url: str) -> dict:
    """Standard classifier for non-social-media URLs."""
    categories_str = ", ".join(CATEGORIES)
    prompt = f"""You are a link classifier. A user shared this URL:

{url}

Tasks:
1. Pick the single best category from: {categories_str}
2. Write a 1-sentence description of what this link likely contains.

Reply ONLY with valid JSON, no markdown fences:
{{"category": "...", "summary": "..."}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*|```$', '', raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


# ── Telegram handlers ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = extract_urls(text)

    if not urls:
        return

    chat_id = str(update.effective_chat.id)
    responses = []

    for url in urls:
        await update.message.chat.send_action("typing")
        try:
            if is_social_media(url):
                meta   = fetch_page_meta(url)
                result = classify_social_link(url, meta)

                topic         = result.get("topic", "Other")
                summary       = result.get("summary", "No summary available.")
                label         = result.get("label", "")
                place_name    = result.get("place_name", "").strip()
                place_address = result.get("place_address", "").strip()

                # Build Google Maps URL if we have place info
                maps_url = ""
                if place_name or place_address:
                    maps_url = make_maps_url(place_name, place_address)

                save_link(
                    chat_id, url, topic, summary,
                    label=label,
                    place_name=place_name,
                    place_address=place_address,
                    maps_url=maps_url,
                )

                emoji = topic_emoji(topic)
                lines = [f"{emoji} *{label or topic}*", f"🏷 _{topic}_", f"_{summary}_"]

                if place_name:
                    lines.append(f"📍 *{place_name}*")
                if place_address:
                    lines.append(f"🗺 {place_address}")
                if maps_url:
                    lines.append(f"[📌 Open in Google Maps]({maps_url})")

                lines.append(f"`{url[:60]}{'...' if len(url) > 60 else ''}`")
                responses.append("\n".join(lines))

            else:
                result   = classify_link(url)
                category = result.get("category", "Other")
                summary  = result.get("summary", "No summary available.")

                save_link(chat_id, url, category, summary)

                emoji = category_emoji(category)
                responses.append(
                    f"{emoji} *{category}*\n"
                    f"_{summary}_\n"
                    f"`{url[:60]}{'...' if len(url) > 60 else ''}`"
                )

        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            responses.append(
                f"⚠️ Could not classify this link.\n"
                f"`{url[:60]}{'...' if len(url) > 60 else ''}`\n"
                f"_Error: {type(e).__name__}_"
            )

    await update.message.reply_text("\n\n".join(responses), parse_mode="Markdown")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List saved links, optionally filtered: /list Restaurant"""
    chat_id    = str(update.effective_chat.id)
    filter_cat = " ".join(context.args).strip() if context.args else None
    links      = get_links(chat_id, category=filter_cat)

    if not links:
        msg = "No links saved yet." if not filter_cat else f"No links in *{filter_cat}*."
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    grouped: dict[str, list] = {}
    for link in links:
        grouped.setdefault(link["category"], []).append(link)

    lines = []
    for cat, items in sorted(grouped.items()):
        e = topic_emoji(cat) or category_emoji(cat)
        lines.append(f"\n{e} *{cat}* ({len(items)})")
        for item in items[-5:]:
            name    = item.get("place_name", "")
            label   = item.get("label", "")
            display = name or label or (item["url"][:40] + "...")
            maps    = item.get("maps_url", "")
            if maps:
                lines.append(f"  • [{display}]({item['url']}) — [📌 Maps]({maps})")
            else:
                lines.append(f"  • [{display}]({item['url']})")

    await update.message.reply_text(
        f"📋 *Your saved links* ({len(links)} total)\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    links   = get_links(chat_id)

    if not links:
        await update.message.reply_text("No links saved yet. Paste a URL to get started!")
        return

    counts: dict[str, int] = {}
    for link in links:
        counts[link["category"]] = counts.get(link["category"], 0) + 1

    lines = ["📊 *Your link categories*\n"]
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        e   = topic_emoji(cat) or category_emoji(cat)
        bar = "▓" * min(count, 10)
        lines.append(f"{e} *{cat}*  {bar} {count}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    clear_links(chat_id)
    await update.message.reply_text("🗑 All your links have been cleared.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Link Organiser Bot*\n\n"
        "Paste any URL and I'll classify it automatically.\n\n"
        "For TikTok, Instagram & YouTube links about places, I'll also extract:\n"
        "📍 Name of the place\n"
        "🗺 Address / area\n"
        "📌 Google Maps pin\n\n"
        "Commands:\n"
        "/list – show all saved links\n"
        "/list Restaurant – filter by topic\n"
        "/categories – see counts by category\n"
        "/clear – delete all your links",
        parse_mode="Markdown"
    )


# ── Emoji helpers ─────────────────────────────────────────────────────────────
def topic_emoji(topic: str) -> str:
    return {
        "Restaurant":              "🍽",
        "Pet Friendly Restaurant": "🐾",
        "Cafe":                    "☕",
        "Bar & Nightlife":         "🍸",
        "Street Food":             "🥡",
        "Food Recipe":             "👨‍🍳",
        "Shopping":                "🛍",
        "Fashion & Outfit":        "👗",
        "Beauty & Skincare":       "💄",
        "Travel & Places":         "✈️",
        "Hotel & Accommodation":   "🏨",
        "Things To Do":            "🎯",
        "Fitness & Workout":       "💪",
        "Pet & Animals":           "🐶",
        "Tech & Gadgets":          "📱",
        "Entertainment & Funny":   "😂",
        "Education & Tips":        "📚",
        "News & Current Affairs":  "📰",
        "Health & Wellness":       "🌿",
        "Other":                   "🔖",
    }.get(topic, "")

def category_emoji(cat: str) -> str:
    return {
        "News":          "📰",
        "Shopping":      "🛒",
        "Tech":          "💻",
        "Entertainment": "🎬",
        "Finance":       "💰",
        "Food & Recipes":"🍳",
        "Travel":        "✈️",
        "Education":     "📚",
        "Health":        "🏥",
        "Sports":        "⚽",
        "Other":         "🗂",
    }.get(cat, "🔗")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Starting bot with model: {MODEL}")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("list",       cmd_list))
    app.add_handler(CommandHandler("categories", cmd_categories))
    app.add_handler(CommandHandler("clear",      cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running. Send a URL in Telegram to test.")
    app.run_polling()

if __name__ == "__main__":
    main()
