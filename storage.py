"""
storage.py — Simple JSON file storage for saved links.
Supports place_name, place_address, maps_url fields for social media links.
"""

import json
import os
import base64
import requests
from datetime import datetime

DATA_FILE = "links_data.json"

def _load() -> dict:
    # On cloud restarts the local file won't exist — pull from GitHub instead
    if not os.path.exists(DATA_FILE):
        token = os.environ.get("GITHUB_TOKEN", "")
        repo  = os.environ.get("GITHUB_REPO", "")
        if token and repo:
            try:
                api_url = f"https://api.github.com/repos/{repo}/contents/{DATA_FILE}"
                r = requests.get(api_url, headers={"Authorization": f"token {token}"}, timeout=10)
                if r.status_code == 200:
                    content = base64.b64decode(r.json()["content"]).decode()
                    with open(DATA_FILE, "w") as f:
                        f.write(content)
            except Exception:
                pass
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def _save(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    _sync_to_github()

def _sync_to_github():
    """Push links_data.json to GitHub so the hosted dashboard stays current."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return
    try:
        api_url = f"https://api.github.com/repos/{repo}/contents/{DATA_FILE}"
        headers = {"Authorization": f"token {token}"}
        with open(DATA_FILE, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        # Fetch current SHA (required for updates)
        r = requests.get(api_url, headers=headers, timeout=10)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": "sync: update links_data.json", "content": encoded}
        if sha:
            payload["sha"] = sha
        requests.put(api_url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass  # Never let a sync failure break the bot

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
