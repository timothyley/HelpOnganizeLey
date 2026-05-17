"""
generate_dashboard.py — Syncs links_data.json into dashboard.html.

Usage:
    python generate_dashboard.py

Run this whenever you add new records via the Telegram bot.
"""

import json
import re
import sys
from pathlib import Path

DATA_FILE      = Path("links_data.json")
DASHBOARD_FILE = Path("dashboard.html")

def main():
    if not DATA_FILE.exists():
        sys.exit(f"Error: {DATA_FILE} not found.")
    if not DASHBOARD_FILE.exists():
        sys.exit(f"Error: {DASHBOARD_FILE} not found.")

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    # Compact single-line JSON (matches the existing inline format)
    raw_data_js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = DASHBOARD_FILE.read_text(encoding="utf-8")

    # Replace the RAW_DATA line (everything between `const RAW_DATA = ` and the trailing `;`)
    new_line = f"  const RAW_DATA = {raw_data_js};"
    updated, n = re.subn(r"  const RAW_DATA = \{.*?\};", new_line, html, count=1, flags=re.DOTALL)

    if n == 0:
        sys.exit("Error: could not find RAW_DATA in dashboard.html — has the file been modified?")

    DASHBOARD_FILE.write_text(updated, encoding="utf-8")

    total = sum(len(v) for v in data.values())
    print(f"Done — {total} records synced into {DASHBOARD_FILE}.")

if __name__ == "__main__":
    main()
