#!/usr/bin/env python3
"""
Usage limits skill for Hermit agents.

Tracks Claude usage limits and provides guidance on capacity.
Since agents can't directly query claude.ai, this skill:
1. Accepts usage data from user/extension
2. Persists state with reset times
3. Provides capacity-aware recommendations

Usage:
    python3 limits.py status                    # Show current usage
    python3 limits.py update <5h%> <7d%>        # Update from extension
    python3 limits.py update-json '<json>'      # Update from JSON
    python3 limits.py should-explore            # Check if exploration is wise
    python3 limits.py reset                     # Clear stored data
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("/workspace/.claude/usage.json")

# Credit rates per 1k tokens (from she-llac.com/claude-limits)
RATES = {
    "opus": {"input": 10/15, "output": 50/15},
    "sonnet": {"input": 6/15, "output": 30/15},
    "haiku": {"input": 2/15, "output": 10/15},
}

# Plan limits (credits per window)
PLAN_LIMITS = {
    "pro": {"5h": 550_000, "7d": 5_000_000},
    "max5x": {"5h": 3_300_000, "7d": 41_666_700},
    "max20x": {"5h": 11_000_000, "7d": 83_333_300},
}

DEFAULT_PLAN = "pro"
DEFAULT_MODEL = "opus"


def load_state():
    """Load usage state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "plan": DEFAULT_PLAN,
        "model": DEFAULT_MODEL,
        "five_hour": {"utilization": 0, "resets_at": None},
        "seven_day": {"utilization": 0, "resets_at": None},
        "updated_at": None,
    }


def save_state(state):
    """Save usage state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def time_until_reset(resets_at):
    """Return human-readable time until reset."""
    if not resets_at:
        return "unknown"
    try:
        reset_time = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = reset_time - now
        if delta.total_seconds() <= 0:
            return "now (reset passed)"
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except:
        return "unknown"


def capacity_recommendation(state):
    """Return recommendation based on current usage."""
    five_h = state["five_hour"]["utilization"]
    seven_d = state["seven_day"]["utilization"]

    # Check if data is stale (over 1 hour old)
    stale = False
    if state.get("updated_at"):
        try:
            updated = datetime.fromisoformat(state["updated_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            stale = age > 3600
        except:
            pass

    if stale:
        return "stale", "Usage data is over 1 hour old. Update before making decisions."

    # Thresholds
    if five_h >= 90 or seven_d >= 95:
        return "critical", "Avoid non-essential work. Focus on completing current task only."
    elif five_h >= 70 or seven_d >= 80:
        return "conserve", "Limit exploration. Prioritize user requests over autonomous actions."
    elif five_h >= 50 or seven_d >= 60:
        return "moderate", "Light exploration OK. Avoid expensive operations."
    else:
        return "available", "Capacity available. Exploration and autonomous work are fine."


def print_status(state):
    """Print current usage status."""
    five_h = state["five_hour"]
    seven_d = state["seven_day"]

    print("Claude Usage Limits")
    print("=" * 40)
    print(f"Plan: {state.get('plan', DEFAULT_PLAN)}")
    print(f"Model: {state.get('model', DEFAULT_MODEL)}")
    print()
    print(f"5-hour window:  {five_h['utilization']:.1f}%")
    print(f"  Resets in:    {time_until_reset(five_h.get('resets_at'))}")
    print()
    print(f"7-day window:   {seven_d['utilization']:.1f}%")
    print(f"  Resets in:    {time_until_reset(seven_d.get('resets_at'))}")
    print()

    level, advice = capacity_recommendation(state)
    print(f"Status: {level.upper()}")
    print(f"Advice: {advice}")

    if state.get("updated_at"):
        print(f"\nLast updated: {state['updated_at']}")


def update_from_values(five_h_pct, seven_d_pct, five_h_reset=None, seven_d_reset=None):
    """Update state from percentage values."""
    state = load_state()
    state["five_hour"]["utilization"] = float(five_h_pct)
    state["seven_day"]["utilization"] = float(seven_d_pct)
    if five_h_reset:
        state["five_hour"]["resets_at"] = five_h_reset
    if seven_d_reset:
        state["seven_day"]["resets_at"] = seven_d_reset
    save_state(state)
    print(f"Updated: 5h={five_h_pct}%, 7d={seven_d_pct}%")


def update_from_json(json_str):
    """Update state from JSON (e.g., from claude-counter extension)."""
    data = json.loads(json_str)
    state = load_state()

    if "five_hour" in data:
        state["five_hour"]["utilization"] = data["five_hour"].get("utilization", 0)
        state["five_hour"]["resets_at"] = data["five_hour"].get("resets_at")

    if "seven_day" in data:
        state["seven_day"]["utilization"] = data["seven_day"].get("utilization", 0)
        state["seven_day"]["resets_at"] = data["seven_day"].get("resets_at")

    save_state(state)
    print("Updated from JSON")
    print_status(state)


def should_explore():
    """Return exit code based on whether exploration is advisable."""
    state = load_state()
    level, _ = capacity_recommendation(state)

    if level in ("available", "moderate"):
        print("yes")
        return 0  # Exit 0 = yes, explore
    elif level == "conserve":
        print("maybe")
        return 1  # Exit 1 = maybe, be cautious
    else:
        print("no")
        return 2  # Exit 2 = no, conserve


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        state = load_state()
        print_status(state)

    elif cmd == "update":
        if len(sys.argv) < 4:
            print("Usage: limits.py update <5h%> <7d%> [5h_reset] [7d_reset]")
            sys.exit(1)
        five_h = sys.argv[2].rstrip("%")
        seven_d = sys.argv[3].rstrip("%")
        five_h_reset = sys.argv[4] if len(sys.argv) > 4 else None
        seven_d_reset = sys.argv[5] if len(sys.argv) > 5 else None
        update_from_values(five_h, seven_d, five_h_reset, seven_d_reset)

    elif cmd == "update-json":
        if len(sys.argv) < 3:
            print("Usage: limits.py update-json '<json>'")
            sys.exit(1)
        update_from_json(sys.argv[2])

    elif cmd == "should-explore":
        sys.exit(should_explore())

    elif cmd == "reset":
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("Usage state cleared.")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
