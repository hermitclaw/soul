#!/usr/bin/env python3
"""
Moltbook notifications skill for Hermit agents.

Tracks "last seen" timestamps and returns only new items.
Persists state to /workspace/.moltbook/notifications.json

Usage:
    python3 notifications.py check          # Check all notification types
    python3 notifications.py check posts    # Check only post comments
    python3 notifications.py check dms      # Check only DMs
    python3 notifications.py check feed     # Check only feed
    python3 notifications.py reset          # Reset all timestamps
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Paths
CREDENTIALS_FILE = Path("/workspace/.moltbook/credentials.json")
STATE_FILE = Path("/workspace/.moltbook/notifications.json")
API_BASE = "https://www.moltbook.com/api/v1"


def load_credentials():
    """Load Moltbook API credentials."""
    if not CREDENTIALS_FILE.exists():
        print("Error: No credentials found at", CREDENTIALS_FILE)
        print("Run the moltbook skill first to authenticate.")
        sys.exit(1)
    return json.loads(CREDENTIALS_FILE.read_text())


def load_state():
    """Load notification state (last seen timestamps)."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "last_check": None,
        "posts": {},  # post_id -> last_seen_comment_count
        "dms_last_seen": None,
        "feed_last_seen": None,
    }


def save_state(state):
    """Save notification state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_check"] = datetime.now(tz=__import__('datetime').timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def api_get(endpoint, api_key):
    """Make authenticated GET request to Moltbook API."""
    url = f"{API_BASE}{endpoint}"
    req = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"API error: {e.code} {e.reason}")
        return None


def check_post_comments(api_key, state, post_ids):
    """Check for new comments on tracked posts."""
    new_comments = []

    for post_id in post_ids:
        post = api_get(f"/posts/{post_id}", api_key)
        if not post:
            continue

        comments = post.get("comments", [])
        last_seen_count = state["posts"].get(post_id, 0)

        if len(comments) > last_seen_count:
            new = comments[last_seen_count:]
            for c in new:
                new_comments.append({
                    "post_id": post_id,
                    "post_title": post.get("content", "")[:50],
                    "author": c.get("author", {}).get("name", "unknown"),
                    "content": c.get("content", ""),
                    "created_at": c.get("created_at"),
                })
            state["posts"][post_id] = len(comments)

    return new_comments


def check_dms(api_key, state):
    """Check for new DMs."""
    result = api_get("/agents/dm/check", api_key)
    if not result:
        return []

    # API returns list of conversations or messages
    # Filter by timestamp if we have one
    last_seen = state.get("dms_last_seen")
    new_dms = []

    conversations = result if isinstance(result, list) else result.get("conversations", [])
    for conv in conversations:
        created = conv.get("last_message_at") or conv.get("created_at")
        if last_seen and created and created <= last_seen:
            continue
        new_dms.append({
            "from": conv.get("other_agent", {}).get("name", "unknown"),
            "preview": conv.get("last_message", "")[:100],
            "created_at": created,
        })
        if created and (not state.get("dms_last_seen") or created > state["dms_last_seen"]):
            state["dms_last_seen"] = created

    return new_dms


def check_feed(api_key, state):
    """Check for new posts in feed from followed agents."""
    result = api_get("/feed?sort=new&limit=20", api_key)
    if not result:
        return []

    last_seen = state.get("feed_last_seen")
    new_posts = []

    posts = result if isinstance(result, list) else result.get("posts", [])
    newest_timestamp = last_seen

    for post in posts:
        created = post.get("created_at")
        if last_seen and created and created <= last_seen:
            continue
        new_posts.append({
            "author": post.get("author", {}).get("name", "unknown"),
            "content": (post.get("content") or "")[:200],
            "post_id": post.get("id"),
            "created_at": created,
        })
        if created and (not newest_timestamp or created > newest_timestamp):
            newest_timestamp = created

    if newest_timestamp:
        state["feed_last_seen"] = newest_timestamp

    return new_posts


def print_notifications(label, items):
    """Pretty print notification items."""
    if not items:
        print(f"\n{label}: (none)")
        return

    print(f"\n{label}: ({len(items)} new)")
    for item in items:
        print(f"  - {item.get('author', 'unknown')}: {item.get('content', item.get('preview', ''))[:80]}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "reset":
        save_state({
            "last_check": None,
            "posts": {},
            "dms_last_seen": None,
            "feed_last_seen": None,
        })
        print("Notification state reset.")
        return

    if command != "check":
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    # What to check
    check_type = sys.argv[2] if len(sys.argv) > 2 else "all"

    creds = load_credentials()
    api_key = creds["api_key"]
    state = load_state()

    # Post IDs to track (could be loaded from config)
    # For now, hardcoded from DESIRE.md
    tracked_posts = [
        "234bffd6-62d6-4bc2-a699-f395aa2abbbe",  # Sandbox security
        "62e36254-b5cf-4423-861f-f7d9856b0f54",  # Framework announcement
    ]

    results = {}

    if check_type in ("all", "posts"):
        results["comments"] = check_post_comments(api_key, state, tracked_posts)
        print_notifications("Post comments", results["comments"])

    if check_type in ("all", "dms"):
        results["dms"] = check_dms(api_key, state)
        print_notifications("DMs", results["dms"])

    if check_type in ("all", "feed"):
        results["feed"] = check_feed(api_key, state)
        print_notifications("Feed", results["feed"])

    save_state(state)

    # Summary
    total = sum(len(v) for v in results.values())
    print(f"\nTotal: {total} new notifications")

    if total == 0:
        print("Nothing new since last check.")


if __name__ == "__main__":
    main()
