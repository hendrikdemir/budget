"""The release script's version suggestion (packaging/release.py). Nothing is built or pushed."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parent.parent / "packaging" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class VersionNumbers(unittest.TestCase):
    def test_bumped(self):
        self.assertEqual(release.bumped("1.4.2", "patch"), "1.4.3")
        self.assertEqual(release.bumped("1.4.2", "minor"), "1.5.0")
        self.assertEqual(release.bumped("1.4.2", "major"), "2.0.0")
        self.assertEqual(release.bumped("v1.9.9", "minor"), "1.10.0")

    def test_parse_refuses_odd_versions(self):
        for odd in ("1.2", "1.2.3-beta", "latest"):
            with self.assertRaises(ValueError):
                release.parse(odd)


class Suggestion(unittest.TestCase):
    def suggest(self, messages=(), added=(), routes=(), settings=(), migrations=0):
        return release.suggest_bump(list(messages), list(added), set(routes), set(settings), migrations)[0]

    def test_fixes_are_a_patch(self):
        self.assertEqual(self.suggest(["Fix the split button in Safari", "Shorten the backup text"], ["tests/test_x.py"]), "patch")

    def test_new_things_are_minor(self):
        self.assertEqual(self.suggest(["Add a History page"]), "minor")
        self.assertEqual(self.suggest(["Tweak"], added=["static/js/history.js"]), "minor")
        self.assertEqual(self.suggest(["Tweak"], routes=["GET /api/history"]), "minor")
        self.assertEqual(self.suggest(["Tweak"], settings=["update_check"]), "minor")
        self.assertEqual(self.suggest(["Tweak"], migrations=1), "minor")

    def test_breaking_is_major(self):
        self.assertEqual(self.suggest(["Add a thing", "Drop old backups\n\nBREAKING: old .budget files can't be imported"]), "major")


class ReadingTheCode(unittest.TestCase):
    """The parsers must keep matching app/api.py and app/db.py as they're written."""
    root = Path(__file__).resolve().parent.parent

    def test_finds_routes_settings_and_migrations(self):
        api, db = (self.root / "app" / "api.py").read_text(), (self.root / "app" / "db.py").read_text()
        self.assertIn(("GET", "update", "False"), release.routes(api))
        self.assertIn(("PUT", "transactions", "True"), release.routes(api))
        self.assertIn("update_check", release.settings_keys(api))
        from app import db as app_db
        self.assertEqual(release.migrations(db), len(app_db.MIGRATIONS))
