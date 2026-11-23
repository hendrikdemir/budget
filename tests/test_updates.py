"""The update check: when the page says a newer Budget is available. GitHub is never asked:
the release comes from a made-up file (the same way BUDGET_RELEASES_URL works for testing by hand)."""
import json
import os
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
        self.on("mac")

    def on(self, platform):
        patch = mock.patch.object(updates, "PLATFORM", platform)
        patch.start()
        self.addCleanup(patch.stop)
        updates._cache.update(until=0, release=None)

    @staticmethod
    def release(tag, files=("Budget.dmg", "Budget-setup.exe")):
        return {"tag_name": tag, "html_url": f"https://github.com/hendrikdemir/budget/releases/tag/{tag}",
                "body": f"What's new in {tag}.",
                "assets": [{"name": f, "browser_download_url": f"https://github.com/hendrikdemir/budget/releases/download/{tag}/{f}"}
                           for f in files]}

    def publish_list(self, *releases):
        self.release_file.write_text(json.dumps(list(releases)))
        updates._cache.update(until=0, release=None)

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

    def test_each_system_gets_its_own_download(self):
        self.publish_list(self.release("v1.2.0"))
        self.assertTrue(self.check()["download"].endswith("/v1.2.0/Budget.dmg"))
        self.assertEqual(self.check()["platform"], "mac")
        self.on("windows")
        result = self.check()
        self.assertTrue(result["download"].endswith("/v1.2.0/Budget-setup.exe"))
        self.assertEqual(result["platform"], "windows")

    def test_a_release_for_one_system_isnt_offered_to_the_other(self):
        self.publish_list(self.release("v1.2.0", files=["Budget-setup.exe"]))  # a Windows-only fix
        self.assertEqual(self.check(), {"available": False, "checked": True})  # Mac: "you have the latest version"
        self.on("windows")
        self.assertTrue(self.check()["available"])
        self.publish_list(self.release("v1.2.0", files=["Budget.dmg"]))  # and the other way around
        self.assertEqual(self.check(), {"available": False, "checked": True})
        self.on("mac")
        self.assertTrue(self.check()["available"])

    def test_the_newest_release_for_this_system_counts(self):
        # GitHub lists the newest first: 1.3.0 is Windows-only, so a Mac gets 1.2.0.
        self.publish_list(self.release("v1.3.0", files=["Budget-setup.exe"]), self.release("v1.2.0"),
                          self.release("v1.1.0", files=["Budget.dmg"]))
        result = self.check()
        self.assertEqual(result["version"], "1.2.0")
        # Every newer release's notes, newest first, so a big release isn't hidden by a fix after it.
        self.assertEqual(result["changes"], [{"version": "1.2.0", "notes": "What's new in v1.2.0."},
                                             {"version": "1.1.0", "notes": "What's new in v1.1.0."}])
        self.on("windows")
        self.assertEqual(self.check()["version"], "1.3.0")

    def test_shows_a_few_releases_and_counts_the_rest(self):
        self.publish_list(*(self.release(f"v1.{n}.0") for n in range(9, 0, -1)), self.release("v0.1.0"))
        result = self.check()
        self.assertEqual([c["version"] for c in result["changes"]], [f"1.{n}.0" for n in range(9, 3, -1)])
        self.assertEqual(result["more"], 3)  # 1.3, 1.2 and 1.1; 0.1.0 is older than this version

    def test_drafts_and_prereleases_in_the_list_are_skipped(self):
        self.publish_list({**self.release("v2.0.0"), "draft": True}, {**self.release("v1.5.0"), "prerelease": True},
                          self.release("v1.2.0"))
        self.assertEqual(self.check()["version"], "1.2.0")

    def test_a_similar_file_name_doesnt_count(self):
        self.publish_list(self.release("v1.2.0", files=["Budget-1.2.0.dmg.sha256", "Budget-setup.exe.zip"]))
        self.assertFalse(self.check()["available"])
        self.on("windows")
        self.assertFalse(self.check()["available"])


class NewerData(AppTest):
    def test_an_older_budget_refuses_newer_data(self):
        self.conn.execute(f"PRAGMA user_version = {len(db.MIGRATIONS) + 1}")
        self.conn.commit()
        with self.assertRaises(db.TooNewError):
            db.migrate()

    def test_an_older_budget_opens_data_with_only_changes_it_can_live_with(self):
        # A newer Budget ran two more migrations that older versions can live with.
        self.conn.execute("PRAGMA user_version = ?".replace("?", str(db.needed_by_older())))
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('migrations', ?)",
                          (str(len(db.MIGRATIONS) + 2),))
        self.conn.commit()
        db.migrate()
        self.assertEqual(self.conn.execute("SELECT value FROM settings WHERE key = 'migrations'").fetchone()[0],
                         str(len(db.MIGRATIONS) + 2))


class Migrations(AppTest):
    def test_harmless_migrations_dont_lock_out_older_versions(self):
        # Budget 0.10 knows 2 migrations; the mode setting (3) doesn't stop it.
        self.assertEqual(db.needed_by_older(), 2)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_data_from_before_runs_only_the_missing_migrations(self):
        self.conn.execute("DELETE FROM settings WHERE key = 'migrations'")
        self.conn.execute("PRAGMA user_version = 3")  # as Budget 0.11 left it
        self.conn.commit()
        db.migrate()
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT value FROM settings WHERE key = 'migrations'").fetchone()[0], "3")
