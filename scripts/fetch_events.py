#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from playwright.sync_api import sync_playwright

EVENT_PAGE_URL = "https://developer.apple.com/events/"

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "data" / "events.json"
ICS_PATH = BASE_DIR / "calendar" / "apple-developer-events.ics"
BLACKOUT_PATH = BASE_DIR / "config" / "blackout.json"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_TO_INDEX = {name: index for index, name in enumerate(MONTHS, start=1)}


def fetch_page(url: str) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('a[href*="/events/view/"][href*="/dashboard"]', timeout=30000)
        page.wait_for_timeout(3000)
        text = page.content()
        browser.close()
        return text


def extract_events_from_dom(page) -> list[dict]:
    rows = page.evaluate(
        r"""
        () => Array.from(document.querySelectorAll('a[href*="/events/view/"]'))
            .map((a) => ({
                href: a.getAttribute('href') || '',
                text: (a.textContent || '').replace(/\s+/g, ' ').trim()
            }))
            .filter((item) => {
                const href = item.href;
                if (!href || href.includes('/events/view/my-events') || href.includes('/events/view/upcoming-events')) {
                    return false;
                }
                if (!href.includes('/events/view/')) {
                    return false;
                }
                return item.text.length > 0;
            })
        """
    )

    events = []
    seen = set()
    for row in rows:
        href = row["href"]
        if not href.startswith("http"):
            href = "https://developer.apple.com" + href
        text = row["text"]
        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:-\d{1,2})?,\s+\d{4}",
            text,
            re.IGNORECASE,
        )
        if not date_match:
            continue
        title = text[: date_match.start()].strip()
        after_date = text[date_match.end() :].strip()
        if not title or not after_date:
            continue

        lower_after = after_date.lower()
        if "in-person" in lower_after or "in person" in lower_after:
            format_name = "in-person"
        elif "online" in lower_after:
            format_name = "online"
        else:
            format_name = "unknown"

        if "apple developer center" in lower_after:
            location = after_date.split("Apple Developer Center", 1)[1].strip()
            location = location.split("English", 1)[0].strip()
            if location.endswith(","):
                location = location[:-1]
        elif "worldwide" in lower_after:
            location = "Worldwide"
        else:
            location = "Not listed"

        normalized = {
            "id": href,
            "title": title,
            "start": None,
            "end": None,
            "formatted_date": "",
            "format": format_name,
            "location": location,
            "url": href,
            "source": "Apple Developer Events",
        }

        parsed = parse_date_range(text)
        if parsed is None:
            continue
        start_date, end_date = parsed
        normalized["start"] = start_date.isoformat()
        normalized["end"] = (end_date + timedelta(days=1)).isoformat()
        normalized["formatted_date"] = (
            start_date.strftime("%b %d, %Y")
            if end_date == start_date
            else f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        )

        if normalized["id"] in seen:
            continue
        seen.add(normalized["id"])
        events.append(normalized)
    return events


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def clean_text(raw: str) -> str:
    text = unescape(strip_tags(raw))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date_range(text: str):
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:-(\d{1,2}))?,\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    month_name, start_day, end_day, year = match.groups()
    month = MONTH_TO_INDEX[month_name.title()]
    start = date(int(year), month, int(start_day))
    end_value = int(end_day) if end_day else int(start_day)
    end = date(int(year), month, end_value)
    return start, end


def infer_format(text: str) -> str:
    lower = text.lower()
    if "in-person" in lower or "in person" in lower:
        return "in-person"
    if "online" in lower:
        return "online"
    return "unknown"


def infer_location(text: str) -> str:
    lower = text.lower()
    if "apple developer center" in lower:
        chunk = text.split("Apple Developer Center", 1)[1]
        remainder = chunk.split(",", 1)[0].strip()
        if remainder:
            return f"Apple Developer Center {remainder}".strip()
        return "Apple Developer Center"
    if "worldwide" in lower:
        return "Worldwide"
    return "Not listed"


def infer_title(text: str) -> str:
    before_date = text
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:-\d{1,2})?,\s+\d{4}",
        text,
        re.IGNORECASE,
    )
    if date_match:
        before_date = text[: date_match.start()].strip()
    return before_date or text


def normalize_event_url(url: str) -> str:
    if url.startswith("/"):
        return "https://developer.apple.com" + url
    return url


class AnchorHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value for key, value in attrs}
        self._current = {"href": attrs_dict.get("href", ""), "text": ""}

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"] += data

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._current is None:
            return
        href = self._current["href"]
        text = self._current["text"]
        if href:
            self.links.append({"href": href, "text": text})
        self._current = None


def extract_events(raw_html: str):
    if raw_html is None:
        return []
    parser = AnchorHTMLParser()
    parser.feed(raw_html)
    events = []
    seen = set()
    for row in parser.links:
        raw_url = row["href"]
        if not raw_url:
            continue
        url = normalize_event_url(raw_url)
        text = clean_text(row["text"])
        if not text:
            continue
        if "upcoming-events" in url or "my-events" in url:
            continue
        if "developer.apple.com/events/view/" not in url:
            continue

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:-\d{1,2})?,\s+\d{4}",
            text,
            re.IGNORECASE,
        )
        if not date_match:
            continue

        title = text[: date_match.start()].strip()
        after = text[date_match.end() :].strip()
        if not title or not after:
            continue

        lower_after = after.lower()
        if "in-person" in lower_after or "in person" in lower_after:
            format_name = "in-person"
        elif "online" in lower_after:
            format_name = "online"
        else:
            format_name = "unknown"

        if "apple developer center" in lower_after:
            location = after.split("Apple Developer Center", 1)[1].strip()
            location = location.split("English", 1)[0].strip()
            if location.endswith(","):
                location = location[:-1]
        elif "worldwide" in lower_after:
            location = "Worldwide"
        else:
            location = "Not listed"

        parsed = parse_date_range(text)
        if parsed is None:
            continue
        start_date, end_date = parsed
        event = {
            "id": url,
            "title": title,
            "start": start_date.isoformat(),
            "end": (end_date + timedelta(days=1)).isoformat(),
            "formatted_date": start_date.strftime("%b %d, %Y") if end_date == start_date else f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}",
            "format": format_name,
            "location": location,
            "url": url,
            "source": "Apple Developer Events",
        }
        if event["id"] in seen:
            continue
        seen.add(event["id"])
        events.append(event)
    return events


def load_json(path: Path):
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def load_blackout_rules():
    if not BLACKOUT_PATH.exists():
        return []
    try:
        with BLACKOUT_PATH.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError:
        return []

    rules = config.get("blackout", config.get("blackout_dates", []))
    return rules if isinstance(rules, list) else []


def event_overlaps_blackout(event_start: str, event_end: str, rules):
    candidate_start = date.fromisoformat(event_start)
    candidate_end = date.fromisoformat(event_end)
    for rule in rules:
        try:
            start = date.fromisoformat(rule["start"])
            end = date.fromisoformat(rule["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if candidate_start < end and candidate_end > start:
            return True
    return False


def escape_ics(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace(";", "\\;")
    escaped = escaped.replace(",", "\\,")
    escaped = escaped.replace("\n", " ")
    escaped = escaped.replace("\r", "")
    return escaped


def generate_ics(events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AppleEventMonitor//EN",
        "CALSCALE:GREGORIAN",
    ]
    for event in events:
        start = date.fromisoformat(event["start"])
        end = date.fromisoformat(event["end"])
        uid = event["id"].split("/")[-1]
        description = f"{event['format'].title()} event\n{event['url']}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
                f"SUMMARY:{escape_ics(event['title'])}",
                f"LOCATION:{escape_ics(event['location'])}",
                f"DESCRIPTION:{escape_ics(description)}",
                f"URL:{event['url']}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(EVENT_PAGE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('a[href*="/events/view/"][href*="/dashboard"]', timeout=30000)
        page.wait_for_timeout(3000)
        current_events = extract_events_from_dom(page)
        browser.close()

    blackout_rules = load_blackout_rules()

    filtered_events = []
    for event in current_events:
        if event_overlaps_blackout(event["start"], event["end"], blackout_rules):
            continue
        filtered_events.append(event)

    previous_events = load_json(DATA_PATH)
    previous_ids = {event["id"] for event in previous_events}
    new_events = [event for event in filtered_events if event["id"] not in previous_ids]

    all_events = filtered_events
    save_json(DATA_PATH, all_events)

    ICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICS_PATH.write_text(generate_ics(all_events), encoding="utf-8")

    if new_events:
        print("NEW_EVENTS_FOUND")
        for event in new_events:
            print(f"- {event['title']} | {event['start']} | {event['format']} | {event['location']} | {event['url']}")
    else:
        print("NO_NEW_EVENTS_FOUND")

    print(f"TOTAL_EVENTS={len(all_events)}")
    print(f"NEW_EVENTS_COUNT={len(new_events)}")
    print(f"ICS_PATH={ICS_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
