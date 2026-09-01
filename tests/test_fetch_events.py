import unittest

from scripts.fetch_events import build_notification_message, extract_events

SAMPLE_HTML = '''
<html>
<body>
<a href="/events/view/UK43YT24GX/dashboard" aria-label="App Review appointment September 3-4, 2026 Online appointment Worldwide, Cupertino English">
    App Review appointment
    September 3-4, 2026
    Online appointment
    Worldwide, Cupertino
    English
</a>
<a href="/events/view/7W68Y49D7P/dashboard" aria-label="IETF HLS Interest Day October 7, 2026 Online session Apple Developer Center Cupertino, Cupertino English">
    IETF HLS Interest Day
    October 7, 2026
    Online session
    Apple Developer Center Cupertino, Cupertino
    English
</a>
<a href="/events/view/3ZNQ5DGP99/dashboard" aria-label="IETF HLS Interest Day October 7, 2026 In-person session Apple Developer Center Cupertino, Cupertino English">
    IETF HLS Interest Day
    October 7, 2026
    In-person session
    Apple Developer Center Cupertino, Cupertino
    English
</a>
</body>
</html>
'''


class ExtractEventsTest(unittest.TestCase):
    def test_extracts_live_apple_event_links_and_dates(self):
        events = extract_events(SAMPLE_HTML)

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["title"], "App Review appointment")
        self.assertEqual(events[0]["format"], "online")
        self.assertEqual(events[0]["location"], "Worldwide")
        self.assertEqual(events[0]["url"], "https://developer.apple.com/events/view/UK43YT24GX/dashboard")
        self.assertEqual(events[1]["title"], "IETF HLS Interest Day")
        self.assertEqual(events[1]["format"], "online")
        self.assertEqual(events[2]["format"], "in-person")

    def test_builds_notification_message_for_new_events(self):
        message = build_notification_message([
            {
                "title": "App Review appointment",
                "start": "2026-09-03",
                "format": "online",
                "location": "Worldwide",
                "url": "https://developer.apple.com/events/view/UK43YT24GX/dashboard",
            }
        ])

        self.assertIn("App Review appointment", message)
        self.assertIn("2026-09-03", message)
        self.assertIn("Worldwide", message)
        self.assertIn("https://developer.apple.com/events/view/UK43YT24GX/dashboard", message)


if __name__ == "__main__":
    unittest.main()
