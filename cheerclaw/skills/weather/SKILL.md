---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: {"nanobot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

Two free services, no API keys needed.

## Important Guidelines

**Before using this skill:**

1. **Extract location**: If the user mentions a city/location (e.g., "What's the weather in Beijing?"), extract the location and query directly.
2. **Ask if missing**: If the user says "check weather" without specifying a location, you MUST ask: "Which city would you like to check the weather for?"
3. **Do NOT use example cities**: The examples below show placeholder cities for demonstration only. Never query any city unless the user explicitly requests it.

## wttr.in (primary)

Quick one-liner (replace `{location}` with the user-specified city):
```bash
curl -s "wttr.in/{location}?format=3"
# Example: curl -s "wttr.in/Beijing?format=3"
# Output: Beijing: ⛅️ +8°C
```

Compact format (replace `{location}` with user-specified city):
```bash
curl -s "wttr.in/{location}?format=%l:+%c+%t+%h+%w"
# Example: curl -s "wttr.in/Shanghai?format=%l:+%c+%t+%h+%w"
# Output: Shanghai: ⛅️ +15°C 65% ↙8km/h
```

Full forecast:
```bash
curl -s "wttr.in/{location}?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:
- URL-encode spaces: `wttr.in/New+York` or `wttr.in/New%20York`
- Airport codes: `wttr.in/JFK`, `wttr.in/PEK`
- Units: `?m` (metric) `?u` (USCS)
- Today only: `?1` · Current only: `?0`
- PNG: `curl -s "wttr.in/{location}.png" -o /tmp/weather.png`

## Open-Meteo (fallback, JSON)

Free, no key, good for programmatic use. First get coordinates for the user-specified city, then query:
```bash
# Example for Beijing (latitude=39.9&longitude=116.4)
curl -s "https://api.open-meteo.com/v1/forecast?latitude=39.9&longitude=116.4&current_weather=true"
```

Returns JSON with temp, windspeed, weathercode.

Docs: https://open-meteo.com/en/docs
