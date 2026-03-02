#!/usr/bin/env python3
"""
Compile all member JSON exports into a single searchable index.
Output: user-index/users.json  (keyed by lowercase email)

Run from repo root: python3 scripts/build_user_index.py
"""

import json
from pathlib import Path

EXPORTS = Path(__file__).parent.parent / "exports" / "members"
OUTPUT  = Path(__file__).parent.parent / "user-index" / "users.json"

OMIT = {"Password", "LastIPAddress", "Photo", "Meta"}

META_FIELDS = {
    "bm_favourite-philosopher": "FavouritePhilosopher",
    "bm_favourite-quotations": "FavouriteQuotations",
    "BioInfo": "Bio",
    "Location": "Location",
}

def main():
    OUTPUT.parent.mkdir(exist_ok=True)

    index = {}
    for json_file in EXPORTS.rglob("*.json"):
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        email = data.get("Email", "").strip().lower()
        if not email:
            continue
        entry = {k: v for k, v in data.items() if k not in OMIT}
        meta = data.get("Meta", {})
        for src, dest in META_FIELDS.items():
            if src in meta:
                entry[dest] = meta[src]
        index[email] = entry

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {len(index)} members → {OUTPUT}")

if __name__ == "__main__":
    main()
