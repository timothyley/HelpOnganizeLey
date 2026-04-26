"""
storage.py — Simple JSON file storage for saved links.
Supports place_name, place_address, maps_url fields for social media links.
"""

import json
import os
from datetime import datetime

DATA_FILE = "links_data.json"

def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def _save(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_link(
    chat_id: str,
    url: str,
    category: str,
    summary: str,
    label: str = "",
    place_name: str = "",
    place_address: str = "",
    maps_url: str = "",
):
    data = _load()
    if chat_id not in data:
        data[chat_id] = []
    existing_urls = [item["url"] for item in data[chat_id]]
    if url not in existing_urls:
        data[chat_id].append({
            "url":           url,
            "category":      category,
            "summary":       summary,
            "label":         label,
            "place_name":    place_name,
            "place_address": place_address,
            "maps_url":      maps_url,
            "saved_at":      datetime.utcnow().isoformat(),
        })
        _save(data)

def get_links(chat_id: str, category: str = None) -> list[dict]:
    data  = _load()
    links = data.get(chat_id, [])
    if category:
        links = [l for l in links if l["category"].lower() == category.lower()]
    return links

def delete_link(chat_id: str, url: str):
    data = _load()
    if chat_id in data:
        data[chat_id] = [l for l in data[chat_id] if l["url"] != url]
        _save(data)

def clear_links(chat_id: str):
    data = _load()
    if chat_id in data:
        data[chat_id] = []
        _save(data)
