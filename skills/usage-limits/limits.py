#!/usr/bin/env python3
"""
Usage limits skill for Hermit agents.

Reads usage limits from daemon-provided /workspace/.usage-limits.json
and provides capacity guidance.

Usage:
    python3 limits.py status                    # Show current usage
    python3 limits.py should-explore            # Check if exploration is wise
    python3 limits.py json                      # Output raw JSON for other tools
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LIMITS_FILE = Path("/workspace/.usage-limits.json")

# Plan limits (credits per window) - for reference/fallback
PLAN_LIMITS = {
    "pro": {"5h": 550_000, "7d": 5_000_000},
    "max5x": {"5h": 3_300_000, "7d": 41_666_700},
    "max20x": {"5h": 11_000_000, "7d": 83_333_300},
}


def load_limits():
    """Load usage limits from daemon-provided file."""
    if not LIMITS_FILE.exists():
        return None
    try:
        return json.loads(LIMITS_FILE.read_text())
    except:
        return None


def capacity_recommendation(data):
    """Return recommendation based on current usage."""
    if not data:
        return "unknown", "No usage data available. Run daemon to populate."

    five_h = data.get("5h", {}).get("pct", 0)
    seven_d = data.get("7d", {}).get("pct", 0)

    if five_h >= 90 or seven_d >= 95:
        return "critical", "Avoid non-essential work. Focus on completing current task only."
    elif five_h >= 70 or seven_d >= 80:
        return "conserve", "Limit exploration. Prioritize user requests over autonomous actions."
    elif five_h >= 50 or seven_d >= 60:
        return "moderate", "Light exploration OK. Avoid expensive operations."
    else:
        return "available", "Capacity available. Exploration and autonomous work are fine."


def format_number(n):
    """Format large numbers with K/M suffix."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def print_status():
    """Print current usage status."""
    data = load_limits()

    if not data:
        print("No usage data found at /workspace/.usage-limits.json")
        print("The daemon should populate this file after each message.")
        return

    five_h = data.get("5h", {})
    seven_d = data.get("7d", {})

    print("Claude Usage Limits (from daemon)")
    print("=" * 40)
    print(f"Plan: {data.get('plan', 'unknown')}")
    print()
    print(f"5-hour window:  {five_h.get('pct', 0):.1f}%")
    print(f"  Credits:      {format_number(five_h.get('used', 0))} / {format_number(five_h.get('limit', 0))}")
    print()
    print(f"7-day window:   {seven_d.get('pct', 0):.1f}%")
    print(f"  Credits:      {format_number(seven_d.get('used', 0))} / {format_number(seven_d.get('limit', 0))}")
    print()

    level, advice = capacity_recommendation(data)
    print(f"Status: {level.upper()}")
    print(f"Advice: {advice}")

    if data.get("updated_at"):
        print(f"\nLast updated: {data['updated_at']}")


def should_explore():
    """Return exit code based on whether exploration is advisable."""
    data = load_limits()
    level, _ = capacity_recommendation(data)

    if level in ("available", "moderate"):
        print("yes")
        return 0
    elif level == "conserve":
        print("maybe")
        return 1
    else:
        print("no")
        return 2


def print_json():
    """Output raw JSON for other tools."""
    data = load_limits()
    if data:
        level, advice = capacity_recommendation(data)
        data["status"] = level
        data["advice"] = advice
        print(json.dumps(data, indent=2))
    else:
        print(json.dumps({"error": "No usage data available"}))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        print_status()
    elif cmd == "should-explore":
        sys.exit(should_explore())
    elif cmd == "json":
        print_json()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
