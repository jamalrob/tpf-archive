#!/usr/bin/env python3
"""
Look up a user in the pre-built index by email address or username.

Usage:
  python3 scripts/lookup_user.py email@example.com
  python3 scripts/lookup_user.py Banno
  python3 scripts/lookup_user.py Banno --json
"""

import json
import sys
from pathlib import Path

INDEX = Path(__file__).parent.parent / "user-index" / "users.json"


def format_date(dt_str):
    """Return just the date portion of an ISO datetime string."""
    if not dt_str:
        return ""
    return dt_str[:10]


def print_readable(result):
    name    = result.get("Name", "")
    uid     = result.get("UserID", "")
    email   = result.get("Email", "")
    roles   = result.get("Roles") or []
    joined  = format_date(result.get("DateFirstVisit", ""))
    active  = format_date(result.get("DateLastActive", ""))
    discs   = result.get("CountDiscussions", 0)
    posts   = result.get("CountComments", 0)
    liked   = result.get("Liked", 0)
    loc     = result.get("Location", "").strip()
    fav_phil = result.get("FavouritePhilosopher", "").strip()
    fav_quot = result.get("FavouriteQuotations", "").strip()
    deleted = result.get("Deleted", 0)
    banned  = result.get("Banned", 0)

    lines = []
    lines.append(f"Name:           {name}")
    lines.append(f"User ID:        {uid}")
    lines.append(f"Email:          {email}")
    if roles:
        lines.append(f"Roles:          {', '.join(roles)}")
    if deleted:
        lines.append("Status:         DELETED")
    if banned:
        lines.append("Status:         BANNED")
    lines.append("")
    lines.append(f"Joined:         {joined}")
    lines.append(f"Last active:    {active}")
    lines.append(f"Discussions:    {discs:,}")
    lines.append(f"Posts:          {posts:,}")
    lines.append(f"Likes received: {liked:,}")

    if loc or fav_phil or fav_quot:
        lines.append("")
    if loc:
        lines.append(f"Location:       {loc}")
    if fav_phil:
        lines.append(f"Fav. philosophers: {fav_phil}")
    if fav_quot:
        lines.append("")
        lines.append("Favourite quotations:")
        for line in fav_quot.splitlines():
            lines.append(f"  {line}")

    print("\n".join(lines))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if not args:
        print("Usage: lookup_user.py <email or username> [--json]")
        sys.exit(1)

    query = args[0].strip()
    as_json = "--json" in flags

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

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print_readable(result)

if __name__ == "__main__":
    main()
