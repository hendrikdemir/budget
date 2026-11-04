"""The update check: when the page says a newer Budget is available. GitHub is never asked:
the release comes from a made-up file (the same way BUDGET_RELEASES_URL works for testing by hand)."""
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from app import api, db, updates

from .base import AppTest


class UpdateCheck(AppTest):
    def setUp(self):
        super().setUp()
        updates._cache.update(until=0, release=None)
        self.release_file = Path(self.folder.name) / "release.json"
        env = mock.patch.dict(os.environ, {"BUDGET_RELEASES_URL": self.release_file.as_uri()})
        env.start()
        self.addCleanup(env.stop)
        version = mock.patch.object(updates, "VERSION", "1.0.0")
        version.start()
        self.addCleanup(version.stop)

    def publish(self, tag, **extra):
        release = {"tag_name": tag, "html_url": f"https://github.com/hendrikdemir/budget/releases/tag/{tag}",
                   "body": "Fixes and improvements.",
                   "assets": [{"name": "Budget.dmg", "browser_download_url": "https://github.com/hendrikdemir/budget/releases/download/x/Budget.dmg"}],
                   **extra}
        self.release_file.write_text(json.dumps(release))
        updates._cache.update(until=0, release=None)

    def check(self):
        return api.check_update(self.conn, None, None, {})

    def test_newer_release(self):
        self.publish("v1.2.0")
        result = self.check()
        self.assertTrue(result["available"])
        self.assertEqual((result["version"], result["current"]), ("1.2.0", "1.0.0"))
        self.assertTrue(result["download"].endswith("/Budget.dmg"))
        self.assertFalse(result["skipped"])

    def test_same_or_older_release(self):
        for tag in ("v1.0.0", "1.0", "v0.9.3"):
            self.publish(tag)
            result = self.check()
            self.assertFalse(result["available"], tag)
            self.assertTrue(result["checked"], tag)  # the page says "you have the latest version"

    def test_versions_compare_as_numbers(self):
        self.publish("v1.10.0")
        with mock.patch.object(updates, "VERSION", "1.9.0"):
            self.assertTrue(self.check()["available"])

    def test_prereleases_drafts_and_odd_tags_are_ignored(self):
        for tag, extra in (("v2.0.0", {"prerelease": True}), ("v2.0.0", {"draft": True}), ("v2.0.0-beta", {}), ("latest", {})):
            self.publish(tag, **extra)
            self.assertFalse(self.check()["available"], (tag, extra))

    def test_no_answer_or_nonsense(self):
        self.assertEqual(self.check(), {"available": False, "checked": False})  # file missing, like being offline
        self.release_file.write_text("<html>not json</html>")
        updates._cache.update(until=0, release=None)
        self.assertFalse(self.check()["available"])

    def test_links_only_go_to_github(self):
        self.publish("v1.2.0", html_url="https://example.com/evil",
                     assets=[{"name": "Budget.dmg", "browser_download_url": "https://example.com/Budget.dmg"}])
        result = self.check()
        self.assertEqual(result["page"], updates.RELEASES_PAGE)
        self.assertEqual(result["download"], updates.RELEASES_PAGE)

    def test_skipped_version_and_a_later_one(self):
        self.publish("v1.2.0")
        api.save_settings(self.conn, None, {"skipped_version": "1.2.0"}, None)
        self.assertTrue(self.check()["skipped"])
        self.publish("v1.3.0")
        self.assertFalse(self.check()["skipped"])

    def test_turned_off(self):
        self.publish("v1.2.0")
        api.save_settings(self.conn, None, {"update_check": "off"}, None)
        with mock.patch.object(updates, "fetch_release") as fetch:
            self.assertFalse(self.check()["available"])
            fetch.assert_not_called()

    def test_asks_at_most_once_a_day(self):
        self.publish("v1.2.0")
        self.check()
        self.release_file.write_text(json.dumps({"tag_name": "v9.0.0"}))  # cache not reset
        self.assertEqual(self.check()["version"], "1.2.0")


class NewerData(AppTest):
    def test_an_older_budget_refuses_newer_data(self):
        self.conn.execute(f"PRAGMA user_version = {len(db.MIGRATIONS) + 1}")
        self.conn.commit()
        with self.assertRaises(db.TooNewError):
            db.migrate()
