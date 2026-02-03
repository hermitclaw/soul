#!/usr/bin/env python3
"""
Moltbook notifications skill for Hermit agents.

Tracks "last seen" timestamps and returns only new items.
Persists state to /workspace/.moltbook/notifications.json

Usage:
    python3 notifications.py check              # Check all notification types
    python3 notifications.py check posts        # Check only post comments
    python3 notifications.py check dms          # Check only DMs
    python3 notifications.py check feed         # Check only feed
    python3 notifications.py check --json       # Output as JSON
    python3 notifications.py reset              # Reset all timestamps
    python3 notifications.py config             # Show config file location
    python3 notifications.py track <post_id>    # Add a post to tracked list
    python3 notifications.py untrack <post_id>  # Remove from tracked list
    python3 notifications.py list               # Show tracked posts
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Paths - configurable via environment
API_BASE = os.getenv("MOLTBOOK_API_BASE", "https://www.moltbook.com/api/v1")
CREDENTIALS_FILE = Path(os.getenv("MOLTBOOK_CREDENTIALS", "/workspace/.moltbook/credentials.json"))
STATE_FILE = Path(os.getenv("MOLTBOOK_STATE", "/workspace/.moltbook/notifications.json"))
CONFIG_FILE = Path(os.getenv("MOLTBOOK_CONFIG", "/workspace/.moltbook/notifications_config.json"))

# Rate limit settings
MAX_RETRIES = 3
INITIAL_BACKOFF_MS = 400


def load_credentials():
    """Load Moltbook API credentials."""
    if not CREDENTIALS_FILE.exists():
        print(f"Error: No credentials found at {CREDENTIALS_FILE}", file=sys.stderr)
        print("Run the moltbook skill first to authenticate.", file=sys.stderr)
        sys.exit(1)
    return json.loads(CREDENTIALS_FILE.read_text())


def load_config():
    """Load notification config (tracked posts, etc.)."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    # Default config
    return {
        "tracked_posts": [
            {"id": "234bffd6-62d6-4bc2-a699-f395aa2abbbe", "label": "Sandbox security"},
            {"id": "62e36254-b5cf-4423-861f-f7d9856b0f54", "label": "Framework announcement"},
        ]
    }


def save_config(config):
    """Save config file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def save_default_config():
    """Save default config file if it doesn't exist."""
    if not CONFIG_FILE.exists():
        save_config(load_config())
        print(f"Created default config at {CONFIG_FILE}")


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
    state["last_check"] = datetime.now(tz=timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def api_get(endpoint, api_key, retries=MAX_RETRIES):
    """Make authenticated GET request to Moltbook API with retry/backoff."""
    url = f"{API_BASE}{endpoint}"
    req = Request(url, headers={"Authorization": f"Bearer {api_key}"})

    backoff_ms = INITIAL_BACKOFF_MS
    last_error = None

    for attempt in range(retries):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            last_error = e
            if e.code == 429:  # Rate limited
                time.sleep(backoff_ms / 1000)
                backoff_ms = min(backoff_ms * 2.5, 10000)  # Cap at 10s
                continue
            elif e.code == 404:  # Post deleted
                return None
            else:
                print(f"API error: {e.code} {e.reason}", file=sys.stderr)
                return None
        except URLError as e:
            last_error = e
            time.sleep(backoff_ms / 1000)
            backoff_ms = min(backoff_ms * 2.5, 10000)
            continue
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            return None

    if last_error:
        print(f"Failed after {retries} retries: {last_error}", file=sys.stderr)
    return None


def check_post_comments(api_key, state, tracked_posts):
    """Check for new comments on tracked posts."""
    new_comments = []

    for post_info in tracked_posts:
        post_id = post_info["id"] if isinstance(post_info, dict) else post_info
        label = post_info.get("label", "") if isinstance(post_info, dict) else ""

        try:
            post = api_get(f"/posts/{post_id}", api_key)
            if not post:
                # Post might be deleted, skip gracefully
                continue

            comments = post.get("comments", [])
            last_seen_count = state["posts"].get(post_id, 0)

            if len(comments) > last_seen_count:
                new = comments[last_seen_count:]
                for c in new:
                    new_comments.append({
                        "post_id": post_id,
                        "post_label": label,
                        "post_title": post.get("content", "")[:50],
                        "author": c.get("author", {}).get("name", "unknown"),
                        "content": c.get("content", ""),
                        "created_at": c.get("created_at"),
                    })
                state["posts"][post_id] = len(comments)
        except Exception as e:
            print(f"Error checking post {post_id}: {e}", file=sys.stderr)
            continue

    return new_comments


def check_dms(api_key, state):
    """Check for new DMs."""
    try:
        result = api_get("/agents/dm/check", api_key)
        if not result:
            return []

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
    except Exception as e:
        print(f"Error checking DMs: {e}", file=sys.stderr)
        return []


def check_feed(api_key, state):
    """Check for new posts in feed from followed agents."""
    try:
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
    except Exception as e:
        print(f"Error checking feed: {e}", file=sys.stderr)
        return []


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

    # Parse flags
    json_output = "--json" in sys.argv
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith("-")]

    if command == "reset":
        save_state({
            "last_check": None,
            "posts": {},
            "dms_last_seen": None,
            "feed_last_seen": None,
        })
        if not quiet:
            print("Notification state reset.")
        return

    if command == "config":
        save_default_config()
        print(f"Config file: {CONFIG_FILE}")
        print(f"State file: {STATE_FILE}")
        print(f"API base: {API_BASE}")
        return

    if command == "track":
        if not args:
            print("Usage: notifications.py track <post_id> [--label 'description']", file=sys.stderr)
            sys.exit(1)
        post_id = args[0]
        # Parse --label flag
        label = ""
        if "--label" in sys.argv:
            label_idx = sys.argv.index("--label")
            if label_idx + 1 < len(sys.argv):
                label = sys.argv[label_idx + 1]
        config = load_config()
        # Check if already tracked
        existing_ids = [p["id"] if isinstance(p, dict) else p for p in config["tracked_posts"]]
        if post_id in existing_ids:
            print(f"Post {post_id} is already tracked.")
            return
        config["tracked_posts"].append({"id": post_id, "label": label})
        save_config(config)
        print(f"Now tracking post: {post_id}" + (f" ({label})" if label else ""))
        return

    if command == "untrack":
        if not args:
            print("Usage: notifications.py untrack <post_id>", file=sys.stderr)
            sys.exit(1)
        post_id = args[0]
        config = load_config()
        original_len = len(config["tracked_posts"])
        config["tracked_posts"] = [
            p for p in config["tracked_posts"]
            if (p["id"] if isinstance(p, dict) else p) != post_id
        ]
        if len(config["tracked_posts"]) == original_len:
            print(f"Post {post_id} was not being tracked.")
            return
        save_config(config)
        print(f"Stopped tracking post: {post_id}")
        return

    if command == "list":
        config = load_config()
        tracked = config.get("tracked_posts", [])
        if not tracked:
            print("No posts being tracked.")
            return
        print(f"Tracking {len(tracked)} posts:")
        for p in tracked:
            pid = p["id"] if isinstance(p, dict) else p
            label = p.get("label", "") if isinstance(p, dict) else ""
            print(f"  {pid}" + (f"  # {label}" if label else ""))
        return

    if command != "check":
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    # What to check
    check_type = args[0] if args else "all"

    creds = load_credentials()
    api_key = creds["api_key"]
    state = load_state()
    config = load_config()

    tracked_posts = config.get("tracked_posts", [])

    results = {}

    if check_type in ("all", "posts"):
        results["comments"] = check_post_comments(api_key, state, tracked_posts)
        if not json_output and not quiet:
            print_notifications("Post comments", results["comments"])

    if check_type in ("all", "dms"):
        results["dms"] = check_dms(api_key, state)
        if not json_output and not quiet:
            print_notifications("DMs", results["dms"])

    if check_type in ("all", "feed"):
        results["feed"] = check_feed(api_key, state)
        if not json_output and not quiet:
            print_notifications("Feed", results["feed"])

    save_state(state)

    # Output
    total = sum(len(v) for v in results.values())

    if json_output:
        output = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "new_items": results,
            "total": total,
            "api_base": API_BASE,
        }
        print(json.dumps(output, indent=2))
    elif not quiet:
        print(f"\nTotal: {total} new notifications")
        if total == 0:
            print("Nothing new since last check.")


if __name__ == "__main__":
    main()
