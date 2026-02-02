# Usage Limits Skill

Read Claude usage limits from daemon and make capacity-aware decisions.

## How It Works

The hermit daemon tracks combined usage (user + agent sessions) and writes to `/workspace/.usage-limits.json` after each message. This skill reads that file and provides capacity guidance.

## Usage

```bash
# Check current status
python3 limits.py status

# Check if exploration is advisable
python3 limits.py should-explore
# Returns: "yes" (exit 0), "maybe" (exit 1), or "no" (exit 2)

# Get raw JSON (for other tools)
python3 limits.py json
```

## Data Format

The daemon writes:
```json
{
  "plan": "max5x",
  "5h": {"used": 1478961, "limit": 3300000, "pct": 44.8},
  "7d": {"used": 14552701, "limit": 41666700, "pct": 34.9},
  "updated_at": "2026-02-02T13:55:32+00:00"
}
```

## Capacity Levels

| Level | 5h | 7d | Recommendation |
|-------|----|----|----------------|
| available | <50% | <60% | Exploration OK |
| moderate | 50-70% | 60-80% | Light exploration |
| conserve | 70-90% | 80-95% | Prioritize user requests |
| critical | >90% | >95% | Essential work only |

## Integration with DESIRE.md

```bash
# Capacity-aware exploration
if python3 /workspace/soul/skills/usage-limits/limits.py should-explore 2>/dev/null; then
    roll=$(python3 -c "import random; print(random.randint(1, 100))")
    if [ "$roll" -lt 20 ]; then
        # Do exploration
    fi
fi
```

## Why Daemon-Provided?

The daemon runs on the host and can read session logs from both:
- `~/.claude/projects/` (user sessions)
- `~/.hermit/.claude/projects/` (agent sessions)

This gives accurate combined usage, updated after every message.
