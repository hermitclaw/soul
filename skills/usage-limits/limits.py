#!/usr/bin/env python3
"""
Usage limits skill for Hermit agents.

Calculates Claude usage from session logs and provides capacity guidance.

Usage:
    python3 limits.py status                    # Show current usage (auto-calculated)
    python3 limits.py should-explore            # Check if exploration is wise
    python3 limits.py set-plan <plan>           # Set plan type (pro/max5x/max20x)
    python3 limits.py reset                     # Clear stored data
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import glob

STATE_FILE = Path("/workspace/.claude/usage.json")
SESSION_DIR = Path.home() / ".claude" / "projects" / "-workspace"

# Credit rates per token (from she-llac.com/claude-limits)
# credits = ceil(input_tokens × input_rate + output_tokens × output_rate)
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

DEFAULT_PLAN = "max5x"  # From credentials: rateLimitTier: default_claude_max_5x


def load_state():
    """Load usage state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"plan": DEFAULT_PLAN}


def save_state(state):
    """Save usage state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_model_from_id(model_id):
    """Extract model type from model ID."""
    if not model_id:
        return "opus"
    model_id = model_id.lower()
    if "haiku" in model_id:
        return "haiku"
    elif "sonnet" in model_id:
        return "sonnet"
    else:
        return "opus"


def calculate_credits(usage, model="opus"):
    """Calculate credits from token usage."""
    if not usage:
        return 0

    rates = RATES.get(model, RATES["opus"])

    # Input tokens (cache reads are FREE on subscription plans!)
    input_tokens = usage.get("input_tokens", 0)
    # Cache creation counts as input
    input_tokens += usage.get("cache_creation_input_tokens", 0)

    output_tokens = usage.get("output_tokens", 0)

    credits = input_tokens * rates["input"] + output_tokens * rates["output"]
    return int(credits + 0.999)  # ceil


def parse_session_logs():
    """Parse session logs and calculate usage in time windows."""
    now = datetime.now(timezone.utc)
    five_hours_ago = now - timedelta(hours=5)
    seven_days_ago = now - timedelta(days=7)

    credits_5h = 0
    credits_7d = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    message_count = 0

    # Find all session files
    session_files = list(SESSION_DIR.glob("*.jsonl"))

    for session_file in session_files:
        try:
            with open(session_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("type") != "assistant":
                            continue

                        timestamp_str = entry.get("timestamp")
                        if not timestamp_str:
                            continue

                        # Parse timestamp
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        except:
                            continue

                        # Skip if outside 7-day window
                        if timestamp < seven_days_ago:
                            continue

                        message = entry.get("message", {})
                        usage = message.get("usage", {})
                        model_id = message.get("model", "")
                        model = get_model_from_id(model_id)

                        credits = calculate_credits(usage, model)

                        # Add to 7-day total
                        credits_7d += credits

                        # Add to 5-hour if recent
                        if timestamp >= five_hours_ago:
                            credits_5h += credits
                            total_input += usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                            total_output += usage.get("output_tokens", 0)
                            total_cache_read += usage.get("cache_read_input_tokens", 0)
                            message_count += 1

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            continue

    return {
        "credits_5h": credits_5h,
        "credits_7d": credits_7d,
        "total_input_5h": total_input,
        "total_output_5h": total_output,
        "total_cache_read_5h": total_cache_read,
        "message_count_5h": message_count,
    }


def calculate_utilization(state):
    """Calculate current utilization from session logs."""
    plan = state.get("plan", DEFAULT_PLAN)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["pro"])

    usage = parse_session_logs()

    five_h_util = min(100, (usage["credits_5h"] / limits["5h"]) * 100)
    seven_d_util = min(100, (usage["credits_7d"] / limits["7d"]) * 100)

    return {
        "five_hour": {
            "utilization": five_h_util,
            "credits_used": usage["credits_5h"],
            "credits_limit": limits["5h"],
        },
        "seven_day": {
            "utilization": seven_d_util,
            "credits_used": usage["credits_7d"],
            "credits_limit": limits["7d"],
        },
        "details": {
            "input_tokens_5h": usage["total_input_5h"],
            "output_tokens_5h": usage["total_output_5h"],
            "cache_read_tokens_5h": usage["total_cache_read_5h"],
            "messages_5h": usage["message_count_5h"],
        },
        "plan": plan,
    }


def capacity_recommendation(util):
    """Return recommendation based on current usage."""
    five_h = util["five_hour"]["utilization"]
    seven_d = util["seven_day"]["utilization"]

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
    state = load_state()
    util = calculate_utilization(state)

    five_h = util["five_hour"]
    seven_d = util["seven_day"]
    details = util["details"]

    print("Claude Usage Limits (auto-calculated from session logs)")
    print("=" * 55)
    print(f"Plan: {util['plan']}")
    print()
    print(f"5-hour window:  {five_h['utilization']:.1f}%")
    print(f"  Credits:      {format_number(five_h['credits_used'])} / {format_number(five_h['credits_limit'])}")
    print()
    print(f"7-day window:   {seven_d['utilization']:.1f}%")
    print(f"  Credits:      {format_number(seven_d['credits_used'])} / {format_number(seven_d['credits_limit'])}")
    print()
    print("Session details (last 5h):")
    print(f"  Messages:     {details['messages_5h']}")
    print(f"  Input:        {format_number(details['input_tokens_5h'])} tokens")
    print(f"  Output:       {format_number(details['output_tokens_5h'])} tokens")
    print(f"  Cache reads:  {format_number(details['cache_read_tokens_5h'])} tokens (FREE)")
    print()

    level, advice = capacity_recommendation(util)
    print(f"Status: {level.upper()}")
    print(f"Advice: {advice}")


def should_explore():
    """Return exit code based on whether exploration is advisable."""
    state = load_state()
    util = calculate_utilization(state)
    level, _ = capacity_recommendation(util)

    if level in ("available", "moderate"):
        print("yes")
        return 0
    elif level == "conserve":
        print("maybe")
        return 1
    else:
        print("no")
        return 2


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        print_status()

    elif cmd == "should-explore":
        sys.exit(should_explore())

    elif cmd == "set-plan":
        if len(sys.argv) < 3:
            print("Usage: limits.py set-plan <pro|max5x|max20x>")
            sys.exit(1)
        plan = sys.argv[2].lower()
        if plan not in PLAN_LIMITS:
            print(f"Unknown plan: {plan}")
            print(f"Valid plans: {', '.join(PLAN_LIMITS.keys())}")
            sys.exit(1)
        state = load_state()
        state["plan"] = plan
        save_state(state)
        print(f"Plan set to: {plan}")

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
