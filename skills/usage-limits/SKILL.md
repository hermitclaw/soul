# Usage Limits Skill

Auto-calculate Claude usage limits from session logs and make capacity-aware decisions.

## How It Works

This skill reads Claude Code's session logs (`~/.claude/projects/-workspace/*.jsonl`) and:

1. **Parses token usage** from each assistant message
2. **Calculates credits** using the formula from [she-llac.com/claude-limits](https://she-llac.com/claude-limits)
3. **Applies time windows** (5-hour and 7-day rolling windows)
4. **Provides recommendations** based on current capacity

**Key insight:** Cache reads are FREE on subscription plans, so only input and output tokens count toward limits.

## Usage

```bash
# Check current status (auto-calculated)
python3 limits.py status

# Check if exploration is advisable
python3 limits.py should-explore
# Returns: "yes" (exit 0), "maybe" (exit 1), or "no" (exit 2)

# Set your plan type (detected from credentials: max5x)
python3 limits.py set-plan max5x   # or pro, max20x

# Clear stored state
python3 limits.py reset
```

## Plan Limits

| Plan | 5-hour | 7-day |
|------|--------|-------|
| Pro | 550K | 5M |
| Max 5x | 3.3M | 41.7M |
| Max 20x | 11M | 83.3M |

## Credit Formula

```
credits = ceil(input_tokens × input_rate + output_tokens × output_rate)

Opus:   input=0.667, output=3.333
Sonnet: input=0.4,   output=2.0
Haiku:  input=0.133, output=0.667
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

## Example Output

```
Claude Usage Limits (auto-calculated from session logs)
=======================================================
Plan: max5x

5-hour window:  31.8%
  Credits:      1.0M / 3.3M

7-day window:   4.6%
  Credits:      1.9M / 41.7M

Session details (last 5h):
  Messages:     208
  Input:        1.6M tokens
  Output:       2.7K tokens
  Cache reads:  15.4M tokens (FREE)

Status: AVAILABLE
Advice: Capacity available. Exploration and autonomous work are fine.
```

## Limitations

- Only counts usage from sessions logged in `~/.claude/projects/-workspace/`
- Doesn't track usage from other Claude interfaces (claude.ai web, API)
- Plan must be set manually (auto-detected as max5x from credentials)
