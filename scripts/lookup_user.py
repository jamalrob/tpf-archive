#!/usr/bin/env python3
"""
Look up a user in the pre-built index by email address or username.

Usage:
  python3 scripts/lookup_user.py email@example.com
  python3 scripts/lookup_user.py Banno
"""

import json
import sys
from pathlib import Path

INDEX = Path(__file__).parent.parent / "user-index" / "users.json"

def main():
    if len(sys.argv) < 2:
        print("Usage: lookup_user.py <email or username>")
        sys.exit(1)

    query = sys.argv[1].strip()

    with open(INDEX, encoding="utf-8") as f:
        index = json.load(f)

    # Try email first (exact, case-insensitive)
    result = index.get(query.lower())

    # Fall back to username search (case-insensitive)
    if result is None:
        ql = query.lower()
        matches = [v for v in index.values() if v.get("Name", "").lower() == ql]
        if len(matches) == 1:
            result = matches[0]
        elif len(matches) > 1:
            print(f"{len(matches)} users match '{query}':")
            for m in matches:
                print(f"  [{m['UserID']}] {m['Name']} — {m.get('Email','')}")
            sys.exit(0)

    if result is None:
        print(f"No user found for '{query}'.")
        sys.exit(1)

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
