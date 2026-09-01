# Apple Developer Events Monitor

This project watches the public Apple Developer events page and alerts you when a new in-person or online event appears.

## What it does

- fetches the Apple Developer events page
- extracts event links and dates
- deduplicates entries already seen
- filters out configured blackout dates
- writes the current event list to `data/events.json`
- generates a calendar export in `calendar/apple-developer-events.ics`
- prints a simple summary when new events are found

## Local run

```bash
python scripts/fetch_events.py
```

## GitHub Actions

This repo includes a scheduled workflow in `.github/workflows/apple-events.yml`.

It runs every 6 hours and can also be started manually.

## Calendar import

Import or subscribe to the generated ICS file:

- `calendar/apple-developer-events.ics`

You can import this into Apple Calendar or Google Calendar.

## Blackout rules

Edit `config/blackout.json` to add date ranges you do not want to include in the events list.

Example:

```json
{
  "blackout": [
    {"start": "2026-09-10", "end": "2026-09-12"}
  ]
}
```

## Notes

This is intentionally simple and free. It uses the public Apple Developer events page and does not require a paid API or service.
