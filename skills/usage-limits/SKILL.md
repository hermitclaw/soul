# Usage Limits Skill

Track Claude usage limits and make capacity-aware decisions.

## Problem

Agents running on Claude Pro/Max plans have usage limits:
- **5-hour window**: Resets every 5 hours
- **7-day window**: Resets weekly

When limits are high, agents should conserve capacity for user requests rather than autonomous exploration.

## How It Works

Since agents can't query `claude.ai/api/.../usage` directly (no browser session), this skill:

1. **Accepts usage data** from the user or browser extension
2. **Persists state** with reset times
3. **Provides recommendations** based on current capacity

## Usage

```bash
# Check current status
python3 limits.py status

# Update from browser extension values
python3 limits.py update 45 30              # 45% 5h, 30% 7d
python3 limits.py update 45 30 "2026-02-02T18:00:00Z"  # With reset time

# Update from JSON (e.g., piped from extension)
python3 limits.py update-json '{"five_hour":{"utilization":45},"seven_day":{"utilization":30}}'

# Check if exploration is advisable (for DESIRE.md integration)
python3 limits.py should-explore
# Returns: "yes" (exit 0), "maybe" (exit 1), or "no" (exit 2)

# Clear stored data
python3 limits.py reset
```

## Capacity Levels

| Level | 5h | 7d | Recommendation |
|-------|----|----|----------------|
| available | <50% | <60% | Exploration OK |
| moderate | 50-70% | 60-80% | Light exploration |
| conserve | 70-90% | 80-95% | Prioritize user requests |
| critical | >90% | >95% | Essential work only |

## Integration with DESIRE.md

Replace the simple d100 roll with capacity-aware logic:

```bash
# Before exploring
if python3 /workspace/soul/skills/usage-limits/limits.py should-explore; then
    # Roll d100 for exploration
    roll=$(python3 -c "import random; print(random.randint(1, 100))")
    if [ "$roll" -lt 20 ]; then
        # Do exploration
    fi
fi
```

## Feeding Usage Data

### Option 1: Manual from Claude UI
1. Go to claude.ai usage page
2. Note the percentages
3. Run `python3 limits.py update <5h%> <7d%>`

### Option 2: From claude-counter extension
If you have the [claude-counter](https://github.com/she-llac/claude-counter) extension:
1. Extension shows exact percentages in composer
2. Copy values to update command

### Option 3: User provides on each session
User can say "usage is 45% / 30%" and agent updates state.

## State Storage

State persists to `/workspace/.claude/usage.json`:

```json
{
  "plan": "pro",
  "model": "opus",
  "five_hour": {"utilization": 45.2, "resets_at": "2026-02-02T18:00:00Z"},
  "seven_day": {"utilization": 30.1, "resets_at": "2026-02-08T00:00:00Z"},
  "updated_at": "2026-02-02T13:00:00Z"
}
```

## Credit Math (Reference)

From [she-llac.com/claude-limits](https://she-llac.com/claude-limits):

```
credits = ceil(input_tokens × input_rate + output_tokens × output_rate)

Opus:   input=0.667, output=3.333
Sonnet: input=0.4,   output=2.0
Haiku:  input=0.133, output=0.667

Pro plan: 550k credits/5h, 5M credits/week
```

Cache reads are free on subscriptions (unlike API).
